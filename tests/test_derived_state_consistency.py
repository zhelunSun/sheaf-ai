"""Offline regression proof for authoritative edits and derived projections."""
from __future__ import annotations

import json

import pytest

from sheaf_ai import _entry_storage, config, feedback, storage
from sheaf_ai.entry_embeddings import EntryEmbeddingError, EntrySemanticIndex
from sheaf_ai.entry_paths import resolve_entry_json_path
from sheaf_ai.retrieval_service import EntryRetrievalService, rebuild_entry_index


def _store(monkeypatch, *, summary="Approval not required"):
    monkeypatch.setattr("sheaf_ai.retrieval_service.update_entry_index_if_initialized", lambda *a, **k: False)
    return storage.store_article(
        "note://derived-fixture", {"title": "Atlas", "text": "Atlas offline indexing reference."},
        {"topics": [], "tags": ["indexing"]},
        {"one_liner": summary, "structured": {"deadline_or_timing": "Review before Friday"}},
    )


def _load(entry_id):
    path = resolve_entry_json_path(config.ENTRIES_DIR, entry_id)
    return path, json.loads(path.read_text(encoding="utf-8"))


def _index(*, embedder=None):
    return EntrySemanticIndex(model="offline-fixture", embedder=embedder or (lambda texts, model: [[1.0, 0.0] for _ in texts]))


def test_correction_excludes_old_vector_offline_and_after_reader_restart(monkeypatch):
    entry_id = _store(monkeypatch)
    index = _index()
    rebuild_entry_index(index=index)
    before = index.manifest_path.read_bytes()
    old_rows = storage.read_storage_index()
    feedback.submit_feedback(entry_id, {"summary": "Approval IS required"})

    def offline(*args):
        pytest.fail("All changed rows must be withheld before a provider call")

    # Even a caller retaining pre-correction index rows must use local authority.
    result = EntryRetrievalService(index=_index(embedder=offline)).semantic_scores("Atlas", old_rows)
    assert result.scores == {}
    assert result.diagnostics.reason_code == "stale"
    assert result.diagnostics.degraded
    assert index.manifest_path.read_bytes() == before
    rebuilt = _index()
    rebuild_entry_index(index=rebuilt)
    result = EntryRetrievalService(index=rebuilt).semantic_scores("Atlas", storage.read_storage_index())
    assert result.diagnostics.status == "ok"
    assert result.scores == {entry_id: 1.0}


def test_only_changed_row_excluded_and_offline_preserves_stale_diagnosis(monkeypatch):
    changed = _store(monkeypatch)
    unchanged = _store(monkeypatch, summary="Second source")
    index = _index()
    rebuild_entry_index(index=index)
    feedback.submit_feedback(changed, {"tags": ["corrected"]})
    service = EntryRetrievalService(index=index)
    result = service.semantic_scores("Atlas", storage.read_storage_index())
    assert result.scores == {unchanged: 1.0}
    assert result.diagnostics.reason_code == "stale"

    def offline(*args):
        raise EntryEmbeddingError("offline")

    result = EntryRetrievalService(index=_index(embedder=offline)).semantic_scores("Atlas", storage.read_storage_index())
    assert result.scores == {}
    assert result.diagnostics.reason_code == "stale"


def test_central_entry_write_covers_non_feedback_writer_and_metadata_only(monkeypatch):
    entry_id = _store(monkeypatch)
    index = _index()
    rebuild_entry_index(index=index)
    path, entry = _load(entry_id)
    entry["metadata"]["author_note"] = "unrelated annotation"
    storage.commit_storage_files({path: json.dumps(entry)})
    result = EntryRetrievalService(index=index).semantic_scores("Atlas", storage.read_storage_index())
    assert result.diagnostics.status == "ok"
    entry["summary"] = "Changed by another cooperative Entry writer"
    storage.commit_storage_files({path: json.dumps(entry)})
    result = EntryRetrievalService(index=index).semantic_scores("Atlas", storage.read_storage_index())
    assert result.diagnostics.reason_code == "stale"
    assert result.scores == {}


@pytest.mark.parametrize("damage", ["deleted", "entry_missing", "raw_missing", "raw_changed"])
def test_deleted_or_missing_or_changed_source_never_uses_old_vector(monkeypatch, damage):
    entry_id = _store(monkeypatch)
    index = _index()
    rebuild_entry_index(index=index)
    rows = storage.read_storage_index()
    path, entry = _load(entry_id)
    raw_path = config.RAW_DIR / f"{entry_id}.txt"
    if damage == "deleted":
        entry["status"] = "deleted"
        storage.commit_storage_files({path: json.dumps(entry)})
    elif damage == "entry_missing":
        path.unlink()
    elif damage == "raw_missing":
        raw_path.unlink()
    else:
        storage.commit_storage_files({raw_path: "Completely revised captured text"})
    result = EntryRetrievalService(index=index).semantic_scores("Atlas", rows)
    assert result.scores == {}
    assert result.diagnostics.reason_code == "stale"


def test_owned_markdown_refreshes_but_handwritten_bytes_survive(monkeypatch):
    entry_id = _store(monkeypatch)
    summary_path = config.SUMMARIES_DIR / f"{entry_id}.md"
    result = feedback.submit_feedback(entry_id, {"summary": "Approval required"})
    assert result["derived"]["summary"]["status"] == "current"
    assert "Approval required" in summary_path.read_text(encoding="utf-8")
    assert "Review before Friday" in summary_path.read_text(encoding="utf-8")
    handwritten = summary_path.read_bytes() + "\n作者手写判断：仍待验证。\n".encode()
    summary_path.write_bytes(handwritten)
    result = feedback.submit_feedback(entry_id, {"summary": "Corrected again"})
    assert summary_path.read_bytes() == handwritten
    assert result["derived"]["summary"] == {"status": "stale", "reason_code": "content_modified"}


def test_legacy_unowned_markdown_preserved_and_diagnosed(monkeypatch):
    entry_id = _store(monkeypatch)
    path, entry = _load(entry_id)
    del entry["metadata"]["derived"]
    path.write_text(json.dumps(entry), encoding="utf-8")
    summary_path = config.SUMMARIES_DIR / f"{entry_id}.md"
    before = summary_path.read_bytes()
    result = feedback.submit_feedback(entry_id, {"summary": "new correction"})
    assert summary_path.read_bytes() == before
    assert result["derived"]["summary"] == {"status": "stale", "reason_code": "ownership_unknown"}


def test_markdown_ownership_checks_exact_bytes_including_newlines(monkeypatch):
    entry_id = _store(monkeypatch)
    summary_path = config.SUMMARIES_DIR / f"{entry_id}.md"
    changed_bytes = summary_path.read_bytes().replace(b"\n", b"\r\n")
    summary_path.write_bytes(changed_bytes)
    result = feedback.submit_feedback(entry_id, {"summary": "new correction"})
    assert summary_path.read_bytes() == changed_bytes
    assert result["derived"]["summary"] == {"status": "stale", "reason_code": "content_modified"}


def test_interrupted_correction_withholds_results_and_recovers_all_derived_bytes(monkeypatch):
    entry_id = _store(monkeypatch)
    index = _index()
    rebuild_entry_index(index=index)
    replace = _entry_storage.durable_replace

    def interrupt_summary(path, text):
        if path.suffix == ".md":
            raise OSError("Injected interruption after durable Entry write")
        return replace(path, text)

    monkeypatch.setattr(_entry_storage, "durable_replace", interrupt_summary)
    with pytest.raises(storage.StorageRecoveryRequired):
        feedback.submit_feedback(entry_id, {"summary": "Recovered correction"})
    result = EntryRetrievalService(index=index).semantic_scores("Atlas", storage.read_storage_index())
    assert result.scores == {}
    assert result.diagnostics.reason_code == "source_state_unavailable"
    monkeypatch.setattr(_entry_storage, "durable_replace", replace)
    storage.recover_pending_storage()
    result = EntryRetrievalService(index=_index()).semantic_scores("Atlas", storage.read_storage_index())
    assert result.scores == {}
    assert result.diagnostics.reason_code == "stale"
    assert "Recovered correction" in (config.SUMMARIES_DIR / f"{entry_id}.md").read_text(encoding="utf-8")
    assert storage.summary_projection_status(_load(entry_id)[1])["status"] == "current"


def test_source_change_during_query_never_returns_mixed_scores(monkeypatch):
    entry_id = _store(monkeypatch)
    index = _index()
    rebuild_entry_index(index=index)

    def concurrent_correction(texts, model):
        feedback.submit_feedback(entry_id, {"summary": "Correction during query"})
        return [[1.0, 0.0] for _ in texts]

    result = EntryRetrievalService(index=_index(embedder=concurrent_correction)).semantic_scores("Atlas", storage.read_storage_index())
    assert result.scores == {}
    assert result.diagnostics.reason_code == "source_changed"


def test_generation_switch_after_freshness_check_is_explicit(monkeypatch):
    entry_id = _store(monkeypatch)
    index = _index()
    rebuild_entry_index(index=index)
    original_search = index.search

    def rebuild_then_search(*args, **kwargs):
        rebuild_entry_index(index=index)
        return original_search(*args, **kwargs)

    monkeypatch.setattr(index, "search", rebuild_then_search)
    result = EntryRetrievalService(index=index).semantic_scores("Atlas", storage.read_storage_index())
    assert result.scores == {}
    assert result.diagnostics.reason_code == "generation_changed"
    assert entry_id


def test_recovery_never_overwrites_a_post_interruption_handwritten_edit(monkeypatch):
    entry_id = _store(monkeypatch)
    summary_path = config.SUMMARIES_DIR / f"{entry_id}.md"
    replace = _entry_storage.durable_replace

    def interrupt_summary(path, text):
        if path.suffix == ".md":
            raise OSError("Injected interruption")
        return replace(path, text)

    monkeypatch.setattr(_entry_storage, "durable_replace", interrupt_summary)
    with pytest.raises(storage.StorageRecoveryRequired):
        feedback.submit_feedback(entry_id, {"summary": "Pending correction"})
    handwritten = summary_path.read_bytes() + b"\nManual judgment after interruption\n"
    summary_path.write_bytes(handwritten)
    monkeypatch.setattr(_entry_storage, "durable_replace", replace)
    with pytest.raises(storage.StorageStateError, match="recovery conflict"):
        storage.recover_pending_storage()
    assert summary_path.read_bytes() == handwritten
    assert (config.DATA_DIR / _entry_storage.JOURNAL_NAME).exists()


def test_embedding_calls_happen_outside_entry_storage_lock(monkeypatch):
    _store(monkeypatch)

    def verify_unlocked(texts, model):
        assert not getattr(_entry_storage._LOCAL, "held", set())
        return [[1.0, 0.0] for _ in texts]

    index = _index(embedder=verify_unlocked)
    rebuild_entry_index(index=index)
    result = EntryRetrievalService(index=index).semantic_scores("Atlas", storage.read_storage_index())
    assert result.diagnostics.status == "ok"


def test_summary_read_checks_current_source_as_well_as_owned_bytes(monkeypatch):
    entry_id = _store(monkeypatch)
    _, entry = _load(entry_id)
    entry["summary"] = "An externally changed authoritative summary"
    assert storage.summary_projection_status(entry) == {
        "status": "stale", "reason_code": "source_changed",
    }


def test_production_dispatch_never_restores_stale_hits_via_legacy_fallback(monkeypatch):
    from sheaf_ai import search

    changed = _store(monkeypatch)
    _store(monkeypatch, summary="Unchanged source")
    rebuild_entry_index(index=_index())
    feedback.submit_feedback(changed, {"summary": "Changed condition"})

    def offline(*args):
        raise EntryEmbeddingError("offline")

    monkeypatch.setattr(search, "EntryRetrievalService", lambda: EntryRetrievalService(index=_index(embedder=offline)))
    monkeypatch.setattr(search, "_fetch_legacy_card_semantic_scores", lambda *a, **k: {changed: 0.99})
    diagnostics = {}
    assert search._fetch_semantic_scores("Atlas", storage.read_storage_index(), diagnostics=diagnostics) == {}
    assert diagnostics["status"] == "degraded"
    assert diagnostics["reason_code"] == "stale"


@pytest.mark.parametrize("metadata", [None, [], "legacy", {"derived": None}, {"derived": {"summary": []}}])
def test_malformed_legacy_metadata_has_unknown_summary_ownership(metadata):
    assert storage.summary_projection_status({"id": "legacy", "metadata": metadata}) == {
        "status": "unknown", "reason_code": "ownership_unknown",
    }


def test_malformed_source_metadata_cannot_activate_legacy_fallback(monkeypatch):
    from sheaf_ai import search

    record = {"id": "legacy", "title": "Missing source", "metadata": None}
    index = _index()
    index.build([record])
    monkeypatch.setattr(search, "EntryRetrievalService", lambda: EntryRetrievalService(index=index))
    monkeypatch.setattr(search, "_fetch_legacy_card_semantic_scores", lambda *a, **k: {"legacy": 0.99})
    diagnostics = {}
    assert search._fetch_semantic_scores("Atlas", [record], diagnostics=diagnostics) == {}
    assert diagnostics["status"] == "degraded"
    assert diagnostics["reason_code"] == "source_state_unavailable"
