"""Entry-level semantic index and hybrid retrieval integration tests."""
from __future__ import annotations

import json
import multiprocessing
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest


class KeywordEmbedder:
    """Small deterministic embedder used to keep semantic tests offline."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def __call__(self, texts: list[str], model: str) -> list[list[float]]:
        self.calls.append((tuple(texts), model))
        vectors = []
        for text in texts:
            lowered = text.lower()
            vectors.append([
                float("atlas" in lowered or "retry behavior" in lowered),
                float("orchid" in lowered or "long document" in lowered),
                float("cedar" in lowered or "cache invalidation" in lowered),
            ])
        return vectors


def _process_embedder(texts: list[str], model: str) -> list[list[float]]:
    del model
    time.sleep(0.1)
    return [[1.0, 0.0, 0.0] for _ in texts]


def _update_index_in_process(index_dir: str, entry_id: str, start_event) -> None:
    from sheaf_ai.entry_embeddings import EntrySemanticIndex

    start_event.wait(timeout=10)
    EntrySemanticIndex(
        Path(index_dir),
        model="fixture-v1",
        embedder=_process_embedder,
    ).update([{"id": entry_id, "title": entry_id}])


def _entries() -> list[dict]:
    return [
        {
            "id": "atlas-v2",
            "url": "https://docs.example/atlas-v2",
            "title": "Atlas SDK v2",
            "topics": ["SDK"],
            "tags": ["retry"],
            "summary": "The default retry count is five.",
        },
        {
            "id": "orchid-long",
            "url": "https://papers.example/orchid",
            "title": "Orchid long-document result",
            "topics": ["retrieval"],
            "tags": ["benchmark"],
            "summary": "Orchid scores below the baseline on long documents.",
        },
    ]


def _manifest(index_dir: Path) -> dict:
    return json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))


def test_build_persists_manifest_and_searches_entries(tmp_path):
    from sheaf_ai.entry_embeddings import EntrySemanticIndex

    embedder = KeywordEmbedder()
    index_dir = tmp_path / "entry-embeddings"
    index = EntrySemanticIndex(index_dir, model="fixture-v1", embedder=embedder)

    report = index.build(_entries())

    assert report.indexed == 2
    manifest = _manifest(index_dir)
    assert manifest["model"] == "fixture-v1"
    assert manifest["dim"] == 3
    assert Path(index_dir / manifest["vector_file"]).exists()
    assert [item["entry_id"] for item in manifest["entries"]] == [
        "atlas-v2",
        "orchid-long",
    ]
    assert all(len(item["content_hash"]) == 64 for item in manifest["entries"])

    hits = index.search("retry behavior", top_k=2)

    assert [hit.entry_id for hit in hits] == ["atlas-v2"]
    assert hits[0].score == pytest.approx(1.0)


def test_update_reembeds_only_changed_and_new_entries(tmp_path):
    from sheaf_ai.entry_embeddings import EntrySemanticIndex

    embedder = KeywordEmbedder()
    index = EntrySemanticIndex(tmp_path / "index", model="fixture-v1", embedder=embedder)
    original = _entries()
    index.build(original)
    old_manifest = _manifest(tmp_path / "index")
    old_hashes = {
        item["entry_id"]: item["content_hash"] for item in old_manifest["entries"]
    }
    embedder.calls.clear()
    changed = [
        original[0],
        {**original[1], "summary": "Orchid has a revised long-document result."},
        {
            "id": "cedar-v3",
            "title": "Cedar cache behavior",
            "summary": "A revision token change invalidates the cache.",
        },
    ]

    report = index.update(changed)

    assert report.added == 1
    assert report.updated == 1
    assert report.unchanged == 1
    assert len(embedder.calls) == 1
    embedded_texts, model = embedder.calls[0]
    assert model == "fixture-v1"
    assert len(embedded_texts) == 2
    assert not any("Atlas SDK v2" in text for text in embedded_texts)
    new_manifest = _manifest(tmp_path / "index")
    new_hashes = {
        item["entry_id"]: item["content_hash"] for item in new_manifest["entries"]
    }
    assert new_hashes["atlas-v2"] == old_hashes["atlas-v2"]
    assert new_hashes["orchid-long"] != old_hashes["orchid-long"]


def test_empty_build_can_accept_incremental_entries(tmp_path):
    from sheaf_ai.entry_embeddings import EntrySemanticIndex

    index_dir = tmp_path / "index"
    index = EntrySemanticIndex(index_dir, model="fixture-v1", embedder=KeywordEmbedder())
    empty = index.build([])

    report = index.update([_entries()[0]])

    assert empty.dim == 0
    assert report.indexed == 1
    assert report.added == 1
    assert report.dim == 3
    assert [hit.entry_id for hit in index.search("retry behavior")] == ["atlas-v2"]


def test_failed_update_preserves_previous_committed_generation(tmp_path):
    from sheaf_ai.entry_embeddings import EntryEmbeddingError, EntrySemanticIndex

    index_dir = tmp_path / "index"
    index = EntrySemanticIndex(index_dir, model="fixture-v1", embedder=KeywordEmbedder())
    index.build(_entries())
    manifest_before = (index_dir / "manifest.json").read_bytes()
    committed = _manifest(index_dir)["vector_file"]
    vectors_before = (index_dir / committed).read_bytes()

    def failing_embedder(texts: list[str], model: str) -> list[list[float]]:
        raise RuntimeError("embedding provider unavailable")

    updater = EntrySemanticIndex(index_dir, model="fixture-v1", embedder=failing_embedder)
    with pytest.raises(EntryEmbeddingError, match="embedding provider unavailable"):
        updater.update([{**_entries()[0], "summary": "Changed content"}])

    assert (index_dir / "manifest.json").read_bytes() == manifest_before
    assert (index_dir / committed).read_bytes() == vectors_before
    status = EntrySemanticIndex(
        index_dir,
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    ).status()
    assert status.available is True
    assert status.reason_code == "stale"
    assert status.stale_entry_ids == ("atlas-v2",)


def test_shared_directory_lock_prevents_multi_instance_lost_update(tmp_path):
    from sheaf_ai.entry_embeddings import EntrySemanticIndex

    index_dir = tmp_path / "index"
    EntrySemanticIndex(
        index_dir,
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    ).build([])
    first_started = threading.Event()
    release_first = threading.Event()
    second_finished = threading.Event()
    errors: list[Exception] = []

    def controlled_embedder(texts: list[str], model: str) -> list[list[float]]:
        del model
        if any("entry-one" in text for text in texts):
            first_started.set()
            if not release_first.wait(timeout=5):
                raise RuntimeError("first writer was never released")
        return [[1.0, 0.0, 0.0] for _ in texts]

    def update(entry_id: str, finished: threading.Event | None = None) -> None:
        try:
            EntrySemanticIndex(
                index_dir,
                model="fixture-v1",
                embedder=controlled_embedder,
            ).update([{"id": entry_id, "title": entry_id}])
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)
        finally:
            if finished:
                finished.set()

    first = threading.Thread(target=update, args=("entry-one",))
    second = threading.Thread(target=update, args=("entry-two", second_finished))
    first.start()
    assert first_started.wait(timeout=5)
    second.start()
    assert second_finished.wait(timeout=0.15) is False
    release_first.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert errors == []
    assert first.is_alive() is False
    assert second.is_alive() is False
    assert [item["entry_id"] for item in _manifest(index_dir)["entries"]] == [
        "entry-one",
        "entry-two",
    ]


def test_cross_process_writer_lock_preserves_all_updates(tmp_path):
    from sheaf_ai.entry_embeddings import EntrySemanticIndex

    index_dir = tmp_path / "index"
    EntrySemanticIndex(
        index_dir,
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    ).build([])
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    processes = [
        context.Process(
            target=_update_index_in_process,
            args=(str(index_dir), f"entry-{index}", start_event),
        )
        for index in range(3)
    ]
    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(timeout=15)

    assert [process.exitcode for process in processes] == [0, 0, 0]
    assert [item["entry_id"] for item in _manifest(index_dir)["entries"]] == [
        "entry-0",
        "entry-1",
        "entry-2",
    ]


def test_successful_updates_clear_only_recovered_stale_entries(tmp_path):
    from sheaf_ai.entry_embeddings import EntryEmbeddingError, EntrySemanticIndex

    index_dir = tmp_path / "index"
    EntrySemanticIndex(
        index_dir,
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    ).build([])

    def failing_embedder(texts: list[str], model: str) -> list[list[float]]:
        raise RuntimeError("provider down")

    failing = EntrySemanticIndex(
        index_dir,
        model="fixture-v1",
        embedder=failing_embedder,
    )
    with pytest.raises(EntryEmbeddingError):
        failing.update([
            {"id": "entry-one", "title": "Atlas entry one"},
            {"id": "entry-two", "title": "Orchid entry two"},
        ])

    healthy = EntrySemanticIndex(
        index_dir,
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    )
    assert healthy.status().stale_entry_ids == ("entry-one", "entry-two")

    healthy.update([{"id": "entry-one", "title": "Atlas entry one"}])
    assert healthy.status().stale_entry_ids == ("entry-two",)

    healthy.build([{"id": "entry-two", "title": "Orchid entry two"}])
    status = healthy.status()
    assert status.reason_code == "ok"
    assert status.stale_entry_ids == ()


def test_model_mismatch_is_explicit(tmp_path):
    from sheaf_ai.entry_embeddings import EntryIndexUnavailable, EntrySemanticIndex

    index_dir = tmp_path / "index"
    EntrySemanticIndex(
        index_dir,
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    ).build(_entries())
    mismatched = EntrySemanticIndex(
        index_dir,
        model="fixture-v2",
        embedder=KeywordEmbedder(),
    )

    status = mismatched.status()
    assert status.available is False
    assert status.reason_code == "model_mismatch"
    with pytest.raises(EntryIndexUnavailable, match="model mismatch"):
        mismatched.search("retry behavior")


def test_hybrid_prefers_entry_index_and_reports_backend(isolated_data_dir):
    from sheaf_ai.entry_embeddings import EntrySemanticIndex
    from sheaf_ai.retrieval_service import EntryRetrievalService
    from sheaf_ai import search

    entries = _entries()
    (isolated_data_dir / "index.jsonl").write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries),
        encoding="utf-8",
    )
    semantic_index = EntrySemanticIndex(
        isolated_data_dir / "entry_embeddings",
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    )
    semantic_index.build(entries)
    service = EntryRetrievalService(index=semantic_index)

    with patch("sheaf_ai.search.EntryRetrievalService", return_value=service):
        results = search.search_hybrid("retry behavior", limit=2, alpha=0.0)

    assert [result["entry"]["id"] for result in results] == ["atlas-v2"]
    assert results[0]["semantic_backend"] == "entry_index"
    assert results[0]["semantic_degraded"] is False
    assert results[0]["semantic_reason"] == ""


def test_hybrid_healthy_entry_index_no_hit_is_not_degraded(isolated_data_dir):
    from sheaf_ai import search
    from sheaf_ai.entry_embeddings import EntrySemanticIndex
    from sheaf_ai.retrieval_service import EntryRetrievalService

    entries = _entries()
    (isolated_data_dir / "index.jsonl").write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries),
        encoding="utf-8",
    )
    semantic_index = EntrySemanticIndex(
        isolated_data_dir / "entry_embeddings",
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    )
    semantic_index.build(entries)
    diagnostics: dict[str, object] = {}

    with patch(
        "sheaf_ai.search.EntryRetrievalService",
        return_value=EntryRetrievalService(index=semantic_index),
    ):
        results = search.search_hybrid(
            "unrepresented vocabulary",
            limit=2,
            alpha=0.0,
            diagnostics=diagnostics,
        )

    assert results == []
    assert diagnostics == {
        "semantic_backend": "entry_index",
        "degraded": False,
        "reason": "",
        "reason_code": "ok",
    }


def test_hybrid_keyword_fallback_is_diagnostic(isolated_data_dir):
    from sheaf_ai import search

    entry = _entries()[0]
    (isolated_data_dir / "index.jsonl").write_text(
        json.dumps(entry) + "\n",
        encoding="utf-8",
    )

    results = search.search_hybrid("Atlas retry", limit=1)

    assert [result["entry"]["id"] for result in results] == ["atlas-v2"]
    assert results[0]["semantic_degraded"] is True
    assert "entry index" in results[0]["semantic_reason"].lower()


def test_hybrid_unavailable_index_no_hit_is_diagnostic(isolated_data_dir):
    from sheaf_ai import search

    entry = _entries()[0]
    (isolated_data_dir / "index.jsonl").write_text(
        json.dumps(entry) + "\n",
        encoding="utf-8",
    )
    diagnostics: dict[str, object] = {}

    with patch(
        "sheaf_ai.search._fetch_legacy_card_semantic_scores",
        return_value={},
    ):
        results = search.search_hybrid(
            "unrepresented vocabulary",
            alpha=0.0,
            diagnostics=diagnostics,
        )

    assert results == []
    assert diagnostics["semantic_backend"] == "keyword_only"
    assert diagnostics["degraded"] is True
    assert diagnostics["reason_code"] == "missing_manifest"


def test_hybrid_uses_old_results_but_reports_stale_index(isolated_data_dir):
    from sheaf_ai import search
    from sheaf_ai.entry_embeddings import EntryEmbeddingError, EntrySemanticIndex
    from sheaf_ai.retrieval_service import EntryRetrievalService

    entries = _entries()
    (isolated_data_dir / "index.jsonl").write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries),
        encoding="utf-8",
    )
    index_dir = isolated_data_dir / "entry_embeddings"
    EntrySemanticIndex(
        index_dir,
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    ).build([entries[0]])

    def failing_embedder(texts: list[str], model: str) -> list[list[float]]:
        raise RuntimeError("provider down")

    with pytest.raises(EntryEmbeddingError):
        EntrySemanticIndex(
            index_dir,
            model="fixture-v1",
            embedder=failing_embedder,
        ).update([entries[1]])

    reader = EntrySemanticIndex(
        index_dir,
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    )
    service = EntryRetrievalService(index=reader)
    diagnostics: dict[str, object] = {}
    with patch("sheaf_ai.search.EntryRetrievalService", return_value=service):
        results = search.search_hybrid(
            "retry behavior",
            limit=2,
            alpha=0.0,
            diagnostics=diagnostics,
        )

    assert [result["entry"]["id"] for result in results] == ["atlas-v2"]
    assert results[0]["semantic_backend"] == "entry_index"
    assert results[0]["semantic_degraded"] is True
    assert "orchid-long" in results[0]["semantic_reason"]
    assert diagnostics["semantic_backend"] == "entry_index"
    assert diagnostics["degraded"] is True
    assert diagnostics["reason_code"] == "stale"


def test_explicit_rebuild_loads_collection_and_raw_text(tmp_path):
    from sheaf_ai.entry_embeddings import EntrySemanticIndex
    from sheaf_ai.retrieval_service import rebuild_entry_index

    entries = _entries()
    collection_file = tmp_path / "index.jsonl"
    collection_file.write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries),
        encoding="utf-8",
    )
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "atlas-v2.txt").write_text("retry behavior", encoding="utf-8")
    index = EntrySemanticIndex(
        tmp_path / "entry-embeddings",
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    )

    report = rebuild_entry_index(
        index=index,
        index_file=collection_file,
        raw_dir=raw_dir,
    )

    assert report.indexed == 2
    assert index.status().available is True


def test_incremental_update_requires_explicit_bootstrap(tmp_path):
    from sheaf_ai.entry_embeddings import EntrySemanticIndex
    from sheaf_ai.retrieval_service import update_entry_index_if_initialized

    index = EntrySemanticIndex(
        tmp_path / "entry-embeddings",
        model="fixture-v1",
        embedder=KeywordEmbedder(),
    )

    assert update_entry_index_if_initialized(_entries()[0], index=index) is False
    assert index.manifest_path.exists() is False

    index.build([])
    assert update_entry_index_if_initialized(_entries()[0], index=index) is True
    assert index.status().entry_count == 1
