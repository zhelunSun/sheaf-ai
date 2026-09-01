"""Immutable records and public exceptions for evidence-governed memory."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


SCHEMA_VERSION = 1
ALGORITHM_VERSION = "evidence-rule-v1"
VALID_ACTIONS = frozenset({"CREATE", "UPDATE", "MERGE", "RETIRE", "CONTEST"})
VALID_TIERS = frozenset({"A", "B", "C", "D", "U"})
VALID_RESOLUTION_BASES = frozenset(
    {"stronger_evidence", "official_correction", "version_change", "manual_adjudication"}
)
TIER_WEIGHTS = {"A": 0.90, "B": 0.70, "C": 0.45, "D": 0.20, "U": 0.10}


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
class EvidenceRef:
    """Immutable reference to an allowlisted collected entry."""

    entry_id: str
    source_tier: str
    source_key: str
    content_hash: str = ""
    is_primary: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "EvidenceRef":
        return cls(
            entry_id=str(data.get("entry_id", "")),
            source_tier=str(data.get("source_tier", "U")),
            source_key=str(data.get("source_key", "unknown")),
            content_hash=str(data.get("content_hash", "")),
            is_primary=bool(data.get("is_primary", False)),
        )


@dataclass(frozen=True)
class EvidenceStrength:
    """Transparent ordinal support score; explicitly not a probability."""

    score: float
    band: str
    algorithm: str
    independent_source_count: int
    tier_counts: tuple[tuple[str, int], ...]
    conflict_penalty: float
    rationale: tuple[str, ...]
    is_probability: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "EvidenceStrength":
        raw_counts = data.get("tier_counts", [])
        counts = tuple((str(item[0]), int(item[1])) for item in raw_counts)  # type: ignore[index]
        return cls(
            score=float(data.get("score", 0.0)),
            band=str(data.get("band", "low")),
            algorithm=str(data.get("algorithm", ALGORITHM_VERSION)),
            independent_source_count=int(data.get("independent_source_count", 0)),
            tier_counts=counts,
            conflict_penalty=float(data.get("conflict_penalty", 0.0)),
            rationale=tuple(str(item) for item in data.get("rationale", [])),  # type: ignore[arg-type]
            is_probability=bool(data.get("is_probability", False)),
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


@dataclass(frozen=True)
class TransitionEvent:
    """Immutable audit record describing a graph transition."""

    event_id: str
    action: str
    topic: str
    parent_version_ids: tuple[str, ...]
    output_version_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    reason: str
    idempotency_key: str
    request_hash: str
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
            reason=str(data.get("reason", "")),
            idempotency_key=str(data.get("idempotency_key", "")),
            request_hash=str(data.get("request_hash", "")),
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
