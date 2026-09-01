"""Attack-oriented tests for the evidence-governed memory core."""
from __future__ import annotations

import json
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from sheaf_ai.evidence_memory import (
    ConflictResolutionRequired,
    EvidenceAlreadyProcessedError,
    EvidenceGovernedMemory,
    EvidenceLedger,
    EvidenceValidationError,
    LedgerCorruptionError,
    TransitionValidationError,
)
from sheaf_cards.base import CardStore, CardStoreError, KnowledgeCard


def _save_cards_in_process(path: str, prefix: str, count: int, start_event) -> None:
    """Spawn-safe writer used to verify the advisory lock, not just thread locks."""
    start_event.wait()
    store = CardStore(Path(path))
    for index in range(count):
        store.save(
            KnowledgeCard(
                card_id=f"{prefix}-{index}",
                title=f"{prefix}-{index}",
                claim="concurrent",
            )
        )


def _entry(
    entry_id: str,
    tier: str = "B",
    *,
    domain: str = "example.com",
    quality_tier: str = "A",
    is_primary: bool = False,
) -> dict:
    return {
        "id": entry_id,
        "url": f"https://{domain}/{entry_id}",
        "source_tier": tier,
        "source": {"domain": domain, "tier": tier, "is_primary": is_primary},
        "quality_tier": quality_tier,
        "content_hash": f"hash-{entry_id}",
    }


def _create(
    memory: EvidenceGovernedMemory,
    entry: dict,
    *,
    title: str = "Initial",
    fact_key: str = "",
    fact_value: str = "",
):
    card = {"title": title, "claim": f"claim-{title}", "source_ids": [entry["id"]]}
    if fact_key:
        card.update({"fact_key": fact_key, "fact_value": fact_value})
    return memory.apply_transition(
        "create",
        topic="topic",
        entries=[entry],
        card=card,
        reason="initial evidence",
    )


def test_rejects_forged_source_id(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")

    with pytest.raises(EvidenceValidationError, match="not in the current evidence allowlist"):
        memory.apply_transition(
            "CREATE",
            topic="topic",
            entries=[_entry("real")],
            card={"title": "T", "claim": "C", "source_ids": ["forged"]},
            reason="initial evidence",
        )

    assert memory.snapshot().events == ()


def test_deduplicates_source_ids_and_uses_source_tier_not_quality_tier(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    result = memory.apply_transition(
        "CREATE",
        topic="topic",
        entries=[_entry("e1", tier="D", quality_tier="A")],
        source_ids=["e1", "e1", "e1"],
        card={"title": "T", "claim": "C"},
        reason="initial evidence",
    )

    version = memory.snapshot().versions_by_id[result.version_ids[0]]
    assert len(version.evidence_refs) == 1
    assert version.evidence_refs[0].source_tier == "D"
    assert version.strength.tier_counts == (("D", 1),)
    assert version.strength.is_probability is False


def test_rejects_conflicting_duplicate_allowlist_entries(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    with pytest.raises(EvidenceValidationError, match="Conflicting duplicate"):
        memory.apply_transition(
            "CREATE",
            topic="topic",
            entries=[_entry("e1", "A"), _entry("e1", "D")],
            source_ids=["e1"],
            card={"title": "T", "claim": "C"},
            reason="initial evidence",
        )


def test_exact_retry_is_idempotent_and_different_reuse_is_rejected(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    kwargs = {
        "topic": "topic",
        "entries": [_entry("e1")],
        "source_ids": ["e1"],
        "card": {"title": "T", "claim": "C"},
        "reason": "initial evidence",
    }
    first = memory.apply_transition("CREATE", **kwargs)
    retry = memory.apply_transition("CREATE", **kwargs)

    assert first.applied is True
    assert retry.applied is False
    assert retry.event_id == first.event_id
    assert len(memory.snapshot().events) == 1

    with pytest.raises(EvidenceAlreadyProcessedError):
        memory.apply_transition(
            "CREATE",
            topic="topic",
            entries=[_entry("e1")],
            source_ids=["e1"],
            card={"title": "Different", "claim": "Different"},
            reason="try to consume evidence twice",
        )


def test_update_keeps_immutable_history(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(memory, _entry("e1"))
    first = memory.snapshot().versions_by_id[created.version_ids[0]]

    updated = memory.apply_transition(
        "UPDATE",
        topic="topic",
        entries=[_entry("e2", domain="other.example")],
        source_ids=["e2"],
        target_card_ids=[first.card_id],
        card={"claim": "refined claim"},
        reason="new corroborating evidence",
    )
    snapshot = memory.snapshot()
    second = snapshot.versions_by_id[updated.version_ids[0]]

    assert first.revision == 1
    assert first.claim == "claim-Initial"
    assert second.revision == 2
    assert second.claim == "refined claim"
    assert second.parent_version_ids == (first.version_id,)
    assert {ref.entry_id for ref in second.evidence_refs} == {"e1", "e2"}
    with pytest.raises(FrozenInstanceError):
        second.claim = "mutated"  # type: ignore[misc]


def test_retire_creates_terminal_version_and_removes_active_head(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(memory, _entry("e1"))
    first = memory.snapshot().versions_by_id[created.version_ids[0]]

    retired = memory.apply_transition(
        "RETIRE",
        topic="topic",
        entries=[],
        target_card_ids=[first.card_id],
        reason="claim is no longer applicable",
    )
    snapshot = memory.snapshot()
    terminal = snapshot.versions_by_id[retired.version_ids[0]]

    assert terminal.card_id == first.card_id
    assert terminal.revision == 2
    assert terminal.state == "retired"
    assert first.card_id not in snapshot.active_heads
    assert snapshot.events[-1].reason == "claim is no longer applicable"

    with pytest.raises(TransitionValidationError, match="not an active head"):
        memory.apply_transition(
            "RETIRE",
            topic="topic",
            entries=[],
            target_card_ids=[first.card_id],
            reason="retire twice",
        )


def test_merge_builds_two_parent_audit_graph_and_replay_state(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    left_result = _create(memory, _entry("e1", domain="one.example"), title="Left")
    right_result = _create(memory, _entry("e2", domain="two.example"), title="Right")
    before = memory.snapshot()
    left = before.versions_by_id[left_result.version_ids[0]]
    right = before.versions_by_id[right_result.version_ids[0]]

    merged_result = memory.apply_transition(
        "MERGE",
        topic="topic",
        entries=[_entry("e3", domain="three.example")],
        source_ids=["e3"],
        target_card_ids=[left.card_id, right.card_id],
        card={"title": "Merged", "claim": "combined claim"},
        reason="duplicate insights",
    )
    snapshot = EvidenceLedger(memory.ledger.path).snapshot()
    merged = snapshot.versions_by_id[merged_result.version_ids[0]]
    graph = memory.audit_graph()

    assert set(merged.parent_version_ids) == {left.version_id, right.version_id}
    assert set(snapshot.active_heads) == {merged.card_id}
    merge_edges = [edge for edge in graph["edges"] if edge["action"] == "MERGE"]
    assert {edge["from"] for edge in merge_edges} == {left.version_id, right.version_id}
    assert {edge["to"] for edge in merge_edges} == {merged.version_id}


def test_stronger_evidence_is_explicit_and_rejects_equal_rule_strength(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(
        memory,
        _entry("old", tier="C", domain="old.example"),
        fact_key="release.status",
        fact_value="planned",
    )
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id
    request = {
        "topic": "topic",
        "entries": [_entry("new", tier="A", domain="primary.example")],
        "source_ids": ["new"],
        "target_card_ids": [card_id],
        "card": {
            "claim": "The release shipped.",
            "fact_key": "release.status",
            "fact_value": "shipped",
        },
        "reason": "primary source changed status",
    }

    with pytest.raises(ConflictResolutionRequired, match="changes from"):
        memory.apply_transition("UPDATE", **request)

    result = memory.apply_transition("UPDATE", resolution_basis="stronger_evidence", **request)
    snapshot = memory.snapshot()
    version = snapshot.versions_by_id[result.version_ids[0]]
    event = snapshot.events[-1]
    assert event.conflict.state == "conflict"
    assert event.resolution_basis == "stronger_evidence"
    assert version.strength.conflict_penalty == 0.20
    assert [ref.entry_id for ref in version.evidence_refs] == ["new"]

    equal_memory = EvidenceGovernedMemory(tmp_path / "equal-ledger.json")
    equal_created = _create(
        equal_memory,
        _entry("old-a", tier="A", domain="old-a.example"),
        fact_key="release.status",
        fact_value="planned",
    )
    equal_card_id = equal_memory.snapshot().versions_by_id[
        equal_created.version_ids[0]
    ].card_id
    with pytest.raises(ConflictResolutionRequired, match="strictly higher"):
        equal_memory.apply_transition(
            "UPDATE",
            topic="topic",
            entries=[_entry("new-a", tier="A", domain="new-a.example")],
            source_ids=["new-a"],
            target_card_ids=[equal_card_id],
            card={
                "claim": "The release shipped.",
                "fact_key": "release.status",
                "fact_value": "shipped",
            },
            reason="equal-tier assertion",
            resolution_basis="stronger_evidence",
        )


def test_contest_preserves_both_sides_then_official_correction_resolves(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(
        memory,
        _entry("old", tier="A", domain="official.example", is_primary=True),
        fact_key="release.status",
        fact_value="planned",
    )
    original = memory.snapshot().versions_by_id[created.version_ids[0]]

    contested_result = memory.apply_transition(
        "CONTEST",
        topic="topic",
        entries=[_entry("correction", tier="A", domain="official.example", is_primary=True)],
        source_ids=["correction"],
        target_card_ids=[original.card_id],
        card={
            "claim": "The release shipped.",
            "evidence": "Official correction notice.",
            "fact_key": "release.status",
            "fact_value": "shipped",
        },
        reason="conflicting official evidence arrived",
    )
    contested_snapshot = memory.snapshot()
    contested = contested_snapshot.versions_by_id[contested_result.version_ids[0]]

    assert contested.state == "contested"
    assert contested_snapshot.active_heads[original.card_id] == contested.version_id
    assert contested.claim == original.claim
    assert [ref.entry_id for ref in contested.evidence_refs] == ["old"]
    assert contested.proposal is not None
    assert contested.proposal.fact_value == "shipped"
    assert [ref.entry_id for ref in contested.proposal.evidence_refs] == ["correction"]
    contest_event = contested_snapshot.events[-1]
    assert contest_event.action == "CONTEST"
    assert contest_event.conflict.state == "conflict"
    assert contest_event.resolution_basis == ""

    resolved_result = memory.apply_transition(
        "UPDATE",
        topic="topic",
        entries=[],
        target_card_ids=[original.card_id],
        card={
            "claim": "The release shipped.",
            "fact_key": "release.status",
            "fact_value": "shipped",
        },
        reason="accept official correction",
        resolution_basis="official_correction",
        resolution_metadata={
            "authoritative_fact_value": "shipped",
            "authority_source_id": "correction",
            "corrects_entry_id": "old",
        },
    )
    resolved_snapshot = EvidenceLedger(memory.ledger.path).snapshot()
    resolved = resolved_snapshot.versions_by_id[resolved_result.version_ids[0]]
    resolution_event = resolved_snapshot.events[-1]

    assert resolved.state == "active"
    assert resolved.fact_value == "shipped"
    assert resolved.proposal is None
    assert [ref.entry_id for ref in resolved.evidence_refs] == ["correction"]
    assert resolution_event.resolution_basis == "official_correction"
    assert dict(resolution_event.resolution_metadata) == {
        "authoritative_fact_value": "shipped",
        "authority_source_id": "correction",
        "corrects_entry_id": "old",
    }
    assert [event.action for event in resolved_snapshot.events] == [
        "CREATE",
        "CONTEST",
        "UPDATE",
    ]


def test_contested_version_can_resolve_as_effective_dated_version_change(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(
        memory,
        _entry("v1", tier="A", domain="releases.example"),
        fact_key="api.version",
        fact_value="1",
    )
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id
    memory.apply_transition(
        "CONTEST",
        topic="topic",
        entries=[_entry("v2", tier="A", domain="releases.example")],
        source_ids=["v2"],
        target_card_ids=[card_id],
        card={"claim": "API v2 is current", "fact_key": "api.version", "fact_value": "2"},
        reason="new release evidence",
    )

    with pytest.raises(ConflictResolutionRequired, match="ISO date"):
        memory.apply_transition(
            "UPDATE",
            topic="topic",
            entries=[],
            target_card_ids=[card_id],
            card={"claim": "API v2 is current", "fact_key": "api.version", "fact_value": "2"},
            reason="resolve version change",
            resolution_basis="version_change",
            resolution_metadata={
                "effective_at": "not-a-date",
                "effective_fact_value": "2",
                "supersedes_fact_value": "1",
            },
        )

    resolved = memory.apply_transition(
        "UPDATE",
        topic="topic",
        entries=[],
        target_card_ids=[card_id],
        card={"claim": "API v2 is current", "fact_key": "api.version", "fact_value": "2"},
        reason="resolve effective-dated version change",
        resolution_basis="version_change",
        resolution_metadata={
            "effective_at": "2026-09-01",
            "effective_fact_value": "2",
            "supersedes_fact_value": "1",
        },
    )
    version = memory.snapshot().versions_by_id[resolved.version_ids[0]]
    assert version.state == "active"
    assert version.fact_value == "2"


def test_new_official_evidence_can_correct_the_contested_proposal(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(
        memory,
        _entry("statement-a", tier="A", domain="archive.example", is_primary=True),
        fact_key="deadline.status",
        fact_value="open",
    )
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id

    memory.apply_transition(
        "CONTEST",
        topic="topic",
        entries=[_entry("claim-b", tier="B", domain="reporter.example")],
        source_ids=["claim-b"],
        target_card_ids=[card_id],
        card={
            "claim": "The deadline was cancelled.",
            "fact_key": "deadline.status",
            "fact_value": "cancelled",
        },
        reason="a conflicting report arrived",
    )

    resolved_result = memory.apply_transition(
        "UPDATE",
        topic="topic",
        entries=[
            _entry(
                "correction-c",
                tier="A",
                domain="authority.example",
                is_primary=True,
            )
        ],
        source_ids=["correction-c"],
        target_card_ids=[card_id],
        card={
            "claim": "The deadline moved to September 30.",
            "fact_key": "deadline.status",
            "fact_value": "extended",
        },
        reason="the authority issued a correction",
        resolution_basis="official_correction",
        resolution_metadata={
            "authority_source_id": "correction-c",
            "corrects_entry_id": "claim-b",
            "authoritative_fact_value": "extended",
        },
    )
    snapshot = memory.snapshot()
    resolved = snapshot.versions_by_id[resolved_result.version_ids[0]]

    assert resolved.state == "active"
    assert resolved.fact_value == "extended"
    assert [ref.entry_id for ref in resolved.evidence_refs] == ["correction-c"]
    assert snapshot.events[-1].evidence_ids == ("correction-c",)
    assert dict(snapshot.events[-1].resolution_metadata)["corrects_entry_id"] == "claim-b"


def test_official_correction_metadata_must_bind_the_output_value(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(
        memory,
        _entry("old"),
        fact_key="status",
        fact_value="old",
    )
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id
    memory.apply_transition(
        "CONTEST",
        topic="topic",
        entries=[_entry("proposal")],
        source_ids=["proposal"],
        target_card_ids=[card_id],
        card={"claim": "new", "fact_key": "status", "fact_value": "new"},
        reason="dispute",
    )
    with pytest.raises(ConflictResolutionRequired, match="must equal the output"):
        memory.apply_transition(
            "UPDATE",
            topic="topic",
            entries=[_entry("official", is_primary=True)],
            source_ids=["official"],
            target_card_ids=[card_id],
            card={"claim": "new", "fact_key": "status", "fact_value": "new"},
            reason="official resolution",
            resolution_basis="official_correction",
            resolution_metadata={
                "authority_source_id": "official",
                "corrects_entry_id": "proposal",
                "authoritative_fact_value": "different",
            },
        )


def test_manual_adjudication_requires_traceable_decision_metadata(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(
        memory,
        _entry("old"),
        fact_key="policy.mode",
        fact_value="draft",
    )
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id
    memory.apply_transition(
        "CONTEST",
        topic="topic",
        entries=[_entry("candidate", domain="other.example")],
        source_ids=["candidate"],
        target_card_ids=[card_id],
        card={"claim": "Policy is final", "fact_key": "policy.mode", "fact_value": "final"},
        reason="conflicting policy record",
    )
    request = {
        "topic": "topic",
        "entries": [],
        "target_card_ids": [card_id],
        "card": {"claim": "Policy is final", "fact_key": "policy.mode", "fact_value": "final"},
        "reason": "human review selected final",
        "resolution_basis": "manual_adjudication",
    }
    with pytest.raises(ConflictResolutionRequired, match="requires exactly"):
        memory.apply_transition(
            "UPDATE",
            resolution_metadata={"adjudicator_id": "reviewer"},
            **request,
        )

    memory.apply_transition(
        "UPDATE",
        resolution_metadata={
            "adjudicator_id": "reviewer-7",
            "decision_id": "decision-42",
            "decided_at": "2026-09-01T10:30:00+08:00",
        },
        **request,
    )
    event = memory.snapshot().events[-1]
    assert event.resolution_basis == "manual_adjudication"


def test_free_text_change_is_unknown_not_fake_semantic_conflict(tmp_path):
    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    created = _create(memory, _entry("e1"))
    card_id = memory.snapshot().versions_by_id[created.version_ids[0]].card_id
    memory.apply_transition(
        "UPDATE",
        topic="topic",
        entries=[_entry("e2", domain="other.example")],
        source_ids=["e2"],
        target_card_ids=[card_id],
        card={"claim": "a completely different sentence"},
        reason="new evidence refines the wording",
    )
    assert memory.snapshot().events[-1].conflict.state == "unknown"


def test_corrupt_card_store_fails_explicitly_without_overwrite(tmp_path):
    path = tmp_path / "cards.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(CardStoreError, match="Cannot read card store"):
        CardStore(path)

    assert path.read_text(encoding="utf-8") == "{not-json"


def test_card_store_replace_failure_is_explicit_and_preserves_previous_file(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "cards.json"
    store = CardStore(path)
    store.save(KnowledgeCard(card_id="stable", title="Stable", claim="old"))
    before = path.read_text(encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("sheaf_cards.base.os.replace", fail_replace)
    with pytest.raises(CardStoreError, match="Cannot write card store"):
        store.save(KnowledgeCard(card_id="new", title="New", claim="new"))

    assert path.read_text(encoding="utf-8") == before
    assert list(tmp_path.glob(".cards.json.*.tmp")) == []


def test_corrupt_ledger_fails_explicitly_without_reinitializing(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(LedgerCorruptionError, match="Cannot read evidence ledger"):
        EvidenceGovernedMemory(path)

    assert path.read_text(encoding="utf-8") == "{not-json"


def test_semantically_broken_graph_is_detected_on_reopen(tmp_path):
    path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(path)
    _create(memory, _entry("e1"))
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["events"][0]["output_version_ids"] = ["forged-version"]
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(LedgerCorruptionError, match="invalid output version"):
        EvidenceGovernedMemory(path)


def test_card_store_concurrent_saves_do_not_lose_updates(tmp_path):
    path = tmp_path / "cards.json"
    stores = [CardStore(path) for _ in range(24)]

    def save_one(index: int) -> None:
        stores[index].save(
            KnowledgeCard(card_id=f"card-{index}", title=f"T{index}", claim=f"C{index}")
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(save_one, range(len(stores))))

    assert CardStore(path).count() == len(stores)
    assert json.loads(path.read_text(encoding="utf-8"))


def test_ledger_concurrent_transitions_do_not_lose_events(tmp_path):
    path = tmp_path / "ledger.json"
    memories = [EvidenceGovernedMemory(path) for _ in range(16)]

    def create_one(index: int) -> None:
        _create(memories[index], _entry(f"e{index}", domain=f"source-{index}.example"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(create_one, range(len(memories))))

    snapshot = EvidenceGovernedMemory(path).snapshot()
    assert len(snapshot.events) == len(memories)
    assert len(snapshot.versions) == len(memories)
    assert len(snapshot.processed_evidence) == len(memories)
    assert len(snapshot.active_heads) == len(memories)


def test_card_store_cross_process_writers_do_not_lose_updates(tmp_path):
    path = tmp_path / "cards.json"
    CardStore(path)
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    processes = [
        context.Process(
            target=_save_cards_in_process,
            args=(str(path), f"worker-{worker}", 5, start_event),
        )
        for worker in range(3)
    ]
    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0

    assert CardStore(path).count() == 15
