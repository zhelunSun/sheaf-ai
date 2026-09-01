"""Regression tests for verified quote/span EvidenceUse identity."""
from __future__ import annotations

import json

import pytest

from sheaf_ai._evidence_memory_models import (
    SCHEMA_VERSION,
    claim_identity_for_version,
    legacy_evidence_use_identity,
)
from sheaf_ai.evidence_memory import (
    EvidenceAlreadyProcessedError,
    EvidenceGovernedMemory,
    EvidenceValidationError,
    LedgerCorruptionError,
)


BODY = "Alpha evidence is unique. Beta evidence is also unique. Repeated. Repeated."


def _entry() -> dict:
    return {
        "id": "entry-1",
        "url": "https://example.com/entry-1",
        "source": {"domain": "example.com", "tier": "B"},
        "content_hash": "legacy-entry-1",
        "metadata": {"evidence_digest": f"sha256:{'a' * 64}"},
        "text": BODY,
    }


def _create(
    memory: EvidenceGovernedMemory,
    *,
    locator: dict,
    reason: str,
    idempotency_key: str = "",
):
    return memory.apply_transition(
        "CREATE",
        topic="topic",
        entries=[_entry()],
        source_ids=["entry-1"],
        evidence_locators={"entry-1": locator},
        card={"title": "Claim", "claim": "Atomic claim"},
        reason=reason,
        idempotency_key=idempotency_key,
    )


def test_unique_quote_is_verified_and_persisted(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")

    result = _create(
        memory,
        locator={"kind": "quote", "quote": "Alpha evidence is unique."},
        reason="quote support",
    )

    snapshot = memory.snapshot()
    ref = snapshot.versions_by_id[result.version_ids[0]].evidence_refs[0]
    assert ref.locator.kind == "quote"
    assert ref.locator.start == 0
    assert ref.locator.end == len("Alpha evidence is unique.")
    assert ref.locator.quote == "Alpha evidence is unique."
    assert snapshot.events[0].evidence_use_ids


def test_same_entry_and_claim_can_use_distinct_fragments_but_not_repeat_one(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    first = _create(
        memory,
        locator={"kind": "quote", "quote": "Alpha evidence is unique."},
        reason="first fragment",
    )
    second = _create(
        memory,
        locator={"kind": "quote", "quote": "Beta evidence is also unique."},
        reason="second fragment",
    )

    assert first.applied is True
    assert second.applied is True
    assert len(memory.snapshot().processed_evidence) == 2
    assert all(version.strength.independent_source_count == 1 for version in memory.snapshot().versions)

    with pytest.raises(EvidenceAlreadyProcessedError, match="evidence span"):
        _create(
            memory,
            locator={"kind": "quote", "quote": "Alpha evidence is unique."},
            reason="repeat first fragment",
            idempotency_key="repeat-fragment",
        )


def test_update_retains_two_fragments_but_strength_counts_entry_once(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(
        memory,
        locator={"kind": "quote", "quote": "Alpha evidence is unique."},
        reason="first fragment",
    )
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id

    updated = memory.apply_transition(
        "UPDATE",
        topic="topic",
        entries=[_entry()],
        source_ids=["entry-1"],
        evidence_locators={
            "entry-1": {"kind": "quote", "quote": "Beta evidence is also unique."}
        },
        target_card_ids=[card_id],
        card={"claim": "Atomic claim"},
        reason="second fragment supports same card claim",
    )

    version = memory.snapshot().versions_by_id[updated.version_ids[0]]
    assert len(version.evidence_refs) == 2
    assert {ref.locator.quote for ref in version.evidence_refs} == {
        "Alpha evidence is unique.",
        "Beta evidence is also unique.",
    }
    assert version.strength.independent_source_count == 1


def test_quote_and_char_span_for_same_location_share_one_identity(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    quote = "Alpha evidence is unique."
    _create(
        memory,
        locator={"kind": "quote", "quote": quote},
        reason="quote locator",
    )

    with pytest.raises(EvidenceAlreadyProcessedError, match="evidence span"):
        _create(
            memory,
            locator={"kind": "char_span", "start": 0, "end": len(quote)},
            reason="equivalent char span",
            idempotency_key="equivalent-span",
        )


@pytest.mark.parametrize(
    ("locator", "message"),
    [
        ({"kind": "quote", "quote": "missing evidence"}, "not found"),
        ({"kind": "quote", "quote": "Repeated."}, "ambiguous"),
        ({"kind": "char_span", "start": -1, "end": 3}, "bounds"),
        ({"kind": "char_span", "start": 0, "end": 999}, "bounds"),
        (
            {"kind": "char_span", "start": 0, "end": 5, "quote": "wrong"},
            "does not match",
        ),
    ],
)
def test_unverifiable_locator_fails_closed(tmp_path, locator, message):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")

    with pytest.raises(EvidenceValidationError, match=message):
        _create(memory, locator=locator, reason="invalid locator")


def test_non_whole_locator_requires_entry_body(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    entry = _entry()
    entry.pop("text")

    with pytest.raises(EvidenceValidationError, match="body"):
        memory.apply_transition(
            "CREATE",
            topic="topic",
            entries=[entry],
            source_ids=["entry-1"],
            evidence_locators={
                "entry-1": {"kind": "quote", "quote": "Alpha evidence is unique."}
            },
            card={"title": "Claim", "claim": "Atomic claim"},
            reason="body required",
        )


def test_schema2_without_locator_replays_as_whole_entry_and_migrates(tmp_path):
    ledger_path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(ledger_path)
    first = memory.apply_transition(
        "CREATE",
        topic="topic",
        entries=[_entry()],
        source_ids=["entry-1"],
        card={"title": "Claim", "claim": "Atomic claim"},
        reason="legacy whole Entry use",
    )
    snapshot = memory.snapshot()
    version = snapshot.versions_by_id[first.version_ids[0]]
    old_use_id = legacy_evidence_use_identity(
        "entry-1",
        claim_identity_for_version(version, "CREATE"),
    )

    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    record = next(iter(raw["processed_evidence"].values()))
    raw["schema_version"] = 2
    raw["events"][0].pop("governance_version", None)
    raw["events"][0].pop("evidence_use_ids", None)
    raw["versions"][0]["evidence_refs"][0].pop("locator", None)
    raw["processed_evidence"] = {old_use_id: record}
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    reopened = EvidenceGovernedMemory(ledger_path)
    legacy_ref = reopened.snapshot().versions[0].evidence_refs[0]
    assert legacy_ref.locator.kind == "whole_entry"

    with pytest.raises(EvidenceAlreadyProcessedError, match="evidence span"):
        reopened.apply_transition(
            "CREATE",
            topic="topic",
            entries=[_entry()],
            source_ids=["entry-1"],
            card={"title": "Retry", "claim": "Atomic claim"},
            reason="same legacy whole Entry use",
            idempotency_key="legacy-whole-reuse",
        )

    reopened.apply_transition(
        "CREATE",
        topic="topic",
        entries=[_entry()],
        source_ids=["entry-1"],
        evidence_locators={
            "entry-1": {"kind": "quote", "quote": "Alpha evidence is unique."}
        },
        card={"title": "Another", "claim": "Another atomic claim"},
        reason="force schema migration",
    )
    migrated = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == SCHEMA_VERSION
    assert all(record["locator_identity"] for record in migrated["processed_evidence"].values())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("start", True),
        ("end", "25"),
        ("quote", ["Alpha evidence is unique."]),
    ],
)
def test_ledger_rejects_coerced_locator_types(tmp_path, field, value):
    ledger_path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(ledger_path)
    _create(
        memory,
        locator={"kind": "quote", "quote": "Alpha evidence is unique."},
        reason="valid locator",
    )
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    raw["versions"][0]["evidence_refs"][0]["locator"][field] = value
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(LedgerCorruptionError, match="Malformed ledger record"):
        EvidenceGovernedMemory(ledger_path)


def test_ledger_rejects_string_authority_array(tmp_path):
    ledger_path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(ledger_path)
    _create(memory, locator={"kind": "whole_entry"}, reason="valid reference")
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    raw["versions"][0]["evidence_refs"][0]["authority_topics"] = "topic"
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(LedgerCorruptionError, match="Malformed ledger record"):
        EvidenceGovernedMemory(ledger_path)
