"""A corrected-away entity must not survive as a keyword-ranking feature."""
from __future__ import annotations

import json

from sheaf_ai import feedback, search, storage


def test_summary_correction_replaces_entities_without_rebuilding_library(monkeypatch):
    calls = []

    def extract(title, summary):
        calls.append((title, summary))
        return [{"text": name, "label": "ORG"} for name in ("OpenAI", "Anthropic") if name in summary]

    monkeypatch.setattr(storage, "_extract_entities_for_index", extract)
    monkeypatch.setattr("sheaf_ai.retrieval_service.update_entry_index_if_initialized", lambda *a, **k: False)
    entry_id = storage.store_article(
        "manual://entity-correction", {"title": "Indexing policy", "text": "Local indexing policy reference."},
        {"topics": [], "tags": []},
        {"one_liner": "OpenAI allows indexing without approval.", "structured": {}},
    )
    rows = storage.read_storage_index()
    rows[0]["custom_client_field"] = "preserve"
    storage.INDEX_FILE.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    assert search.search_hybrid("OpenAI", alpha=1.0)
    calls.clear()

    result = feedback.submit_feedback(entry_id, {"summary": "Anthropic requires explicit approval."})

    assert result["success"]
    corrected = storage.read_storage_index()[0]
    assert corrected["summary"] == "Anthropic requires explicit approval."
    assert corrected["entities"] == [{"text": "Anthropic", "label": "ORG"}]
    assert corrected["custom_client_field"] == "preserve"
    assert calls == [("Indexing policy", "Anthropic requires explicit approval.")]
    assert search.search_hybrid("OpenAI", alpha=1.0) == []
    assert [hit["entry"]["id"] for hit in search.search_hybrid("Anthropic", alpha=1.0)] == [entry_id]
