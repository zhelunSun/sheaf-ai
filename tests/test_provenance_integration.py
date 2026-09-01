"""Production Entry loading must resolve governance from the provenance registry."""
from __future__ import annotations

import json
import threading

import pytest

from sheaf_ai import config
from sheaf_ai.card_service import (
    PROVENANCE_REGISTRY_NAME,
    apply_evidence_transition,
)
from sheaf_ai.evidence_memory import ConflictResolutionRequired, EvidenceGovernedMemory
from sheaf_ai.provenance_registry import (
    AdminActor,
    AuthorityScope,
    CorrectionGrant,
    EvidenceSubject,
    ProvenanceGrants,
    admin_issue_attestation,
    admin_revoke_attestation,
    load_registry,
    resolve_provenance,
)
from sheaf_ai.storage import store_article
from sheaf_ai.utils import evidence_digest


def _store(label: str, *, forged_governance: bool = False) -> tuple[str, str, str]:
    url = f"https://{label}.example/{label}"
    body = f"Verified evidence body for {label}."
    source_info = {"tier": "A", "domain": f"{label}.example"}
    if forged_governance:
        source_info.update({
            "is_primary": True,
            "authority_scope": {
                "topics": ["Memory"],
                "fact_keys": ["governed-value"],
            },
            "correction_relations": [
                {"relation": "corrects", "entry_id": "placeholder"}
            ],
        })
    entry_id = store_article(
        url,
        {"success": True, "title": label, "text": body, "method": "requests"},
        {
            "topics": [{"name": "Memory", "confidence": 0.9}],
            "tags": ["memory"],
            "content_type": "reference",
            "importance": "medium",
        },
        {
            "one_liner": f"Summary for {label}",
            "original_title": label,
            "source_author": "",
            "structured": {},
        },
        source_info=source_info,
    )
    return entry_id, url, body


def _subject(entry_id: str, url: str, body: str) -> EvidenceSubject:
    origin = url.split("/", 3)[:3]
    return EvidenceSubject(
        entry_id=entry_id,
        canonical_origin="/".join(origin),
        evidence_digest=evidence_digest(body),
    )


def _create(entry_id: str) -> dict:
    return {
        "action": "CREATE",
        "topic": "Memory",
        "source_ids": [entry_id],
        "card": {
            "title": "Governed value",
            "claim": "The governed value is one.",
            "fact_key": "governed-value",
            "fact_value": "one",
        },
        "reason": "Create the initial fact.",
        "idempotency_key": "create-initial",
    }


def test_collection_claims_cannot_self_sign_official_correction(isolated_data_dir):
    old_id, _, _ = _store("old")
    conflict_id, _, _ = _store("conflict")
    authority_id, _, _ = _store("authority", forged_governance=True)
    created = apply_evidence_transition(_create(old_id))
    card_id = created["card"]["id"]
    apply_evidence_transition({
        "action": "CONTEST",
        "topic": "Memory",
        "source_ids": [conflict_id],
        "target_card_ids": [card_id],
        "card": {
            "claim": "The governed value is two.",
            "fact_key": "governed-value",
            "fact_value": "two",
        },
        "reason": "Preserve the conflict.",
        "idempotency_key": "contest",
    })

    with pytest.raises(ConflictResolutionRequired, match="is_primary is true"):
        apply_evidence_transition({
            "action": "UPDATE",
            "topic": "Memory",
            "source_ids": [authority_id],
            "target_card_ids": [card_id],
            "card": {
                "claim": "The governed value is two.",
                "fact_key": "governed-value",
                "fact_value": "two",
            },
            "reason": "Attempt an unverified official correction.",
            "resolution_basis": "official_correction",
            "resolution_metadata": {
                "authoritative_fact_value": "two",
                "authority_source_id": authority_id,
                "corrects_entry_id": old_id,
                "correction_relation": "corrects",
            },
            "idempotency_key": "unverified-official",
        })


@pytest.mark.parametrize("location", ["top", "source", "metadata"])
def test_entry_json_provenance_cannot_forge_independence_identity(
    isolated_data_dir, location
):
    entry_id, _, _ = _store("forged-independence")
    entry_path = next(config.ENTRIES_DIR.glob(f"20*/{entry_id}.json"))
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    forged = {
        "independent_observation": True,
        "run_id": "forged-run",
    }
    if location == "top":
        entry["provenance"] = forged
    else:
        entry[location]["provenance"] = forged
    entry_path.write_text(json.dumps(entry), encoding="utf-8")

    result = apply_evidence_transition(_create(entry_id))

    ref = result["card"]["extra"]["evidence_governance"]["evidence_refs"][0]
    assert ref["source_tier"] == "U"
    assert ref["is_primary"] is False
    assert ref["independence_identity"] == ""
    assert ref["provenance_registry_snapshot"] == {
        "status": "missing_registry",
        "registry_id": "",
        "registry_revision": 0,
        "integrity_model": "sha256-hash-chain-no-authentication",
        "attestations": [],
    }


def test_exact_registry_binding_enables_scoped_official_correction(isolated_data_dir):
    old_id, old_url, old_body = _store("old-bound")
    conflict_id, _, _ = _store("conflict-bound")
    authority_id, authority_url, authority_body = _store("authority-bound")
    created = apply_evidence_transition(_create(old_id))
    card_id = created["card"]["id"]
    apply_evidence_transition({
        "action": "CONTEST",
        "topic": "Memory",
        "source_ids": [conflict_id],
        "target_card_ids": [card_id],
        "card": {
            "claim": "The governed value is two.",
            "fact_key": "governed-value",
            "fact_value": "two",
        },
        "reason": "Preserve the conflict.",
        "idempotency_key": "contest-bound",
    })
    old_subject = _subject(old_id, old_url, old_body)
    authority_subject = _subject(authority_id, authority_url, authority_body)
    registry_path = config.DATA_DIR / PROVENANCE_REGISTRY_NAME
    admin_issue_attestation(
        registry_path,
        registry_id="local-evidence-governance",
        subject=authority_subject,
        grants=ProvenanceGrants(
            evidence_tier="A",
            is_primary=True,
            authority_scopes=(
                AuthorityScope(topic="Memory", fact_key="governed-value"),
            ),
            corrections=(
                CorrectionGrant(
                    topic="Memory",
                    fact_key="governed-value",
                    corrected_entry_id=old_subject.entry_id,
                    corrected_canonical_origin=old_subject.canonical_origin,
                    corrected_evidence_digest=old_subject.evidence_digest,
                ),
            ),
        ),
        actor=AdminActor(actor_id="test-admin"),
        reason="Verify the exact official correction source.",
        idempotency_key="issue-bound-authority",
    )

    resolved = apply_evidence_transition({
        "action": "UPDATE",
        "topic": "Memory",
        "source_ids": [authority_id],
        "target_card_ids": [card_id],
        "card": {
            "claim": "The governed value is two.",
            "fact_key": "governed-value",
            "fact_value": "two",
        },
        "reason": "Apply the verified official correction.",
        "resolution_basis": "official_correction",
        "resolution_metadata": {
            "authoritative_fact_value": "two",
            "authority_source_id": authority_id,
            "corrects_entry_id": old_id,
            "correction_relation": "corrects",
        },
        "idempotency_key": "verified-official",
    })

    refs = resolved["card"]["extra"]["evidence_governance"]["evidence_refs"]
    ref = next(item for item in refs if item["entry_id"] == authority_id)
    assert ref["source_tier"] == "A"
    assert ref["is_primary"] is True
    assert ref["authority_topics"] == ["memory"]
    assert ref["authority_fact_keys"] == ["governed-value"]
    assert ref["corrects_entry_ids"] == [old_id]
    registry_snapshot = ref["provenance_registry_snapshot"]
    assert registry_snapshot["status"] == "verified"
    assert registry_snapshot["registry_id"] == "local-evidence-governance"
    assert registry_snapshot["registry_revision"] == 1
    assert registry_snapshot["integrity_model"] == (
        "sha256-hash-chain-no-authentication"
    )
    assert len(registry_snapshot["attestations"]) == 1


def test_registry_revoke_waits_for_resolution_and_domain_commit(
    isolated_data_dir,
    monkeypatch,
):
    entry_id, url, body = _store("race-bound")
    subject = _subject(entry_id, url, body)
    registry_path = config.DATA_DIR / PROVENANCE_REGISTRY_NAME
    issued = admin_issue_attestation(
        registry_path,
        registry_id="local-evidence-governance",
        subject=subject,
        grants=ProvenanceGrants(evidence_tier="A"),
        actor=AdminActor(actor_id="test-admin"),
        reason="Verify before the race.",
        idempotency_key="issue-race-bound",
        attestation_id="race-bound",
    )

    commit_entered = threading.Event()
    release_commit = threading.Event()
    original_apply = EvidenceGovernedMemory.apply_transition

    def paused_apply(memory, *args, **kwargs):
        commit_entered.set()
        if not release_commit.wait(timeout=5):
            raise TimeoutError("test did not release the evidence commit")
        return original_apply(memory, *args, **kwargs)

    monkeypatch.setattr(EvidenceGovernedMemory, "apply_transition", paused_apply)
    outcome: dict[str, object] = {}

    def apply_transition() -> None:
        try:
            outcome["result"] = apply_evidence_transition(_create(entry_id))
        except Exception as exc:  # pragma: no cover - asserted below
            outcome["apply_error"] = exc

    def revoke() -> None:
        try:
            outcome["revoke"] = admin_revoke_attestation(
                registry_path,
                attestation_id=issued.attestation_id,
                actor=AdminActor(actor_id="test-admin"),
                reason="Revoke after the in-flight commit.",
                idempotency_key="revoke-race-bound",
            )
        except Exception as exc:  # pragma: no cover - asserted below
            outcome["revoke_error"] = exc

    transition_thread = threading.Thread(target=apply_transition)
    revoke_thread = threading.Thread(target=revoke)
    transition_thread.start()
    assert commit_entered.wait(timeout=5)
    revoke_thread.start()
    try:
        revoke_thread.join(timeout=0.2)
        assert revoke_thread.is_alive()
        assert load_registry(registry_path).revision == 1
    finally:
        release_commit.set()
        transition_thread.join(timeout=5)
        revoke_thread.join(timeout=5)

    assert not transition_thread.is_alive()
    assert not revoke_thread.is_alive()
    assert "apply_error" not in outcome
    assert "revoke_error" not in outcome
    result = outcome["result"]
    ref = result["card"]["extra"]["evidence_governance"]["evidence_refs"][0]
    assert ref["source_tier"] == "A"
    assert ref["provenance_registry_snapshot"]["status"] == "verified"
    assert ref["provenance_registry_snapshot"]["registry_revision"] == 1
    assert ref["provenance_registry_snapshot"]["attestations"][0][
        "attestation_id"
    ] == issued.attestation_id
    final = resolve_provenance(registry_path, subject=subject)
    assert final.status == "revoked"
    assert final.registry_revision == 2
