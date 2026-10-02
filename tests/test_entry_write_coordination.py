"""Corrections and reclassification share collection's recoverable write boundary."""
from __future__ import annotations

import json

import pytest

from sheaf_ai import feedback, pipeline, storage
from sheaf_ai import _entry_storage as journal
from sheaf_ai.entry_paths import resolve_entry_json_path


def _entry(monkeypatch):
    monkeypatch.setattr(storage, "_extract_entities_for_index", lambda *_: [])
    return storage.store_article(
        "https://example.invalid/coordination",
        {"title": "Source condition", "text": "Version two requires explicit consent. " * 5},
        {"topics": [{"name": "source", "confidence": 0.9}], "tags": ["original"]},
        {"one_liner": "Original summary", "structured": {}},
    )


def test_feedback_recovers_entry_index_and_history_once(isolated_data_dir, monkeypatch):
    entry_id = _entry(monkeypatch)
    replace = journal.durable_replace

    def fail_index(path, text):
        if path.name == "index.jsonl":
            raise OSError("injected index publication failure")
        return replace(path, text)

    monkeypatch.setattr(journal, "durable_replace", fail_index)
    with pytest.raises(storage.StorageRecoveryRequired):
        feedback.submit_feedback(entry_id, {"summary": "Author corrected the condition"})
    assert (isolated_data_dir / journal.JOURNAL_NAME).exists()

    monkeypatch.setattr(journal, "durable_replace", replace)
    assert storage.recover_pending_storage()
    assert storage.recover_pending_storage() is None
    entry = json.loads(resolve_entry_json_path(storage.ENTRIES_DIR, entry_id).read_text("utf-8"))
    assert entry["summary"] == "Author corrected the condition"
    assert storage.read_storage_index()[0]["summary"] == entry["summary"]
    history = feedback.get_feedback_history(entry_id)
    assert len(history) == 1
    assert history[0]["before"]["summary"] == "Original summary"
    assert history[0]["after"]["summary"] == entry["summary"]


def test_feedback_refuses_corrupt_index_without_overwriting_entry(isolated_data_dir, monkeypatch):
    entry_id = _entry(monkeypatch)
    path = resolve_entry_json_path(storage.ENTRIES_DIR, entry_id)
    before = path.read_bytes()
    storage.INDEX_FILE.write_text('{"id":', encoding="utf-8")
    with pytest.raises(storage.StorageStateError):
        feedback.submit_feedback(entry_id, {"summary": "Must not be committed"})
    assert path.read_bytes() == before
    assert storage.INDEX_FILE.read_text("utf-8") == '{"id":'
    assert not feedback.FEEDBACK_FILE.exists()
    assert not (isolated_data_dir / journal.JOURNAL_NAME).exists()


def test_feedback_keeps_legacy_flat_entry_compatible(isolated_data_dir):
    entry_id = "2026-05-19_legacy"
    entry = {
        "id": entry_id, "title": "Legacy source", "url": "https://example.invalid/legacy",
        "category": {"primary": "old", "sub": ""}, "tags": [],
        "summary": "Before", "collected_at": "2026-05-19T00:00:00",
    }
    path = resolve_entry_json_path(storage.ENTRIES_DIR, entry_id)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(entry), encoding="utf-8")
    storage.INDEX_FILE.write_text(json.dumps({
        "id": entry_id, "summary": "Before", "custom_client_field": "keep",
        "collected_at": entry["collected_at"],
        "metadata": {"client_annotations": {"star": True}},
    }) + "\n", encoding="utf-8")
    assert feedback.submit_feedback(entry_id, {"summary": "After"})["success"]
    stored = json.loads(path.read_text("utf-8"))
    assert stored["summary"] == "After"
    assert "metadata" not in stored
    row = storage.read_storage_index()[0]
    assert row["summary"] == "After"
    assert row["custom_client_field"] == "keep"
    assert row["collected_at"] == entry["collected_at"]
    assert row["metadata"] == {"client_annotations": {"star": True}}


def test_reclassification_does_not_overwrite_a_correction_during_model_call(monkeypatch):
    entry_id = _entry(monkeypatch)

    def classify(*_):
        feedback.submit_feedback(entry_id, {"summary": "Author correction during inference"})
        return {"topics": [{"name": "new", "confidence": 0.8}], "tags": ["new"]}

    monkeypatch.setattr(pipeline, "classify_article", classify)
    monkeypatch.setattr(pipeline, "summarize_article", lambda *_: {
        "one_liner": "Stale model output", "structured": {},
    })
    result = pipeline.reclassify_entries([entry_id])
    assert result["updated"] == 0
    assert len(result["errors"]) == 1
    assert "changed during reclassification" in result["errors"][0]["error"]
    assert storage.read_storage_index()[0]["summary"] == "Author correction during inference"


def test_reclassification_dry_run_never_replays_pending_writes(isolated_data_dir, monkeypatch):
    replace = journal.durable_replace

    def fail_tags(path, text):
        if path.name == "tags_registry.json":
            raise OSError("injected tags publication failure")
        return replace(path, text)

    monkeypatch.setattr(journal, "durable_replace", fail_tags)
    with pytest.raises(storage.StorageRecoveryRequired):
        storage.commit_storage_files({storage.TAGS_REGISTRY_FILE: '{"pending":{"count":1}}'})
    monkeypatch.setattr(journal, "durable_replace", replace)
    pending = isolated_data_dir / journal.JOURNAL_NAME
    before = pending.read_bytes()
    monkeypatch.setattr(pipeline, "classify_article", lambda *_: pytest.fail("No model call allowed"))
    with pytest.raises(storage.StorageStateError, match="recover explicitly"):
        pipeline.reclassify_entries(dry_run=True)
    assert pending.read_bytes() == before
    assert not storage.TAGS_REGISTRY_FILE.exists()


def test_reclassification_publishes_matching_entry_summary_and_index(monkeypatch):
    entry_id = _entry(monkeypatch)
    rows = storage.read_storage_index()
    rows[0]["custom_client_field"] = "preserve"
    rows[0]["metadata"]["client_annotations"] = {"star": True}
    storage.commit_storage_files({storage.INDEX_FILE: json.dumps(rows[0]) + "\n"})
    monkeypatch.setattr(pipeline, "classify_article", lambda *_: {
        "topics": [{"name": "revised", "confidence": 0.8}], "tags": ["revised"],
    })
    monkeypatch.setattr(pipeline, "summarize_article", lambda *_: {
        "one_liner": "Revised summary", "structured": {"core_argument": "Requires consent"},
    })
    result = pipeline.reclassify_entries([entry_id])
    assert result == {"updated": 1, "skipped": 0, "errors": []}
    entry = json.loads(resolve_entry_json_path(storage.ENTRIES_DIR, entry_id).read_text("utf-8"))
    row = storage.read_storage_index()[0]
    assert row["summary"] == entry["summary"] == "Revised summary"
    assert row["custom_client_field"] == "preserve"
    assert row["metadata"]["client_annotations"] == {"star": True}
    assert row["tags"] == entry["tags"] == ["revised"]
    assert "Revised summary" in (storage.SUMMARIES_DIR / f"{entry_id}.md").read_text("utf-8")
    assert storage.load_tags_registry()["revised"]["count"] == 1
