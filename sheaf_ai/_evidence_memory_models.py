"""Immutable records and public exceptions for evidence-governed memory."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Sequence


SCHEMA_VERSION = 3
LEGACY_ALGORITHM_VERSION = "evidence-rule-v1"
DIGEST_ALGORITHM_VERSION = "evidence-rule-v2"
ALGORITHM_VERSION = "evidence-rule-v3"
VALID_ALGORITHM_VERSIONS = frozenset({
    LEGACY_ALGORITHM_VERSION,
    DIGEST_ALGORITHM_VERSION,
    ALGORITHM_VERSION,
})
LEGACY_GOVERNANCE_VERSION = "evidence-governance-v1"
GOVERNANCE_VERSION = "evidence-governance-v2"
VALID_GOVERNANCE_VERSIONS = frozenset(
    {LEGACY_GOVERNANCE_VERSION, GOVERNANCE_VERSION}
)
VALID_ACTIONS = frozenset({"CREATE", "UPDATE", "MERGE", "RETIRE", "CONTEST"})
VALID_TIERS = frozenset({"A", "B", "C", "D", "U"})
VALID_RESOLUTION_BASES = frozenset(
    {"stronger_evidence", "official_correction", "version_change", "manual_adjudication"}
)
TIER_WEIGHTS = {"A": 0.90, "B": 0.70, "C": 0.45, "D": 0.20, "U": 0.10}


def _identity_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _identity_text(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _strict_string(data: Mapping[str, object], key: str, default: str = "") -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _strict_int(data: Mapping[str, object], key: str, default: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _strict_bool(data: Mapping[str, object], key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _strict_number(
    data: Mapping[str, object],
    key: str,
    default: float = 0.0,
) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value)


def _string_tuple(data: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or any(not isinstance(item, str) for item in value)
    ):
        raise ValueError(f"{key} must be an array of strings")
    return tuple(value)


def claim_identity(
    *,
    topic: str,
    claim: str,
    fact_key: str = "",
    fact_value: str = "",
) -> str:
    """Return a stable identity for one atomic claim within a topic."""
    normalised_key = _identity_text(fact_key)
    normalised_value = _identity_text(fact_value)
    if normalised_key and normalised_value:
        body = {
            "topic": _identity_text(topic),
            "kind": "structured_fact",
            "fact_key": normalised_key,
            "fact_value": normalised_value,
        }
    else:
        body = {
            "topic": _identity_text(topic),
            "kind": "claim",
            "claim": _identity_text(claim),
        }
    return f"claim_{_identity_hash(body)}"


def legacy_evidence_use_identity(entry_id: str, atomic_claim_identity: str) -> str:
    """Return the pre-span v2 identity for replaying old ledgers."""
    return f"use_{_identity_hash([str(entry_id).strip(), atomic_claim_identity])}"


def evidence_use_identity(
    entry_id: str,
    atomic_claim_identity: str,
    locator_identity: str = "whole_entry",
) -> str:
    """Return the identity of one Entry span supporting one atomic claim."""
    return f"use_{_identity_hash([str(entry_id).strip(), atomic_claim_identity, locator_identity])}"


class EvidenceMemoryError(RuntimeError):
    """Base class for trustworthy-memory failures."""


class LedgerCorruptionError(EvidenceMemoryError):
    """The ledger is unreadable or violates its event-graph invariants."""


class TransitionValidationError(EvidenceMemoryError):
    """A requested state transition violates the transition contract."""


class EvidenceValidationError(TransitionValidationError):
    """Evidence references are forged, ambiguous, or malformed."""


class EvidenceAlreadyProcessedError(TransitionValidationError):
    """Evidence was already consumed by a different transition."""


class ConflictResolutionRequired(TransitionValidationError):
    """A structured contradiction needs an explicit resolution basis."""


@dataclass(frozen=True)
class EvidenceLocator:
    """Verified location of supporting text within an Entry body."""

    kind: str = "whole_entry"
    start: int = -1
    end: int = -1
    quote: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, object] | None) -> "EvidenceLocator":
        if data is None:
            return cls()
        if not isinstance(data, Mapping):
            raise ValueError("locator must be an object")
        return cls(
            kind=_strict_string(data, "kind", "whole_entry"),
            start=_strict_int(data, "start", -1),
            end=_strict_int(data, "end", -1),
            quote=_strict_string(data, "quote"),
        )


def locator_identity(locator: EvidenceLocator) -> str:
    """Canonicalise quote and char-span locators for duplicate detection."""
    if locator.kind == "whole_entry":
        return "whole_entry"
    return f"span_{_identity_hash([locator.start, locator.end, locator.quote])}"


@dataclass(frozen=True, order=True)
class EvidenceDuplicateRelation:
    """Immutable duplicate decision copied from Entry metadata."""

    related_entry_id: str
    classification: str
    similarity: float
    rule: str
    reason: str
    algorithm_version: str

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "EvidenceDuplicateRelation":
        similarity = data.get("similarity", 0.0)
        if isinstance(similarity, bool) or not isinstance(similarity, (int, float)):
            raise ValueError("similarity must be a number")
        return cls(
            related_entry_id=_strict_string(data, "related_entry_id"),
            classification=_strict_string(data, "classification"),
            similarity=float(similarity),
            rule=_strict_string(data, "rule"),
            reason=_strict_string(data, "reason"),
            algorithm_version=_strict_string(data, "algorithm_version"),
        )


@dataclass(frozen=True)
class EvidenceRef:
    """Immutable reference to an allowlisted collected entry."""

    entry_id: str
    source_tier: str
    source_key: str
    content_hash: str = ""
    evidence_digest: str = ""
    locator: EvidenceLocator = field(default_factory=EvidenceLocator)
    is_primary: bool = False
    authority_topics: tuple[str, ...] = ()
    authority_fact_keys: tuple[str, ...] = ()
    corrects_entry_ids: tuple[str, ...] = ()
    duplicate_detection_version: str = ""
    duplicate_relations: tuple[EvidenceDuplicateRelation, ...] = ()
    independence_identity: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "EvidenceRef":
        raw_relations = data.get("duplicate_relations", [])
        if (
            not isinstance(raw_relations, Sequence)
            or isinstance(raw_relations, (str, bytes, bytearray))
            or not all(isinstance(item, Mapping) for item in raw_relations)
        ):
            raise ValueError("duplicate_relations must be an array of objects")
        return cls(
            entry_id=str(data.get("entry_id", "")),
            source_tier=str(data.get("source_tier", "U")),
            source_key=str(data.get("source_key", "unknown")),
            content_hash=str(data.get("content_hash", "")),
            evidence_digest=str(data.get("evidence_digest", "")),
            locator=EvidenceLocator.from_dict(data.get("locator")),  # type: ignore[arg-type]
            is_primary=_strict_bool(data, "is_primary"),
            authority_topics=_string_tuple(data, "authority_topics"),
            authority_fact_keys=_string_tuple(data, "authority_fact_keys"),
            corrects_entry_ids=_string_tuple(data, "corrects_entry_ids"),
            duplicate_detection_version=str(
                data.get("duplicate_detection_version", "")
            ),
            duplicate_relations=tuple(
                EvidenceDuplicateRelation.from_dict(item)
                for item in raw_relations
            ),
            independence_identity=str(data.get("independence_identity", "")),
        )


@dataclass(frozen=True)
class EvidenceStrength:
    """Transparent ordinal support score; explicitly not a probability."""

    score: float
    band: str
    algorithm: str
    independent_source_count: int
    source_group_count: int
    tier_counts: tuple[tuple[str, int], ...]
    conflict_penalty: float
    rationale: tuple[str, ...]
    is_probability: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "EvidenceStrength":
        raw_counts = data.get("tier_counts", [])
        if (
            not isinstance(raw_counts, Sequence)
            or isinstance(raw_counts, (str, bytes, bytearray))
        ):
            raise ValueError("tier_counts must be an array of pairs")
        counts: list[tuple[str, int]] = []
        for item in raw_counts:
            if (
                not isinstance(item, Sequence)
                or isinstance(item, (str, bytes, bytearray))
                or len(item) != 2
                or not isinstance(item[0], str)
                or isinstance(item[1], bool)
                or not isinstance(item[1], int)
            ):
                raise ValueError("tier_counts must contain string/integer pairs")
            counts.append((item[0], item[1]))
        independent_count = _strict_int(data, "independent_source_count", 0)
        return cls(
            score=_strict_number(data, "score"),
            band=_strict_string(data, "band", "low"),
            algorithm=_strict_string(data, "algorithm", LEGACY_ALGORITHM_VERSION),
            independent_source_count=independent_count,
            source_group_count=_strict_int(
                data,
                "source_group_count",
                independent_count,
            ),
            tier_counts=tuple(counts),
            conflict_penalty=_strict_number(data, "conflict_penalty"),
            rationale=_string_tuple(data, "rationale"),
            is_probability=_strict_bool(data, "is_probability"),
        )


@dataclass(frozen=True)
class ConflictAssessment:
    """Conservative conflict result based only on explicit structured facts."""

    state: str
    rule: str
    explanation: str

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ConflictAssessment":
        return cls(
            state=str(data.get("state", "unknown")),
            rule=str(data.get("rule", "structured-fact-v1")),
            explanation=str(data.get("explanation", "")),
        )


@dataclass(frozen=True)
class ContestedClaim:
    """The conflicting side preserved without overwriting the current claim."""

    claim: str
    evidence: str
    fact_key: str
    fact_value: str
    evidence_refs: tuple[EvidenceRef, ...]
    strength: EvidenceStrength

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ContestedClaim":
        return cls(
            claim=str(data.get("claim", "")),
            evidence=str(data.get("evidence", "")),
            fact_key=str(data.get("fact_key", "")),
            fact_value=str(data.get("fact_value", "")),
            evidence_refs=tuple(
                EvidenceRef.from_dict(item)
                for item in data.get("evidence_refs", [])  # type: ignore[union-attr]
            ),
            strength=EvidenceStrength.from_dict(data.get("strength", {})),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class CardVersion:
    """Immutable snapshot produced by exactly one transition event."""

    version_id: str
    card_id: str
    revision: int
    topic: str
    title: str
    claim: str
    evidence: str
    tags: tuple[str, ...]
    evidence_refs: tuple[EvidenceRef, ...]
    state: str
    parent_version_ids: tuple[str, ...]
    event_id: str
    created_at: str
    strength: EvidenceStrength
    proposal: ContestedClaim | None = None
    fact_key: str = ""
    fact_value: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "CardVersion":
        raw_proposal = data.get("proposal")
        return cls(
            version_id=str(data.get("version_id", "")),
            card_id=str(data.get("card_id", "")),
            revision=int(data.get("revision", 0)),
            topic=str(data.get("topic", "")),
            title=str(data.get("title", "")),
            claim=str(data.get("claim", "")),
            evidence=str(data.get("evidence", "")),
            tags=tuple(str(item) for item in data.get("tags", [])),  # type: ignore[arg-type]
            evidence_refs=tuple(
                EvidenceRef.from_dict(item)
                for item in data.get("evidence_refs", [])  # type: ignore[union-attr]
            ),
            state=str(data.get("state", "")),
            parent_version_ids=tuple(
                str(item) for item in data.get("parent_version_ids", [])  # type: ignore[arg-type]
            ),
            event_id=str(data.get("event_id", "")),
            created_at=str(data.get("created_at", "")),
            strength=EvidenceStrength.from_dict(data.get("strength", {})),  # type: ignore[arg-type]
            proposal=(
                ContestedClaim.from_dict(raw_proposal)
                if isinstance(raw_proposal, Mapping)
                else None
            ),
            fact_key=str(data.get("fact_key", "")),
            fact_value=str(data.get("fact_value", "")),
        )


def claim_identity_for_version(version: CardVersion, action: str) -> str:
    """Derive the claim supported by evidence introduced by a transition."""
    if action == "CONTEST" and version.proposal is not None:
        return claim_identity(
            topic=version.topic,
            claim=version.proposal.claim,
            fact_key=version.proposal.fact_key,
            fact_value=version.proposal.fact_value,
        )
    return claim_identity(
        topic=version.topic,
        claim=version.claim,
        fact_key=version.fact_key,
        fact_value=version.fact_value,
    )


@dataclass(frozen=True)
class TransitionEvent:
    """Immutable audit record describing a graph transition."""

    event_id: str
    action: str
    topic: str
    parent_version_ids: tuple[str, ...]
    output_version_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    evidence_use_ids: tuple[str, ...]
    reason: str
    idempotency_key: str
    request_hash: str
    algorithm_version: str
    governance_version: str
    resolution_basis: str
    resolution_metadata: tuple[tuple[str, str], ...]
    created_at: str
    conflict: ConflictAssessment

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "TransitionEvent":
        return cls(
            event_id=str(data.get("event_id", "")),
            action=str(data.get("action", "")),
            topic=str(data.get("topic", "")),
            parent_version_ids=tuple(
                str(item) for item in data.get("parent_version_ids", [])  # type: ignore[arg-type]
            ),
            output_version_ids=tuple(
                str(item) for item in data.get("output_version_ids", [])  # type: ignore[arg-type]
            ),
            evidence_ids=tuple(
                str(item) for item in data.get("evidence_ids", [])  # type: ignore[arg-type]
            ),
            evidence_use_ids=tuple(
                str(item) for item in data.get("evidence_use_ids", [])  # type: ignore[arg-type]
            ),
            reason=str(data.get("reason", "")),
            idempotency_key=str(data.get("idempotency_key", "")),
            request_hash=str(data.get("request_hash", "")),
            algorithm_version=str(
                data.get("algorithm_version", LEGACY_ALGORITHM_VERSION)
            ),
            governance_version=str(
                data.get("governance_version", LEGACY_GOVERNANCE_VERSION)
            ),
            resolution_basis=str(data.get("resolution_basis", "")),
            resolution_metadata=tuple(
                (str(item[0]), str(item[1]))
                for item in data.get("resolution_metadata", [])  # type: ignore[union-attr]
            ),
            created_at=str(data.get("created_at", "")),
            conflict=ConflictAssessment.from_dict(data.get("conflict", {})),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class MemorySnapshot:
    """Validated result of replaying the complete ledger."""

    versions: tuple[CardVersion, ...]
    events: tuple[TransitionEvent, ...]
    active_heads: Mapping[str, str]
    versions_by_id: Mapping[str, CardVersion]
    processed_evidence: Mapping[str, str]

    def active_versions(self, topic: str = "") -> tuple[CardVersion, ...]:
        versions = tuple(self.versions_by_id[vid] for vid in self.active_heads.values())
        if topic:
            versions = tuple(version for version in versions if version.topic == topic)
        return versions

    @classmethod
    def from_replay(
        cls,
        versions: tuple[CardVersion, ...],
        events: tuple[TransitionEvent, ...],
        active_heads: Mapping[str, str],
        processed_evidence: Mapping[str, str],
    ) -> "MemorySnapshot":
        versions_by_id = {version.version_id: version for version in versions}
        return cls(
            versions=versions,
            events=events,
            active_heads=MappingProxyType(dict(active_heads)),
            versions_by_id=MappingProxyType(versions_by_id),
            processed_evidence=MappingProxyType(dict(processed_evidence)),
        )


@dataclass(frozen=True)
class TransitionResult:
    """Result of an applied transition or an idempotent retry."""

    applied: bool
    event_id: str
    action: str
    version_ids: tuple[str, ...]
    idempotency_key: str
