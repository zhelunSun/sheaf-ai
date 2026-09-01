"""Auditable preview and execution policy for compound memory decisions.

The evidence-memory ledger intentionally understands only atomic lifecycle
transitions.  This module sits one level above it: it records a decision before
execution and expands a ``SPLIT`` suggestion into one ``UPDATE`` plus one
``CREATE``.  A split is executed only through an explicitly atomic, idempotent
batch executor.  It never emulates atomicity with two sequential calls.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, Protocol, Sequence, runtime_checkable


DECISION_LEDGER_SCHEMA_VERSION = 1
DECISION_POLICY_VERSION = "evidence-policy-v1"
DECISION_ALGORITHM_VERSION = "split-noop-v1"

_GENESIS_HASH = "0" * 64
_VALID_SUGGESTIONS = frozenset({"NOOP", "SPLIT"})
_VALID_STATUSES = frozenset({"PREVIEWED", "NOOP", "APPLIED", "FAILED"})


class EvidencePolicyError(RuntimeError):
    """Base class for decision-policy failures."""


class DecisionValidationError(EvidencePolicyError):
    """A decision request or status transition violates the policy contract."""


class DecisionLedgerCorruptionError(EvidencePolicyError):
    """The decision ledger is unreadable or fails its integrity chain."""


class StaleDecisionError(EvidencePolicyError):
    """A previewed target is no longer the active version at apply time."""


class AtomicBatchRequiredError(EvidencePolicyError):
    """A SPLIT was given an executor without an atomic batch protocol."""


class DecisionExecutionError(EvidencePolicyError):
    """An atomic batch executor rejected or failed a SPLIT."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DecisionValidationError(
            "Decision inputs must be finite JSON-compatible values"
        ) from exc


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_clone(value: object) -> object:
    """Detach audit inputs from mutable caller-owned objects."""
    try:
        return json.loads(_canonical_json(value))
    except json.JSONDecodeError as exc:  # pragma: no cover - canonical JSON is valid
        raise DecisionValidationError("Decision inputs could not be normalised") from exc


def _normalise_ids(values: Sequence[object]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


@dataclass(frozen=True)
class TargetHead:
    """The exact active version a preview was based on."""

    card_id: str
    version_id: str

    def to_dict(self) -> dict[str, str]:
        return {"card_id": self.card_id, "version_id": self.version_id}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "TargetHead":
        return cls(
            card_id=str(data.get("card_id", "")),
            version_id=str(data.get("version_id", "")),
        )


@dataclass(frozen=True)
class PlannedOperation:
    """One executor request belonging to a previewed compound decision."""

    decision_id: str
    operation: str
    target_card_ids: tuple[str, ...]
    target_heads: tuple[TargetHead, ...]
    request: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "operation": self.operation,
            "target_card_ids": list(self.target_card_ids),
            "target_heads": [head.to_dict() for head in self.target_heads],
            "request": _json_clone(self.request),
        }

    def request_identity(self) -> dict[str, object]:
        """Return the operation content excluding generated decision identity."""
        return {
            "operation": self.operation,
            "target_card_ids": list(self.target_card_ids),
            "target_heads": [head.to_dict() for head in self.target_heads],
            "request": _json_clone(self.request),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "PlannedOperation":
        raw_heads = data.get("target_heads", [])
        raw_request = data.get("request", {})
        raw_targets = data.get("target_card_ids", [])
        if (
            not isinstance(raw_heads, list)
            or not all(isinstance(item, Mapping) for item in raw_heads)
            or not isinstance(raw_request, Mapping)
            or not isinstance(raw_targets, list)
        ):
            raise DecisionLedgerCorruptionError("Malformed planned operation")
        try:
            return cls(
                decision_id=str(data.get("decision_id", "")),
                operation=str(data.get("operation", "")),
                target_card_ids=tuple(str(item) for item in raw_targets),
                target_heads=tuple(TargetHead.from_dict(item) for item in raw_heads),
                request=_json_clone(dict(raw_request)),  # type: ignore[arg-type]
            )
        except (DecisionValidationError, TypeError, ValueError) as exc:
            raise DecisionLedgerCorruptionError("Malformed planned operation") from exc


@dataclass(frozen=True)
class DecisionTrace:
    """Preview-first, immutable audit view of a NOOP or SPLIT decision."""

    decision_id: str
    input_snapshot: dict[str, object]
    request_hash: str
    policy_version: str
    algorithm_version: str
    suggested_operation: str
    reason: str
    evidence_ids: tuple[str, ...]
    target_heads: tuple[TargetHead, ...]
    operations: tuple[PlannedOperation, ...]
    created_at: str
    status: str
    idempotency_key: str
    failure_reason: str = ""
    applied_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "input_snapshot": _json_clone(self.input_snapshot),
            "request_hash": self.request_hash,
            "policy_version": self.policy_version,
            "algorithm_version": self.algorithm_version,
            "suggested_operation": self.suggested_operation,
            "reason": self.reason,
            "evidence_ids": list(self.evidence_ids),
            "target_heads": [head.to_dict() for head in self.target_heads],
            "operations": [operation.to_dict() for operation in self.operations],
            "created_at": self.created_at,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "failure_reason": self.failure_reason,
            "applied_at": self.applied_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "DecisionTrace":
        raw_snapshot = data.get("input_snapshot", {})
        raw_heads = data.get("target_heads", [])
        raw_operations = data.get("operations", [])
        raw_evidence_ids = data.get("evidence_ids", [])
        if (
            not isinstance(raw_snapshot, Mapping)
            or not isinstance(raw_heads, list)
            or not all(isinstance(item, Mapping) for item in raw_heads)
            or not isinstance(raw_operations, list)
            or not all(isinstance(item, Mapping) for item in raw_operations)
            or not isinstance(raw_evidence_ids, list)
        ):
            raise DecisionLedgerCorruptionError("Malformed decision trace")
        try:
            return cls(
                decision_id=str(data.get("decision_id", "")),
                input_snapshot=_json_clone(dict(raw_snapshot)),  # type: ignore[arg-type]
                request_hash=str(data.get("request_hash", "")),
                policy_version=str(data.get("policy_version", "")),
                algorithm_version=str(data.get("algorithm_version", "")),
                suggested_operation=str(data.get("suggested_operation", "")),
                reason=str(data.get("reason", "")),
                evidence_ids=tuple(str(item) for item in raw_evidence_ids),
                target_heads=tuple(TargetHead.from_dict(item) for item in raw_heads),
                operations=tuple(
                    PlannedOperation.from_dict(item) for item in raw_operations
                ),
                created_at=str(data.get("created_at", "")),
                status=str(data.get("status", "")),
                idempotency_key=str(data.get("idempotency_key", "")),
                failure_reason=str(data.get("failure_reason", "")),
                applied_at=str(data.get("applied_at", "")),
            )
        except (DecisionValidationError, TypeError, ValueError) as exc:
            raise DecisionLedgerCorruptionError("Malformed decision trace") from exc


@runtime_checkable
class AtomicDecisionBatchExecutor(Protocol):
    """Executor contract required for SPLIT.

    Implementations must commit all operations or none, and must treat
    ``idempotency_key`` as exactly-once identity across retries.  Returning
    normally means the complete batch committed.
    """

    def execute_atomic(
        self,
        operations: tuple[PlannedOperation, ...],
        *,
        decision_id: str,
        idempotency_key: str,
    ) -> object:
        """Atomically execute the complete decision batch."""


def _request_document(trace: DecisionTrace) -> dict[str, object]:
    return {
        "input_snapshot": _json_clone(trace.input_snapshot),
        "policy_version": trace.policy_version,
        "algorithm_version": trace.algorithm_version,
        "suggested_operation": trace.suggested_operation,
        "reason": trace.reason,
        "evidence_ids": list(trace.evidence_ids),
        "target_heads": [head.to_dict() for head in trace.target_heads],
        "operations": [operation.request_identity() for operation in trace.operations],
    }


def _immutable_trace_identity(trace: DecisionTrace) -> dict[str, object]:
    data = trace.to_dict()
    data.pop("status")
    data.pop("failure_reason")
    data.pop("applied_at")
    return data


def _validate_trace(trace: DecisionTrace, *, corruption: bool = False) -> None:
    error_type = DecisionLedgerCorruptionError if corruption else DecisionValidationError
    if (
        not trace.decision_id
        or not trace.reason
        or not trace.created_at
        or not trace.idempotency_key
    ):
        raise error_type("Decision trace is missing required audit identity")
    if trace.suggested_operation not in _VALID_SUGGESTIONS:
        raise error_type(f"Unsupported suggested operation: {trace.suggested_operation!r}")
    if trace.status not in _VALID_STATUSES:
        raise error_type(f"Unsupported decision status: {trace.status!r}")
    if not trace.policy_version or not trace.algorithm_version:
        raise error_type("Decision trace is missing policy or algorithm version")
    if len({head.card_id for head in trace.target_heads}) != len(trace.target_heads):
        raise error_type("Decision trace repeats a target card")
    if any(not head.card_id or not head.version_id for head in trace.target_heads):
        raise error_type("Decision trace has an incomplete target head")
    if any(operation.decision_id != trace.decision_id for operation in trace.operations):
        raise error_type("Planned operation does not share its decision_id")

    if trace.suggested_operation == "NOOP":
        if trace.operations:
            raise error_type("NOOP cannot contain executor operations")
        if trace.status not in {"PREVIEWED", "NOOP"}:
            raise error_type("NOOP has an invalid status")
    else:
        if trace.status not in {"PREVIEWED", "FAILED", "APPLIED"}:
            raise error_type("SPLIT has an invalid status")
        if tuple(operation.operation for operation in trace.operations) != (
            "UPDATE",
            "CREATE",
        ):
            raise error_type("SPLIT must expand to UPDATE followed by CREATE")
        if len(trace.target_heads) != 1:
            raise error_type("SPLIT requires exactly one target head")
        update, create = trace.operations
        target = trace.target_heads[0]
        if update.target_card_ids != (target.card_id,) or update.target_heads != (target,):
            raise error_type("SPLIT UPDATE does not bind the previewed target head")
        if create.target_card_ids or create.target_heads:
            raise error_type("SPLIT CREATE cannot target an existing head")

    if trace.status == "FAILED" and not trace.failure_reason:
        raise error_type("FAILED decision is missing a failure reason")
    if trace.status in {"NOOP", "APPLIED"} and not trace.applied_at:
        raise error_type("Terminal decision is missing its applied timestamp")
    if trace.status == "PREVIEWED" and (trace.failure_reason or trace.applied_at):
        raise error_type("PREVIEWED decision contains terminal status metadata")

    try:
        expected_hash = _canonical_hash(_request_document(trace))
    except DecisionValidationError as exc:
        raise error_type("Decision trace contains non-canonical JSON values") from exc
    if trace.request_hash != expected_hash:
        raise error_type("Decision request hash does not match its inputs")


_LOCKS_GUARD = threading.Lock()
_LEDGER_LOCKS: dict[str, threading.RLock] = {}


def _ledger_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LEDGER_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    """Use the platform file lock so read-check-write is cross-process atomic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":  # pragma: no cover - exercised on Windows CI/hosts
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:  # pragma: no cover - platform-specific branch
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class DecisionTraceLedger:
    """Hash-chained append-only decision records stored via atomic JSON replace."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _ledger_lock(self.path)
        self._lock_path = self.path.with_name(f".{self.path.name}.lock")
        with self._lock:
            with _exclusive_file_lock(self._lock_path):
                if not self.path.exists():
                    self._write_unlocked(
                        {
                            "schema_version": DECISION_LEDGER_SCHEMA_VERSION,
                            "records": [],
                        }
                    )
                else:
                    self._read_unlocked()

    def _read_unlocked(self) -> dict[str, object]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DecisionLedgerCorruptionError(
                f"Cannot read decision ledger {self.path}: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise DecisionLedgerCorruptionError("Decision ledger root must be an object")
        self._replay(raw)
        return raw

    def _write_unlocked(self, state: Mapping[str, object]) -> None:
        payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)
        tmp_path: str | None = None
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
            raise EvidencePolicyError(f"Cannot write decision ledger {self.path}: {exc}") from exc

    @staticmethod
    def _replay(raw: Mapping[str, object]) -> tuple[DecisionTrace, ...]:
        if raw.get("schema_version") != DECISION_LEDGER_SCHEMA_VERSION:
            raise DecisionLedgerCorruptionError(
                f"Unsupported decision ledger schema: {raw.get('schema_version')!r}"
            )
        records = raw.get("records")
        if not isinstance(records, list):
            raise DecisionLedgerCorruptionError("Decision ledger records must be an array")

        previous_hash = _GENESIS_HASH
        latest: dict[str, DecisionTrace] = {}
        order: list[str] = []
        keys: dict[str, str] = {}
        for sequence, raw_record in enumerate(records, 1):
            if not isinstance(raw_record, Mapping):
                raise DecisionLedgerCorruptionError("Malformed decision ledger record")
            record = dict(raw_record)
            record_hash = str(record.pop("record_hash", ""))
            if record.get("sequence") != sequence:
                raise DecisionLedgerCorruptionError("Decision ledger sequence is not contiguous")
            if record.get("previous_hash") != previous_hash:
                raise DecisionLedgerCorruptionError("Decision ledger hash chain is broken")
            try:
                expected_record_hash = _canonical_hash(record)
            except DecisionValidationError as exc:
                raise DecisionLedgerCorruptionError(
                    "Decision ledger record contains non-canonical JSON values"
                ) from exc
            if record_hash != expected_record_hash:
                raise DecisionLedgerCorruptionError("Decision ledger record hash is invalid")
            raw_trace = record.get("trace")
            if not isinstance(raw_trace, Mapping):
                raise DecisionLedgerCorruptionError("Decision ledger record has no trace")
            trace = DecisionTrace.from_dict(raw_trace)
            _validate_trace(trace, corruption=True)
            if record.get("decision_id") != trace.decision_id:
                raise DecisionLedgerCorruptionError("Record and trace decision_id disagree")

            prior = latest.get(trace.decision_id)
            if prior is None:
                if trace.status != "PREVIEWED":
                    raise DecisionLedgerCorruptionError(
                        "A decision history must begin with PREVIEWED"
                    )
                if trace.idempotency_key in keys:
                    raise DecisionLedgerCorruptionError("Duplicate decision idempotency key")
                keys[trace.idempotency_key] = trace.request_hash
                order.append(trace.decision_id)
            else:
                if _immutable_trace_identity(prior) != _immutable_trace_identity(trace):
                    raise DecisionLedgerCorruptionError(
                        "A status record changed immutable decision inputs"
                    )
                allowed = {
                    ("PREVIEWED", "NOOP"),
                    ("PREVIEWED", "APPLIED"),
                    ("PREVIEWED", "FAILED"),
                    ("FAILED", "FAILED"),
                    ("FAILED", "APPLIED"),
                }
                if (prior.status, trace.status) not in allowed:
                    raise DecisionLedgerCorruptionError("Invalid decision status transition")
            latest[trace.decision_id] = trace
            previous_hash = record_hash
        return tuple(latest[decision_id] for decision_id in order)

    @staticmethod
    def _append_record(state: dict[str, object], trace: DecisionTrace) -> None:
        records = state["records"]
        if not isinstance(records, list):  # validated before every append
            raise DecisionLedgerCorruptionError("Decision ledger records must be an array")
        previous_hash = str(records[-1]["record_hash"]) if records else _GENESIS_HASH
        record: dict[str, object] = {
            "sequence": len(records) + 1,
            "previous_hash": previous_hash,
            "decision_id": trace.decision_id,
            "recorded_at": _now_iso(),
            "trace": trace.to_dict(),
        }
        record["record_hash"] = _canonical_hash(record)
        records.append(record)

    def append_preview(self, trace: DecisionTrace) -> DecisionTrace:
        """Persist a preview, returning the prior trace on an exact retry."""
        _validate_trace(trace)
        if trace.status != "PREVIEWED":
            raise DecisionValidationError("A new decision must be PREVIEWED")
        with self._lock:
            with _exclusive_file_lock(self._lock_path):
                state = self._read_unlocked()
                traces = self._replay(state)
                for prior in traces:
                    if prior.idempotency_key == trace.idempotency_key:
                        if prior.request_hash != trace.request_hash:
                            raise DecisionValidationError(
                                f"Idempotency key {trace.idempotency_key!r} "
                                "was reused for a different decision"
                            )
                        return prior
                    if prior.decision_id == trace.decision_id:
                        raise DecisionValidationError(
                            f"Decision id already exists: {trace.decision_id}"
                        )
                self._append_record(state, trace)
                self._write_unlocked(state)
                return trace

    def record_status(
        self,
        decision_id: str,
        status: str,
        *,
        failure_reason: str = "",
    ) -> DecisionTrace:
        """Append a status event without rewriting the preview record."""
        with self._lock:
            with _exclusive_file_lock(self._lock_path):
                state = self._read_unlocked()
                traces = self._replay(state)
                prior = next(
                    (trace for trace in traces if trace.decision_id == decision_id),
                    None,
                )
                if prior is None:
                    raise DecisionValidationError(f"Unknown decision id: {decision_id}")
                if prior.status == status and status in {"NOOP", "APPLIED"}:
                    return prior
                updated = replace(
                    prior,
                    status=status,
                    failure_reason=str(failure_reason).strip(),
                    applied_at=_now_iso() if status in {"NOOP", "APPLIED"} else "",
                )
                _validate_trace(updated)
                self._append_record(state, updated)
                self._replay(state)
                self._write_unlocked(state)
                return updated

    def snapshot(self) -> tuple[DecisionTrace, ...]:
        with self._lock:
            with _exclusive_file_lock(self._lock_path):
                return self._replay(self._read_unlocked())

    def get(self, decision_id: str) -> DecisionTrace:
        trace = next(
            (item for item in self.snapshot() if item.decision_id == decision_id),
            None,
        )
        if trace is None:
            raise DecisionValidationError(f"Unknown decision id: {decision_id}")
        return trace


class EvidenceDecisionPolicy:
    """Create decision previews and apply them under fail-closed rules."""

    def __init__(
        self,
        ledger: DecisionTraceLedger | Path,
        *,
        policy_version: str = DECISION_POLICY_VERSION,
        algorithm_version: str = DECISION_ALGORITHM_VERSION,
    ):
        self.ledger = (
            ledger if isinstance(ledger, DecisionTraceLedger) else DecisionTraceLedger(ledger)
        )
        self.policy_version = str(policy_version).strip()
        self.algorithm_version = str(algorithm_version).strip()
        if not self.policy_version or not self.algorithm_version:
            raise DecisionValidationError("Policy and algorithm versions are required")

    @staticmethod
    def _heads(target_heads: Mapping[object, object]) -> tuple[TargetHead, ...]:
        heads = tuple(
            sorted(
                (
                    TargetHead(str(card_id).strip(), str(version_id).strip())
                    for card_id, version_id in target_heads.items()
                ),
                key=lambda head: head.card_id,
            )
        )
        if any(not head.card_id or not head.version_id for head in heads):
            raise DecisionValidationError("Target card and version ids must be non-empty")
        if len({head.card_id for head in heads}) != len(heads):
            raise DecisionValidationError("Target card ids must be unique")
        return heads

    def _preview(
        self,
        *,
        suggested_operation: str,
        input_snapshot: Mapping[str, object],
        reason: str,
        evidence_ids: Sequence[object],
        target_heads: Mapping[object, object],
        update_request: Mapping[str, object] | None,
        create_request: Mapping[str, object] | None,
        idempotency_key: str,
        decision_id: str,
    ) -> DecisionTrace:
        suggestion = str(suggested_operation).upper().strip()
        reason = str(reason).strip()
        if suggestion not in _VALID_SUGGESTIONS:
            raise DecisionValidationError(f"Unsupported suggested operation: {suggestion!r}")
        if not reason:
            raise DecisionValidationError("Decision reason is required for auditability")
        snapshot = _json_clone(dict(input_snapshot))
        if not isinstance(snapshot, dict):  # for type checkers and defensive clarity
            raise DecisionValidationError("Input snapshot must be a JSON object")
        evidence = _normalise_ids(evidence_ids)
        heads = self._heads(target_heads)

        placeholder_id = "pending"
        if suggestion == "NOOP":
            if update_request is not None or create_request is not None:
                raise DecisionValidationError("NOOP cannot carry split requests")
            operations: tuple[PlannedOperation, ...] = ()
        else:
            if len(heads) != 1:
                raise DecisionValidationError("SPLIT requires exactly one target head")
            if update_request is None or create_request is None:
                raise DecisionValidationError("SPLIT requires UPDATE and CREATE requests")
            update_payload = _json_clone(dict(update_request))
            create_payload = _json_clone(dict(create_request))
            if not isinstance(update_payload, dict) or not isinstance(create_payload, dict):
                raise DecisionValidationError("SPLIT requests must be JSON objects")
            target = heads[0]
            operations = (
                PlannedOperation(
                    decision_id=placeholder_id,
                    operation="UPDATE",
                    target_card_ids=(target.card_id,),
                    target_heads=(target,),
                    request=update_payload,
                ),
                PlannedOperation(
                    decision_id=placeholder_id,
                    operation="CREATE",
                    target_card_ids=(),
                    target_heads=(),
                    request=create_payload,
                ),
            )

        provisional = DecisionTrace(
            decision_id=placeholder_id,
            input_snapshot=snapshot,
            request_hash="",
            policy_version=self.policy_version,
            algorithm_version=self.algorithm_version,
            suggested_operation=suggestion,
            reason=reason,
            evidence_ids=evidence,
            target_heads=heads,
            operations=operations,
            created_at="pending",
            status="PREVIEWED",
            idempotency_key="pending",
        )
        request_hash = _canonical_hash(_request_document(provisional))
        resolved_decision_id = str(decision_id).strip() or f"decision_{uuid.uuid4().hex}"
        resolved_key = str(idempotency_key).strip() or f"auto:{request_hash}"
        bound_operations = tuple(
            replace(operation, decision_id=resolved_decision_id)
            for operation in operations
        )
        trace = replace(
            provisional,
            decision_id=resolved_decision_id,
            request_hash=request_hash,
            operations=bound_operations,
            created_at=_now_iso(),
            idempotency_key=resolved_key,
        )
        return self.ledger.append_preview(trace)

    def preview_noop(
        self,
        *,
        input_snapshot: Mapping[str, object],
        reason: str,
        evidence_ids: Sequence[object] = (),
        target_heads: Mapping[object, object] | None = None,
        idempotency_key: str = "",
        decision_id: str = "",
    ) -> DecisionTrace:
        return self._preview(
            suggested_operation="NOOP",
            input_snapshot=input_snapshot,
            reason=reason,
            evidence_ids=evidence_ids,
            target_heads=target_heads or {},
            update_request=None,
            create_request=None,
            idempotency_key=idempotency_key,
            decision_id=decision_id,
        )

    def preview_split(
        self,
        *,
        input_snapshot: Mapping[str, object],
        reason: str,
        evidence_ids: Sequence[object],
        target_heads: Mapping[object, object],
        update_request: Mapping[str, object],
        create_request: Mapping[str, object],
        idempotency_key: str = "",
        decision_id: str = "",
    ) -> DecisionTrace:
        return self._preview(
            suggested_operation="SPLIT",
            input_snapshot=input_snapshot,
            reason=reason,
            evidence_ids=evidence_ids,
            target_heads=target_heads,
            update_request=update_request,
            create_request=create_request,
            idempotency_key=idempotency_key,
            decision_id=decision_id,
        )

    def apply_decision(
        self,
        decision_id: str,
        *,
        current_heads: Mapping[object, object],
        executor: AtomicDecisionBatchExecutor | None = None,
    ) -> DecisionTrace:
        """Apply a preview or return its terminal trace on an idempotent retry."""
        trace = self.ledger.get(str(decision_id).strip())
        if trace.status in {"NOOP", "APPLIED"}:
            return trace
        if trace.suggested_operation == "NOOP":
            return self.ledger.record_status(trace.decision_id, "NOOP")

        actual_heads = {
            str(card_id).strip(): str(version_id).strip()
            for card_id, version_id in current_heads.items()
        }
        stale = [
            head
            for head in trace.target_heads
            if actual_heads.get(head.card_id) != head.version_id
        ]
        if stale:
            detail = "; ".join(
                f"{head.card_id}: expected {head.version_id}, "
                f"found {actual_heads.get(head.card_id, '<missing>')}"
                for head in stale
            )
            self.ledger.record_status(
                trace.decision_id,
                "FAILED",
                failure_reason=f"Target head changed before apply ({detail})",
            )
            raise StaleDecisionError(f"Target head changed before apply ({detail})")

        execute_atomic = getattr(executor, "execute_atomic", None)
        if executor is None or not callable(execute_atomic):
            raise AtomicBatchRequiredError(
                "SPLIT requires an atomic batch executor; sequential transition calls "
                "are not permitted"
            )
        try:
            execute_atomic(
                trace.operations,
                decision_id=trace.decision_id,
                idempotency_key=trace.decision_id,
            )
        except Exception as exc:
            failure = f"Atomic SPLIT failed: {type(exc).__name__}: {exc}"
            self.ledger.record_status(
                trace.decision_id,
                "FAILED",
                failure_reason=failure,
            )
            raise DecisionExecutionError(failure) from exc
        return self.ledger.record_status(trace.decision_id, "APPLIED")


# Short alias for callers that prefer the module's name as the service name.
EvidencePolicy = EvidenceDecisionPolicy


__all__ = [
    "AtomicBatchRequiredError",
    "AtomicDecisionBatchExecutor",
    "DECISION_ALGORITHM_VERSION",
    "DECISION_LEDGER_SCHEMA_VERSION",
    "DECISION_POLICY_VERSION",
    "DecisionExecutionError",
    "DecisionLedgerCorruptionError",
    "DecisionTrace",
    "DecisionTraceLedger",
    "DecisionValidationError",
    "EvidenceDecisionPolicy",
    "EvidencePolicy",
    "EvidencePolicyError",
    "PlannedOperation",
    "StaleDecisionError",
    "TargetHead",
]
