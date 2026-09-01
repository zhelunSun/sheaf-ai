"""Atomic persistence and full semantic replay for evidence memory."""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from sheaf_ai._evidence_memory_models import (
    LEGACY_GOVERNANCE_VERSION,
    SCHEMA_VERSION,
    SPAN_IDENTITY_SCHEMA_VERSION,
    VALID_ACTIONS,
    VALID_ALGORITHM_VERSIONS,
    VALID_GOVERNANCE_VERSIONS,
    VALID_TIERS,
    AtomicBatchReceipt,
    CardVersion,
    EvidenceMemoryError,
    EvidenceRef,
    EvidenceValidationError,
    LedgerCorruptionError,
    MemorySnapshot,
    TransitionEvent,
    TransitionValidationError,
    atomic_batch_event_key,
    claim_identity_for_version,
    evidence_use_identity,
    legacy_evidence_use_identity,
    locator_identity,
)
from sheaf_ai._evidence_memory_rules import (
    _normalise_text,
    assess_transition_conflict,
    compute_evidence_strength,
    merge_evidence_refs,
    validate_resolution_basis,
)
from sheaf_ai.source_independence import SOURCE_INDEPENDENCE_VERSION


_LEDGER_LOCKS: dict[str, threading.RLock] = {}
_LEDGER_LOCKS_GUARD = threading.Lock()


def _ledger_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _LEDGER_LOCKS_GUARD:
        return _LEDGER_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _exclusive_file_lock(path: Path):
    """Hold an advisory cross-process writer lock for one ledger path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    locked = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _fsync_parent_directory(path: Path) -> None:
    """Persist the rename itself where directory fsync is supported."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(str(Path(path).parent), flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _empty_ledger() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "events": [],
        "versions": [],
        "processed_evidence": {},
        "atomic_batches": [],
    }


def _advance_entry_identity(
    identities: dict[str, EvidenceRef],
    ref: EvidenceRef,
    error_type: type[EvidenceMemoryError],
    *,
    strict_source_attributes: bool = False,
) -> None:
    previous = identities.get(ref.entry_id)
    if previous is None:
        identities[ref.entry_id] = ref
        return
    if previous.source_key != ref.source_key:
        raise error_type(f"Entry {ref.entry_id} source identity changed")
    if strict_source_attributes and previous.source_tier != ref.source_tier:
        raise error_type(f"Entry {ref.entry_id} source tier changed")
    if strict_source_attributes and previous.is_primary != ref.is_primary:
        raise error_type(f"Entry {ref.entry_id} primary authority status changed")

    def advance_hash(previous_value: str, current_value: str, label: str) -> str:
        if previous_value and not current_value:
            raise error_type(f"Entry {ref.entry_id} {label} cannot become unknown")
        if previous_value and current_value != previous_value:
            raise error_type(f"Entry {ref.entry_id} {label} changed")
        return previous_value or current_value

    def advance_scope(
        previous_value: tuple[str, ...],
        current_value: tuple[str, ...],
        label: str,
    ) -> tuple[str, ...]:
        if previous_value and not current_value:
            raise error_type(f"Entry {ref.entry_id} {label} cannot become unknown")
        if previous_value and current_value != previous_value:
            raise error_type(f"Entry {ref.entry_id} {label} changed")
        return previous_value or current_value

    def advance_text(previous_value: str, current_value: str, label: str) -> str:
        if previous_value and not current_value:
            raise error_type(f"Entry {ref.entry_id} {label} cannot become unknown")
        if previous_value and current_value != previous_value:
            raise error_type(f"Entry {ref.entry_id} {label} changed")
        return previous_value or current_value

    identities[ref.entry_id] = EvidenceRef(
        entry_id=previous.entry_id,
        source_tier=previous.source_tier,
        source_key=previous.source_key,
        content_hash=advance_hash(previous.content_hash, ref.content_hash, "content hash"),
        evidence_digest=advance_hash(
            previous.evidence_digest,
            ref.evidence_digest,
            "evidence digest",
        ),
        locator=previous.locator,
        is_primary=previous.is_primary,
        authority_topics=advance_scope(
            previous.authority_topics,
            ref.authority_topics,
            "authority topic scope",
        ),
        authority_fact_keys=advance_scope(
            previous.authority_fact_keys,
            ref.authority_fact_keys,
            "authority fact scope",
        ),
        corrects_entry_ids=advance_scope(
            previous.corrects_entry_ids,
            ref.corrects_entry_ids,
            "correction relations",
        ),
        duplicate_detection_version=advance_text(
            previous.duplicate_detection_version,
            ref.duplicate_detection_version,
            "duplicate detection version",
        ),
        duplicate_relations=advance_scope(
            previous.duplicate_relations,
            ref.duplicate_relations,
            "duplicate relations",
        ),
        independence_identity=advance_text(
            previous.independence_identity,
            ref.independence_identity,
            "independent provenance identity",
        ),
    )


def _event_new_refs(event: TransitionEvent, output: CardVersion) -> tuple[EvidenceRef, ...]:
    claim_refs = (
        output.proposal.evidence_refs
        if event.action == "CONTEST" and output.proposal is not None
        else output.evidence_refs
    )
    if event.evidence_use_ids:
        atomic_claim_identity = claim_identity_for_version(output, event.action)
        use_ids = set(event.evidence_use_ids)
        return tuple(
            ref
            for ref in claim_refs
            if evidence_use_identity(
                ref.entry_id,
                atomic_claim_identity,
                locator_identity(ref.locator),
            )
            in use_ids
        )
    return tuple(ref for ref in claim_refs if ref.entry_id in event.evidence_ids)


def _validate_new_entry_identities(
    snapshot: MemorySnapshot,
    refs: tuple[EvidenceRef, ...],
) -> None:
    identities: dict[str, EvidenceRef] = {}
    for event in snapshot.events:
        output = snapshot.versions_by_id[event.output_version_ids[0]]
        for prior_ref in _event_new_refs(event, output):
            _advance_entry_identity(identities, prior_ref, LedgerCorruptionError)
    for ref in refs:
        _advance_entry_identity(
            identities,
            ref,
            EvidenceValidationError,
            strict_source_attributes=True,
        )


class EvidenceLedger:
    """Atomic JSON event ledger with semantic corruption detection."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _ledger_lock(self.path)
        self._lock_path = self.path.with_name(f".{self.path.name}.lock")
        with self._lock:
            with _exclusive_file_lock(self._lock_path):
                if not self.path.exists():
                    self._write_unlocked(_empty_ledger())
                else:
                    self._read_unlocked()  # fail explicitly; never overwrite corruption

    def _read_unlocked(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LedgerCorruptionError(f"Cannot read evidence ledger {self.path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise LedgerCorruptionError("Evidence ledger root must be a JSON object")
        _decode_and_replay(raw)
        return raw

    def _write_unlocked(self, state: dict) -> None:
        payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.path.parent),
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.path)
            _fsync_parent_directory(self.path)
        except OSError as exc:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise EvidenceMemoryError(f"Cannot write evidence ledger {self.path}: {exc}") from exc

    def snapshot(self) -> MemorySnapshot:
        with self._lock:
            return _decode_and_replay(self._read_unlocked())


def _atomic_batch_receipts(raw: Mapping[str, object]) -> tuple[AtomicBatchReceipt, ...]:
    """Decode already-validated schema-v4 atomic batch records."""
    records = raw.get("atomic_batches", [])
    if not isinstance(records, list):
        raise LedgerCorruptionError("Ledger atomic_batches must be an array")
    try:
        return tuple(
            AtomicBatchReceipt.from_record(record)
            for record in records
            if isinstance(record, Mapping)
        )
    except (TypeError, ValueError) as exc:
        raise LedgerCorruptionError(f"Malformed atomic batch receipt: {exc}") from exc


def _validate_atomic_batches(
    raw: Mapping[str, object],
    schema_version: object,
    events: tuple[TransitionEvent, ...],
    versions_by_id: Mapping[str, CardVersion],
) -> None:
    raw_batches = raw.get("atomic_batches")
    if schema_version != SCHEMA_VERSION:
        if raw_batches not in (None, []):
            raise LedgerCorruptionError(
                "Legacy evidence ledger cannot contain atomic batch receipts"
            )
        return
    if not isinstance(raw_batches, list):
        raise LedgerCorruptionError("Schema 4 atomic_batches must be an array")
    if any(not isinstance(record, Mapping) for record in raw_batches):
        raise LedgerCorruptionError("Malformed atomic batch receipt")
    receipts = _atomic_batch_receipts(raw)
    event_positions = {event.event_id: index for index, event in enumerate(events)}
    events_by_id = {event.event_id: event for event in events}
    seen_decisions: set[str] = set()
    seen_keys: set[str] = set()
    claimed_events: set[str] = set()
    claimed_versions: set[str] = set()
    last_event_position = -1
    for receipt in receipts:
        if (
            not receipt.decision_id
            or not re.fullmatch(r"[0-9a-f]{64}", receipt.request_hash)
            or not receipt.idempotency_key
            or not receipt.policy_version
            or not receipt.algorithm_version
            or not re.fullmatch(r"[0-9a-f]{64}", receipt.execution_manifest_hash)
            or not receipt.committed_at
        ):
            raise LedgerCorruptionError("Atomic batch receipt is missing audit identity")
        if receipt.decision_id in seen_decisions:
            raise LedgerCorruptionError("Duplicate atomic batch decision_id")
        if receipt.idempotency_key in seen_keys:
            raise LedgerCorruptionError("Duplicate atomic batch idempotency_key")
        if len(receipt.expected_heads) != 1 or any(
            not card_id or not version_id
            for card_id, version_id in receipt.expected_heads.items()
        ):
            raise LedgerCorruptionError("Atomic SPLIT must bind exactly one target head")
        if receipt.operation_actions != ("UPDATE", "CREATE"):
            raise LedgerCorruptionError("Atomic SPLIT operation order is invalid")
        if len(receipt.operation_request_hashes) != 2 or any(
            not re.fullmatch(r"[0-9a-f]{64}", request_hash)
            for request_hash in receipt.operation_request_hashes
        ):
            raise LedgerCorruptionError("Atomic SPLIT operation request hashes are invalid")
        if len(receipt.event_ids) != 2 or len(set(receipt.event_ids)) != 2:
            raise LedgerCorruptionError("Atomic SPLIT must reference two unique events")
        if len(receipt.version_ids) != 2 or len(set(receipt.version_ids)) != 2:
            raise LedgerCorruptionError("Atomic SPLIT must reference two unique versions")
        if claimed_events.intersection(receipt.event_ids):
            raise LedgerCorruptionError("An event belongs to more than one atomic batch")
        if claimed_versions.intersection(receipt.version_ids):
            raise LedgerCorruptionError("A version belongs to more than one atomic batch")
        if any(event_id not in events_by_id for event_id in receipt.event_ids):
            raise LedgerCorruptionError("Atomic batch references an unknown event")
        if any(version_id not in versions_by_id for version_id in receipt.version_ids):
            raise LedgerCorruptionError("Atomic batch references an unknown version")

        positions = tuple(event_positions[event_id] for event_id in receipt.event_ids)
        if positions[1] != positions[0] + 1 or positions[0] <= last_event_position:
            raise LedgerCorruptionError("Atomic batch event order is invalid")
        batch_events = tuple(events_by_id[event_id] for event_id in receipt.event_ids)
        if tuple(event.action for event in batch_events) != receipt.operation_actions:
            raise LedgerCorruptionError("Atomic batch actions disagree with its events")
        if (
            tuple(event.request_hash for event in batch_events)
            != receipt.operation_request_hashes
        ):
            raise LedgerCorruptionError("Atomic batch request hashes disagree with its events")
        if tuple(event.output_version_ids[0] for event in batch_events) != receipt.version_ids:
            raise LedgerCorruptionError("Atomic batch versions disagree with its events")
        if any(
            event.idempotency_key
            != atomic_batch_event_key(receipt.decision_id, operation_index)
            for operation_index, event in enumerate(batch_events)
        ):
            raise LedgerCorruptionError("Atomic batch event idempotency is invalid")

        target_card_id, target_version_id = next(iter(receipt.expected_heads.items()))
        update_event, create_event = batch_events
        update_version = versions_by_id[receipt.version_ids[0]]
        create_version = versions_by_id[receipt.version_ids[1]]
        if update_event.parent_version_ids != (target_version_id,):
            raise LedgerCorruptionError("Atomic batch UPDATE does not bind its expected head")
        if update_version.card_id != target_card_id:
            raise LedgerCorruptionError("Atomic batch UPDATE changes the target card identity")
        if create_event.parent_version_ids or create_version.card_id == target_card_id:
            raise LedgerCorruptionError("Atomic batch CREATE is not independent of its target")

        seen_decisions.add(receipt.decision_id)
        seen_keys.add(receipt.idempotency_key)
        claimed_events.update(receipt.event_ids)
        claimed_versions.update(receipt.version_ids)
        last_event_position = positions[1]


def _decode_and_replay(raw: Mapping[str, object]) -> MemorySnapshot:
    schema_version = raw.get("schema_version")
    if schema_version not in {1, 2, SPAN_IDENTITY_SCHEMA_VERSION, SCHEMA_VERSION}:
        raise LedgerCorruptionError(
            f"Unsupported evidence ledger schema: {schema_version!r}"
        )
    raw_events = raw.get("events")
    raw_versions = raw.get("versions")
    raw_processed = raw.get("processed_evidence")
    if not isinstance(raw_events, list) or not isinstance(raw_versions, list):
        raise LedgerCorruptionError("Ledger events and versions must be arrays")
    if not isinstance(raw_processed, dict):
        raise LedgerCorruptionError("Ledger processed_evidence must be an object")
    if schema_version == SCHEMA_VERSION:
        required_event_fields = (
            "algorithm_version",
            "governance_version",
            "evidence_use_ids",
        )
        for index, raw_event in enumerate(raw_events):
            if not isinstance(raw_event, Mapping):
                raise LedgerCorruptionError(f"Malformed ledger event at index {index}")
            for field_name in required_event_fields:
                if field_name not in raw_event:
                    raise LedgerCorruptionError(
                        f"Schema 4 event at index {index} is missing {field_name}"
                    )
    try:
        events = tuple(TransitionEvent.from_dict(item) for item in raw_events)
        versions = tuple(CardVersion.from_dict(item) for item in raw_versions)
    except (AttributeError, TypeError, ValueError, IndexError) as exc:
        raise LedgerCorruptionError(f"Malformed ledger record: {exc}") from exc

    if len({event.event_id for event in events}) != len(events):
        raise LedgerCorruptionError("Duplicate event_id in evidence ledger")
    if len({event.idempotency_key for event in events}) != len(events):
        raise LedgerCorruptionError("Duplicate idempotency_key in evidence ledger")
    versions_by_id = {version.version_id: version for version in versions}
    if len(versions_by_id) != len(versions):
        raise LedgerCorruptionError("Duplicate version_id in evidence ledger")
    _validate_atomic_batches(raw, schema_version, events, versions_by_id)

    active: dict[str, str] = {}
    seen_versions: set[str] = set()
    seen_evidence_uses: dict[str, tuple[str, str, str, str]] = {}
    seen_schema2_uses: dict[str, tuple[str, str]] = {}
    seen_legacy_evidence: dict[str, tuple[str, str]] = {}
    seen_entry_identities: dict[str, EvidenceRef] = {}
    for event in events:
        if event.action not in VALID_ACTIONS:
            raise LedgerCorruptionError(f"Unknown transition action: {event.action!r}")
        if event.algorithm_version not in VALID_ALGORITHM_VERSIONS:
            raise LedgerCorruptionError(
                f"Unknown evidence-strength algorithm: {event.algorithm_version!r}"
            )
        if event.governance_version not in VALID_GOVERNANCE_VERSIONS:
            raise LedgerCorruptionError(
                f"Unknown evidence governance version: {event.governance_version!r}"
            )
        if not event.event_id or not event.idempotency_key or not event.request_hash:
            raise LedgerCorruptionError("Transition event is missing audit identity")
        if len(event.output_version_ids) != 1:
            raise LedgerCorruptionError("Every transition must produce exactly one version")
        output_id = event.output_version_ids[0]
        output = versions_by_id.get(output_id)
        if output is None or output.event_id != event.event_id:
            raise LedgerCorruptionError(f"Event {event.event_id} has an invalid output version")
        if output.topic != event.topic or not output.topic:
            raise LedgerCorruptionError(f"Event {event.event_id} topic disagrees with output")
        if len(set(event.parent_version_ids)) != len(event.parent_version_ids):
            raise LedgerCorruptionError(f"Event {event.event_id} repeats a parent version")
        if len(set(event.evidence_ids)) != len(event.evidence_ids):
            raise LedgerCorruptionError(f"Event {event.event_id} repeats an evidence id")
        if len(set(event.evidence_use_ids)) != len(event.evidence_use_ids):
            raise LedgerCorruptionError(f"Event {event.event_id} repeats an evidence use id")
        if event.governance_version != LEGACY_GOVERNANCE_VERSION and (
            len(event.evidence_use_ids) != len(event.evidence_ids)
        ):
            raise LedgerCorruptionError(
                f"Event {event.event_id} evidence use identities disagree with evidence ids"
            )
        if event.conflict.state not in {"consistent", "conflict", "unknown"}:
            raise LedgerCorruptionError(f"Event {event.event_id} has invalid conflict state")
        if output.parent_version_ids != event.parent_version_ids:
            raise LedgerCorruptionError(f"Event {event.event_id} parent graph disagrees with output")
        if output_id in seen_versions:
            raise LedgerCorruptionError(f"Version {output_id} is emitted more than once")

        parents: list[CardVersion] = []
        for parent_id in event.parent_version_ids:
            if parent_id not in seen_versions:
                raise LedgerCorruptionError(f"Parent version {parent_id} does not precede its event")
            parents.append(versions_by_id[parent_id])
        if any(parent.topic != event.topic for parent in parents):
            raise LedgerCorruptionError(f"Event {event.event_id} crosses topic boundaries")
        conflict_fact_key = output.fact_key
        conflict_fact_value = output.fact_value
        if event.action == "CONTEST" and output.proposal is not None:
            conflict_fact_key = output.proposal.fact_key
            conflict_fact_value = output.proposal.fact_value
        expected_conflict = assess_transition_conflict(
            event.action,
            parents,
            conflict_fact_key,
            conflict_fact_value,
        )
        if event.conflict != expected_conflict:
            raise LedgerCorruptionError(f"Event {event.event_id} conflict result is not reproducible")

        if output.state == "contested" and output.proposal is None:
            raise LedgerCorruptionError(f"Contested version {output_id} has no proposal")
        if output.state != "contested" and output.proposal is not None:
            raise LedgerCorruptionError(f"Non-contested version {output_id} carries a proposal")
        proposal_refs = output.proposal.evidence_refs if output.proposal is not None else ()
        all_refs = output.evidence_refs + proposal_refs
        ref_ids = [ref.entry_id for ref in all_refs]
        if any(
            not ref.entry_id
            or ref.source_tier not in VALID_TIERS
            or not ref.source_key
            for ref in all_refs
        ):
            raise LedgerCorruptionError(f"Version {output_id} has invalid evidence references")
        for ref in all_refs:
            locator = ref.locator
            if locator.kind == "whole_entry":
                locator_valid = locator.start == -1 and locator.end == -1 and not locator.quote
            else:
                locator_valid = (
                    locator.kind in {"quote", "char_span"}
                    and locator.start >= 0
                    and locator.end > locator.start
                    and len(locator.quote) == locator.end - locator.start
                )
            if not locator_valid:
                raise LedgerCorruptionError(
                    f"Version {output_id} has an invalid evidence locator"
                )
            if ref.duplicate_detection_version not in {
                "",
                SOURCE_INDEPENDENCE_VERSION,
            }:
                raise LedgerCorruptionError(
                    f"Version {output_id} has an invalid duplicate detection version"
                )
            if ref.independence_identity and not re.fullmatch(
                r"[0-9a-f]{64}",
                ref.independence_identity,
            ):
                raise LedgerCorruptionError(
                    f"Version {output_id} has an invalid independent provenance identity"
                )
            relation_targets: set[str] = set()
            for relation in ref.duplicate_relations:
                if (
                    not relation.related_entry_id
                    or relation.related_entry_id == ref.entry_id
                    or relation.related_entry_id in relation_targets
                    or relation.classification not in {"exact", "near_duplicate"}
                    or not math.isfinite(relation.similarity)
                    or not 0.0 <= relation.similarity <= 1.0
                    or relation.algorithm_version != SOURCE_INDEPENDENCE_VERSION
                    or not relation.rule
                    or not relation.reason
                ):
                    raise LedgerCorruptionError(
                        f"Version {output_id} has an invalid duplicate relation"
                    )
                relation_targets.add(relation.related_entry_id)
        if len(
            {(ref.entry_id, locator_identity(ref.locator)) for ref in output.evidence_refs}
        ) != len(output.evidence_refs):
            raise LedgerCorruptionError(f"Version {output_id} repeats a supporting reference")
        if len(
            {(ref.entry_id, locator_identity(ref.locator)) for ref in proposal_refs}
        ) != len(proposal_refs):
            raise LedgerCorruptionError(f"Version {output_id} repeats a proposal reference")
        if not set(event.evidence_ids).issubset(ref_ids):
            raise LedgerCorruptionError(f"Event {event.event_id} evidence is absent from its output")
        expected_strength = compute_evidence_strength(
            output.evidence_refs,
            conflict=event.conflict.state == "conflict",
            algorithm_version=event.algorithm_version,
        )
        if output.strength != expected_strength:
            raise LedgerCorruptionError(f"Version {output_id} evidence strength is not reproducible")
        if output.proposal is not None:
            expected_proposal_strength = compute_evidence_strength(
                output.proposal.evidence_refs,
                conflict=True,
                algorithm_version=event.algorithm_version,
            )
            if output.proposal.strength != expected_proposal_strength:
                raise LedgerCorruptionError(
                    f"Version {output_id} proposal strength is not reproducible"
                )

        atomic_claim_identity = claim_identity_for_version(output, event.action)
        new_refs = _event_new_refs(event, output)
        derived_use_ids = {
            evidence_use_identity(
                ref.entry_id,
                atomic_claim_identity,
                locator_identity(ref.locator),
            )
            for ref in new_refs
        }
        if {ref.entry_id for ref in new_refs} != set(event.evidence_ids):
            raise LedgerCorruptionError(
                f"Event {event.event_id} evidence is absent from its supported claim"
            )
        if event.evidence_use_ids and derived_use_ids != set(event.evidence_use_ids):
            raise LedgerCorruptionError(
                f"Event {event.event_id} evidence use identity is not reproducible"
            )
        for ref in new_refs:
            _advance_entry_identity(
                seen_entry_identities,
                ref,
                LedgerCorruptionError,
                strict_source_attributes=(
                    event.governance_version != LEGACY_GOVERNANCE_VERSION
                ),
            )
        resolution_refs = new_refs
        if event.action == "UPDATE" and len(parents) == 1 and parents[0].proposal is not None:
            proposal = parents[0].proposal
            if _normalise_text(output.fact_value) == _normalise_text(proposal.fact_value):
                resolution_refs = merge_evidence_refs(proposal.evidence_refs, new_refs)
            elif _normalise_text(output.fact_value) == _normalise_text(parents[0].fact_value):
                resolution_refs = merge_evidence_refs(parents[0].evidence_refs, new_refs)
        try:
            validate_resolution_basis(
                parents,
                resolution_refs,
                event.conflict,
                event.resolution_basis,
                event.resolution_metadata,
                output.fact_value,
                allow_unresolved=event.action == "CONTEST",
                algorithm_version=event.algorithm_version,
                governance_version=event.governance_version,
                topic=event.topic,
                fact_key=conflict_fact_key,
            )
        except TransitionValidationError as exc:
            raise LedgerCorruptionError(
                f"Event {event.event_id} has an invalid resolution basis: {exc}"
            ) from exc

        if event.action == "CREATE":
            if parents or output.revision != 1 or output.state != "active":
                raise LedgerCorruptionError("CREATE must make an active revision 1 with no parents")
            if output.card_id in active:
                raise LedgerCorruptionError("CREATE reuses an active card_id")
        elif event.action in {"UPDATE", "RETIRE", "CONTEST"}:
            if len(parents) != 1:
                raise LedgerCorruptionError(f"{event.action} must have exactly one parent")
            parent = parents[0]
            if active.get(parent.card_id) != parent.version_id:
                raise LedgerCorruptionError(f"{event.action} parent is not an active head")
            if output.card_id != parent.card_id or output.revision != parent.revision + 1:
                raise LedgerCorruptionError(f"{event.action} must advance the same card by one revision")
            if event.action == "UPDATE" and output.state != "active":
                raise LedgerCorruptionError("UPDATE output must be active")
            if event.action == "RETIRE" and output.state != "retired":
                raise LedgerCorruptionError("RETIRE output must be retired")
            if event.action == "CONTEST":
                if parent.state != "active" or output.state != "contested":
                    raise LedgerCorruptionError(
                        "CONTEST must advance an active parent to a contested version"
                    )
            active.pop(parent.card_id)
        else:  # MERGE
            if len(parents) < 2 or output.revision != 1 or output.state != "active":
                raise LedgerCorruptionError("MERGE needs 2+ parents and a new active revision 1")
            parent_cards = {parent.card_id for parent in parents}
            if output.card_id in parent_cards:
                raise LedgerCorruptionError("MERGE output must have a new card_id")
            for parent in parents:
                if active.get(parent.card_id) != parent.version_id:
                    raise LedgerCorruptionError("MERGE parent is not an active head")
                active.pop(parent.card_id)

        if output.state in {"active", "contested"}:
            active[output.card_id] = output.version_id
        seen_versions.add(output_id)
        for ref in new_refs:
            use_id = evidence_use_identity(
                ref.entry_id,
                atomic_claim_identity,
                locator_identity(ref.locator),
            )
            if use_id in seen_evidence_uses:
                raise LedgerCorruptionError(
                    f"Evidence {ref.entry_id} supports the same atomic claim more than once"
                )
            seen_evidence_uses[use_id] = (
                event.event_id,
                ref.entry_id,
                atomic_claim_identity,
                ref.content_hash,
            )
            if schema_version == 2:
                schema2_use_id = legacy_evidence_use_identity(
                    ref.entry_id,
                    atomic_claim_identity,
                )
                if schema2_use_id in seen_schema2_uses:
                    raise LedgerCorruptionError(
                        f"Legacy evidence {ref.entry_id} supports the same claim more than once"
                    )
                seen_schema2_uses[schema2_use_id] = (event.event_id, ref.content_hash)
            if schema_version == 1:
                if ref.entry_id in seen_legacy_evidence:
                    raise LedgerCorruptionError(
                        f"Legacy evidence {ref.entry_id} was processed more than once"
                    )
                seen_legacy_evidence[ref.entry_id] = (event.event_id, ref.content_hash)

    if seen_versions != set(versions_by_id):
        raise LedgerCorruptionError("Ledger contains a version not emitted by any event")
    if schema_version == 1:
        if set(raw_processed) != set(seen_legacy_evidence):
            raise LedgerCorruptionError(
                "Legacy processed_evidence does not match transition evidence events"
            )
        for evidence_id, (event_id, content_hash) in seen_legacy_evidence.items():
            record = raw_processed.get(evidence_id)
            if not isinstance(record, Mapping) or record.get("event_id") != event_id:
                raise LedgerCorruptionError(
                    f"Legacy processed evidence record is invalid: {evidence_id}"
                )
            if str(record.get("content_hash", "")) != content_hash:
                raise LedgerCorruptionError(
                    f"Legacy processed evidence hash is invalid: {evidence_id}"
                )
    elif schema_version == 2:
        if set(raw_processed) != set(seen_schema2_uses):
            raise LedgerCorruptionError(
                "Schema 2 processed_evidence does not match transition evidence uses"
            )
        for use_id, (event_id, content_hash) in seen_schema2_uses.items():
            record = raw_processed.get(use_id)
            if not isinstance(record, Mapping) or record.get("event_id") != event_id:
                raise LedgerCorruptionError(
                    f"Schema 2 processed evidence use is invalid: {use_id}"
                )
            if str(record.get("content_hash", "")) != content_hash:
                raise LedgerCorruptionError(
                    f"Schema 2 processed evidence hash is invalid: {use_id}"
                )
    else:
        if set(raw_processed) != set(seen_evidence_uses):
            raise LedgerCorruptionError(
                "processed_evidence does not match transition evidence uses"
            )
        for use_id, expected in seen_evidence_uses.items():
            event_id, entry_id, atomic_claim_identity, content_hash = expected
            record = raw_processed.get(use_id)
            if not isinstance(record, Mapping):
                raise LedgerCorruptionError(f"Processed evidence use is invalid: {use_id}")
            if (
                record.get("event_id") != event_id
                or record.get("entry_id") != entry_id
                or record.get("claim_identity") != atomic_claim_identity
            ):
                raise LedgerCorruptionError(f"Processed evidence use is invalid: {use_id}")
            if str(record.get("content_hash", "")) != content_hash:
                raise LedgerCorruptionError(f"Processed evidence hash is invalid: {use_id}")
            event = next(item for item in events if item.event_id == event_id)
            output = versions_by_id[event.output_version_ids[0]]
            ref = next(
                item
                for item in _event_new_refs(event, output)
                if evidence_use_identity(
                    item.entry_id,
                    claim_identity_for_version(output, event.action),
                    locator_identity(item.locator),
                )
                == use_id
            )
            if record.get("locator_identity") != locator_identity(ref.locator):
                raise LedgerCorruptionError(
                    f"Processed evidence locator is invalid: {use_id}"
                )
            if str(record.get("evidence_digest", "")) != ref.evidence_digest:
                raise LedgerCorruptionError(
                    f"Processed evidence digest is invalid: {use_id}"
                )
            if str(record.get("source_key", "")) != ref.source_key:
                raise LedgerCorruptionError(
                    f"Processed evidence source identity is invalid: {use_id}"
                )

    return MemorySnapshot(
        versions=versions,
        events=events,
        active_heads=MappingProxyType(dict(active)),
        versions_by_id=MappingProxyType(versions_by_id),
        processed_evidence=MappingProxyType(
            {use_id: values[0] for use_id, values in seen_evidence_uses.items()}
        ),
    )


def _upgrade_ledger_state(raw: dict) -> None:
    """Migrate a validated v1-v3 ledger to the atomic-batch schema."""
    if raw.get("schema_version") == SCHEMA_VERSION:
        return
    snapshot = _decode_and_replay(raw)
    old_schema = raw.get("schema_version")
    materialised_events: list[dict[str, object]] = []
    for raw_event, event in zip(raw["events"], snapshot.events, strict=True):
        output = snapshot.versions_by_id[event.output_version_ids[0]]
        atomic_claim_identity = claim_identity_for_version(output, event.action)
        materialised = dict(raw_event)
        materialised["algorithm_version"] = event.algorithm_version
        materialised["governance_version"] = event.governance_version
        materialised["evidence_use_ids"] = [
            evidence_use_identity(
                ref.entry_id,
                atomic_claim_identity,
                locator_identity(ref.locator),
            )
            for ref in _event_new_refs(event, output)
        ]
        materialised_events.append(materialised)
    raw["events"] = materialised_events
    if old_schema == SPAN_IDENTITY_SCHEMA_VERSION:
        raw["schema_version"] = SCHEMA_VERSION
        raw["atomic_batches"] = []
        _decode_and_replay(raw)
        return
    legacy_processed = raw["processed_evidence"]
    migrated: dict[str, dict[str, str]] = {}
    for event in snapshot.events:
        output = snapshot.versions_by_id[event.output_version_ids[0]]
        atomic_claim_identity = claim_identity_for_version(output, event.action)
        for ref in _event_new_refs(event, output):
            legacy_key = (
                ref.entry_id
                if old_schema == 1
                else legacy_evidence_use_identity(ref.entry_id, atomic_claim_identity)
            )
            legacy_record = legacy_processed[legacy_key]
            ref_locator_identity = locator_identity(ref.locator)
            use_id = evidence_use_identity(
                ref.entry_id,
                atomic_claim_identity,
                ref_locator_identity,
            )
            migrated[use_id] = {
                "event_id": event.event_id,
                "entry_id": ref.entry_id,
                "claim_identity": atomic_claim_identity,
                "content_hash": ref.content_hash,
                "evidence_digest": ref.evidence_digest,
                "source_key": ref.source_key,
                "locator_identity": ref_locator_identity,
                "processed_at": str(legacy_record.get("processed_at", event.created_at)),
            }
    raw["schema_version"] = SCHEMA_VERSION
    raw["processed_evidence"] = migrated
    raw["atomic_batches"] = []
    _decode_and_replay(raw)
