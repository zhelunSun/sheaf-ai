"""Collection keeps source persistence separate from model enrichment outcome."""
from __future__ import annotations

import json

import pytest

from sheaf_ai import llm_client, pipeline, storage
from sheaf_ai.entry_paths import resolve_entry_json_path


CLASSIFIED = {
    "topics": [{"name": "Agent", "confidence": 0.9}],
    "tags": ["retrieval"], "content_type": "research", "importance": "medium",
}
SUMMARIZED = {
    "one_liner": "Version two requires consent.",
    "structured": {"core_argument": "Consent must be explicit."},
    "original_title": "Consent conditions", "source_author": "Author",
}
SOURCE = "Version two requires explicit consent. " * 8
SECRET_ERROR = "injected endpoint=https://private.invalid token=sk-DO-NOT-STORE"


@pytest.fixture(autouse=True)
def offline_models(monkeypatch):
    monkeypatch.setattr(storage, "_extract_entities_for_index", lambda *_: [])
    from sheaf_ai import retrieval_service
    monkeypatch.setattr(retrieval_service, "update_entry_index_if_initialized", lambda *_a, **_k: None)
    monkeypatch.setattr(llm_client, "chat", lambda **_k: pytest.fail("Unexpected model call"))


def _models(monkeypatch, classify=CLASSIFIED, summarize=SUMMARIZED):
    calls = iter([classify, summarize])

    def chat(**_kwargs):
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return json.dumps(result)

    monkeypatch.setattr(llm_client, "chat", chat)


def _collect(monkeypatch, **responses):
    _models(monkeypatch, **responses)
    return pipeline.process_url("manual://stage-contract", manual_text=SOURCE)


def _load(entry_id):
    return json.loads(resolve_entry_json_path(storage.ENTRIES_DIR, entry_id).read_text("utf-8"))


def test_summary_failure_is_partial_retains_raw_without_exception_text(monkeypatch, isolated_data_dir):
    result = _collect(monkeypatch, summarize=RuntimeError(SECRET_ERROR))
    assert result["success"] is True and result["stored"] is True
    assert result["status"] == "partial"
    assert result["processing"]["summarize"] == {"status": "error", "method": "none"}
    assert result["one_liner"] == ""
    assert result["warnings"]
    entry = _load(result["entry_id"])
    assert entry["summary"] == "" and entry["structured_summary"] == {}
    assert entry["metadata"]["collection"] == {
        key: result[key] for key in ("status", "processing", "warnings", "quality")
    }
    assert (storage.RAW_DIR / f"{result['entry_id']}.txt").read_text("utf-8") == SOURCE
    for path in isolated_data_dir.rglob("*"):
        if path.is_file():
            assert SECRET_ERROR not in path.read_text("utf-8", errors="replace")
    assert SECRET_ERROR not in json.dumps(result)


def test_rule_classification_is_explicit_partial(monkeypatch):
    result = _collect(monkeypatch, classify=RuntimeError(SECRET_ERROR))
    assert result["status"] == "partial"
    assert result["processing"]["classify"] == {"status": "fallback", "method": "rules"}
    assert result["processing"]["summarize"]["status"] == "success"
    assert result["one_liner"] == SUMMARIZED["one_liner"]
    assert SECRET_ERROR not in json.dumps(_load(result["entry_id"]))


def test_complete_collection_persists_assessed_success(monkeypatch):
    result = _collect(monkeypatch)
    assert result["status"] == "success"
    assert result["stored"] and result["success"]
    assert result["warnings"] == []
    assert all(stage == {"status": "success", "method": "llm"}
               for stage in result["processing"].values())
    assert _load(result["entry_id"])["metadata"]["collection"]["status"] == "success"


@pytest.mark.parametrize("malformed", [[], None, {}, {"topics": ["bad"]},
    {**CLASSIFIED, "tags": "not-a-list"},
    {**CLASSIFIED, "topics": [{"name": "x", "confidence": "high"}]},
    {**CLASSIFIED, "topics": [{"name": "x", "confidence": float("nan")}]},
    {**CLASSIFIED, "content_type": []},
    {**CLASSIFIED, "source_assessment": "primary"},
])
def test_invalid_classification_shape_falls_back_and_stores(monkeypatch, malformed):
    result = _collect(monkeypatch, classify=malformed)
    assert result["stored"] and result["status"] == "partial"
    assert result["processing"]["classify"]["status"] == "fallback"


@pytest.mark.parametrize("malformed", [[], None, {}, {"one_liner": ""},
    {**SUMMARIZED, "structured": []},
    {**SUMMARIZED, "structured": {"core_argument": ["bad"]}},
    {**SUMMARIZED, "original_title": {"text": "bad"}},
    {**SUMMARIZED, "source_author": 123},
])
def test_invalid_summary_shape_is_partial_and_never_saved_as_knowledge(monkeypatch, malformed):
    result = _collect(monkeypatch, summarize=malformed)
    assert result["stored"] and result["status"] == "partial"
    assert result["processing"]["summarize"]["status"] == "error"
    assert _load(result["entry_id"])["summary"] == ""


def test_failed_reclassification_preserves_existing_knowledge(monkeypatch):
    result = _collect(monkeypatch)
    entry_id = result["entry_id"]
    old_entry = _load(entry_id)
    _models(monkeypatch, RuntimeError(SECRET_ERROR), RuntimeError(SECRET_ERROR))
    outcome = pipeline.reclassify_entries([entry_id])
    assert outcome["updated"] == 1 and outcome["partial"] == 1 and outcome["complete"] == 0
    assert outcome["items"][0]["status"] == "partial"
    entry = _load(entry_id)
    for key in ("summary", "structured_summary", "timeliness", "topics", "tags", "content_type"):
        assert entry[key] == old_entry[key]
    assert entry["metadata"]["collection"]["status"] == "partial"
    assert SECRET_ERROR not in json.dumps(outcome)


def test_failed_summary_reclassification_can_update_valid_classification(monkeypatch):
    result = _collect(monkeypatch)
    entry_id = result["entry_id"]
    _models(monkeypatch, {**CLASSIFIED, "tags": ["new-tag"]}, RuntimeError(SECRET_ERROR))
    outcome = pipeline.reclassify_entries([entry_id])
    assert outcome["partial"] == 1
    entry = _load(entry_id)
    assert entry["tags"] == ["new-tag"]
    assert entry["summary"] == SUMMARIZED["one_liner"]


def test_dedup_reports_no_new_storage_or_processing(monkeypatch):
    first = _collect(monkeypatch)
    result = pipeline.process_url("manual://stage-contract", manual_text=SOURCE)
    assert result["status"] == "error" and result["stored"] is False
    assert result["success"] is False and result["existing_id"] == first["entry_id"]
    assert all(stage["status"] == "not_run" for stage in result["processing"].values())


@pytest.mark.parametrize("stage", ["fetch", "quality"])
def test_rejected_source_has_no_storage_and_no_enrichment(monkeypatch, stage):
    from sheaf_ai import collectors
    fetch = {"success": stage != "fetch", "title": "short", "text": "tiny", "method": "test",
             "error": "Fetch rejected", "fetch_error": {"code": "unavailable"}}
    monkeypatch.setattr(collectors, "route_fetch", lambda _url: fetch)
    result = pipeline.process_url("https://example.invalid/reject")
    assert result["stage"] == stage
    assert result["status"] == "error" and result["stored"] is False
    assert all(value["status"] == "not_run" for value in result["processing"].values())
    assert storage.read_storage_index() == []


def test_legacy_model_classification_shape_stays_compatible(monkeypatch):
    result = _collect(monkeypatch, classify={"primary_category": "AI", "sub_category": "Agents"})
    assert result["status"] == "success"
    assert result["topics"] == ["AI", "Agents"]


def test_conversation_metadata_survives_collection_diagnostics(monkeypatch):
    from sheaf_ai import collectors
    conversation = {"content_type": "ai_conversation", "turns": 4}
    monkeypatch.setattr(collectors, "route_fetch", lambda _url: {
        "success": True, "title": "Saved conversation", "text": SOURCE,
        "method": "chatgpt-share", "meta": conversation,
    })
    _models(monkeypatch, summarize=RuntimeError(SECRET_ERROR))
    result = pipeline.process_url("https://example.invalid/conversation")
    entry = _load(result["entry_id"])
    assert entry["content_type"] == "ai_conversation"
    assert entry["metadata"]["conversation"] == conversation
    assert entry["metadata"]["collection"]["status"] == "partial"


def test_reclassification_dry_run_exposes_partial_without_mutation(monkeypatch, isolated_data_dir):
    collected = _collect(monkeypatch)
    before = {path: path.read_bytes() for path in isolated_data_dir.rglob("*") if path.is_file()}
    _models(monkeypatch, summarize=RuntimeError(SECRET_ERROR))
    result = pipeline.reclassify_entries([collected["entry_id"]], dry_run=True)
    assert result["updated"] == 0 and result["partial"] == 0 and result["skipped"] == 1
    assert result["items"][0]["status"] == "partial" and not result["items"][0]["applied"]
    assert before == {path: path.read_bytes() for path in isolated_data_dir.rglob("*") if path.is_file()}


@pytest.mark.parametrize("function", [pipeline.classify_article, pipeline.summarize_article])
def test_broken_prompt_loading_is_a_safe_enrichment_failure(monkeypatch, function):
    def fail(_name):
        raise OSError(SECRET_ERROR)

    monkeypatch.setattr(pipeline, "load_prompt", fail)
    result = function("Known title", SOURCE)
    assert result["_processing"]["status"] in {"error", "fallback"}
    assert SECRET_ERROR not in json.dumps(result)
