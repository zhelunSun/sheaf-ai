"""
Unit tests for sheaf_ai.storage — entry storage, tags registry, index management.

Uses conftest.py's isolated_data_dir fixture for true path isolation.
"""
import json


class TestTagsRegistry:
    def test_empty_registry(self, isolated_data_dir):
        from sheaf_ai.storage import load_tags_registry
        registry = load_tags_registry()
        assert registry == {}

    def test_save_and_load(self, isolated_data_dir):
        from sheaf_ai.storage import save_tags_registry, load_tags_registry
        data = {"ai": {"canonical": "AI", "count": 5, "first_seen": "2026-01-01", "last_seen": "2026-05-01", "aliases": []}}
        save_tags_registry(data)
        loaded = load_tags_registry()
        assert loaded == data

    def test_update_new_tags(self, isolated_data_dir):
        from sheaf_ai.storage import update_tags_registry, load_tags_registry
        update_tags_registry(["AI", "Python", "LLM"], "2026-05-19T12:00:00")
        registry = load_tags_registry()
        assert "ai" in registry
        assert "python" in registry
        assert "llm" in registry
        assert registry["ai"]["count"] == 1

    def test_update_increments_count(self, isolated_data_dir):
        from sheaf_ai.storage import update_tags_registry, load_tags_registry
        update_tags_registry(["AI"], "2026-05-19T12:00:00")
        update_tags_registry(["AI"], "2026-05-20T12:00:00")
        registry = load_tags_registry()
        assert registry["ai"]["count"] == 2

    def test_similar_tags_merge(self, isolated_data_dir):
        from sheaf_ai.storage import update_tags_registry, load_tags_registry
        update_tags_registry(["artificial intelligence"], "2026-05-19T12:00:00")
        update_tags_registry(["artifical intelligence"], "2026-05-20T12:00:00")  # typo
        registry = load_tags_registry()
        # Should have merged due to similarity > 0.85
        assert len(registry) == 1
        first_key = list(registry.keys())[0]
        assert registry[first_key]["count"] == 2

    def test_concurrent_update_no_lost_tags(self, isolated_data_dir):
        """Regression: concurrent batch-collect threads must not lose tag updates.

        Pre-fix, update_tags_registry was an unlocked read-modify-write. Two
        failure modes without the lock: (1) lost-update — threads load the same
        registry, mutate, and the last save clobbers the others; (2) on Windows,
        concurrent atomic_write -> os.replace on the same target raises
        PermissionError [WinError 5], aborting saves outright. The _STORAGE_LOCK
        serializes the full RMW so every distinct tag survives.

        Tags use uuid hex so pairwise similarity is < 0.85 — otherwise the
        registry's own similarity-merge would collapse them and mask the race.
        A barrier releases all threads at once to maximize the contention window.
        """
        import threading
        import uuid
        from sheaf_ai.storage import update_tags_registry, load_tags_registry

        n = 40
        tags = [uuid.uuid4().hex for _ in range(n)]  # pairwise dissimilar
        barrier = threading.Barrier(n)
        errors = []

        def worker(tag):
            try:
                barrier.wait()  # release all threads at once → maximize overlap
                update_tags_registry([tag], "2026-05-19T12:00:00")
            except Exception as e:  # pragma: no cover - defensive
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in tags]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"threads raised: {errors}"
        registry = load_tags_registry()
        present = {t for t in tags if t in registry}
        # Every thread's distinct tag must survive — no lost updates, no save aborts.
        assert len(present) == n, (
            f"lost-update/save-abort race: expected {n} tags, registry has {len(present)} "
            f"(missing {n - len(present)})"
        )

    def test_concurrent_append_index_no_lost_lines(self, isolated_data_dir):
        """Regression: concurrent append_index must not interleave/drop lines.

        Each JSONL line must be intact (parseable) and all N lines present.
        """
        import threading
        from sheaf_ai.storage import append_index

        n = 40
        barrier = threading.Barrier(n)
        errors = []

        def worker(i):
            try:
                barrier.wait()
                append_index({
                    "id": f"2026-05-19_{i:08d}",
                    "url": f"https://example.com/{i}",
                    "title": f"Entry {i}",
                    "topics": [],
                    "category": {"primary": "test", "sub": ""},
                    "tags": [],
                    "importance": "medium",
                    "summary": "x",
                    "metadata": {"collected_at": "2026-05-19T12:00:00"},
                })
            except Exception as e:  # pragma: no cover - defensive
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"threads raised: {errors}"
        from sheaf_ai.config import INDEX_FILE
        lines = [ln for ln in INDEX_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
        # All lines present and every line is valid JSON (no interleaving corruption).
        assert len(lines) == n, f"expected {n} index lines, got {len(lines)}"
        for ln in lines:
            json.loads(ln)  # raises if a line was interleaved/corrupted


class TestArticleStorage:
    def _make_test_data(self):
        """Create minimal test data for store_article."""
        return {
            "url": "https://example.com/test-article",
            "fetch_result": {
                "success": True,
                "title": "Test Article",
                "text": "This is a test article about AI and remote sensing.",
                "method": "requests",
            },
            "classify_result": {
                "topics": [{"name": "AI", "confidence": 0.95}],
                "tags": ["test", "ai"],
                "content_type": "research",
                "importance": "medium",
            },
            "summary_result": {
                "one_liner": "A test article for unit testing.",
                "original_title": "Test Article",
                "source_author": "Test Author",
                "structured": {
                    "core_argument": "Testing is important",
                    "key_data": "100% pass rate",
                    "relevance_to_user": "High",
                    "action_items": "Run tests",
                },
            },
        }

    def test_store_article_creates_files(self, isolated_data_dir):
        from sheaf_ai.storage import store_article
        td = self._make_test_data()
        entry_id = store_article(td["url"], td["fetch_result"], td["classify_result"], td["summary_result"])

        # Check entry JSON
        month_dir = isolated_data_dir / "entries" / entry_id[:7]
        assert month_dir.exists()
        entry_file = month_dir / f"{entry_id}.json"
        assert entry_file.exists()

        # Check raw text
        raw_file = isolated_data_dir / "raw" / f"{entry_id}.txt"
        assert raw_file.exists()

        # Check summary MD
        summary_file = isolated_data_dir / "summaries" / f"{entry_id}.md"
        assert summary_file.exists()

        # Check index
        index_file = isolated_data_dir / "index.jsonl"
        assert index_file.exists()

    def test_store_article_entry_structure(self, isolated_data_dir):
        from sheaf_ai.storage import store_article
        td = self._make_test_data()
        entry_id = store_article(td["url"], td["fetch_result"], td["classify_result"], td["summary_result"])

        month_dir = isolated_data_dir / "entries" / entry_id[:7]
        entry = json.loads((month_dir / f"{entry_id}.json").read_text(encoding="utf-8"))

        assert entry["id"] == entry_id
        assert entry["url"] == td["url"]
        assert entry["title"] == "Test Article"
        assert entry["category"]["primary"] == "AI"
        assert entry["content_type"] == "research"
        assert entry["quality_tier"] == "B"
        assert entry["status"] == "active"
        assert entry["metadata"]["schema_version"] == "1.2.0"

    def test_store_article_persists_explicit_quality_tier(self, isolated_data_dir):
        from sheaf_ai.storage import store_article
        td = self._make_test_data()
        entry_id = store_article(
            td["url"],
            td["fetch_result"],
            td["classify_result"],
            td["summary_result"],
            quality_tier="A",
        )

        month_dir = isolated_data_dir / "entries" / entry_id[:7]
        entry = json.loads((month_dir / f"{entry_id}.json").read_text(encoding="utf-8"))
        assert entry["quality_tier"] == "A"

    def test_store_article_summary_md(self, isolated_data_dir):
        from sheaf_ai.storage import store_article
        td = self._make_test_data()
        entry_id = store_article(td["url"], td["fetch_result"], td["classify_result"], td["summary_result"])

        summary_path = isolated_data_dir / "summaries" / f"{entry_id}.md"
        md = summary_path.read_text(encoding="utf-8")
        assert "Test Article" in md
        assert "AI" in md

    def test_rebuild_index(self, isolated_data_dir):
        from sheaf_ai.storage import store_article, rebuild_index
        td = self._make_test_data()

        # Store two articles
        store_article(td["url"], td["fetch_result"], td["classify_result"], td["summary_result"])
        td2 = {**td, "url": "https://example.com/second-article"}
        store_article(td2["url"], td2["fetch_result"], td2["classify_result"], td2["summary_result"])

        # Rebuild
        count = rebuild_index()
        assert count == 2

        # Verify index file
        index_file = isolated_data_dir / "index.jsonl"
        lines = [line for line in index_file.read_text(encoding="utf-8").strip().split("\n") if line.strip()]
        assert len(lines) == 2


class TestBuildSummaryMd:
    def test_basic_summary(self):
        from sheaf_ai.storage import build_summary_md
        entry = {
            "title": "Test Title",
            "url": "https://example.com",
            "category": {"primary": "AI", "sub": ""},
            "topics": [{"name": "AI", "confidence": 0.95}],
            "tags": ["test"],
            "importance": "high",
            "source": {"author": "Author Name"},
            "summary": "A one-liner summary.",
            "metadata": {"collected_at": "2026-05-19T12:00:00+08:00"},
        }
        structured = {
            "core_argument": "Testing is key",
            "key_data": "100% coverage",
        }
        md = build_summary_md(entry, structured)
        assert "Test Title" in md
        assert "Author Name" in md
        assert "Testing is key" in md
        assert "Sheaf" in md  # footer
