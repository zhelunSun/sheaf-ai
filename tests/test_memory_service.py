"""Application-service tests for evidence-governed memory adapters."""
from pathlib import Path

import pytest

from sheaf_ai import config
from sheaf_ai.card_service import (
    EVIDENCE_MEMORY_LEDGER_NAME,
    EvidenceTransitionRequest,
    apply_evidence_transition,
    get_memory_history,
    get_memory_snapshot,
)
from sheaf_ai.evidence_memory import EvidenceValidationError
from sheaf_ai.storage import store_article


def _store_entry(label: str, *, tier: str = "B", domain: str | None = None) -> str:
    return store_article(
        f"https://{domain or f'{label}.example'}/{label}",
        {
            "success": True,
            "title": f"Entry {label}",
            "text": f"Evidence text for {label}.",
            "method": "requests",
        },
        {
            "topics": [{"name": "Memory", "confidence": 0.9}],
            "tags": ["memory"],
            "content_type": "reference",
            "importance": "medium",
        },
        {
            "one_liner": f"Evidence summary for {label}.",
            "original_title": f"Entry {label}",
            "source_author": "",
            "structured": {},
        },
        source_info={"tier": tier, "domain": domain or f"{label}.example"},
    )


def _create_request(entry_id: str) -> dict:
    return {
        "action": "CREATE",
        "topic": "Memory",
        "source_ids": [entry_id],
        "card": {
            "title": "Governed claim",
            "claim": "The governed value is one.",
            "evidence": "Supported by the captured source.",
            "tags": ["governed"],
            "fact_key": "governed-value",
            "fact_value": "one",
        },
        "reason": "Create an explicit initial state.",
        "idempotency_key": "memory-service-create",
    }


def test_request_schema_rejects_free_form_fields():
    request = _create_request("entry-id")
    request["model_instruction"] = "write directly"
    with pytest.raises(ValueError, match="Unsupported transition fields"):
        EvidenceTransitionRequest.from_mapping(request)


def test_request_schema_rejects_locator_for_unrequested_source():
    request = _create_request("entry-id")
    request["evidence_locators"] = {
        "different-entry": {"kind": "quote", "quote": "evidence"}
    }
    with pytest.raises(ValueError, match="unrequested source_ids"):
        EvidenceTransitionRequest.from_mapping(request)


def test_request_schema_rejects_locator_ids_that_collide_after_trimming():
    request = _create_request("entry-id")
    request["evidence_locators"] = {
        "entry-id": {"kind": "whole_entry"},
        " entry-id ": {"kind": "whole_entry"},
    }

    with pytest.raises(ValueError, match="after trimming"):
        EvidenceTransitionRequest.from_mapping(request)


def test_apply_loads_real_entry_and_projects_public_card(isolated_data_dir):
    entry_id = _store_entry("create")

    result = apply_evidence_transition(_create_request(entry_id))

    assert result["applied"] is True
    assert result["card"]["source_ids"] == [entry_id]
    assert result["card"]["provenance"]["memory_state"] == "active"
    assert result["card"]["provenance"]["confidence_kind"] == (
        "ordinal_evidence_strength"
    )
    assert result["card"]["provenance"]["is_probability"] is False
    assert (config.DATA_DIR / EVIDENCE_MEMORY_LEDGER_NAME).is_file()


def test_apply_verifies_stored_quote_and_projects_locator(isolated_data_dir):
    entry_id = _store_entry("located")
    request = _create_request(entry_id)
    request["idempotency_key"] = "memory-service-located"
    request["evidence_locators"] = {
        entry_id: {"kind": "quote", "quote": "Evidence text for located."}
    }

    result = apply_evidence_transition(request)

    evidence_refs = result["card"]["extra"]["evidence_governance"]["evidence_refs"]
    assert len(evidence_refs) == 1
    ref = evidence_refs[0]
    assert ref["entry_id"] == entry_id
    assert ref["locator"] == {
        "kind": "quote",
        "start": 0,
        "end": len("Evidence text for located."),
        "quote": "Evidence text for located.",
    }
    assert ref["source_tier"] == "B"
    assert ref["source_key"] == "domain:located.example"
    assert ref["authority_topics"] == []
    assert ref["authority_fact_keys"] == []
    assert ref["corrects_entry_ids"] == []
    assert ref["duplicate_detection_version"] == "source-independence-v1"
    assert ref["duplicate_relations"] == []
    assert ref["independence_identity"] == ""
    assert ref["evidence_digest"].startswith("sha256:")
    assert len(result["event"]["evidence_use_ids"]) == 1
    assert result["event"]["governance_version"] == "evidence-governance-v2"


def test_apply_rejects_quote_not_present_in_trusted_raw_body(isolated_data_dir):
    entry_id = _store_entry("wrong-quote")
    request = _create_request(entry_id)
    request["idempotency_key"] = "memory-service-wrong-quote"
    request["evidence_locators"] = {
        entry_id: {"kind": "quote", "quote": "Invented supporting sentence."}
    }

    with pytest.raises(EvidenceValidationError, match="not found"):
        apply_evidence_transition(request)


def test_apply_rejects_nonexistent_source_before_creating_ledger(isolated_data_dir):
    with pytest.raises(EvidenceValidationError, match="not a stored Entry"):
        apply_evidence_transition(_create_request("2026-09-01_deadbeef"))

    assert not (config.DATA_DIR / EVIDENCE_MEMORY_LEDGER_NAME).exists()


def test_snapshot_and_history_preserve_contest_and_resolution(isolated_data_dir):
    initial_entry = _store_entry("initial", tier="B", domain="one.example")
    conflicting_entry = _store_entry("conflict", tier="A", domain="two.example")
    created = apply_evidence_transition(_create_request(initial_entry))
    card_id = created["card"]["id"]

    contested = apply_evidence_transition({
        "action": "CONTEST",
        "topic": "Memory",
        "source_ids": [conflicting_entry],
        "target_card_ids": [card_id],
        "card": {
            "claim": "The governed value is two.",
            "evidence": "A captured source proposes a different value.",
            "fact_key": "governed-value",
            "fact_value": "two",
        },
        "reason": "Preserve the explicit contradiction without overwriting.",
        "idempotency_key": "memory-service-contest",
    })
    assert contested["card"]["provenance"]["memory_state"] == "contested"

    snapshot = get_memory_snapshot(topic="Memory")
    assert snapshot["state_counts"]["contested"] == 1
    assert snapshot["states"]["contested"][0]["extra"]["evidence_governance"][
        "proposed_conflict"
    ]["source_ids"] == [conflicting_entry]

    resolved = apply_evidence_transition({
        "action": "UPDATE",
        "topic": "Memory",
        "target_card_ids": [card_id],
        "card": {
            "claim": "The governed value is two.",
            "fact_key": "governed-value",
            "fact_value": "two",
        },
        "reason": "Record a traceable manual adjudication.",
        "resolution_basis": "manual_adjudication",
        "resolution_metadata": {
            "adjudicator_id": "reviewer-1",
            "decision_id": "decision-1",
            "decided_at": "2026-09-01T00:00:00+00:00",
        },
        "idempotency_key": "memory-service-resolve",
    })
    assert resolved["card"]["provenance"]["memory_state"] == "active"

    history = get_memory_history(topic="Memory", card_id=card_id)
    contest_event = next(event for event in history["events"] if event["action"] == "CONTEST")
    update_event = next(event for event in history["events"] if event["action"] == "UPDATE")
    assert contest_event["proposed_conflict"]["fact_value"] == "two"
    assert contest_event["resolution"]["basis"] == ""
    assert update_event["resolution"]["basis"] == "manual_adjudication"
    assert update_event["resolution"]["metadata"]["decision_id"] == "decision-1"
    assert history["audit_graph"]["edges"]


def test_retired_state_is_distinct_in_public_snapshot(isolated_data_dir):
    entry_id = _store_entry("retire")
    created = apply_evidence_transition(_create_request(entry_id))
    card_id = created["card"]["id"]

    retired = apply_evidence_transition({
        "action": "RETIRE",
        "topic": "Memory",
        "target_card_ids": [card_id],
        "reason": "This memory is no longer current.",
        "idempotency_key": "memory-service-retire",
    })

    assert retired["card"]["provenance"]["memory_state"] == "retired"
    snapshot = get_memory_snapshot()
    assert snapshot["current_total"] == 0
    assert snapshot["state_counts"]["retired"] == 1
    assert snapshot["states"]["retired"][0]["id"] == card_id


def test_custom_ledger_path_is_supported_without_changing_entry_allowlist(
    isolated_data_dir,
    tmp_path,
):
    entry_id = _store_entry("custom")
    ledger_path = tmp_path / "custom-ledger.json"
    result = apply_evidence_transition(_create_request(entry_id), ledger_path=ledger_path)
    assert result["card"]["source_ids"] == [entry_id]
    assert get_memory_snapshot(ledger_path=ledger_path)["current_total"] == 1
    assert Path(ledger_path).is_file()
