"""Atomic persistence and full semantic replay for evidence memory."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from sheaf_ai._evidence_memory_models import (
    SCHEMA_VERSION,
    VALID_ACTIONS,
    VALID_TIERS,
    CardVersion,
    EvidenceMemoryError,
    LedgerCorruptionError,
    MemorySnapshot,
    TransitionEvent,
    TransitionValidationError,
)
from sheaf_ai._evidence_memory_rules import (
    _normalise_text,
    assess_transition_conflict,
    compute_evidence_strength,
    merge_evidence_refs,
    validate_resolution_basis,
)


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


def _empty_ledger() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "events": [],
        "versions": [],
        "processed_evidence": {},
    }


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


def _decode_and_replay(raw: Mapping[str, object]) -> MemorySnapshot:
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise LedgerCorruptionError(
            f"Unsupported evidence ledger schema: {raw.get('schema_version')!r}"
        )
    raw_events = raw.get("events")
    raw_versions = raw.get("versions")
    raw_processed = raw.get("processed_evidence")
    if not isinstance(raw_events, list) or not isinstance(raw_versions, list):
        raise LedgerCorruptionError("Ledger events and versions must be arrays")
    if not isinstance(raw_processed, dict):
        raise LedgerCorruptionError("Ledger processed_evidence must be an object")
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

    active: dict[str, str] = {}
    seen_versions: set[str] = set()
    seen_evidence: dict[str, str] = {}
    for event in events:
        if event.action not in VALID_ACTIONS:
            raise LedgerCorruptionError(f"Unknown transition action: {event.action!r}")
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
        all_refs = output.evidence_refs + (
            output.proposal.evidence_refs if output.proposal is not None else ()
        )
        ref_ids = [ref.entry_id for ref in all_refs]
        if any(
            not ref.entry_id
            or ref.source_tier not in VALID_TIERS
            or not ref.source_key
            for ref in all_refs
        ):
            raise LedgerCorruptionError(f"Version {output_id} has invalid evidence references")
        if len(set(ref_ids)) != len(ref_ids):
            raise LedgerCorruptionError(f"Version {output_id} repeats an evidence reference")
        if not set(event.evidence_ids).issubset(ref_ids):
            raise LedgerCorruptionError(f"Event {event.event_id} evidence is absent from its output")
        expected_strength = compute_evidence_strength(
            output.evidence_refs,
            conflict=event.conflict.state == "conflict",
        )
        if output.strength != expected_strength:
            raise LedgerCorruptionError(f"Version {output_id} evidence strength is not reproducible")
        if output.proposal is not None:
            expected_proposal_strength = compute_evidence_strength(
                output.proposal.evidence_refs,
                conflict=True,
            )
            if output.proposal.strength != expected_proposal_strength:
                raise LedgerCorruptionError(
                    f"Version {output_id} proposal strength is not reproducible"
                )

        new_refs = tuple(ref for ref in all_refs if ref.entry_id in event.evidence_ids)
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
        for evidence_id in event.evidence_ids:
            if evidence_id in seen_evidence:
                raise LedgerCorruptionError(f"Evidence {evidence_id} was processed more than once")
            seen_evidence[evidence_id] = event.event_id

    if seen_versions != set(versions_by_id):
        raise LedgerCorruptionError("Ledger contains a version not emitted by any event")
    processed_ids = set(raw_processed)
    if processed_ids != set(seen_evidence):
        raise LedgerCorruptionError("processed_evidence does not match transition evidence events")
    for evidence_id, event_id in seen_evidence.items():
        record = raw_processed.get(evidence_id)
        if not isinstance(record, Mapping) or record.get("event_id") != event_id:
            raise LedgerCorruptionError(f"Processed evidence record is invalid: {evidence_id}")
        event = next(item for item in events if item.event_id == event_id)
        output = versions_by_id[event.output_version_ids[0]]
        output_refs = output.evidence_refs + (
            output.proposal.evidence_refs if output.proposal is not None else ()
        )
        ref = next(item for item in output_refs if item.entry_id == evidence_id)
        if str(record.get("content_hash", "")) != ref.content_hash:
            raise LedgerCorruptionError(f"Processed evidence hash is invalid: {evidence_id}")

    return MemorySnapshot(
        versions=versions,
        events=events,
        active_heads=MappingProxyType(dict(active)),
        versions_by_id=MappingProxyType(versions_by_id),
        processed_evidence=MappingProxyType(dict(seen_evidence)),
    )


