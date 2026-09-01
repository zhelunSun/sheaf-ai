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
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence


from sheaf_ai._evidence_memory_models import (
    ALGORITHM_VERSION,
    DIGEST_ALGORITHM_VERSION,
    GOVERNANCE_VERSION,
    VALID_ACTIONS,
    VALID_RESOLUTION_BASES,
    AtomicBatchConflictError,
    AtomicBatchReceipt,
    AtomicSplitOperation,
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
    StaleHeadError,
    TransitionEvent,
    TransitionResult,
    TransitionValidationError,
    atomic_batch_event_key,
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
    "AtomicBatchConflictError",
    "AtomicBatchReceipt",
    "AtomicSplitOperation",
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
    "StaleHeadError",
    "TransitionEvent",
    "TransitionResult",
    "TransitionValidationError",
    "allowlisted_evidence",
    "assess_structured_conflict",
    "compute_evidence_strength",
]


from sheaf_ai._evidence_memory_ledger import (
    EvidenceLedger,
    _atomic_batch_receipts,
    _decode_and_replay,
    _exclusive_file_lock,
    _now_iso,
    _upgrade_ledger_state,
    _validate_new_entry_identities,
)


@dataclass(frozen=True)
class _PreparedTransition:
    action: str
    topic: str
    payload: Mapping[str, object]
    refs: tuple[EvidenceRef, ...]
    targets: tuple[str, ...]
    reason: str
    resolution_basis: str
    resolution_metadata: tuple[tuple[str, str], ...]
    request_hash: str
    idempotency_key: str


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
        prepared = self._prepare_transition(
            action,
            topic=topic,
            entries=entries,
            source_ids=source_ids,
            evidence_locators=evidence_locators,
            card=card,
            target_card_ids=target_card_ids,
            reason=reason,
            resolution_basis=resolution_basis,
            resolution_metadata=resolution_metadata,
            idempotency_key=idempotency_key,
        )
        with self.ledger._lock:
            with _exclusive_file_lock(self.ledger._lock_path):
                raw = self.ledger._read_unlocked()
                snapshot = _decode_and_replay(raw)
                result, _snapshot = self._stage_transition(raw, snapshot, prepared)
                if not result.applied:
                    return result
                self.ledger._write_unlocked(raw)
                return result

    def apply_atomic_split(
        self,
        *,
        update: AtomicSplitOperation,
        create: AtomicSplitOperation,
        decision_id: str,
        request_hash: str,
        expected_heads: Mapping[str, str],
        policy_version: str,
        algorithm_version: str,
        execution_manifest_hash: str,
        idempotency_key: str = "",
        fault_injector: Callable[[str], None] | None = None,
    ) -> AtomicBatchReceipt:
        """Commit one UPDATE plus one CREATE in a single domain-ledger replace."""
        decision = str(decision_id).strip()
        request_identity = str(request_hash).strip()
        key = str(idempotency_key).strip() or decision
        policy = str(policy_version).strip()
        algorithm = str(algorithm_version).strip()
        manifest_hash = str(execution_manifest_hash).strip()
        heads = {
            str(card_id).strip(): str(version_id).strip()
            for card_id, version_id in expected_heads.items()
        }
        if not decision or not key or not policy or not algorithm:
            raise TransitionValidationError(
                "Atomic SPLIT requires decision, idempotency, policy, and algorithm identity"
            )
        if len(request_identity) != 64 or any(
            character not in "0123456789abcdef" for character in request_identity
        ):
            raise TransitionValidationError("Atomic SPLIT request_hash must be a SHA-256 hex digest")
        if len(manifest_hash) != 64 or any(
            character not in "0123456789abcdef" for character in manifest_hash
        ):
            raise TransitionValidationError(
                "Atomic SPLIT execution_manifest_hash must be a SHA-256 hex digest"
            )
        if len(heads) != 1 or any(not item for pair in heads.items() for item in pair):
            raise TransitionValidationError("Atomic SPLIT requires exactly one expected head")
        if str(update.action).upper().strip() != "UPDATE":
            raise TransitionValidationError("Atomic SPLIT first operation must be UPDATE")
        if str(create.action).upper().strip() != "CREATE":
            raise TransitionValidationError("Atomic SPLIT second operation must be CREATE")
        if str(update.topic).strip() != str(create.topic).strip():
            raise TransitionValidationError("Atomic SPLIT operations must share one topic")
        target_ids = tuple(sorted(heads))
        if tuple(sorted(_dedupe_strings(update.target_card_ids))) != target_ids:
            raise TransitionValidationError("Atomic SPLIT UPDATE must target the expected head")
        if _dedupe_strings(create.target_card_ids):
            raise TransitionValidationError("Atomic SPLIT CREATE cannot target an existing card")

        prepared_update = self._prepare_transition(
            "UPDATE",
            topic=update.topic,
            entries=update.entries,
            source_ids=update.source_ids,
            evidence_locators=update.evidence_locators,
            card=update.card,
            target_card_ids=update.target_card_ids,
            reason=update.reason,
            resolution_basis=update.resolution_basis,
            resolution_metadata=update.resolution_metadata,
            idempotency_key=atomic_batch_event_key(decision, 0),
        )
        prepared_create = self._prepare_transition(
            "CREATE",
            topic=create.topic,
            entries=create.entries,
            source_ids=create.source_ids,
            evidence_locators=create.evidence_locators,
            card=create.card,
            target_card_ids=create.target_card_ids,
            reason=create.reason,
            resolution_basis=create.resolution_basis,
            resolution_metadata=create.resolution_metadata,
            idempotency_key=atomic_batch_event_key(decision, 1),
        )

        def checkpoint(name: str) -> None:
            if fault_injector is not None:
                fault_injector(name)

        with self.ledger._lock:
            with _exclusive_file_lock(self.ledger._lock_path):
                raw = self.ledger._read_unlocked()
                prior = self._matching_atomic_receipt(
                    raw,
                    decision_id=decision,
                    request_hash=request_identity,
                    idempotency_key=key,
                    expected_heads=heads,
                    operation_request_hashes=(
                        prepared_update.request_hash,
                        prepared_create.request_hash,
                    ),
                    policy_version=policy,
                    algorithm_version=algorithm,
                    execution_manifest_hash=manifest_hash,
                )
                if prior is not None:
                    return replace(prior, applied=False)
                checkpoint("after_read")
                snapshot = _decode_and_replay(raw)
                for card_id, expected_version_id in heads.items():
                    actual_version_id = snapshot.active_heads.get(card_id)
                    if actual_version_id != expected_version_id:
                        raise StaleHeadError(
                            f"Target head changed for {card_id}: expected "
                            f"{expected_version_id}, found {actual_version_id or '<missing>'}"
                        )

                update_result, snapshot = self._stage_transition(
                    raw,
                    snapshot,
                    prepared_update,
                )
                if not update_result.applied:
                    raise AtomicBatchConflictError(
                        "Atomic SPLIT UPDATE event exists without a batch receipt"
                    )
                checkpoint("after_update_staged")
                create_result, _snapshot = self._stage_transition(
                    raw,
                    snapshot,
                    prepared_create,
                )
                if not create_result.applied:
                    raise AtomicBatchConflictError(
                        "Atomic SPLIT CREATE event exists without a batch receipt"
                    )
                checkpoint("after_create_staged")

                receipt = AtomicBatchReceipt(
                    applied=True,
                    decision_id=decision,
                    request_hash=request_identity,
                    idempotency_key=key,
                    expected_heads=dict(heads),
                    operation_actions=("UPDATE", "CREATE"),
                    operation_request_hashes=(
                        prepared_update.request_hash,
                        prepared_create.request_hash,
                    ),
                    event_ids=(update_result.event_id, create_result.event_id),
                    version_ids=(
                        update_result.version_ids[0],
                        create_result.version_ids[0],
                    ),
                    policy_version=policy,
                    algorithm_version=algorithm,
                    execution_manifest_hash=manifest_hash,
                    committed_at=_now_iso(),
                )
                raw["atomic_batches"].append(receipt.to_record())  # type: ignore[union-attr]
                _decode_and_replay(raw)
                checkpoint("before_replace")
                self.ledger._write_unlocked(raw)
                checkpoint("after_replace")
                return receipt

    def lookup_atomic_batch(
        self,
        decision_id: str,
        request_hash: str = "",
    ) -> AtomicBatchReceipt | None:
        """Return the durable domain receipt for recovery without changing state."""
        decision = str(decision_id).strip()
        expected_hash = str(request_hash).strip()
        if not decision:
            raise TransitionValidationError("decision_id is required")
        with self.ledger._lock:
            with _exclusive_file_lock(self.ledger._lock_path):
                raw = self.ledger._read_unlocked()
                receipt = next(
                    (
                        item
                        for item in _atomic_batch_receipts(raw)
                        if item.decision_id == decision
                    ),
                    None,
                )
        if receipt is None:
            return None
        if expected_hash and receipt.request_hash != expected_hash:
            raise AtomicBatchConflictError(
                f"Decision {decision!r} is committed with a different request hash"
            )
        return replace(receipt, applied=False)

    @staticmethod
    def _matching_atomic_receipt(
        raw: Mapping[str, object],
        *,
        decision_id: str,
        request_hash: str,
        idempotency_key: str,
        expected_heads: Mapping[str, str],
        operation_request_hashes: tuple[str, str],
        policy_version: str,
        algorithm_version: str,
        execution_manifest_hash: str,
    ) -> AtomicBatchReceipt | None:
        receipts = _atomic_batch_receipts(raw)
        prior = next(
            (receipt for receipt in receipts if receipt.decision_id == decision_id),
            None,
        )
        if prior is not None:
            if prior.request_hash != request_hash:
                raise AtomicBatchConflictError(
                    f"Decision {decision_id!r} was reused for a different request hash"
                )
            if prior.idempotency_key != idempotency_key:
                raise AtomicBatchConflictError(
                    f"Decision {decision_id!r} was reused with a different idempotency key"
                )
            if dict(prior.expected_heads) != dict(expected_heads):
                raise AtomicBatchConflictError(
                    f"Decision {decision_id!r} was reused with different expected heads"
                )
            if prior.operation_request_hashes != operation_request_hashes:
                raise AtomicBatchConflictError(
                    f"Decision {decision_id!r} was reused for different domain operations"
                )
            if (
                prior.policy_version != policy_version
                or prior.algorithm_version != algorithm_version
                or prior.execution_manifest_hash != execution_manifest_hash
            ):
                raise AtomicBatchConflictError(
                    f"Decision {decision_id!r} was reused with different policy identity"
                )
            return prior
        conflicting = next(
            (
                receipt
                for receipt in receipts
                if receipt.idempotency_key == idempotency_key
            ),
            None,
        )
        if conflicting is not None:
            raise AtomicBatchConflictError(
                f"Atomic batch idempotency key {idempotency_key!r} is already committed"
            )
        return None

    def _prepare_transition(
        self,
        action: str,
        *,
        topic: str,
        entries: Sequence[Mapping[str, object]] | Mapping[str, Mapping[str, object]],
        source_ids: Sequence[object] | None,
        evidence_locators: Mapping[str, Mapping[str, object]] | None,
        card: Mapping[str, object] | None,
        target_card_ids: Sequence[object],
        reason: str,
        resolution_basis: str,
        resolution_metadata: Mapping[str, object] | None,
        idempotency_key: str,
    ) -> _PreparedTransition:
        normalised_action = str(action).upper().strip()
        normalised_topic = str(topic).strip()
        normalised_reason = str(reason).strip()
        payload = dict(card or {})
        unknown_fields = set(payload) - self._CARD_FIELDS
        if unknown_fields:
            raise TransitionValidationError(
                "Unsupported card fields: " + ", ".join(sorted(unknown_fields))
            )
        if normalised_action not in VALID_ACTIONS:
            raise TransitionValidationError(
                f"Unsupported transition action: {normalised_action!r}"
            )
        if not normalised_topic:
            raise TransitionValidationError("Transition topic is required")
        if not normalised_reason:
            raise TransitionValidationError("Transition reason is required for auditability")

        payload_source_ids = payload.pop("source_ids", None)
        effective_source_ids = source_ids
        if effective_source_ids is None:
            effective_source_ids = payload_source_ids or ()
        elif payload_source_ids is not None and (
            _dedupe_strings(effective_source_ids) != _dedupe_strings(payload_source_ids)
        ):
            raise EvidenceValidationError(
                "Card source_ids disagree with transition source_ids"
            )
        refs = allowlisted_evidence(entries, effective_source_ids, evidence_locators)
        targets = tuple(sorted(_dedupe_strings(target_card_ids)))
        basis = str(resolution_basis).strip()
        resolution = _normalise_resolution_metadata(resolution_metadata)
        self._validate_shape(normalised_action, targets, payload, refs)
        request_document = {
            "action": normalised_action,
            "topic": normalised_topic,
            "target_card_ids": targets,
            "card": payload,
            "evidence_refs": [asdict(ref) for ref in refs],
            "reason": normalised_reason,
            "resolution_basis": basis,
            "resolution_metadata": resolution,
        }
        request_identity = _canonical_hash(request_document)
        key = str(idempotency_key).strip() or f"auto:{request_identity}"
        return _PreparedTransition(
            action=normalised_action,
            topic=normalised_topic,
            payload=payload,
            refs=refs,
            targets=targets,
            reason=normalised_reason,
            resolution_basis=basis,
            resolution_metadata=resolution,
            request_hash=request_identity,
            idempotency_key=key,
        )

    def _stage_transition(
        self,
        raw: dict,
        snapshot: MemorySnapshot,
        prepared: _PreparedTransition,
    ) -> tuple[TransitionResult, MemorySnapshot]:
        prior = next(
            (
                event
                for event in snapshot.events
                if event.idempotency_key == prepared.idempotency_key
            ),
            None,
        )
        if prior is not None:
            if prior.request_hash != prepared.request_hash:
                raise TransitionValidationError(
                    f"Idempotency key {prepared.idempotency_key!r} "
                    "was reused for a different request"
                )
            return (
                TransitionResult(
                    applied=False,
                    event_id=prior.event_id,
                    action=prior.action,
                    version_ids=prior.output_version_ids,
                    idempotency_key=prepared.idempotency_key,
                ),
                snapshot,
            )

        action = prepared.action
        topic = prepared.topic
        payload = prepared.payload
        refs = prepared.refs
        _validate_new_entry_identities(snapshot, refs)
        parents = self._resolve_parents(snapshot, action, prepared.targets)
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
                (_normalise_text(parent.fact_key), _normalise_text(parent.fact_value)): (
                    parent.fact_key,
                    parent.fact_value,
                )
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
            prepared.resolution_basis,
            prepared.resolution_metadata,
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
            reason=prepared.reason,
            idempotency_key=prepared.idempotency_key,
            request_hash=prepared.request_hash,
            algorithm_version=ALGORITHM_VERSION,
            governance_version=GOVERNANCE_VERSION,
            resolution_basis=prepared.resolution_basis,
            resolution_metadata=prepared.resolution_metadata,
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
        updated_snapshot = _decode_and_replay(raw)
        return (
            TransitionResult(
                applied=True,
                event_id=event_id,
                action=action,
                version_ids=(version_id,),
                idempotency_key=prepared.idempotency_key,
            ),
            updated_snapshot,
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
