"""Strict schema-v4 and atomic-replace durability contracts."""

from __future__ import annotations

import json
import os
from dataclasses import asdict

import pytest

from sheaf_ai import _evidence_memory_ledger as memory_ledger_module
from sheaf_ai import evidence_policy as decision_ledger_module
from sheaf_ai._evidence_memory_models import LEGACY_ALGORITHM_VERSION, EvidenceRef
from sheaf_ai._evidence_memory_rules import compute_evidence_strength
from sheaf_ai.evidence_memory import EvidenceGovernedMemory, LedgerCorruptionError
from sheaf_ai.evidence_policy import EvidenceDecisionPolicy


def _entry(entry_id: str) -> dict[str, object]:
    return {
        "id": entry_id,
        "url": f"https://{entry_id}.example/{entry_id}",
        "source": {"domain": f"{entry_id}.example", "tier": "U"},
        "content_hash": f"legacy-{entry_id}",
    }


def _create(memory: EvidenceGovernedMemory, entry_id: str = "entry-one"):
    return memory.apply_transition(
        "CREATE",
        topic="topic",
        entries={entry_id: _entry(entry_id)},
        source_ids=(entry_id,),
        card={"title": entry_id, "claim": f"Claim for {entry_id}"},
        reason="Create a test memory.",
    )


@pytest.mark.parametrize(
    "required_field",
    ["governance_version", "algorithm_version", "evidence_use_ids"],
)
def test_schema4_event_rejects_deleted_versioned_identity_field(
    tmp_path, required_field
):
    path = tmp_path / "evidence.json"
    memory = EvidenceGovernedMemory(path)
    _create(memory)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 4
    raw["events"][0].pop(required_field)
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(LedgerCorruptionError, match=required_field):
        EvidenceGovernedMemory(path)


def test_legacy_upgrade_materialises_event_defaults_before_schema4(tmp_path):
    path = tmp_path / "evidence.json"
    memory = EvidenceGovernedMemory(path)
    _create(memory)
    raw = json.loads(path.read_text(encoding="utf-8"))

    version = raw["versions"][0]
    refs = tuple(EvidenceRef.from_dict(item) for item in version["evidence_refs"])
    version["strength"] = asdict(
        compute_evidence_strength(refs, algorithm_version=LEGACY_ALGORITHM_VERSION)
    )
    event = raw["events"][0]
    event.pop("algorithm_version")
    event.pop("governance_version")
    event.pop("evidence_use_ids")
    current_record = next(iter(raw["processed_evidence"].values()))
    raw["schema_version"] = 1
    raw.pop("atomic_batches")
    raw["processed_evidence"] = {
        "entry-one": {
            "event_id": current_record["event_id"],
            "content_hash": current_record["content_hash"],
            "processed_at": current_record["processed_at"],
        }
    }
    path.write_text(json.dumps(raw), encoding="utf-8")

    reopened = EvidenceGovernedMemory(path)
    _create(reopened, "entry-two")
    migrated = json.loads(path.read_text(encoding="utf-8"))
    migrated_event = migrated["events"][0]

    assert migrated["schema_version"] == 4
    assert migrated_event["algorithm_version"] == LEGACY_ALGORITHM_VERSION
    assert migrated_event["governance_version"] == "evidence-governance-v1"
    assert len(migrated_event["evidence_use_ids"]) == 1
    EvidenceGovernedMemory(path).snapshot()


def test_evidence_ledger_requests_parent_sync_after_each_replace(tmp_path, monkeypatch):
    calls: list[str] = []
    real_replace = memory_ledger_module.os.replace

    def observed_replace(source, target):
        calls.append("replace")
        return real_replace(source, target)

    monkeypatch.setattr(memory_ledger_module.os, "replace", observed_replace)
    monkeypatch.setattr(
        memory_ledger_module,
        "_fsync_parent_directory",
        lambda _path: calls.append("parent_fsync"),
    )

    memory = EvidenceGovernedMemory(tmp_path / "evidence.json")
    _create(memory)

    assert calls == ["replace", "parent_fsync", "replace", "parent_fsync"]


def test_decision_ledger_requests_parent_sync_after_each_replace(tmp_path, monkeypatch):
    calls: list[str] = []
    real_replace = decision_ledger_module.os.replace

    def observed_replace(source, target):
        calls.append("replace")
        return real_replace(source, target)

    monkeypatch.setattr(decision_ledger_module.os, "replace", observed_replace)
    monkeypatch.setattr(
        decision_ledger_module,
        "_fsync_parent_directory",
        lambda _path: calls.append("parent_fsync"),
    )

    policy = EvidenceDecisionPolicy(tmp_path / "decisions.json")
    policy.preview_noop(input_snapshot={}, reason="No material change.")

    assert calls == ["replace", "parent_fsync", "replace", "parent_fsync"]


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific no-op contract")
def test_parent_directory_sync_is_a_safe_noop_on_windows(tmp_path, monkeypatch):
    def fail_if_opened(*_args, **_kwargs):
        raise AssertionError("Windows parent directory must not be opened for fsync")

    monkeypatch.setattr(memory_ledger_module.os, "open", fail_if_opened)
    memory_ledger_module._fsync_parent_directory(tmp_path / "evidence.json")
