"""Compatibility tests for versioned evidence-strength replay."""
from __future__ import annotations

import json
from dataclasses import asdict

from sheaf_ai._evidence_memory_models import (
    ALGORITHM_VERSION,
    LEGACY_ALGORITHM_VERSION,
    SCHEMA_VERSION,
    EvidenceRef,
)
from sheaf_ai._evidence_memory_rules import compute_evidence_strength
from sheaf_ai.evidence_memory import EvidenceGovernedMemory


def _entry(entry_id: str, domain: str, *, digest: str = "") -> dict:
    return {
        "id": entry_id,
        "url": f"https://{domain}/{entry_id}",
        "source": {"domain": domain, "tier": "B"},
        "content_hash": f"legacy-{entry_id}",
        "metadata": {"evidence_digest": digest},
    }


def test_strength_algorithm_versions_have_distinct_mirror_semantics():
    digest = f"sha256:{'a' * 64}"
    refs = (
        EvidenceRef("one", "B", "domain:one.example", evidence_digest=digest),
        EvidenceRef("two", "B", "domain:two.example", evidence_digest=digest),
    )

    legacy = compute_evidence_strength(refs, algorithm_version=LEGACY_ALGORITHM_VERSION)
    current = compute_evidence_strength(refs, algorithm_version=ALGORITHM_VERSION)

    assert legacy.algorithm == LEGACY_ALGORITHM_VERSION
    assert legacy.independent_source_count == 2
    assert current.algorithm == ALGORITHM_VERSION
    assert current.independent_source_count == 1


def test_legacy_v1_mirror_ledger_replays_and_migrates(tmp_path):
    ledger_path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(ledger_path)
    digest = f"sha256:{'b' * 64}"
    entries = [
        _entry("one", "one.example", digest=digest),
        _entry("two", "two.example", digest=digest),
    ]
    first = memory.apply_transition(
        "CREATE",
        topic="topic",
        entries=entries,
        card={"title": "Legacy", "claim": "Legacy claim", "source_ids": ["one", "two"]},
        reason="legacy evidence",
    )

    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    version = raw["versions"][0]
    refs = tuple(EvidenceRef.from_dict(item) for item in version["evidence_refs"])
    version["strength"] = asdict(
        compute_evidence_strength(refs, algorithm_version=LEGACY_ALGORITHM_VERSION)
    )
    raw["events"][0].pop("algorithm_version", None)
    raw["schema_version"] = 1
    raw["processed_evidence"] = {
        record["entry_id"]: {
            "event_id": record["event_id"],
            "content_hash": record["content_hash"],
            "processed_at": record["processed_at"],
        }
        for record in raw["processed_evidence"].values()
    }
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    reopened = EvidenceGovernedMemory(ledger_path)
    snapshot = reopened.snapshot()
    assert snapshot.events[0].algorithm_version == LEGACY_ALGORITHM_VERSION
    assert snapshot.versions_by_id[first.version_ids[0]].strength.independent_source_count == 2

    reopened.apply_transition(
        "CREATE",
        topic="topic",
        entries=[_entry("three", "three.example")],
        card={"title": "Current", "claim": "Current claim", "source_ids": ["three"]},
        reason="force migration",
    )

    migrated = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == SCHEMA_VERSION
    assert migrated["events"][0]["algorithm_version"] == LEGACY_ALGORITHM_VERSION
    assert migrated["events"][0]["governance_version"] == "evidence-governance-v2"
    assert len(migrated["events"][0]["evidence_use_ids"]) == 2
    assert migrated["events"][1]["algorithm_version"] == ALGORITHM_VERSION
    final = reopened.snapshot()
    assert [event.algorithm_version for event in final.events] == [
        LEGACY_ALGORITHM_VERSION,
        ALGORITHM_VERSION,
    ]


def test_legacy_update_and_contest_history_replays_before_v2_resolution(tmp_path):
    ledger_path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(ledger_path)
    created = memory.apply_transition(
        "CREATE",
        topic="topic",
        entries=[_entry("one", "one.example")],
        card={
            "title": "Count",
            "claim": "Count is one",
            "fact_key": "count",
            "fact_value": "1",
            "source_ids": ["one"],
        },
        reason="initial evidence",
    )
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id
    memory.apply_transition(
        "UPDATE",
        topic="topic",
        entries=[_entry("two", "two.example")],
        target_card_ids=[card_id],
        card={"claim": "Count remains one", "source_ids": ["two"]},
        reason="corroboration",
    )
    memory.apply_transition(
        "CONTEST",
        topic="topic",
        entries=[_entry("three", "three.example")],
        target_card_ids=[card_id],
        card={
            "claim": "Count is two",
            "fact_key": "count",
            "fact_value": "2",
            "source_ids": ["three"],
        },
        reason="conflicting evidence",
    )

    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    events_by_id = {event["event_id"]: event for event in raw["events"]}
    for event in raw["events"]:
        event.pop("algorithm_version", None)
    for version in raw["versions"]:
        event = events_by_id[version["event_id"]]
        refs = tuple(EvidenceRef.from_dict(item) for item in version["evidence_refs"])
        version["strength"] = asdict(
            compute_evidence_strength(
                refs,
                conflict=event["conflict"]["state"] == "conflict",
                algorithm_version=LEGACY_ALGORITHM_VERSION,
            )
        )
        if version.get("proposal"):
            proposal_refs = tuple(
                EvidenceRef.from_dict(item) for item in version["proposal"]["evidence_refs"]
            )
            version["proposal"]["strength"] = asdict(
                compute_evidence_strength(
                    proposal_refs,
                    conflict=True,
                    algorithm_version=LEGACY_ALGORITHM_VERSION,
                )
            )
    raw["schema_version"] = 1
    raw["processed_evidence"] = {
        record["entry_id"]: {
            "event_id": record["event_id"],
            "content_hash": record["content_hash"],
            "processed_at": record["processed_at"],
        }
        for record in raw["processed_evidence"].values()
    }
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    reopened = EvidenceGovernedMemory(ledger_path)
    assert [event.algorithm_version for event in reopened.snapshot().events] == [
        LEGACY_ALGORITHM_VERSION,
        LEGACY_ALGORITHM_VERSION,
        LEGACY_ALGORITHM_VERSION,
    ]
    reopened.apply_transition(
        "UPDATE",
        topic="topic",
        entries=[],
        target_card_ids=[card_id],
        card={"claim": "Count is two", "fact_key": "count", "fact_value": "2"},
        reason="adjudicated resolution",
        resolution_basis="manual_adjudication",
        resolution_metadata={
            "adjudicator_id": "reviewer",
            "decision_id": "decision-1",
            "decided_at": "2026-09-01",
        },
    )

    final = reopened.snapshot()
    assert len(final.events) == 4
    assert final.events[-1].algorithm_version == ALGORITHM_VERSION
    assert (
        json.loads(ledger_path.read_text(encoding="utf-8"))["schema_version"]
        == SCHEMA_VERSION
    )
