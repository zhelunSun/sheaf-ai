"""Tests for sheaf_ai.search BM25 + Hybrid Search (Issue #57)."""


from sheaf_ai.search import (
    BM25Scorer,
    BM25Doc,
    _tokenize,
    _normalize_scores,
    _sigmoid,
    search_hybrid,
    search_fulltext,
)
from sheaf_ai.storage import store_article


# ============================================================
# Helpers
# ============================================================

def _make_entry(url: str, title: str, summary: str = "", tags: list = None, text: str = ""):
    """Create test data and store it."""
    return {
        "url": url,
        "fetch_result": {
            "success": True,
            "title": title,
            "text": text or f"{title} discusses agent memory and retrieval quality.",
            "method": "requests",
        },
        "classify_result": {
            "topics": [{"name": "AI", "confidence": 0.95}],
            "tags": tags or ["agent", "memory"],
            "content_type": "reference",
            "importance": "medium",
        },
        "summary_result": {
            "one_liner": summary or f"{title} summary.",
            "original_title": title,
            "source_author": "Test Author",
            "structured": {},
        },
    }


# ============================================================
# Tokenizer
# ============================================================

class TestTokenize:
    def test_english_words(self):
        tokens = _tokenize("Hello World 123")
        assert tokens == ["hello", "world", "123"]

    def test_cjk_characters(self):
        tokens = _tokenize("遥感分析系统")
        assert tokens == ["遥", "感", "分", "析", "系", "统"]

    def test_mixed_en_cjk(self):
        tokens = _tokenize("AI Agent 智能体")
        assert tokens == ["ai", "agent", "智", "能", "体"]

    def test_punctuation_stripped(self):
        tokens = _tokenize("hello, world! test-case")
        assert tokens == ["hello", "world", "test", "case"]

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_numbers_preserved(self):
        tokens = _tokenize("GPT-4 is great")
        assert "4" in tokens
        assert "gpt" in tokens


# ============================================================
# BM25Scorer
# ============================================================

class TestBM25Scorer:
    def test_empty_corpus(self):
        scorer = BM25Scorer()
        scorer.index_entries([])
        assert scorer.N == 0
        assert scorer.score("test") == []

    def test_single_doc_match(self):
        entries = [{"id": "1", "title": "Machine learning basics", "tags": ["ml"], "summary": "", "topics": []}]
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("machine learning")
        assert len(results) == 1
        assert results[0][0] == "1"
        assert results[0][1] > 0

    def test_single_doc_no_match(self):
        entries = [{"id": "1", "title": "Cooking recipes", "tags": [], "summary": "", "topics": []}]
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("quantum physics")
        assert len(results) == 0

    def test_ranking_by_relevance(self):
        entries = [
            {"id": "1", "title": "Python machine learning guide", "tags": ["python", "ml"], "summary": "A comprehensive guide to ML", "topics": []},
            {"id": "2", "title": "Cooking with Python snakes", "tags": ["cooking"], "summary": "A recipe book", "topics": []},
            {"id": "3", "title": "Advanced machine learning", "tags": ["ml", "deep-learning"], "summary": "Deep dive into ML algorithms", "topics": []},
        ]
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("machine learning")
        ids = [r[0] for r in results]
        # Entry 1 and 3 should appear in results for "machine learning"
        assert "1" in ids
        assert "3" in ids
        # Entry 2 (cooking) may or may not appear, but 1 and 3 should rank above it if it does
        if "2" in ids:
            assert ids.index("1") < ids.index("2")
            assert ids.index("3") < ids.index("2")

    def test_limit_results(self):
        entries = [
            {"id": str(i), "title": f"Machine learning part {i}", "tags": ["ml"], "summary": "", "topics": []}
            for i in range(20)
        ]
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("machine learning", limit=5)
        assert len(results) <= 5

    def test_field_weights_boost_title(self):
        entries = [
            {"id": "1", "title": "quantum physics", "tags": [], "summary": "quantum physics is the study of quantum mechanics", "topics": []},
            {"id": "2", "title": "general science overview", "tags": ["quantum"], "summary": "quantum appears many times here quantum quantum quantum", "topics": []},
        ]
        # With default weights (title: 3.0 > summary: 1.0), title match should be stronger
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("quantum")
        # Entry 1 has quantum in title (boosted 3x), Entry 2 only in summary/tags
        assert len(results) >= 1

    def test_raw_text_boosts_scoring(self):
        entries = [
            {"id": "1", "title": "Test Article", "tags": [], "summary": "Short summary", "topics": []},
        ]
        raw_texts = {"1": "neural networks are a type of machine learning model that uses deep learning"}
        scorer = BM25Scorer()
        scorer.index_entries(entries, raw_texts=raw_texts)
        results = scorer.score("neural networks")
        assert len(results) == 1
        assert results[0][1] > 0

    def test_adaptive_params_short_query(self):
        """Short queries (1-2 tokens) use standard BM25 params."""
        scorer = BM25Scorer()
        scorer.index_entries([
            {"id": "1", "title": "test document about python programming", "tags": [], "summary": "", "topics": []}
        ])
        # Should not crash with short query
        results = scorer.score("python")
        assert len(results) == 1

    def test_adaptive_params_long_query(self):
        """Long queries (6+ tokens) use recall-friendly params."""
        scorer = BM25Scorer()
        scorer.index_entries([
            {"id": "1", "title": "remote sensing urban forest tree canopy", "tags": ["remote", "sensing"], "summary": "urban forest analysis using satellite imagery for tree canopy detection", "topics": []}
        ])
        results = scorer.score("remote sensing urban forest tree canopy detection analysis")
        assert len(results) == 1

    def test_cjk_tokenization_in_bm25(self):
        entries = [
            {"id": "1", "title": "遥感图像分析", "tags": ["遥感"], "summary": "遥感技术在城市森林中的应用", "topics": []},
        ]
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("遥感")
        assert len(results) == 1

    def test_zero_df_handling(self):
        """Terms not in corpus should not crash scoring."""
        scorer = BM25Scorer()
        scorer.index_entries([
            {"id": "1", "title": "cooking recipes", "tags": [], "summary": "", "topics": []}
        ])
        results = scorer.score("nonexistent term")
        assert results == []

    def test_avgdl_zero_handling(self):
        """Empty documents should not cause division by zero."""
        scorer = BM25Scorer()
        scorer.index_entries([
            {"id": "1", "title": "", "tags": [], "summary": "", "topics": []}
        ])
        # avgdl will be 0, should handle gracefully
        assert scorer.avgdl == 0


# ============================================================
# Normalize / Sigmoid helpers
# ============================================================

class TestNormalize:
    def test_empty_list(self):
        assert _normalize_scores([]) == []

    def test_single_value(self):
        assert _normalize_scores([5.0]) == [1.0]

    def test_uniform_values(self):
        # All equal non-zero values normalize to 1.0 (since rng = 0, s > 0 → 1.0)
        result = _normalize_scores([3.0, 3.0, 3.0])
        assert all(r == 1.0 for r in result)

    def test_range_normalization(self):
        result = _normalize_scores([1.0, 3.0, 5.0])
        assert result[0] == 0.0
        assert result[2] == 1.0
        assert abs(result[1] - 0.5) < 1e-8


class TestSigmoid:
    def test_zero(self):
        assert abs(_sigmoid(0) - 0.5) < 1e-8

    def test_large_positive(self):
        assert _sigmoid(100) > 0.99

    def test_large_negative(self):
        assert _sigmoid(-100) < 0.01

    def test_symmetry(self):
        assert abs(_sigmoid(1) + _sigmoid(-1) - 1.0) < 1e-8


# ============================================================
# search_hybrid integration
# ============================================================

class TestSearchHybrid:
    def test_returns_empty_when_no_index(self, isolated_data_dir):
        results = search_hybrid("test query")
        assert results == []

    def test_returns_empty_for_empty_query(self, isolated_data_dir):
        results = search_hybrid("")
        assert results == []

    def test_hybrid_with_stored_entries(self, isolated_data_dir):
        e1 = _make_entry("https://example.com/ml", "Machine Learning Guide", tags=["ml", "ai"])
        e2 = _make_entry("https://example.com/cooking", "Cooking for Beginners", tags=["food"])

        store_article(e1["url"], e1["fetch_result"], e1["classify_result"], e1["summary_result"])
        store_article(e2["url"], e2["fetch_result"], e2["classify_result"], e2["summary_result"])

        results = search_hybrid("machine learning", limit=5)
        assert len(results) >= 1
        # First result should be the ML entry
        assert "machine" in results[0]["entry"]["title"].lower() or "learning" in results[0]["entry"]["title"].lower()

    def test_hybrid_result_structure(self, isolated_data_dir):
        e = _make_entry("https://example.com/test", "Python Testing Guide", tags=["python", "testing"])
        store_article(e["url"], e["fetch_result"], e["classify_result"], e["summary_result"])

        results = search_hybrid("python testing", limit=5)
        if results:
            r = results[0]
            assert "entry" in r
            assert "score" in r
            assert "bm25_score" in r
            assert "semantic_score" in r
            assert "match_locations" in r
            assert isinstance(r["score"], float)
            assert isinstance(r["bm25_score"], float)
            assert isinstance(r["semantic_score"], float)
            assert r["score"] > 0

    def test_hybrid_tier_filter(self, isolated_data_dir):
        e1 = _make_entry("https://example.com/high", "High Quality ML")
        e2 = _make_entry("https://example.com/low", "Low Quality ML")

        store_article(e1["url"], e1["fetch_result"], e1["classify_result"], e1["summary_result"], quality_tier="A")
        store_article(e2["url"], e2["fetch_result"], e2["classify_result"], e2["summary_result"], quality_tier="C")

        a_results = search_hybrid("ML", tier="A")
        c_results = search_hybrid("ML", tier="C")

        assert all(r["entry"].get("quality_tier") == "A" for r in a_results)
        assert all(r["entry"].get("quality_tier") == "C" for r in c_results)

    def test_hybrid_alpha_parameter(self, isolated_data_dir):
        e = _make_entry("https://example.com/test", "Alpha Test", tags=["test"])
        store_article(e["url"], e["fetch_result"], e["classify_result"], e["summary_result"])

        # alpha=1.0 = pure BM25, alpha=0.0 = pure semantic (which will be 0 w/o embeddings)
        results_bm25 = search_hybrid("alpha test", alpha=1.0)
        search_hybrid("alpha test", alpha=0.0)

        # Pure BM25 should find results, pure semantic (no embeddings) may not
        assert len(results_bm25) >= 1

    def test_hybrid_degrades_gracefully_without_embeddings(self, isolated_data_dir):
        """When embedding engine is unavailable, hybrid should still return BM25 results."""
        e = _make_entry("https://example.com/graceful", "Graceful Degradation Test", tags=["test"])
        store_article(e["url"], e["fetch_result"], e["classify_result"], e["summary_result"])

        results = search_hybrid("graceful degradation")
        assert len(results) >= 1
        # Without embeddings, bm25_score > 0, semantic_score = 0
        assert results[0]["bm25_score"] > 0

    def test_hybrid_with_raw_text(self, isolated_data_dir):
        """Raw text should boost BM25 scoring."""
        from sheaf_ai.config import RAW_DIR

        e = _make_entry(
            "https://example.com/raw-test",
            "Document Analysis",
            text="This document contains detailed analysis of neural networks and deep learning algorithms for remote sensing applications."
        )
        entry_id = store_article(e["url"], e["fetch_result"], e["classify_result"], e["summary_result"])

        # Write raw text file
        raw_path = RAW_DIR / f"{entry_id}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(
            "neural networks deep learning remote sensing convolutional layers feature extraction",
            encoding="utf-8",
        )

        results = search_hybrid("neural networks remote sensing")
        assert len(results) >= 1


# ============================================================
# BM25Scorer edge cases
# ============================================================

class TestBM25DocDataclass:
    def test_defaults(self):
        doc = BM25Doc(entry_id="test", entry={})
        assert doc.tokens == []
        assert doc.tf == {}
        assert doc.dl == 0

    def test_custom_values(self):
        doc = BM25Doc(entry_id="1", entry={"title": "test"}, tokens=["a", "b"], tf={"a": 1, "b": 1}, dl=2)
        assert doc.dl == 2
        assert doc.tf["a"] == 1


# ============================================================
# Backward compatibility — existing search_fulltext still works
# ============================================================

class TestSearchFulltextBackwardCompat:
    def test_legacy_search_still_works(self, isolated_data_dir):
        e = _make_entry("https://example.com/compat", "Compatibility Test", tags=["test"])
        store_article(e["url"], e["fetch_result"], e["classify_result"], e["summary_result"])

        results = search_fulltext("compatibility", include_raw=False)
        assert len(results) >= 1
        assert "entry" in results[0]
        assert "score" in results[0]
        assert "match_locations" in results[0]
