"""Evidence-governed, event-sourced knowledge memory core.

This module is deliberately independent of the public ``KnowledgeCard`` JSON
contract.  It records immutable versions and transitions in a private ledger;
an application service may later project an active version into a public card.

The rule score exposed here is an *evidence-strength heuristic*, not a
calibrated probability.  Its inputs and arithmetic are persisted so a caller
can explain and recompute every result.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence


from sheaf_ai._evidence_memory_models import (
    ALGORITHM_VERSION,
    DIGEST_ALGORITHM_VERSION,
    GOVERNANCE_VERSION,
    VALID_ACTIONS,
    VALID_RESOLUTION_BASES,
    CardVersion,
    ConflictAssessment,
    ConflictResolutionRequired,
    ContestedClaim,
    EvidenceAlreadyProcessedError,
    EvidenceMemoryError,
    EvidenceLocator,
    EvidenceDuplicateRelation,
    EvidenceRef,
    EvidenceStrength,
    EvidenceValidationError,
    LedgerCorruptionError,
    MemorySnapshot,
    TransitionEvent,
    TransitionResult,
    TransitionValidationError,
    claim_identity_for_version,
    evidence_use_identity,
    locator_identity,
)
from sheaf_ai._evidence_memory_rules import (
    _canonical_hash,
    _dedupe_strings,
    _normalise_resolution_metadata,
    _normalise_text,
    allowlisted_evidence,
    assess_structured_conflict,
    assess_transition_conflict,
    compute_evidence_strength,
    merge_evidence_refs,
    validate_resolution_basis,
)

__all__ = [
    "ALGORITHM_VERSION",
    "DIGEST_ALGORITHM_VERSION",
    "VALID_ACTIONS",
    "VALID_RESOLUTION_BASES",
    "CardVersion",
    "ConflictAssessment",
    "ConflictResolutionRequired",
    "ContestedClaim",
    "GOVERNANCE_VERSION",
    "EvidenceAlreadyProcessedError",
    "EvidenceGovernedMemory",
    "EvidenceLedger",
    "EvidenceMemoryError",
    "EvidenceLocator",
    "EvidenceDuplicateRelation",
    "EvidenceRef",
    "EvidenceStrength",
    "EvidenceValidationError",
    "LedgerCorruptionError",
    "MemorySnapshot",
    "TransitionEvent",
    "TransitionResult",
    "TransitionValidationError",
    "allowlisted_evidence",
    "assess_structured_conflict",
    "compute_evidence_strength",
]


from sheaf_ai._evidence_memory_ledger import (
    EvidenceLedger,
    _decode_and_replay,
    _exclusive_file_lock,
    _now_iso,
    _upgrade_ledger_state,
    _validate_new_entry_identities,
)


class EvidenceGovernedMemory:
    """Apply validated lifecycle and dispute transitions to a ledger."""

    _CARD_FIELDS = frozenset(
        {"title", "claim", "evidence", "tags", "fact_key", "fact_value", "source_ids"}
    )

    def __init__(self, ledger_path: Path):
        self.ledger = EvidenceLedger(ledger_path)

    def snapshot(self) -> MemorySnapshot:
        return self.ledger.snapshot()

    def apply_transition(
        self,
        action: str,
        *,
        topic: str,
        entries: Sequence[Mapping[str, object]] | Mapping[str, Mapping[str, object]],
        source_ids: Sequence[object] | None = None,
        evidence_locators: Mapping[str, Mapping[str, object]] | None = None,
        card: Mapping[str, object] | None = None,
        target_card_ids: Sequence[object] = (),
        reason: str,
        resolution_basis: str = "",
        resolution_metadata: Mapping[str, object] | None = None,
        idempotency_key: str = "",
    ) -> TransitionResult:
        action = str(action).upper().strip()
        topic = str(topic).strip()
        reason = str(reason).strip()
        payload = dict(card or {})
        unknown_fields = set(payload) - self._CARD_FIELDS
        if unknown_fields:
            raise TransitionValidationError(
                "Unsupported card fields: " + ", ".join(sorted(unknown_fields))
            )
        if action not in VALID_ACTIONS:
            raise TransitionValidationError(f"Unsupported transition action: {action!r}")
        if not topic:
            raise TransitionValidationError("Transition topic is required")
        if not reason:
            raise TransitionValidationError("Transition reason is required for auditability")

        payload_source_ids = payload.pop("source_ids", None)
        if source_ids is None:
            source_ids = payload_source_ids or ()
        elif payload_source_ids is not None:
            if _dedupe_strings(source_ids) != _dedupe_strings(payload_source_ids):
                raise EvidenceValidationError("Card source_ids disagree with transition source_ids")
        refs = allowlisted_evidence(entries, source_ids, evidence_locators)
        targets = tuple(sorted(_dedupe_strings(target_card_ids)))
        basis = str(resolution_basis).strip()
        resolution = _normalise_resolution_metadata(resolution_metadata)
        self._validate_shape(action, targets, payload, refs)

        request_document = {
            "action": action,
            "topic": topic,
            "target_card_ids": targets,
            "card": payload,
            "evidence_refs": [asdict(ref) for ref in refs],
            "reason": reason,
            "resolution_basis": basis,
            "resolution_metadata": resolution,
        }
        request_hash = _canonical_hash(request_document)
        key = idempotency_key.strip() or f"auto:{request_hash}"

        with self.ledger._lock:
            with _exclusive_file_lock(self.ledger._lock_path):
                raw = self.ledger._read_unlocked()
                snapshot = _decode_and_replay(raw)
                prior = next(
                    (event for event in snapshot.events if event.idempotency_key == key),
                    None,
                )
                if prior:
                    if prior.request_hash != request_hash:
                        raise TransitionValidationError(
                            f"Idempotency key {key!r} was reused for a different request"
                        )
                    return TransitionResult(
                        applied=False,
                        event_id=prior.event_id,
                        action=prior.action,
                        version_ids=prior.output_version_ids,
                        idempotency_key=key,
                    )

                _validate_new_entry_identities(snapshot, refs)
                parents = self._resolve_parents(snapshot, action, targets)
                if any(parent.topic != topic for parent in parents):
                    raise TransitionValidationError(
                        "Transition topic must match every target card topic"
                    )
                if action == "MERGE" and any(parent.state == "contested" for parent in parents):
                    raise TransitionValidationError(
                        "Contested cards must be resolved or retired before MERGE"
                    )
                if action == "CONTEST" and parents[0].state != "active":
                    raise TransitionValidationError(
                        "A contested card must be resolved before another CONTEST"
                    )
                if action == "UPDATE" and not refs and parents[0].state != "contested":
                    raise EvidenceValidationError(
                        "UPDATE requires new evidence unless it resolves a contested version"
                    )
                effective_fact_key = str(payload.get("fact_key", ""))
                effective_fact_value = str(payload.get("fact_value", ""))
                if action == "MERGE" and not effective_fact_key:
                    structured_facts = {
                        (_normalise_text(parent.fact_key), _normalise_text(parent.fact_value)):
                        (parent.fact_key, parent.fact_value)
                        for parent in parents
                        if _normalise_text(parent.fact_key) and _normalise_text(parent.fact_value)
                    }
                    if len(structured_facts) == 1:
                        effective_fact_key, effective_fact_value = next(
                            iter(structured_facts.values())
                        )
                    elif len(structured_facts) > 1:
                        raise ConflictResolutionRequired(
                            "MERGE parents contain different structured facts; "
                            "the output fact_key and fact_value must be explicit"
                        )
                elif not effective_fact_key and len(parents) == 1:
                    effective_fact_key = parents[0].fact_key
                    effective_fact_value = parents[0].fact_value
                conflict = assess_transition_conflict(
                    action,
                    parents,
                    effective_fact_key,
                    effective_fact_value,
                )
                if action == "CONTEST" and conflict.state != "conflict":
                    raise TransitionValidationError(
                        "CONTEST requires an explicit fact_key/fact_value that differs "
                        "from the active version"
                    )
                resolution_refs = refs
                if action == "UPDATE" and parents[0].proposal is not None:
                    proposal = parents[0].proposal
                    if _normalise_text(effective_fact_value) == _normalise_text(
                        proposal.fact_value
                    ):
                        resolution_refs = merge_evidence_refs(proposal.evidence_refs, refs)
                    elif _normalise_text(effective_fact_value) == _normalise_text(
                        parents[0].fact_value
                    ):
                        resolution_refs = merge_evidence_refs(parents[0].evidence_refs, refs)
                validate_resolution_basis(
                    parents,
                    resolution_refs,
                    conflict,
                    basis,
                    resolution,
                    effective_fact_value,
                    allow_unresolved=action == "CONTEST",
                    governance_version=GOVERNANCE_VERSION,
                    topic=topic,
                    fact_key=effective_fact_key,
                )

                event_id = f"evt_{uuid.uuid4().hex}"
                version_id = f"ver_{uuid.uuid4().hex}"
                now = _now_iso()
                version = self._build_version(
                    action=action,
                    topic=topic,
                    payload=payload,
                    parents=parents,
                    refs=refs,
                    resolution_refs=resolution_refs,
                    event_id=event_id,
                    version_id=version_id,
                    now=now,
                    conflict=conflict,
                )
                atomic_claim_identity = claim_identity_for_version(version, action)
                evidence_uses = tuple(
                    (
                        ref,
                        evidence_use_identity(
                            ref.entry_id,
                            atomic_claim_identity,
                            locator_identity(ref.locator),
                        ),
                    )
                    for ref in refs
                )
                reused = [
                    ref.entry_id
                    for ref, use_id in evidence_uses
                    if use_id in snapshot.processed_evidence
                ]
                if reused:
                    raise EvidenceAlreadyProcessedError(
                        "The same evidence span already supports this atomic claim: "
                        + ", ".join(reused)
                    )
                event = TransitionEvent(
                    event_id=event_id,
                    action=action,
                    topic=topic,
                    parent_version_ids=tuple(parent.version_id for parent in parents),
                    output_version_ids=(version_id,),
                    evidence_ids=tuple(ref.entry_id for ref in refs),
                    evidence_use_ids=tuple(use_id for _, use_id in evidence_uses),
                    reason=reason,
                    idempotency_key=key,
                    request_hash=request_hash,
                    algorithm_version=ALGORITHM_VERSION,
                    governance_version=GOVERNANCE_VERSION,
                    resolution_basis=basis,
                    resolution_metadata=resolution,
                    created_at=now,
                    conflict=conflict,
                )
                _upgrade_ledger_state(raw)
                raw["events"].append(asdict(event))  # type: ignore[union-attr]
                raw["versions"].append(asdict(version))  # type: ignore[union-attr]
                processed = raw["processed_evidence"]
                for ref, use_id in evidence_uses:
                    processed[use_id] = {  # type: ignore[index]
                        "event_id": event_id,
                        "entry_id": ref.entry_id,
                        "claim_identity": atomic_claim_identity,
                        "content_hash": ref.content_hash,
                        "evidence_digest": ref.evidence_digest,
                        "source_key": ref.source_key,
                        "locator_identity": locator_identity(ref.locator),
                        "processed_at": now,
                    }
                _decode_and_replay(raw)
                self.ledger._write_unlocked(raw)
                return TransitionResult(
                    applied=True,
                    event_id=event_id,
                    action=action,
                    version_ids=(version_id,),
                    idempotency_key=key,
                )

    @staticmethod
    def _validate_shape(
        action: str,
        targets: tuple[str, ...],
        payload: Mapping[str, object],
        refs: tuple[EvidenceRef, ...],
    ) -> None:
        if action == "CREATE":
            if targets:
                raise TransitionValidationError("CREATE cannot have target cards")
            if not refs:
                raise EvidenceValidationError("CREATE requires at least one new evidence source")
            if not str(payload.get("title", "")).strip() or not str(payload.get("claim", "")).strip():
                raise TransitionValidationError("CREATE requires non-empty title and claim")
        elif action == "UPDATE":
            if len(targets) != 1:
                raise TransitionValidationError("UPDATE requires exactly one target card")
        elif action == "MERGE":
            if len(targets) < 2:
                raise TransitionValidationError("MERGE requires at least two distinct target cards")
            if not str(payload.get("title", "")).strip() or not str(payload.get("claim", "")).strip():
                raise TransitionValidationError("MERGE requires non-empty title and claim")
        elif action == "CONTEST":
            if len(targets) != 1:
                raise TransitionValidationError("CONTEST requires exactly one target card")
            if not refs:
                raise EvidenceValidationError("CONTEST requires new conflicting evidence")
            if not str(payload.get("claim", "")).strip():
                raise TransitionValidationError("CONTEST requires the proposed conflicting claim")
            if not str(payload.get("fact_key", "")).strip() or not str(
                payload.get("fact_value", "")
            ).strip():
                raise TransitionValidationError(
                    "CONTEST requires proposed fact_key and fact_value"
                )
        else:  # RETIRE
            if len(targets) != 1:
                raise TransitionValidationError("RETIRE requires exactly one target card")
            if payload:
                raise TransitionValidationError("RETIRE does not accept replacement card content")

        fact_key = str(payload.get("fact_key", "")).strip()
        fact_value = str(payload.get("fact_value", "")).strip()
        if bool(fact_key) != bool(fact_value):
            raise TransitionValidationError("fact_key and fact_value must be supplied together")
        tags = payload.get("tags")
        if tags is not None and (isinstance(tags, (str, bytes)) or not isinstance(tags, Sequence)):
            raise TransitionValidationError("Card tags must be a sequence of strings")

    @staticmethod
    def _resolve_parents(
        snapshot: MemorySnapshot,
        action: str,
        targets: tuple[str, ...],
    ) -> tuple[CardVersion, ...]:
        if action == "CREATE":
            return ()
        parents: list[CardVersion] = []
        for card_id in targets:
            version_id = snapshot.active_heads.get(card_id)
            if version_id is None:
                raise TransitionValidationError(f"Target card is not an active head: {card_id}")
            parents.append(snapshot.versions_by_id[version_id])
        topics = {parent.topic for parent in parents}
        if len(topics) > 1:
            raise TransitionValidationError("A transition cannot combine cards from different topics")
        return tuple(parents)

    @staticmethod
    def _build_version(
        *,
        action: str,
        topic: str,
        payload: Mapping[str, object],
        parents: tuple[CardVersion, ...],
        refs: tuple[EvidenceRef, ...],
        resolution_refs: tuple[EvidenceRef, ...],
        event_id: str,
        version_id: str,
        now: str,
        conflict: ConflictAssessment,
    ) -> CardVersion:
        parent = parents[0] if len(parents) == 1 else None
        if action == "CREATE":
            card_id = f"card_{uuid.uuid4().hex[:16]}"
            revision = 1
            state = "active"
            support_refs = refs
        elif action == "UPDATE":
            assert parent is not None
            card_id = parent.card_id
            revision = parent.revision + 1
            state = "active"
            support_refs = (
                resolution_refs
                if conflict.state == "conflict"
                else merge_evidence_refs(parent.evidence_refs, refs)
            )
        elif action == "MERGE":
            card_id = f"card_{uuid.uuid4().hex[:16]}"
            revision = 1
            state = "active"
            inherited = tuple(ref for item in parents for ref in item.evidence_refs)
            support_refs = (
                refs if conflict.state == "conflict" else merge_evidence_refs(inherited, refs)
            )
        elif action == "CONTEST":
            assert parent is not None
            card_id = parent.card_id
            revision = parent.revision + 1
            state = "contested"
            support_refs = parent.evidence_refs
        else:
            assert parent is not None
            card_id = parent.card_id
            revision = parent.revision + 1
            state = "retired"
            support_refs = merge_evidence_refs(parent.evidence_refs, refs)

        fallback = parent if parent is not None else None
        title = str(payload.get("title", fallback.title if fallback else "")).strip()
        claim = str(payload.get("claim", fallback.claim if fallback else "")).strip()
        evidence = str(payload.get("evidence", fallback.evidence if fallback else "")).strip()
        raw_tags = payload.get("tags", fallback.tags if fallback else ())
        tags = _dedupe_strings(raw_tags)  # type: ignore[arg-type]
        fact_key = str(payload.get("fact_key", fallback.fact_key if fallback else "")).strip()
        fact_value = str(payload.get("fact_value", fallback.fact_value if fallback else "")).strip()
        proposal = None
        if action == "MERGE" and not fact_key:
            structured_facts = {
                (_normalise_text(item.fact_key), _normalise_text(item.fact_value)):
                (item.fact_key, item.fact_value)
                for item in parents
                if _normalise_text(item.fact_key) and _normalise_text(item.fact_value)
            }
            if len(structured_facts) == 1:
                fact_key, fact_value = next(iter(structured_facts.values()))
        if action == "RETIRE":
            title = parent.title  # type: ignore[union-attr]
            claim = parent.claim  # type: ignore[union-attr]
            evidence = parent.evidence  # type: ignore[union-attr]
            tags = parent.tags  # type: ignore[union-attr]
            fact_key = parent.fact_key  # type: ignore[union-attr]
            fact_value = parent.fact_value  # type: ignore[union-attr]
        elif action == "CONTEST":
            proposal = ContestedClaim(
                claim=claim,
                evidence=evidence,
                fact_key=fact_key,
                fact_value=fact_value,
                evidence_refs=refs,
                strength=compute_evidence_strength(refs, conflict=True),
            )
            title = parent.title  # type: ignore[union-attr]
            claim = parent.claim  # type: ignore[union-attr]
            evidence = parent.evidence  # type: ignore[union-attr]
            tags = parent.tags  # type: ignore[union-attr]
            fact_key = parent.fact_key  # type: ignore[union-attr]
            fact_value = parent.fact_value  # type: ignore[union-attr]
        return CardVersion(
            version_id=version_id,
            card_id=card_id,
            revision=revision,
            topic=topic,
            title=title,
            claim=claim,
            evidence=evidence,
            tags=tags,
            evidence_refs=support_refs,
            state=state,
            parent_version_ids=tuple(item.version_id for item in parents),
            event_id=event_id,
            created_at=now,
            strength=compute_evidence_strength(
                support_refs,
                conflict=conflict.state == "conflict",
            ),
            proposal=proposal,
            fact_key=fact_key,
            fact_value=fact_value,
        )

    def audit_graph(self) -> dict[str, list[dict]]:
        """Return the replayable version DAG without projecting public cards."""
        snapshot = self.snapshot()
        nodes = [
            {
                "version_id": version.version_id,
                "card_id": version.card_id,
                "revision": version.revision,
                "state": version.state,
                "event_id": version.event_id,
            }
            for version in snapshot.versions
        ]
        edges = []
        for event in snapshot.events:
            output_id = event.output_version_ids[0]
            edges.extend(
                {
                    "from": parent_id,
                    "to": output_id,
                    "event_id": event.event_id,
                    "action": event.action,
                }
                for parent_id in event.parent_version_ids
            )
        return {"nodes": nodes, "edges": edges}
