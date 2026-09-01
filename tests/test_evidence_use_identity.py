"""Regression tests for claim-scoped evidence-use identity."""
from __future__ import annotations

import json

import pytest

from sheaf_ai.evidence_memory import (
    EvidenceAlreadyProcessedError,
    EvidenceGovernedMemory,
    EvidenceValidationError,
)


def _entry(
    entry_id: str = "entry-1",
    *,
    domain: str = "example.com",
    content_hash: str | None = None,
    evidence_digest: str = "",
) -> dict:
    entry = {
        "id": entry_id,
        "url": f"https://{domain}/{entry_id}",
        "source_tier": "B",
        "source": {"domain": domain, "tier": "B"},
        "content_hash": f"hash-{entry_id}" if content_hash is None else content_hash,
    }
    if evidence_digest:
        entry["metadata"] = {"evidence_digest": evidence_digest}
    return entry


def _create(
    memory: EvidenceGovernedMemory,
    *,
    claim: str,
    fact_key: str = "",
    fact_value: str = "",
    reason: str = "record atomic claim",
    idempotency_key: str = "",
    entry: dict | None = None,
):
    entry = entry or _entry()
    card = {"title": claim, "claim": claim, "source_ids": ["entry-1"]}
    if fact_key:
        card.update({"fact_key": fact_key, "fact_value": fact_value})
    return memory.apply_transition(
        "CREATE",
        topic="topic",
        entries=[entry],
        card=card,
        reason=reason,
        idempotency_key=idempotency_key,
    )


def test_same_entry_can_support_distinct_unstructured_claims(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")

    first = _create(memory, claim="The policy starts in June")
    second = _create(memory, claim="The policy applies to public agencies")

    assert first.applied is True
    assert second.applied is True
    assert len(memory.snapshot().processed_evidence) == 2


def test_claim_identity_is_scoped_by_topic(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    _create(memory, claim="The threshold is 42")

    result = memory.apply_transition(
        "CREATE",
        topic="another-topic",
        entries=[_entry()],
        card={"title": "Threshold", "claim": "The threshold is 42", "source_ids": ["entry-1"]},
        reason="same words have a distinct meaning in another topic",
    )

    assert result.applied is True


def test_same_entry_same_claim_rejects_after_exact_retry(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    first = _create(memory, claim="The policy starts in June")
    retry = _create(memory, claim="The policy starts in June")

    assert retry.applied is False
    assert retry.event_id == first.event_id

    with pytest.raises(EvidenceAlreadyProcessedError, match="atomic claim"):
        _create(
            memory,
            claim="  the POLICY starts   in June  ",
            reason="same evidence and claim, different request",
            idempotency_key="different-request",
        )


def test_structured_identity_uses_fact_instead_of_claim_wording(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    _create(
        memory,
        claim="The programme has 42 participants",
        fact_key="participant_count",
        fact_value="42",
    )

    with pytest.raises(EvidenceAlreadyProcessedError, match="atomic claim"):
        _create(
            memory,
            claim="Participation totals forty-two people",
            fact_key=" Participant_Count ",
            fact_value=" 42 ",
            reason="same structured fact with new wording",
        )


def test_same_entry_can_support_distinct_structured_facts(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")

    _create(
        memory,
        claim="The programme has 42 participants",
        fact_key="participant_count",
        fact_value="42",
    )
    _create(
        memory,
        claim="The programme begins in June",
        fact_key="start_month",
        fact_value="June",
    )

    assert len(memory.snapshot().processed_evidence) == 2


def test_schema_v1_replays_then_migrates_when_new_claim_is_written(tmp_path):
    ledger_path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(ledger_path)
    first = _create(memory, claim="The policy starts in June")

    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    v2_record = next(iter(raw["processed_evidence"].values()))
    raw["schema_version"] = 1
    raw["processed_evidence"] = {
        "entry-1": {
            "event_id": first.event_id,
            "content_hash": "hash-entry-1",
            "processed_at": v2_record["processed_at"],
        }
    }
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    reopened = EvidenceGovernedMemory(ledger_path)
    assert len(reopened.snapshot().processed_evidence) == 1
    _create(reopened, claim="The policy applies to public agencies")

    migrated = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 2
    assert len(migrated["processed_evidence"]) == 2
    assert {item["entry_id"] for item in migrated["processed_evidence"].values()} == {
        "entry-1"
    }
    assert all(item["claim_identity"] for item in migrated["processed_evidence"].values())


def test_schema_v1_replay_still_rejects_same_claim(tmp_path):
    ledger_path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(ledger_path)
    first = _create(memory, claim="The policy starts in June")

    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    v2_record = next(iter(raw["processed_evidence"].values()))
    raw["schema_version"] = 1
    raw["processed_evidence"] = {
        "entry-1": {
            "event_id": first.event_id,
            "content_hash": "hash-entry-1",
            "processed_at": v2_record["processed_at"],
        }
    }
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    reopened = EvidenceGovernedMemory(ledger_path)
    with pytest.raises(EvidenceAlreadyProcessedError, match="atomic claim"):
        _create(
            reopened,
            claim="the policy starts in june",
            reason="same claim after legacy replay",
        )


def test_schema_v1_exact_retry_is_idempotent_without_forcing_a_write(tmp_path):
    ledger_path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(ledger_path)
    first = _create(memory, claim="The policy starts in June")

    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    v2_record = next(iter(raw["processed_evidence"].values()))
    raw["schema_version"] = 1
    raw["processed_evidence"] = {
        "entry-1": {
            "event_id": first.event_id,
            "content_hash": "hash-entry-1",
            "processed_at": v2_record["processed_at"],
        }
    }
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    retry = _create(EvidenceGovernedMemory(ledger_path), claim="The policy starts in June")

    assert retry.applied is False
    assert retry.event_id == first.event_id
    assert json.loads(ledger_path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_entry_content_hash_can_upgrade_from_unknown_to_known(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    _create(memory, claim="First claim", entry=_entry(content_hash=""))

    result = _create(memory, claim="Second claim", entry=_entry(content_hash="known-hash"))

    assert result.applied is True
    assert memory.snapshot().versions_by_id[result.version_ids[0]].evidence_refs[0].content_hash == (
        "known-hash"
    )


def test_hash_upgrade_does_not_rewrite_or_block_an_older_card_branch(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    old_branch = _create(memory, claim="First claim", entry=_entry(content_hash=""))
    _create(memory, claim="Second claim", entry=_entry(content_hash="known-hash"))
    old_card_id = memory.snapshot().versions_by_id[old_branch.version_ids[0]].card_id

    updated = memory.apply_transition(
        "UPDATE",
        topic="topic",
        entries=[_entry("entry-2")],
        target_card_ids=[old_card_id],
        card={"claim": "First claim refined", "source_ids": ["entry-2"]},
        reason="advance old branch without reasserting entry-1 provenance",
    )

    assert updated.applied is True
    assert len(memory.snapshot().events) == 3


@pytest.mark.parametrize("new_hash", ["", "different-hash"])
def test_entry_content_hash_cannot_downgrade_or_change(tmp_path, new_hash):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    _create(memory, claim="First claim", entry=_entry(content_hash="known-hash"))

    with pytest.raises(EvidenceValidationError, match="content hash"):
        _create(memory, claim="Second claim", entry=_entry(content_hash=new_hash))


def test_entry_source_identity_cannot_change(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    _create(memory, claim="First claim", entry=_entry(domain="one.example"))

    with pytest.raises(EvidenceValidationError, match="source identity"):
        _create(memory, claim="Second claim", entry=_entry(domain="two.example"))


def test_trusted_evidence_digest_is_an_immutable_entry_identity(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    _create(
        memory,
        claim="First claim",
        entry=_entry(evidence_digest=f"sha256:{'a' * 64}"),
    )

    with pytest.raises(EvidenceValidationError, match="evidence digest"):
        _create(
            memory,
            claim="Second claim",
            entry=_entry(evidence_digest=f"sha256:{'b' * 64}"),
        )


def test_update_rejects_changed_entry_hash_before_ledger_replay(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(memory, claim="First claim", entry=_entry(content_hash="known-hash"))
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id

    with pytest.raises(EvidenceValidationError, match="content hash"):
        memory.apply_transition(
            "UPDATE",
            topic="topic",
            entries=[_entry(content_hash="different-hash")],
            target_card_ids=[card_id],
            card={"claim": "Second claim", "source_ids": ["entry-1"]},
            reason="changed Entry must fail before append",
        )
    assert len(memory.snapshot().events) == 1


def test_update_can_enrich_an_unknown_entry_hash(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(memory, claim="First claim", entry=_entry(content_hash=""))
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id

    updated = memory.apply_transition(
        "UPDATE",
        topic="topic",
        entries=[_entry(content_hash="known-hash")],
        target_card_ids=[card_id],
        card={"claim": "Second claim", "source_ids": ["entry-1"]},
        reason="enrich immutable Entry provenance",
    )

    version = memory.snapshot().versions_by_id[updated.version_ids[0]]
    assert version.evidence_refs[0].content_hash == "known-hash"


def test_contest_rejects_changed_entry_hash(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(
        memory,
        claim="Count is one",
        fact_key="count",
        fact_value="1",
        entry=_entry(content_hash="known-hash"),
    )
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id

    with pytest.raises(EvidenceValidationError, match="content hash"):
        memory.apply_transition(
            "CONTEST",
            topic="topic",
            entries=[_entry(content_hash="different-hash")],
            target_card_ids=[card_id],
            card={
                "claim": "Count is two",
                "fact_key": "count",
                "fact_value": "2",
                "source_ids": ["entry-1"],
            },
            reason="same Entry identity cannot mutate in a proposal",
        )
