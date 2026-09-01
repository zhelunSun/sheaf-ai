from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from sheaf_ai.provenance_registry import (
    AdminActor,
    AuthorityScope,
    CorrectionGrant,
    EvidenceSubject,
    IdempotencyConflictError,
    ProvenanceGrants,
    RegistryCorruptionError,
    RegistryValidationError,
    admin_issue_attestation,
    admin_revoke_attestation,
    admin_supersede_attestation,
    load_registry,
    resolve_provenance,
)


OLD_DIGEST = "sha256:" + "1" * 64
NEW_DIGEST = "sha256:" + "2" * 64
AUTHORITY_DIGEST = "sha256:" + "a" * 64


def _authority_subject() -> EvidenceSubject:
    return EvidenceSubject(
        entry_id="authority-entry",
        canonical_origin="https://authority.example",
        evidence_digest=AUTHORITY_DIGEST,
    )


def _old_subject() -> EvidenceSubject:
    return EvidenceSubject(
        entry_id="old-entry",
        canonical_origin="https://source.example",
        evidence_digest=OLD_DIGEST,
    )


def _new_subject() -> EvidenceSubject:
    return EvidenceSubject(
        entry_id="new-entry",
        canonical_origin="https://source.example",
        evidence_digest=NEW_DIGEST,
    )


def _actor() -> AdminActor:
    return AdminActor(actor_id="local-admin")


def _authority_grants() -> ProvenanceGrants:
    old = _old_subject()
    return ProvenanceGrants(
        evidence_tier="A",
        is_primary=True,
        independent_observation=True,
        authority_scopes=(AuthorityScope(topic="release", fact_key="release.status"),),
        corrections=(
            CorrectionGrant(
                topic="release",
                fact_key="release.status",
                corrected_entry_id=old.entry_id,
                corrected_canonical_origin=old.canonical_origin,
                corrected_evidence_digest=old.evidence_digest,
            ),
        ),
    )


def test_issue_replay_and_exact_correction_binding(tmp_path):
    registry_path = tmp_path / "provenance.json"
    event = admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=_authority_subject(),
        grants=_authority_grants(),
        actor=_actor(),
        reason="verified official release authority",
        idempotency_key="issue-authority",
        attestation_id="release-authority",
    )

    assert event.action == "ISSUE"
    assert event.revision == 1
    assert event.attestation_version == 1
    assert event.previous_event_hash == ""
    assert event.event_hash.startswith("sha256:")

    resolution = resolve_provenance(registry_path, subject=_authority_subject())
    assert resolution.status == "verified"
    assert resolution.registry_id == "test-registry"
    assert resolution.registry_revision == 1
    assert resolution.evidence_tier == "A"
    assert resolution.is_primary is True
    assert resolution.independent_observation is True
    assert resolution.authorizes_authority(topic="release", fact_key="release.status")
    assert resolution.authorizes_correction(
        topic="release", fact_key="release.status", corrected_subject=_old_subject()
    )
    assert resolution.authorizes_official_correction(
        topic="release", fact_key="release.status", corrected_subject=_old_subject()
    )
    assert not resolution.authorizes_correction(
        topic="release", fact_key="release.status", corrected_subject=_new_subject()
    )

    replayed = load_registry(registry_path)
    assert replayed.revision == 1
    assert replayed.events == (event,)


@pytest.mark.parametrize("value", [1, 0, "true", "false", None])
def test_grant_booleans_are_strict(value):
    with pytest.raises(RegistryValidationError):
        ProvenanceGrants(is_primary=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [True, 1, None, "a", "T1", ""])
def test_evidence_tier_is_strict(value):
    with pytest.raises(RegistryValidationError):
        ProvenanceGrants(evidence_tier=value)  # type: ignore[arg-type]


def test_missing_corrupt_and_binding_mismatch_fail_closed(tmp_path):
    registry_path = tmp_path / "provenance.json"

    missing = resolve_provenance(registry_path, subject=_authority_subject())
    assert missing.status == "missing_registry"
    assert missing.evidence_tier == "U"
    assert not missing.has_governance_grant

    admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=_authority_subject(),
        grants=_authority_grants(),
        actor=_actor(),
        reason="verified official release authority",
        idempotency_key="issue-authority",
    )

    wrong_digest = EvidenceSubject(
        entry_id="authority-entry",
        canonical_origin="https://authority.example",
        evidence_digest="sha256:" + "b" * 64,
    )
    assert resolve_provenance(registry_path, subject=wrong_digest).status == "unverified"

    wrong_origin = EvidenceSubject(
        entry_id="authority-entry",
        canonical_origin="https://other.example",
        evidence_digest=AUTHORITY_DIGEST,
    )
    assert resolve_provenance(registry_path, subject=wrong_origin).status == "unverified"

    document = json.loads(registry_path.read_text(encoding="utf-8"))
    document["events"][0]["grants"]["is_primary"] = False
    registry_path.write_text(json.dumps(document), encoding="utf-8")

    corrupt = resolve_provenance(registry_path, subject=_authority_subject())
    assert corrupt.status == "corrupt_registry"
    assert corrupt.evidence_tier == "U"
    assert not corrupt.has_governance_grant
    with pytest.raises(RegistryCorruptionError):
        admin_revoke_attestation(
            registry_path,
            attestation_id=document["events"][0]["attestation_id"],
            actor=_actor(),
            reason="must not overwrite a corrupt registry",
            idempotency_key="revoke-corrupt",
        )


def test_registry_identity_is_covered_by_each_event_hash(tmp_path):
    registry_path = tmp_path / "provenance.json"
    admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=_authority_subject(),
        grants=_authority_grants(),
        actor=_actor(),
        reason="verified official release authority",
        idempotency_key="issue-authority",
    )
    document = json.loads(registry_path.read_text(encoding="utf-8"))
    document["registry_id"] = "replacement-registry"
    registry_path.write_text(json.dumps(document), encoding="utf-8")

    assert resolve_provenance(registry_path, subject=_authority_subject()).status == (
        "corrupt_registry"
    )


def test_malformed_json_and_string_boolean_fail_closed(tmp_path):
    registry_path = tmp_path / "provenance.json"
    registry_path.write_text("{not-json", encoding="utf-8")
    assert resolve_provenance(registry_path, subject=_authority_subject()).status == (
        "corrupt_registry"
    )

    registry_path.unlink()
    admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=_authority_subject(),
        grants=_authority_grants(),
        actor=_actor(),
        reason="verified official release authority",
        idempotency_key="issue-authority",
    )
    document = json.loads(registry_path.read_text(encoding="utf-8"))
    document["events"][0]["grants"]["is_primary"] = "false"
    registry_path.write_text(json.dumps(document), encoding="utf-8")
    resolution = resolve_provenance(registry_path, subject=_authority_subject())
    assert resolution.status == "corrupt_registry"
    assert resolution.evidence_tier == "U"
    assert resolution.is_primary is False


def test_correction_relation_without_primary_is_not_official_authority(tmp_path):
    registry_path = tmp_path / "provenance.json"
    grants = _authority_grants()
    admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=_authority_subject(),
        grants=ProvenanceGrants(
            authority_scopes=grants.authority_scopes,
            corrections=grants.corrections,
        ),
        actor=_actor(),
        reason="relation known but primary status not established",
        idempotency_key="issue-limited-authority",
    )

    resolution = resolve_provenance(registry_path, subject=_authority_subject())
    assert resolution.authorizes_correction(
        topic="release", fact_key="release.status", corrected_subject=_old_subject()
    )
    assert not resolution.authorizes_official_correction(
        topic="release", fact_key="release.status", corrected_subject=_old_subject()
    )


def test_separate_attestations_cannot_compose_official_correction(tmp_path):
    registry_path = tmp_path / "provenance.json"
    full = _authority_grants()
    admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=_authority_subject(),
        grants=ProvenanceGrants(is_primary=True),
        actor=_actor(),
        reason="primary status only",
        idempotency_key="primary-only",
        attestation_id="primary-only",
    )
    admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=_authority_subject(),
        grants=ProvenanceGrants(
            authority_scopes=full.authority_scopes,
            corrections=full.corrections,
        ),
        actor=_actor(),
        reason="correction relation only",
        idempotency_key="correction-only",
        attestation_id="correction-only",
    )

    resolution = resolve_provenance(registry_path, subject=_authority_subject())
    assert resolution.is_primary is True
    assert resolution.authorizes_correction(
        topic="release", fact_key="release.status", corrected_subject=_old_subject()
    )
    assert not resolution.authorizes_official_correction(
        topic="release", fact_key="release.status", corrected_subject=_old_subject()
    )


def test_conflicting_active_tiers_fail_closed_instead_of_guessing(tmp_path):
    registry_path = tmp_path / "provenance.json"
    subject = _authority_subject()
    admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=subject,
        grants=ProvenanceGrants(evidence_tier="A", is_primary=True),
        actor=_actor(),
        reason="first source review",
        idempotency_key="tier-a",
        attestation_id="tier-a",
    )
    admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=subject,
        grants=ProvenanceGrants(evidence_tier="B", independent_observation=True),
        actor=_actor(),
        reason="conflicting second source review",
        idempotency_key="tier-b",
        attestation_id="tier-b",
    )

    resolution = resolve_provenance(registry_path, subject=subject)
    assert resolution.status == "conflicting_attestations"
    assert resolution.evidence_tier == "U"
    assert resolution.is_primary is False
    assert resolution.independent_observation is False
    assert not resolution.has_governance_grant


def test_unset_tier_does_not_conflict_with_one_explicit_verified_tier(tmp_path):
    registry_path = tmp_path / "provenance.json"
    subject = _authority_subject()
    admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=subject,
        grants=ProvenanceGrants(evidence_tier="B"),
        actor=_actor(),
        reason="explicit evidence tier review",
        idempotency_key="tier-b",
        attestation_id="tier-b",
    )
    admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=subject,
        grants=ProvenanceGrants(independent_observation=True),
        actor=_actor(),
        reason="independence review without a tier grant",
        idempotency_key="independence",
        attestation_id="independence",
    )

    resolution = resolve_provenance(registry_path, subject=subject)
    assert resolution.status == "verified"
    assert resolution.evidence_tier == "B"
    assert resolution.independent_observation is True


def test_supersede_and_revoke_are_versioned_and_fail_closed(tmp_path):
    registry_path = tmp_path / "provenance.json"
    issued = admin_issue_attestation(
        registry_path,
        registry_id="test-registry",
        subject=_authority_subject(),
        grants=_authority_grants(),
        actor=_actor(),
        reason="initial verification",
        idempotency_key="issue",
        attestation_id="authority",
    )
    superseded = admin_supersede_attestation(
        registry_path,
        attestation_id=issued.attestation_id,
        subject=_new_subject(),
        grants=ProvenanceGrants(is_primary=True),
        actor=_actor(),
        reason="authority moved to a new source record",
        idempotency_key="supersede",
    )

    assert superseded.action == "SUPERSEDE"
    assert superseded.attestation_version == 2
    assert superseded.target_event_hash == issued.event_hash
    old = resolve_provenance(registry_path, subject=_authority_subject())
    assert old.status == "superseded"
    assert not old.has_governance_grant
    current = resolve_provenance(registry_path, subject=_new_subject())
    assert current.status == "verified"
    assert current.is_primary

    revoked = admin_revoke_attestation(
        registry_path,
        attestation_id=issued.attestation_id,
        actor=_actor(),
        reason="source authority withdrawn",
        idempotency_key="revoke",
    )
    assert revoked.action == "REVOKE"
    assert revoked.attestation_version == 3
    assert revoked.target_event_hash == superseded.event_hash
    after_revoke = resolve_provenance(registry_path, subject=_new_subject())
    assert after_revoke.status == "revoked"
    assert after_revoke.evidence_tier == "U"
    assert not after_revoke.has_governance_grant


def test_exact_retry_is_idempotent_and_conflicting_retry_is_rejected(tmp_path):
    registry_path = tmp_path / "provenance.json"
    kwargs = dict(
        registry_path=registry_path,
        registry_id="test-registry",
        subject=_authority_subject(),
        grants=_authority_grants(),
        actor=_actor(),
        reason="verified",
        idempotency_key="stable-request",
        attestation_id="authority",
    )
    first = admin_issue_attestation(**kwargs)
    retry = admin_issue_attestation(**kwargs)
    assert retry == first
    assert load_registry(registry_path).revision == 1

    with pytest.raises(IdempotencyConflictError):
        admin_issue_attestation(**{**kwargs, "reason": "different request"})


def test_concurrent_admin_writers_keep_a_complete_hash_chain(tmp_path):
    registry_path = tmp_path / "provenance.json"

    def issue(index: int):
        return admin_issue_attestation(
            registry_path,
            registry_id="test-registry",
            subject=EvidenceSubject(
                entry_id=f"entry-{index}",
                canonical_origin=f"https://source-{index}.example",
                evidence_digest="sha256:" + f"{index:064x}",
            ),
            grants=ProvenanceGrants(independent_observation=True),
            actor=_actor(),
            reason=f"verify source {index}",
            idempotency_key=f"issue-{index}",
            attestation_id=f"attestation-{index}",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        events = list(executor.map(issue, range(20)))

    assert len({event.event_hash for event in events}) == 20
    registry = load_registry(registry_path)
    assert registry.revision == 20
    assert [event.revision for event in registry.events] == list(range(1, 21))
    for previous, current in zip(registry.events, registry.events[1:]):
        assert current.previous_event_hash == previous.event_hash
