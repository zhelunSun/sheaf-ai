"""Decision-trace contracts for SPLIT and NOOP policy decisions."""
from __future__ import annotations

import json

import pytest

from sheaf_ai.evidence_policy import (
    AtomicBatchRequiredError,
    DECISION_ALGORITHM_VERSION,
    DECISION_POLICY_VERSION,
    DecisionExecutionError,
    DecisionLedgerCorruptionError,
    DecisionTraceLedger,
    DecisionValidationError,
    EvidenceDecisionPolicy,
    PlannedOperation,
    execution_manifest_hash,
)


def _policy(tmp_path):
    return EvidenceDecisionPolicy(tmp_path / "decisions.json")


def _split(policy, *, key="split-1"):
    return policy.preview_split(
        input_snapshot={
            "topic": "retrieval",
            "candidate_claims": ["hybrid search is enabled", "index is healthy"],
        },
        reason="The evidence supports two independently maintainable claims",
        evidence_ids=["entry-2", "entry-1", "entry-2"],
        target_heads={"card-1": "version-3"},
        update_request={"claim": "Hybrid search is enabled", "source_ids": ["entry-1"]},
        create_request={"claim": "The index is healthy", "source_ids": ["entry-2"]},
        idempotency_key=key,
    )


class AtomicFake:
    def __init__(self, *, fail=False, fail_after_commit=False, lookup_fail=False):
        self.fail = fail
        self.fail_after_commit = fail_after_commit
        self.lookup_fail = lookup_fail
        self.calls = []
        self.committed: list[PlannedOperation] = []
        self.receipts = {}

    def lookup_commit(self, decision_id, request_hash):
        if self.lookup_fail:
            raise OSError("receipt ledger unavailable")
        receipt = self.receipts.get(decision_id)
        if receipt is not None and receipt["request_hash"] != request_hash:
            raise RuntimeError("receipt hash conflict")
        return receipt

    def execute_atomic(self, trace):
        self.calls.append(trace)
        staged = list(trace.operations)
        if self.fail:
            raise RuntimeError("simulated transaction rollback")
        self.committed.extend(staged)
        self.receipts[trace.decision_id] = {
            "decision_id": trace.decision_id,
            "request_hash": trace.request_hash,
            "idempotency_key": trace.idempotency_key,
            "expected_heads": {
                head.card_id: head.version_id for head in trace.target_heads
            },
            "policy_version": trace.policy_version,
            "algorithm_version": trace.algorithm_version,
            "execution_manifest_hash": execution_manifest_hash(trace),
            "operation_actions": tuple(
                operation.operation for operation in trace.operations
            ),
        }
        if self.fail_after_commit:
            raise RuntimeError("simulated crash after domain commit")


def test_split_preview_is_versioned_hashed_and_expands_shared_decision_id(tmp_path):
    trace = _split(_policy(tmp_path))

    assert trace.status == "PREVIEWED"
    assert trace.policy_version == DECISION_POLICY_VERSION
    assert trace.algorithm_version == DECISION_ALGORITHM_VERSION
    assert trace.request_hash
    assert trace.created_at.endswith("Z")
    assert trace.evidence_ids == ("entry-1", "entry-2")
    assert [(head.card_id, head.version_id) for head in trace.target_heads] == [
        ("card-1", "version-3")
    ]
    assert [operation.operation for operation in trace.operations] == ["UPDATE", "CREATE"]
    assert {operation.decision_id for operation in trace.operations} == {trace.decision_id}
    assert trace.operations[0].target_card_ids == ("card-1",)
    assert trace.operations[1].target_card_ids == ()


def test_noop_is_persisted_and_never_calls_executor(tmp_path):
    policy = _policy(tmp_path)
    trace = policy.preview_noop(
        input_snapshot={"claim": "Already represented"},
        reason="No material knowledge change",
        evidence_ids=["entry-1"],
        target_heads={"card-1": "version-3"},
        idempotency_key="noop-1",
    )
    executor = AtomicFake()

    applied = policy.apply_decision(
        trace.decision_id,
        current_heads={},
        executor=executor,
    )

    assert applied.status == "NOOP"
    assert executor.calls == []
    assert applied.operations == ()
    assert applied.target_heads[0].version_id == "version-3"
    reopened = DecisionTraceLedger(tmp_path / "decisions.json")
    assert reopened.get(trace.decision_id).status == "NOOP"


def test_caller_head_snapshot_is_not_the_authoritative_cas(tmp_path):
    policy = _policy(tmp_path)
    trace = _split(policy)
    executor = AtomicFake()

    applied = policy.apply_decision(
        trace.decision_id,
        current_heads={"card-1": "version-4"},
        executor=executor,
    )

    assert applied.status == "APPLIED"
    assert {
        head.card_id: head.version_id for head in executor.calls[0].target_heads
    } == {"card-1": "version-3"}


def test_split_fails_closed_without_atomic_batch_protocol(tmp_path):
    policy = _policy(tmp_path)
    trace = _split(policy)

    class LegacySingleTransitionExecutor:
        def apply_transition(self, *_args, **_kwargs):
            raise AssertionError("must not be called")

    with pytest.raises(AtomicBatchRequiredError, match="atomic batch executor"):
        policy.apply_decision(
            trace.decision_id,
            current_heads={"card-1": "version-3"},
            executor=LegacySingleTransitionExecutor(),  # type: ignore[arg-type]
        )

    assert policy.ledger.get(trace.decision_id).status == "PREVIEWED"


def test_receipt_lookup_failure_leaves_preview_state_unchanged(tmp_path):
    policy = _policy(tmp_path)
    trace = _split(policy)

    with pytest.raises(DecisionExecutionError, match="outcome is unknown"):
        policy.apply_decision(
            trace.decision_id,
            current_heads={},
            executor=AtomicFake(lookup_fail=True),
        )

    assert policy.ledger.get(trace.decision_id).status == "PREVIEWED"


def test_mismatched_domain_receipt_cannot_advance_preview(tmp_path):
    policy = _policy(tmp_path)
    trace = _split(policy)
    executor = AtomicFake()
    executor.execute_atomic(trace)
    executor.receipts[trace.decision_id]["execution_manifest_hash"] = "c" * 64

    with pytest.raises(DecisionExecutionError, match="execution manifest"):
        policy.apply_decision(
            trace.decision_id,
            current_heads={},
            executor=executor,
        )

    assert policy.ledger.get(trace.decision_id).status == "PREVIEWED"


def test_failed_atomic_split_records_failure_without_partial_commit(tmp_path):
    policy = _policy(tmp_path)
    trace = _split(policy)
    executor = AtomicFake(fail=True)

    with pytest.raises(DecisionExecutionError, match="simulated transaction rollback"):
        policy.apply_decision(
            trace.decision_id,
            current_heads={"card-1": "version-3"},
            executor=executor,
        )

    assert executor.committed == []
    assert len(executor.calls) == 1
    failed = policy.ledger.get(trace.decision_id)
    assert failed.status == "FAILED"
    assert "Atomic SPLIT failed" in failed.failure_reason


def test_successful_split_is_one_batch_and_apply_retry_is_idempotent(tmp_path):
    policy = _policy(tmp_path)
    trace = _split(policy)
    executor = AtomicFake()

    applied = policy.apply_decision(
        trace.decision_id,
        current_heads={"card-1": "version-3"},
        executor=executor,
    )
    retry = policy.apply_decision(
        trace.decision_id,
        current_heads={"card-1": "version-999"},
        executor=executor,
    )

    assert applied.status == "APPLIED"
    assert retry == applied
    assert len(executor.calls) == 1
    call = executor.calls[0]
    operations = call.operations
    assert [operation.operation for operation in operations] == ["UPDATE", "CREATE"]
    assert call.decision_id == trace.decision_id
    assert call.idempotency_key == trace.idempotency_key
    assert call.request_hash == trace.request_hash
    assert call.policy_version == trace.policy_version
    assert call.algorithm_version == trace.algorithm_version
    assert call.evidence_ids == trace.evidence_ids
    assert len(executor.committed) == 2


def test_crash_after_domain_commit_is_reconciled_to_applied(tmp_path):
    policy = _policy(tmp_path)
    trace = _split(policy)
    executor = AtomicFake(fail_after_commit=True)

    applied = policy.apply_decision(
        trace.decision_id,
        current_heads={},
        executor=executor,
    )

    assert applied.status == "APPLIED"
    assert len(executor.calls) == 1
    assert len(executor.committed) == 2


def test_preview_retry_returns_same_trace_and_key_reuse_with_new_input_fails(tmp_path):
    policy = _policy(tmp_path)
    first = _split(policy, key="stable-request")
    retry = _split(policy, key="stable-request")

    assert retry.decision_id == first.decision_id
    assert retry.request_hash == first.request_hash
    assert len(policy.ledger.snapshot()) == 1

    with pytest.raises(DecisionValidationError, match="reused for a different decision"):
        policy.preview_noop(
            input_snapshot={"claim": "different"},
            reason="Different request",
            idempotency_key="stable-request",
        )


def test_auto_idempotency_ignores_generated_identity_and_time(tmp_path):
    policy = _policy(tmp_path)
    kwargs = {
        "input_snapshot": {"claim": "No change"},
        "reason": "Evidence is already represented",
        "evidence_ids": ["entry-1"],
    }

    first = policy.preview_noop(**kwargs)
    retry = policy.preview_noop(**kwargs)

    assert retry == first
    assert first.idempotency_key == f"auto:{first.request_hash}"


def test_trace_detaches_mutable_input_snapshot(tmp_path):
    policy = _policy(tmp_path)
    snapshot = {"claims": ["one"]}
    trace = policy.preview_noop(
        input_snapshot=snapshot,
        reason="No new claim",
    )
    snapshot["claims"].append("mutated")

    assert trace.input_snapshot == {"claims": ["one"]}
    assert policy.ledger.get(trace.decision_id).input_snapshot == {"claims": ["one"]}


def test_hash_chain_detects_trace_tampering(tmp_path):
    path = tmp_path / "decisions.json"
    policy = EvidenceDecisionPolicy(path)
    policy.preview_noop(
        input_snapshot={"claim": "stable"},
        reason="No material change",
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["records"][0]["trace"]["reason"] = "tampered"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(DecisionLedgerCorruptionError, match="record hash"):
        DecisionTraceLedger(path)
