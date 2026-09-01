"""Production domain-ledger atomicity tests for UPDATE + CREATE SPLIT batches."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from sheaf_ai.evidence_memory import (
    AtomicBatchConflictError,
    AtomicSplitOperation,
    EvidenceGovernedMemory,
    LedgerCorruptionError,
    StaleHeadError,
)


def _entry(entry_id: str, domain: str) -> dict[str, object]:
    return {
        "id": entry_id,
        "url": f"https://{domain}/{entry_id}",
        "source": {"domain": domain, "tier": "B", "is_primary": False},
        "source_tier": "B",
        "quality_tier": "A",
        "content_hash": f"hash-{entry_id}",
    }


def _fixture(tmp_path):
    path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(path)
    initial = _entry("entry-initial", "initial.example")
    created = memory.apply_transition(
        "CREATE",
        topic="topic",
        entries={"entry-initial": initial},
        source_ids=("entry-initial",),
        card={"title": "Combined", "claim": "The combined claim."},
        reason="Create the previewed head.",
    )
    snapshot = memory.snapshot()
    version = snapshot.versions_by_id[created.version_ids[0]]
    return memory, path, version.card_id, version.version_id


def _operations(card_id: str, suffix: str = "one"):
    update_entry = _entry(f"entry-update-{suffix}", f"update-{suffix}.example")
    create_entry = _entry(f"entry-create-{suffix}", f"create-{suffix}.example")
    update = AtomicSplitOperation(
        action="UPDATE",
        topic="topic",
        entries={str(update_entry["id"]): update_entry},
        source_ids=(str(update_entry["id"]),),
        target_card_ids=(card_id,),
        card={"claim": f"The retained claim {suffix}."},
        reason="Keep one independently maintainable claim.",
    )
    create = AtomicSplitOperation(
        action="CREATE",
        topic="topic",
        entries={str(create_entry["id"]): create_entry},
        source_ids=(str(create_entry["id"]),),
        card={
            "title": f"Split claim {suffix}",
            "claim": f"The new independent claim {suffix}.",
        },
        reason="Create the second independently maintainable claim.",
    )
    return update, create


def _apply(
    memory: EvidenceGovernedMemory,
    card_id: str,
    version_id: str,
    *,
    suffix: str = "one",
    decision_id: str = "decision-one",
    request_hash: str = "a" * 64,
    fault_injector=None,
):
    update, create = _operations(card_id, suffix)
    return memory.apply_atomic_split(
        update=update,
        create=create,
        decision_id=decision_id,
        request_hash=request_hash,
        idempotency_key=f"request-{decision_id}",
        expected_heads={card_id: version_id},
        policy_version="evidence-policy-v1",
        algorithm_version="split-noop-v1",
        execution_manifest_hash="b" * 64,
        fault_injector=fault_injector,
    )


def test_atomic_split_commits_two_events_and_one_receipt_with_one_replace(
    tmp_path,
    monkeypatch,
):
    memory, path, card_id, version_id = _fixture(tmp_path)
    real_replace = __import__("sheaf_ai._evidence_memory_ledger", fromlist=["os"]).os.replace
    replacements: list[tuple[object, object]] = []

    def counted_replace(source, target):
        replacements.append((source, target))
        return real_replace(source, target)

    monkeypatch.setattr("sheaf_ai._evidence_memory_ledger.os.replace", counted_replace)
    receipt = _apply(memory, card_id, version_id)

    assert receipt.applied is True
    assert receipt.operation_actions == ("UPDATE", "CREATE")
    assert len(receipt.event_ids) == len(receipt.version_ids) == 2
    assert len(replacements) == 1
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 4
    assert len(raw["atomic_batches"]) == 1
    assert raw["atomic_batches"][0]["event_ids"] == list(receipt.event_ids)
    snapshot = memory.snapshot()
    assert len(snapshot.events) == 3
    assert len(snapshot.active_heads) == 2


@pytest.mark.parametrize(
    "checkpoint",
    ["after_read", "after_update_staged", "after_create_staged", "before_replace"],
)
def test_fault_before_replace_preserves_exact_ledger_bytes(tmp_path, checkpoint):
    memory, path, card_id, version_id = _fixture(tmp_path)
    before = path.read_bytes()

    def fail_at(actual: str) -> None:
        if actual == checkpoint:
            raise RuntimeError(f"crash at {checkpoint}")

    with pytest.raises(RuntimeError, match=checkpoint):
        _apply(memory, card_id, version_id, fault_injector=fail_at)

    assert path.read_bytes() == before
    assert memory.lookup_atomic_batch("decision-one", "a" * 64) is None


def test_fault_after_replace_is_recovered_by_idempotent_retry(tmp_path):
    memory, _path, card_id, version_id = _fixture(tmp_path)

    def fail_after_replace(checkpoint: str) -> None:
        if checkpoint == "after_replace":
            raise RuntimeError("caller did not observe commit")

    with pytest.raises(RuntimeError, match="did not observe commit"):
        _apply(memory, card_id, version_id, fault_injector=fail_after_replace)

    committed = memory.lookup_atomic_batch("decision-one", "a" * 64)
    assert committed is not None
    assert committed.applied is False
    retry = _apply(memory, card_id, version_id)
    assert retry.applied is False
    assert retry.event_ids == committed.event_ids
    assert len(memory.snapshot().events) == 3


def test_same_decision_with_different_hash_or_key_fails_closed(tmp_path):
    memory, _path, card_id, version_id = _fixture(tmp_path)
    _apply(memory, card_id, version_id)

    with pytest.raises(AtomicBatchConflictError, match="different request hash"):
        _apply(memory, card_id, version_id, request_hash="b" * 64)

    with pytest.raises(AtomicBatchConflictError, match="different domain operations"):
        _apply(memory, card_id, version_id, suffix="changed")

    update, create = _operations(card_id)
    with pytest.raises(AtomicBatchConflictError, match="different idempotency key"):
        memory.apply_atomic_split(
            update=update,
            create=create,
            decision_id="decision-one",
            request_hash="a" * 64,
            idempotency_key="different-key",
            expected_heads={card_id: version_id},
            policy_version="evidence-policy-v1",
            algorithm_version="split-noop-v1",
            execution_manifest_hash="b" * 64,
        )


def test_concurrent_batches_from_same_old_head_allow_at_most_one_commit(tmp_path):
    memory, _path, card_id, version_id = _fixture(tmp_path)

    def run(index: int):
        return _apply(
            EvidenceGovernedMemory(memory.ledger.path),
            card_id,
            version_id,
            suffix=str(index),
            decision_id=f"decision-{index}",
            request_hash=f"{index + 1:064x}",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, index) for index in range(2)]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result())
        except StaleHeadError:
            outcomes.append("stale")

    assert sum(outcome != "stale" for outcome in outcomes) == 1
    assert sum(outcome == "stale" for outcome in outcomes) == 1
    raw = json.loads(memory.ledger.path.read_text(encoding="utf-8"))
    assert len(raw["atomic_batches"]) == 1
    assert len(memory.snapshot().events) == 3


def test_schema3_replays_and_upgrades_when_atomic_split_is_written(tmp_path):
    memory, path, card_id, version_id = _fixture(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = 3
    raw.pop("atomic_batches")
    path.write_text(json.dumps(raw), encoding="utf-8")

    reopened = EvidenceGovernedMemory(path)
    receipt = _apply(reopened, card_id, version_id)

    assert receipt.applied is True
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 4
    assert len(migrated["atomic_batches"]) == 1


def test_replay_rejects_tampered_atomic_batch_event_order(tmp_path):
    memory, path, card_id, version_id = _fixture(tmp_path)
    _apply(memory, card_id, version_id)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["atomic_batches"][0]["event_ids"].reverse()
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(LedgerCorruptionError, match="event order"):
        EvidenceGovernedMemory(path)
