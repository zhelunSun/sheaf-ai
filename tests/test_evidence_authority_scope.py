"""Regression tests for scoped official-correction authority."""
from __future__ import annotations

import json

import pytest

from sheaf_ai._evidence_memory_models import (
    claim_identity_for_version,
    legacy_evidence_use_identity,
)
from sheaf_ai.evidence_memory import (
    ConflictResolutionRequired,
    EvidenceGovernedMemory,
    EvidenceValidationError,
)


def _entry(
    entry_id: str,
    *,
    primary: bool = False,
    topics: tuple[str, ...] = (),
    fact_keys: tuple[str, ...] = (),
    corrects: tuple[str, ...] = (),
) -> dict:
    source: dict[str, object] = {
        "domain": "authority.example" if primary else "example.com",
        "tier": "A" if primary else "B",
        "is_primary": primary,
    }
    if topics or fact_keys:
        source["authority_scope"] = {
            "topics": list(topics),
            "fact_keys": list(fact_keys),
        }
    if corrects:
        source["correction_relations"] = [
            {"relation": "corrects", "entry_id": entry_id_to_correct}
            for entry_id_to_correct in corrects
        ]
    return {
        "id": entry_id,
        "url": f"https://{source['domain']}/{entry_id}",
        "source": source,
        "content_hash": f"hash-{entry_id}",
    }


def _contested(memory: EvidenceGovernedMemory) -> str:
    created = memory.apply_transition(
        "CREATE",
        topic="release",
        entries=[_entry("old")],
        card={
            "title": "Status",
            "claim": "Release is planned",
            "fact_key": "release.status",
            "fact_value": "planned",
            "source_ids": ["old"],
        },
        reason="initial status",
    )
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id
    memory.apply_transition(
        "CONTEST",
        topic="release",
        entries=[_entry("proposal")],
        target_card_ids=[card_id],
        card={
            "claim": "Release shipped",
            "fact_key": "release.status",
            "fact_value": "shipped",
            "source_ids": ["proposal"],
        },
        reason="conflicting report",
    )
    return card_id


def _resolve(memory: EvidenceGovernedMemory, card_id: str, authority: dict):
    return memory.apply_transition(
        "UPDATE",
        topic="release",
        entries=[authority],
        target_card_ids=[card_id],
        card={
            "claim": "Release shipped",
            "fact_key": "release.status",
            "fact_value": "shipped",
            "source_ids": ["authority"],
        },
        reason="official correction",
        resolution_basis="official_correction",
        resolution_metadata={
            "authority_source_id": "authority",
            "corrects_entry_id": "old",
            "authoritative_fact_value": "shipped",
            "correction_relation": "corrects",
        },
    )


def test_is_primary_without_explicit_scope_is_insufficient(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    card_id = _contested(memory)

    with pytest.raises(ConflictResolutionRequired, match="authority scope"):
        _resolve(memory, card_id, _entry("authority", primary=True))


def test_existing_entry_cannot_escalate_itself_to_primary_authority(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    non_primary = _entry("authority")
    non_primary["url"] = "https://authority.example/authority"
    non_primary["source"]["domain"] = "authority.example"
    non_primary["source"]["tier"] = "A"
    memory.apply_transition(
        "CREATE",
        topic="release",
        entries=[non_primary],
        card={"title": "First", "claim": "First claim", "source_ids": ["authority"]},
        reason="non-authoritative use",
    )

    with pytest.raises(EvidenceValidationError, match="primary authority status"):
        memory.apply_transition(
            "CREATE",
            topic="release",
            entries=[
                _entry(
                    "authority",
                    primary=True,
                    topics=("release",),
                    fact_keys=("release.status",),
                    corrects=("old",),
                )
            ],
            card={
                "title": "Second",
                "claim": "Second claim",
                "source_ids": ["authority"],
            },
            reason="authority escalation must fail",
        )


@pytest.mark.parametrize(
    ("topics", "fact_keys", "corrects", "message"),
    [
        (("another-topic",), ("release.status",), ("old",), "topic"),
        (("release",), ("another.fact",), ("old",), "fact_key"),
        (("release",), ("release.status",), ("proposal",), "correction relation"),
    ],
)
def test_authority_scope_must_cover_topic_fact_and_corrected_entry(
    tmp_path,
    topics,
    fact_keys,
    corrects,
    message,
):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    card_id = _contested(memory)
    authority = _entry(
        "authority",
        primary=True,
        topics=topics,
        fact_keys=fact_keys,
        corrects=corrects,
    )

    with pytest.raises(ConflictResolutionRequired, match=message):
        _resolve(memory, card_id, authority)


def test_scoped_authority_can_apply_bound_official_correction(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    card_id = _contested(memory)
    authority = _entry(
        "authority",
        primary=True,
        topics=("release",),
        fact_keys=("release.status",),
        corrects=("old",),
    )

    result = _resolve(memory, card_id, authority)
    snapshot = memory.snapshot()
    resolved = snapshot.versions_by_id[result.version_ids[0]]

    assert resolved.fact_value == "shipped"
    authority_ref = next(ref for ref in resolved.evidence_refs if ref.entry_id == "authority")
    assert authority_ref.authority_topics == ("release",)
    assert authority_ref.authority_fact_keys == ("release.status",)
    assert authority_ref.corrects_entry_ids == ("old",)


def test_schema2_official_correction_replays_under_legacy_authority_rule(tmp_path):
    ledger_path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(ledger_path)
    card_id = _contested(memory)
    authority = _entry(
        "authority",
        primary=True,
        topics=("release",),
        fact_keys=("release.status",),
        corrects=("old",),
    )
    _resolve(memory, card_id, authority)
    snapshot = memory.snapshot()

    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    records_by_event = {
        record["event_id"]: record for record in raw["processed_evidence"].values()
    }
    legacy_processed = {}
    for event in snapshot.events:
        output = snapshot.versions_by_id[event.output_version_ids[0]]
        claim_refs = (
            output.proposal.evidence_refs
            if event.action == "CONTEST" and output.proposal is not None
            else output.evidence_refs
        )
        claim_identity = claim_identity_for_version(output, event.action)
        for ref in claim_refs:
            if ref.entry_id not in event.evidence_ids:
                continue
            use_id = legacy_evidence_use_identity(ref.entry_id, claim_identity)
            legacy_processed[use_id] = records_by_event[event.event_id]

    raw["schema_version"] = 2
    for event in raw["events"]:
        event.pop("governance_version", None)
        event.pop("evidence_use_ids", None)
    raw["events"][-1]["resolution_metadata"] = [
        item
        for item in raw["events"][-1]["resolution_metadata"]
        if item[0] != "correction_relation"
    ]
    for version in raw["versions"]:
        ref_groups = [version["evidence_refs"]]
        if version.get("proposal"):
            ref_groups.append(version["proposal"]["evidence_refs"])
        for refs in ref_groups:
            for ref in refs:
                ref.pop("locator", None)
                ref.pop("authority_topics", None)
                ref.pop("authority_fact_keys", None)
                ref.pop("corrects_entry_ids", None)
    raw["processed_evidence"] = legacy_processed
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    replayed = EvidenceGovernedMemory(ledger_path).snapshot()
    assert replayed.versions[-1].fact_value == "shipped"
    assert replayed.events[-1].governance_version == "evidence-governance-v1"
