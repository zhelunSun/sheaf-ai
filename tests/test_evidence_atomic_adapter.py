"""End-to-end policy -> production adapter -> evidence ledger tests."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from sheaf_ai.card_service import (
    EvidenceMemoryAtomicBatchExecutor,
    apply_evidence_transition,
)
from sheaf_ai.evidence_policy import (
    DecisionValidationError,
    EvidenceDecisionPolicy,
    StaleDecisionError,
)
from sheaf_ai.storage import store_article


def _store(label: str) -> str:
    return store_article(
        f"https://{label}.example/{label}",
        {
            "success": True,
            "title": label,
            "text": f"Evidence body for {label}.",
            "method": "requests",
        },
        {
            "topics": [{"name": "Memory", "confidence": 0.9}],
            "tags": ["memory"],
            "content_type": "reference",
            "importance": "medium",
        },
        {
            "one_liner": f"Summary for {label}.",
            "original_title": label,
            "source_author": "",
            "structured": {},
        },
        source_info={"tier": "B", "domain": f"{label}.example"},
    )


def _initial(entry_id: str, ledger_path) -> dict:
    return apply_evidence_transition(
        {
            "action": "CREATE",
            "topic": "Memory",
            "source_ids": [entry_id],
            "card": {
                "title": "Initial",
                "claim": "The initial claim is active.",
                "fact_key": "initial-status",
                "fact_value": "active",
            },
            "reason": "Create an initial target.",
            "idempotency_key": "initial",
        },
        ledger_path=ledger_path,
    )


def _preview(policy, *, card_id, head, update_id, create_id):
    return policy.preview_split(
        input_snapshot={"topic": "Memory", "head": head},
        reason="Split two independently maintainable claims.",
        evidence_ids=[update_id, create_id],
        target_heads={card_id: head},
        update_request={
            "topic": "Memory",
            "source_ids": [update_id],
            "card": {
                "title": "Updated",
                "claim": "The initial claim remains active with new evidence.",
                "fact_key": "initial-status",
                "fact_value": "active",
            },
            "reason": "Update the existing claim.",
        },
        create_request={
            "topic": "Memory",
            "source_ids": [create_id],
            "card": {
                "title": "Independent claim",
                "claim": "A second claim is independently maintainable.",
                "fact_key": "second-status",
                "fact_value": "active",
            },
            "reason": "Create the independent claim.",
        },
        idempotency_key="atomic-split",
    )


def test_policy_uses_real_atomic_adapter_and_writes_one_domain_receipt(
    isolated_data_dir, tmp_path
):
    ledger_path = tmp_path / "evidence.json"
    decision_path = tmp_path / "decisions.json"
    initial_id = _store("atomic-initial")
    update_id = _store("atomic-update")
    create_id = _store("atomic-create")
    created = _initial(initial_id, ledger_path)
    card_id = created["card"]["id"]
    head = created["card"]["provenance"]["memory_version_id"]
    policy = EvidenceDecisionPolicy(decision_path)
    trace = _preview(
        policy,
        card_id=card_id,
        head=head,
        update_id=update_id,
        create_id=create_id,
    )
    executor = EvidenceMemoryAtomicBatchExecutor(ledger_path=ledger_path)

    applied = policy.apply_decision(
        trace.decision_id,
        current_heads={card_id: "caller-state-is-not-authoritative"},
        executor=executor,
    )

    assert applied.status == "APPLIED"
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert [event["action"] for event in raw["events"][-2:]] == ["UPDATE", "CREATE"]
    assert len(raw["atomic_batches"]) == 1
    receipt = raw["atomic_batches"][0]
    assert receipt["decision_id"] == trace.decision_id
    assert receipt["request_hash"] == trace.request_hash
    assert len(receipt["event_ids"]) == 2
    assert len(receipt["version_ids"]) == 2

    replayed = policy.apply_decision(
        trace.decision_id,
        current_heads={},
        executor=executor,
    )
    assert replayed == applied
    assert len(json.loads(ledger_path.read_text(encoding="utf-8"))["atomic_batches"]) == 1


def test_internal_head_cas_rejects_stale_preview_even_if_caller_lies(
    isolated_data_dir, tmp_path
):
    ledger_path = tmp_path / "evidence.json"
    initial_id = _store("stale-initial")
    update_id = _store("stale-update")
    create_id = _store("stale-create")
    drift_id = _store("stale-drift")
    created = _initial(initial_id, ledger_path)
    card_id = created["card"]["id"]
    old_head = created["card"]["provenance"]["memory_version_id"]
    policy = EvidenceDecisionPolicy(tmp_path / "decisions.json")
    trace = _preview(
        policy,
        card_id=card_id,
        head=old_head,
        update_id=update_id,
        create_id=create_id,
    )
    apply_evidence_transition(
        {
            "action": "UPDATE",
            "topic": "Memory",
            "source_ids": [drift_id],
            "target_card_ids": [card_id],
            "card": {
                "claim": "The initial claim remains active after drift.",
                "fact_key": "initial-status",
                "fact_value": "active",
            },
            "reason": "Advance the real domain head.",
            "idempotency_key": "drift",
        },
        ledger_path=ledger_path,
    )

    with pytest.raises(StaleDecisionError, match="Target head changed"):
        policy.apply_decision(
            trace.decision_id,
            current_heads={card_id: old_head},
            executor=EvidenceMemoryAtomicBatchExecutor(ledger_path=ledger_path),
        )

    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert raw["atomic_batches"] == []
    assert policy.ledger.get(trace.decision_id).status == "FAILED"


def test_production_adapter_rejects_operation_substitution_after_preview(
    isolated_data_dir, tmp_path
):
    ledger_path = tmp_path / "evidence.json"
    initial_id = _store("manifest-initial")
    update_id = _store("manifest-update")
    create_id = _store("manifest-create")
    created = _initial(initial_id, ledger_path)
    card_id = created["card"]["id"]
    head = created["card"]["provenance"]["memory_version_id"]
    policy = EvidenceDecisionPolicy(tmp_path / "decisions.json")
    trace = _preview(
        policy,
        card_id=card_id,
        head=head,
        update_id=update_id,
        create_id=create_id,
    )
    forged_create = replace(
        trace.operations[1],
        request={
            **trace.operations[1].request,
            "card": {
                "title": "Substituted",
                "claim": "This claim was not part of the preview.",
                "fact_key": "forged-status",
                "fact_value": "forged",
            },
        },
    )
    forged_trace = replace(
        trace,
        operations=(trace.operations[0], forged_create),
    )

    with pytest.raises(DecisionValidationError, match="request hash"):
        EvidenceMemoryAtomicBatchExecutor(ledger_path=ledger_path).execute_atomic(
            forged_trace
        )

    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert raw["atomic_batches"] == []
    assert [event["action"] for event in raw["events"]] == ["CREATE"]
    assert policy.ledger.get(trace.decision_id).status == "PREVIEWED"
