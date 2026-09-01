"""Versioned provenance attestations for evidence governance.

This module deliberately separates integrity from authentication.  The SHA-256
event chain detects accidental corruption and edits to a registry document; it
does *not* prove who wrote the file.  Deployments that must resist an attacker
with write access to the registry need an external authenticated key or OS
keystore boundary in addition to this module.

Only the explicitly named ``admin_*`` functions mutate a registry.  Ordinary
collection code should use :func:`resolve_provenance`, whose failure modes are
fail-closed for governance grants but non-raising so content reads may continue.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.parse import urlsplit


REGISTRY_SCHEMA_VERSION = 1
EVENT_SCHEMA_VERSION = 1
INTEGRITY_MODEL = "sha256-hash-chain-no-authentication"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ACTIONS = frozenset({"ISSUE", "SUPERSEDE", "REVOKE"})
_EVIDENCE_TIERS = frozenset({"A", "B", "C", "D", "U"})
_MAX_TEXT = 2_000
_REGISTRY_THREAD_LOCKS_GUARD = threading.Lock()
_REGISTRY_THREAD_LOCKS: dict[str, threading.RLock] = {}


class ProvenanceRegistryError(Exception):
    """Base error for provenance registry operations."""


class RegistryValidationError(ProvenanceRegistryError, ValueError):
    """A caller or serialized field violates the registry schema."""


class RegistryCorruptionError(ProvenanceRegistryError):
    """A persisted registry is malformed or fails its hash-chain checks."""


class IdempotencyConflictError(ProvenanceRegistryError):
    """An idempotency key was reused for a different admin request."""


class AttestationStateError(ProvenanceRegistryError):
    """An attestation transition is invalid for its current state."""


def _require_text(name: str, value: Any, *, max_length: int = _MAX_TEXT) -> str:
    if type(value) is not str:  # bool/int coercion is intentionally forbidden
        raise RegistryValidationError(f"{name} must be a string")
    if not value or value != value.strip():
        raise RegistryValidationError(f"{name} must be non-empty and trimmed")
    if len(value) > max_length or "\x00" in value:
        raise RegistryValidationError(f"{name} is invalid")
    return value


def _require_digest(name: str, value: Any) -> str:
    value = _require_text(name, value, max_length=71)
    if not _SHA256_RE.fullmatch(value):
        raise RegistryValidationError(f"{name} must be a versioned full SHA-256 digest")
    return value


def canonicalize_origin(source_url: str) -> str:
    """Return the HTTP(S) origin used by exact registry bindings.

    Paths, queries, fragments and credentials are rejected because callers must
    consciously bind an origin, not accidentally treat a complete source URL as
    an origin-level attestation.
    """

    source_url = _require_text("canonical_origin", source_url, max_length=2_048)
    try:
        parsed = urlsplit(source_url)
        port = parsed.port
    except ValueError as exc:
        raise RegistryValidationError("canonical_origin is not a valid URL origin") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RegistryValidationError("canonical_origin must be an HTTP(S) origin")
    if parsed.username is not None or parsed.password is not None:
        raise RegistryValidationError("canonical_origin must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RegistryValidationError(
            "canonical_origin must not contain a path, query, or fragment"
        )

    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = f"[{host}]"
    default_port = (parsed.scheme == "http" and port == 80) or (
        parsed.scheme == "https" and port == 443
    )
    port_suffix = "" if port is None or default_port else f":{port}"
    return f"{parsed.scheme.lower()}://{host}{port_suffix}"


@dataclass(frozen=True)
class EvidenceSubject:
    entry_id: str
    canonical_origin: str
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "entry_id", _require_text("entry_id", self.entry_id, max_length=512)
        )
        canonical = canonicalize_origin(self.canonical_origin)
        if canonical != self.canonical_origin:
            raise RegistryValidationError(
                f"canonical_origin must already be canonical; expected {canonical!r}"
            )
        object.__setattr__(
            self,
            "evidence_digest",
            _require_digest("evidence_digest", self.evidence_digest),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "entry_id": self.entry_id,
            "canonical_origin": self.canonical_origin,
            "evidence_digest": self.evidence_digest,
        }

    @classmethod
    def from_dict(cls, value: Any) -> EvidenceSubject:
        data = _strict_mapping(
            "subject", value, {"entry_id", "canonical_origin", "evidence_digest"}
        )
        return cls(**data)


@dataclass(frozen=True, order=True)
class AuthorityScope:
    topic: str
    fact_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "topic", _require_text("topic", self.topic, max_length=512))
        object.__setattr__(
            self, "fact_key", _require_text("fact_key", self.fact_key, max_length=512)
        )

    def to_dict(self) -> dict[str, str]:
        return {"topic": self.topic, "fact_key": self.fact_key}

    @classmethod
    def from_dict(cls, value: Any) -> AuthorityScope:
        return cls(**_strict_mapping("authority_scope", value, {"topic", "fact_key"}))


@dataclass(frozen=True, order=True)
class CorrectionGrant:
    topic: str
    fact_key: str
    corrected_entry_id: str
    corrected_canonical_origin: str
    corrected_evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "topic", _require_text("topic", self.topic, max_length=512))
        object.__setattr__(
            self, "fact_key", _require_text("fact_key", self.fact_key, max_length=512)
        )
        object.__setattr__(
            self,
            "corrected_entry_id",
            _require_text("corrected_entry_id", self.corrected_entry_id, max_length=512),
        )
        canonical = canonicalize_origin(self.corrected_canonical_origin)
        if canonical != self.corrected_canonical_origin:
            raise RegistryValidationError(
                f"corrected_canonical_origin must already be canonical; expected {canonical!r}"
            )
        object.__setattr__(
            self,
            "corrected_evidence_digest",
            _require_digest("corrected_evidence_digest", self.corrected_evidence_digest),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "topic": self.topic,
            "fact_key": self.fact_key,
            "corrected_entry_id": self.corrected_entry_id,
            "corrected_canonical_origin": self.corrected_canonical_origin,
            "corrected_evidence_digest": self.corrected_evidence_digest,
        }

    @classmethod
    def from_dict(cls, value: Any) -> CorrectionGrant:
        return cls(
            **_strict_mapping(
                "correction",
                value,
                {
                    "topic",
                    "fact_key",
                    "corrected_entry_id",
                    "corrected_canonical_origin",
                    "corrected_evidence_digest",
                },
            )
        )

    def matches(self, *, topic: str, fact_key: str, subject: EvidenceSubject) -> bool:
        return (
            self.topic == topic
            and self.fact_key == fact_key
            and self.corrected_entry_id == subject.entry_id
            and self.corrected_canonical_origin == subject.canonical_origin
            and self.corrected_evidence_digest == subject.evidence_digest
        )


@dataclass(frozen=True)
class ProvenanceGrants:
    evidence_tier: Literal["A", "B", "C", "D", "U"] = "U"
    is_primary: bool = False
    independent_observation: bool = False
    authority_scopes: tuple[AuthorityScope, ...] = ()
    corrections: tuple[CorrectionGrant, ...] = ()

    def __post_init__(self) -> None:
        if type(self.evidence_tier) is not str or self.evidence_tier not in _EVIDENCE_TIERS:
            raise RegistryValidationError("evidence_tier must be one of A, B, C, D, or U")
        if type(self.is_primary) is not bool:
            raise RegistryValidationError("is_primary must be a JSON boolean")
        if type(self.independent_observation) is not bool:
            raise RegistryValidationError("independent_observation must be a JSON boolean")
        if type(self.authority_scopes) is not tuple or not all(
            type(scope) is AuthorityScope for scope in self.authority_scopes
        ):
            raise RegistryValidationError("authority_scopes must be a tuple of AuthorityScope")
        if type(self.corrections) is not tuple or not all(
            type(correction) is CorrectionGrant for correction in self.corrections
        ):
            raise RegistryValidationError("corrections must be a tuple of CorrectionGrant")
        if len(set(self.authority_scopes)) != len(self.authority_scopes):
            raise RegistryValidationError("authority_scopes must not contain duplicates")
        if len(set(self.corrections)) != len(self.corrections):
            raise RegistryValidationError("corrections must not contain duplicates")
        scopes = {(scope.topic, scope.fact_key) for scope in self.authority_scopes}
        if any((item.topic, item.fact_key) not in scopes for item in self.corrections):
            raise RegistryValidationError(
                "every correction grant requires a matching authority scope"
            )

    @property
    def has_any(self) -> bool:
        return bool(
            self.evidence_tier != "U"
            or self.is_primary
            or self.independent_observation
            or self.authority_scopes
            or self.corrections
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_tier": self.evidence_tier,
            "is_primary": self.is_primary,
            "independent_observation": self.independent_observation,
            "authority_scopes": [scope.to_dict() for scope in self.authority_scopes],
            "corrections": [correction.to_dict() for correction in self.corrections],
        }

    @classmethod
    def from_dict(cls, value: Any) -> ProvenanceGrants:
        data = _strict_mapping(
            "grants",
            value,
            {
                "evidence_tier",
                "is_primary",
                "independent_observation",
                "authority_scopes",
                "corrections",
            },
        )
        scopes = _strict_list("authority_scopes", data["authority_scopes"])
        corrections = _strict_list("corrections", data["corrections"])
        return cls(
            evidence_tier=data["evidence_tier"],
            is_primary=data["is_primary"],
            independent_observation=data["independent_observation"],
            authority_scopes=tuple(AuthorityScope.from_dict(item) for item in scopes),
            corrections=tuple(CorrectionGrant.from_dict(item) for item in corrections),
        )


@dataclass(frozen=True)
class AdminActor:
    actor_id: str
    actor_kind: Literal["local_admin"] = "local_admin"

    def __post_init__(self) -> None:
        if self.actor_kind != "local_admin":
            raise RegistryValidationError("actor_kind must be local_admin")
        object.__setattr__(
            self, "actor_id", _require_text("actor_id", self.actor_id, max_length=512)
        )

    def to_dict(self) -> dict[str, str]:
        return {"actor_kind": self.actor_kind, "actor_id": self.actor_id}

    @classmethod
    def from_dict(cls, value: Any) -> AdminActor:
        return cls(**_strict_mapping("actor", value, {"actor_kind", "actor_id"}))


@dataclass(frozen=True)
class RegistryEvent:
    registry_id: str
    event_id: str
    revision: int
    action: Literal["ISSUE", "SUPERSEDE", "REVOKE"]
    attestation_id: str
    attestation_version: int
    subject: EvidenceSubject
    grants: ProvenanceGrants
    actor: AdminActor
    reason: str
    idempotency_key: str
    request_hash: str
    occurred_at: str
    previous_event_hash: str
    target_event_hash: str
    event_hash: str

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "registry_id": self.registry_id,
            "event_id": self.event_id,
            "revision": self.revision,
            "action": self.action,
            "attestation_id": self.attestation_id,
            "attestation_version": self.attestation_version,
            "subject": self.subject.to_dict(),
            "grants": self.grants.to_dict(),
            "actor": self.actor.to_dict(),
            "reason": self.reason,
            "idempotency_key": self.idempotency_key,
            "request_hash": self.request_hash,
            "occurred_at": self.occurred_at,
            "previous_event_hash": self.previous_event_hash,
            "target_event_hash": self.target_event_hash,
        }
        if include_hash:
            value["event_hash"] = self.event_hash
        return value

    @classmethod
    def from_dict(cls, value: Any) -> RegistryEvent:
        keys = {
            "schema_version",
            "registry_id",
            "event_id",
            "revision",
            "action",
            "attestation_id",
            "attestation_version",
            "subject",
            "grants",
            "actor",
            "reason",
            "idempotency_key",
            "request_hash",
            "occurred_at",
            "previous_event_hash",
            "target_event_hash",
            "event_hash",
        }
        data = _strict_mapping("event", value, keys)
        if data.pop("schema_version") != EVENT_SCHEMA_VERSION:
            raise RegistryValidationError("unsupported event schema_version")
        action = data["action"]
        if type(action) is not str or action not in _ACTIONS:
            raise RegistryValidationError("event action is invalid")
        for name in ("revision", "attestation_version"):
            if type(data[name]) is not int or data[name] < 1:
                raise RegistryValidationError(f"{name} must be a positive integer")
        data["registry_id"] = _require_text("registry_id", data["registry_id"], max_length=512)
        data["event_id"] = _require_text("event_id", data["event_id"], max_length=128)
        data["attestation_id"] = _require_text(
            "attestation_id", data["attestation_id"], max_length=512
        )
        data["subject"] = EvidenceSubject.from_dict(data["subject"])
        data["grants"] = ProvenanceGrants.from_dict(data["grants"])
        data["actor"] = AdminActor.from_dict(data["actor"])
        data["reason"] = _require_text("reason", data["reason"])
        data["idempotency_key"] = _require_text(
            "idempotency_key", data["idempotency_key"], max_length=512
        )
        data["request_hash"] = _require_digest("request_hash", data["request_hash"])
        data["occurred_at"] = _validate_timestamp(data["occurred_at"])
        for name in ("previous_event_hash", "target_event_hash"):
            if data[name] != "":
                data[name] = _require_digest(name, data[name])
        data["event_hash"] = _require_digest("event_hash", data["event_hash"])
        return cls(**data)


@dataclass(frozen=True)
class ProvenanceRegistry:
    registry_id: str
    revision: int
    events: tuple[RegistryEvent, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "registry_id": self.registry_id,
            "integrity_model": INTEGRITY_MODEL,
            "revision": self.revision,
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True, order=True)
class AttestationRef:
    attestation_id: str
    attestation_version: int
    event_hash: str


@dataclass(frozen=True)
class ProvenanceResolution:
    status: Literal[
        "verified",
        "unverified",
        "revoked",
        "superseded",
        "missing_registry",
        "corrupt_registry",
        "unavailable_registry",
        "conflicting_attestations",
    ]
    registry_id: str = ""
    registry_revision: int = 0
    evidence_tier: Literal["A", "B", "C", "D", "U"] = "U"
    is_primary: bool = False
    independent_observation: bool = False
    authority_scopes: tuple[AuthorityScope, ...] = ()
    corrections: tuple[CorrectionGrant, ...] = ()
    official_corrections: tuple[CorrectionGrant, ...] = ()
    attestation_refs: tuple[AttestationRef, ...] = ()

    @property
    def has_governance_grant(self) -> bool:
        return self.status == "verified" and bool(
            self.evidence_tier != "U"
            or self.is_primary
            or self.independent_observation
            or self.authority_scopes
            or self.corrections
        )

    def authorizes_authority(self, *, topic: str, fact_key: str) -> bool:
        if self.status != "verified":
            return False
        return AuthorityScope(topic=topic, fact_key=fact_key) in self.authority_scopes

    def authorizes_correction(
        self, *, topic: str, fact_key: str, corrected_subject: EvidenceSubject
    ) -> bool:
        if self.status != "verified":
            return False
        return any(
            correction.matches(topic=topic, fact_key=fact_key, subject=corrected_subject)
            for correction in self.corrections
        )

    def authorizes_official_correction(
        self, *, topic: str, fact_key: str, corrected_subject: EvidenceSubject
    ) -> bool:
        """Require the complete primary + scope + correction relationship."""

        if self.status != "verified":
            return False
        # The three required grants must come from one attestation bundle.
        # Aggregating a primary-only event with a separate correction-only
        # event would otherwise manufacture an authority nobody issued.
        return any(
            correction.matches(
                topic=topic,
                fact_key=fact_key,
                subject=corrected_subject,
            )
            for correction in self.official_corrections
        )


def _strict_mapping(name: str, value: Any, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise RegistryValidationError(f"{name} must be a JSON object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise RegistryValidationError(f"{name} fields mismatch; missing={missing}, extra={extra}")
    if not all(type(key) is str for key in value):
        raise RegistryValidationError(f"{name} keys must be strings")
    return dict(value)


def _strict_list(name: str, value: Any) -> list[Any]:
    if type(value) is not list:
        raise RegistryValidationError(f"{name} must be a JSON array")
    return value


def _validate_timestamp(value: Any) -> str:
    value = _require_text("occurred_at", value, max_length=64)
    if not value.endswith("Z"):
        raise RegistryValidationError("occurred_at must be an RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RegistryValidationError("occurred_at must be an RFC 3339 UTC timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise RegistryValidationError("occurred_at must be UTC")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_registry(raw: str) -> ProvenanceRegistry:
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        data = _strict_mapping(
            "registry",
            value,
            {"schema_version", "registry_id", "integrity_model", "revision", "events"},
        )
        if data["schema_version"] != REGISTRY_SCHEMA_VERSION:
            raise RegistryValidationError("unsupported registry schema_version")
        if data["integrity_model"] != INTEGRITY_MODEL:
            raise RegistryValidationError("unsupported registry integrity_model")
        registry_id = _require_text("registry_id", data["registry_id"], max_length=512)
        revision = data["revision"]
        if type(revision) is not int or revision < 0:
            raise RegistryValidationError("registry revision must be a non-negative integer")
        events = tuple(
            RegistryEvent.from_dict(item) for item in _strict_list("events", data["events"])
        )
        registry = ProvenanceRegistry(registry_id=registry_id, revision=revision, events=events)
        _validate_replay(registry)
        return registry
    except RegistryValidationError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RegistryValidationError("registry JSON is invalid") from exc


def _validate_replay(registry: ProvenanceRegistry) -> None:
    if registry.revision != len(registry.events):
        raise RegistryValidationError("registry revision does not match event count")
    previous_hash = ""
    states: dict[str, RegistryEvent] = {}
    idempotency: dict[str, str] = {}
    event_ids: set[str] = set()
    for expected_revision, event in enumerate(registry.events, start=1):
        if event.registry_id != registry.registry_id:
            raise RegistryValidationError("event registry_id does not match registry header")
        if event.event_id in event_ids:
            raise RegistryValidationError("event_id must be unique")
        event_ids.add(event.event_id)
        if event.revision != expected_revision:
            raise RegistryValidationError("event revisions are not contiguous")
        if event.previous_event_hash != previous_hash:
            raise RegistryValidationError("event hash-chain link does not match")
        if _hash(event.to_dict(include_hash=False)) != event.event_hash:
            raise RegistryValidationError("event hash does not match its content")
        if event.idempotency_key in idempotency:
            raise RegistryValidationError("idempotency keys must be unique in the event log")
        idempotency[event.idempotency_key] = event.request_hash

        current = states.get(event.attestation_id)
        if event.action == "ISSUE":
            if current is not None or event.attestation_version != 1 or event.target_event_hash:
                raise RegistryValidationError("invalid ISSUE transition")
            if not event.grants.has_any:
                raise RegistryValidationError("ISSUE must contain a governance grant")
        else:
            if current is None or current.action == "REVOKE":
                raise RegistryValidationError("transition target is absent or revoked")
            if event.attestation_version != current.attestation_version + 1:
                raise RegistryValidationError("attestation versions are not contiguous")
            if event.target_event_hash != current.event_hash:
                raise RegistryValidationError("transition target_event_hash does not match")
            if event.action == "SUPERSEDE" and not event.grants.has_any:
                raise RegistryValidationError("SUPERSEDE must contain a governance grant")
            if event.action == "REVOKE" and (
                event.subject != current.subject or event.grants != current.grants
            ):
                raise RegistryValidationError("REVOKE must snapshot its target subject and grants")
        states[event.attestation_id] = event
        previous_hash = event.event_hash


def load_registry(registry_path: str | os.PathLike[str]) -> ProvenanceRegistry:
    """Load and strictly replay a registry, raising on absence or corruption."""

    path = Path(registry_path)
    try:
        raw = path.read_text(encoding="utf-8")
        return _parse_registry(raw)
    except FileNotFoundError:
        raise
    except OSError:
        raise
    except (UnicodeError, RegistryValidationError) as exc:
        raise RegistryCorruptionError(f"provenance registry is corrupt: {path}") from exc


def _current_states(registry: ProvenanceRegistry) -> dict[str, RegistryEvent]:
    states: dict[str, RegistryEvent] = {}
    for event in registry.events:
        states[event.attestation_id] = event
    return states


def resolve_provenance(
    registry_path: str | os.PathLike[str], *, subject: EvidenceSubject
) -> ProvenanceResolution:
    """Resolve active grants for an exact Entry/origin/digest binding.

    Registry availability and integrity failures intentionally return no grants
    rather than raising.  This allows ordinary content reads to proceed without
    turning a missing governance registry into a general product outage.
    """

    try:
        registry = load_registry(registry_path)
    except FileNotFoundError:
        return ProvenanceResolution(status="missing_registry")
    except RegistryCorruptionError:
        return ProvenanceResolution(status="corrupt_registry")
    except OSError:
        return ProvenanceResolution(status="unavailable_registry")

    states = _current_states(registry)
    historical_subjects: dict[str, set[EvidenceSubject]] = {}
    for event in registry.events:
        historical_subjects.setdefault(event.attestation_id, set()).add(event.subject)
    active: list[RegistryEvent] = []
    revoked_match = False
    superseded_match = False
    for attestation_id, current in states.items():
        if current.subject == subject:
            if current.action == "REVOKE":
                revoked_match = True
            else:
                active.append(current)
        elif subject in historical_subjects[attestation_id]:
            superseded_match = True

    if active:
        explicit_tiers = {
            event.grants.evidence_tier for event in active if event.grants.evidence_tier != "U"
        }
        scopes = tuple(
            sorted({scope for event in active for scope in event.grants.authority_scopes})
        )
        corrections = tuple(sorted({item for event in active for item in event.grants.corrections}))
        official_corrections = tuple(
            sorted({
                item
                for event in active
                if event.grants.is_primary
                for item in event.grants.corrections
            })
        )
        refs = tuple(
            sorted(
                (
                    AttestationRef(
                        attestation_id=event.attestation_id,
                        attestation_version=event.attestation_version,
                        event_hash=event.event_hash,
                    )
                    for event in active
                ),
                key=lambda item: item.attestation_id,
            )
        )
        if len(explicit_tiers) > 1:
            return ProvenanceResolution(
                status="conflicting_attestations",
                registry_id=registry.registry_id,
                registry_revision=registry.revision,
                attestation_refs=refs,
            )
        return ProvenanceResolution(
            status="verified",
            registry_id=registry.registry_id,
            registry_revision=registry.revision,
            evidence_tier=next(iter(explicit_tiers), "U"),
            is_primary=any(event.grants.is_primary for event in active),
            independent_observation=any(event.grants.independent_observation for event in active),
            authority_scopes=scopes,
            corrections=corrections,
            official_corrections=official_corrections,
            attestation_refs=refs,
        )
    status: Literal["revoked", "superseded", "unverified"]
    if revoked_match:
        status = "revoked"
    elif superseded_match:
        status = "superseded"
    else:
        status = "unverified"
    return ProvenanceResolution(
        status=status,
        registry_id=registry.registry_id,
        registry_revision=registry.revision,
    )


def _registry_thread_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _REGISTRY_THREAD_LOCKS_GUARD:
        return _REGISTRY_THREAD_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _exclusive_registry_lock(path: Path, *, timeout: float = 15.0) -> Iterator[None]:
    """Serialize registry readers-with-commit and admin writers.

    The in-process lock closes thread races on platforms whose file-lock
    semantics are process-scoped. The byte-range/flock lock preserves the same
    boundary across processes.
    """
    path = Path(path)
    with _registry_thread_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_name(path.name + ".lock")
        handle = lock_path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            deadline = time.monotonic() + timeout
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"timed out locking provenance registry: {path}")
                    time.sleep(0.01)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


@contextmanager
def provenance_registry_lock(
    registry_path: str | os.PathLike[str],
    *,
    timeout: float = 15.0,
) -> Iterator[None]:
    """Hold the registry mutation boundary across a dependent domain commit."""
    with _exclusive_registry_lock(Path(registry_path), timeout=timeout):
        yield


def _atomic_write(path: Path, registry: ProvenanceRegistry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = -1
            json.dump(
                registry.to_dict(),
                handle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _request_hash(
    *,
    action: str,
    attestation_id: str,
    subject: EvidenceSubject | None,
    grants: ProvenanceGrants | None,
    actor: AdminActor,
    reason: str,
) -> str:
    return _hash(
        {
            "action": action,
            "attestation_id": attestation_id,
            "subject": subject.to_dict() if subject is not None else None,
            "grants": grants.to_dict() if grants is not None else None,
            "actor": actor.to_dict(),
            "reason": reason,
        }
    )


def _empty_registry(registry_id: str) -> ProvenanceRegistry:
    return ProvenanceRegistry(
        registry_id=_require_text("registry_id", registry_id, max_length=512),
        revision=0,
        events=(),
    )


def _load_for_admin(path: Path, *, registry_id: str | None = None) -> ProvenanceRegistry:
    try:
        registry = load_registry(path)
    except FileNotFoundError:
        if registry_id is None:
            raise RegistryValidationError("registry_id is required to create a registry")
        return _empty_registry(registry_id)
    if registry_id is not None and registry.registry_id != registry_id:
        raise RegistryValidationError("registry_id does not match the existing registry")
    return registry


def _find_idempotent(
    registry: ProvenanceRegistry, *, idempotency_key: str, request_hash: str
) -> RegistryEvent | None:
    for event in registry.events:
        if event.idempotency_key != idempotency_key:
            continue
        if event.request_hash != request_hash:
            raise IdempotencyConflictError(
                "idempotency key was already used for a different admin request"
            )
        return event
    return None


def _append_event(
    path: Path,
    registry: ProvenanceRegistry,
    *,
    action: Literal["ISSUE", "SUPERSEDE", "REVOKE"],
    attestation_id: str,
    attestation_version: int,
    subject: EvidenceSubject,
    grants: ProvenanceGrants,
    actor: AdminActor,
    reason: str,
    idempotency_key: str,
    request_hash: str,
    target_event_hash: str,
) -> RegistryEvent:
    previous_event_hash = registry.events[-1].event_hash if registry.events else ""
    values: dict[str, Any] = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "registry_id": registry.registry_id,
        "event_id": f"event-{uuid.uuid4()}",
        "revision": registry.revision + 1,
        "action": action,
        "attestation_id": attestation_id,
        "attestation_version": attestation_version,
        "subject": subject.to_dict(),
        "grants": grants.to_dict(),
        "actor": actor.to_dict(),
        "reason": reason,
        "idempotency_key": idempotency_key,
        "request_hash": request_hash,
        "occurred_at": _utc_now(),
        "previous_event_hash": previous_event_hash,
        "target_event_hash": target_event_hash,
    }
    values["event_hash"] = _hash(values)
    event = RegistryEvent.from_dict(values)
    updated = ProvenanceRegistry(
        registry_id=registry.registry_id,
        revision=event.revision,
        events=registry.events + (event,),
    )
    _validate_replay(updated)
    _atomic_write(path, updated)
    return event


def admin_issue_attestation(
    registry_path: str | os.PathLike[str],
    *,
    registry_id: str,
    subject: EvidenceSubject,
    grants: ProvenanceGrants,
    actor: AdminActor,
    reason: str,
    idempotency_key: str,
    attestation_id: str = "",
) -> RegistryEvent:
    """Explicit local-admin mutation: issue a new bound attestation."""

    reason = _require_text("reason", reason)
    idempotency_key = _require_text("idempotency_key", idempotency_key, max_length=512)
    if type(subject) is not EvidenceSubject or type(grants) is not ProvenanceGrants:
        raise RegistryValidationError("subject and grants must use provenance registry types")
    if type(actor) is not AdminActor or not grants.has_any:
        raise RegistryValidationError(
            "an admin actor and at least one governance grant are required"
        )
    requested_id = attestation_id
    if requested_id:
        _require_text("attestation_id", requested_id, max_length=512)
    request_hash = _request_hash(
        action="ISSUE",
        attestation_id=requested_id,
        subject=subject,
        grants=grants,
        actor=actor,
        reason=reason,
    )
    path = Path(registry_path)
    with _exclusive_registry_lock(path):
        registry = _load_for_admin(path, registry_id=registry_id)
        prior = _find_idempotent(
            registry, idempotency_key=idempotency_key, request_hash=request_hash
        )
        if prior is not None:
            return prior
        assigned_id = requested_id or f"attestation-{uuid.uuid4()}"
        if assigned_id in _current_states(registry):
            raise AttestationStateError("attestation_id already exists")
        return _append_event(
            path,
            registry,
            action="ISSUE",
            attestation_id=assigned_id,
            attestation_version=1,
            subject=subject,
            grants=grants,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            target_event_hash="",
        )


def admin_supersede_attestation(
    registry_path: str | os.PathLike[str],
    *,
    attestation_id: str,
    subject: EvidenceSubject,
    grants: ProvenanceGrants,
    actor: AdminActor,
    reason: str,
    idempotency_key: str,
) -> RegistryEvent:
    """Explicit local-admin mutation: replace an active attestation version."""

    attestation_id = _require_text("attestation_id", attestation_id, max_length=512)
    reason = _require_text("reason", reason)
    idempotency_key = _require_text("idempotency_key", idempotency_key, max_length=512)
    if type(subject) is not EvidenceSubject or type(grants) is not ProvenanceGrants:
        raise RegistryValidationError("subject and grants must use provenance registry types")
    if type(actor) is not AdminActor or not grants.has_any:
        raise RegistryValidationError(
            "an admin actor and at least one governance grant are required"
        )
    request_hash = _request_hash(
        action="SUPERSEDE",
        attestation_id=attestation_id,
        subject=subject,
        grants=grants,
        actor=actor,
        reason=reason,
    )
    path = Path(registry_path)
    with _exclusive_registry_lock(path):
        registry = _load_for_admin(path)
        prior = _find_idempotent(
            registry, idempotency_key=idempotency_key, request_hash=request_hash
        )
        if prior is not None:
            return prior
        current = _current_states(registry).get(attestation_id)
        if current is None or current.action == "REVOKE":
            raise AttestationStateError("attestation is absent or revoked")
        return _append_event(
            path,
            registry,
            action="SUPERSEDE",
            attestation_id=attestation_id,
            attestation_version=current.attestation_version + 1,
            subject=subject,
            grants=grants,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            target_event_hash=current.event_hash,
        )


def admin_revoke_attestation(
    registry_path: str | os.PathLike[str],
    *,
    attestation_id: str,
    actor: AdminActor,
    reason: str,
    idempotency_key: str,
) -> RegistryEvent:
    """Explicit local-admin mutation: revoke an active attestation."""

    attestation_id = _require_text("attestation_id", attestation_id, max_length=512)
    reason = _require_text("reason", reason)
    idempotency_key = _require_text("idempotency_key", idempotency_key, max_length=512)
    if type(actor) is not AdminActor:
        raise RegistryValidationError("actor must be an AdminActor")
    request_hash = _request_hash(
        action="REVOKE",
        attestation_id=attestation_id,
        subject=None,
        grants=None,
        actor=actor,
        reason=reason,
    )
    path = Path(registry_path)
    with _exclusive_registry_lock(path):
        registry = _load_for_admin(path)
        prior = _find_idempotent(
            registry, idempotency_key=idempotency_key, request_hash=request_hash
        )
        if prior is not None:
            return prior
        current = _current_states(registry).get(attestation_id)
        if current is None or current.action == "REVOKE":
            raise AttestationStateError("attestation is absent or already revoked")
        return _append_event(
            path,
            registry,
            action="REVOKE",
            attestation_id=attestation_id,
            attestation_version=current.attestation_version + 1,
            subject=current.subject,
            grants=current.grants,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            target_event_hash=current.event_hash,
        )


__all__ = [
    "AdminActor",
    "AttestationRef",
    "AttestationStateError",
    "AuthorityScope",
    "CorrectionGrant",
    "EVENT_SCHEMA_VERSION",
    "EvidenceSubject",
    "INTEGRITY_MODEL",
    "IdempotencyConflictError",
    "ProvenanceGrants",
    "ProvenanceRegistry",
    "ProvenanceRegistryError",
    "ProvenanceResolution",
    "REGISTRY_SCHEMA_VERSION",
    "RegistryCorruptionError",
    "RegistryEvent",
    "RegistryValidationError",
    "admin_issue_attestation",
    "admin_revoke_attestation",
    "admin_supersede_attestation",
    "canonicalize_origin",
    "load_registry",
    "provenance_registry_lock",
    "resolve_provenance",
]
