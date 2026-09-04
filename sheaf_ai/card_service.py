"""Application service boundary for knowledge card use cases.

Adapters should use this module for card operations and public JSON projection.
The service delegates persistence/extraction to ``crystallize`` and does not
change the KnowledgeCard schema or card store format.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence
from urllib.parse import urlsplit

from sheaf_ai import config, crystallize
from sheaf_ai.entry_paths import InvalidEntryId, resolve_entry_json_path
from sheaf_ai.evidence_memory import (
    VALID_ACTIONS,
    VALID_RESOLUTION_BASES,
    AtomicSplitOperation,
    CardVersion,
    EvidenceGovernedMemory,
    EvidenceValidationError,
    StaleHeadError,
)
from sheaf_ai.evidence_policy import (
    DecisionTrace,
    PlannedOperation,
    StaleDecisionError,
    execution_manifest_hash,
    validate_decision_trace,
)
from sheaf_ai.provenance_registry import (
    EvidenceSubject,
    ProvenanceResolution,
    RegistryValidationError,
    canonicalize_origin,
    provenance_registry_lock,
    resolve_provenance,
)
from sheaf_ai.source_independence import (
    SOURCE_INDEPENDENCE_VERSION,
    assess_source_pair,
)
from sheaf_ai.utils import content_hash, evidence_digest
from sheaf_cards.base import KnowledgeCard


EVIDENCE_MEMORY_LEDGER_NAME = "evidence_memory_ledger.json"
PROVENANCE_REGISTRY_NAME = "provenance_registry.json"
_TRANSITION_FIELDS = frozenset(
    {
        "action",
        "topic",
        "source_ids",
        "evidence_locators",
        "target_card_ids",
        "card",
        "reason",
        "resolution_basis",
        "resolution_metadata",
        "idempotency_key",
    }
)
_TRANSITION_CARD_FIELDS = frozenset(
    {"title", "claim", "evidence", "tags", "fact_key", "fact_value"}
)


MEMORY_TRANSITION_REQUEST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": sorted(VALID_ACTIONS)},
        "topic": {"type": "string", "minLength": 1},
        "source_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
            "default": [],
        },
        "evidence_locators": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["whole_entry", "quote", "char_span"],
                    },
                    "start": {"type": "integer", "minimum": 0},
                    "end": {"type": "integer", "minimum": 1},
                    "quote": {"type": "string"},
                },
            },
            "default": {},
        },
        "target_card_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
            "default": [],
        },
        "card": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "claim": {"type": "string"},
                "evidence": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "fact_key": {"type": "string"},
                "fact_value": {"type": "string"},
            },
        },
        "reason": {"type": "string", "minLength": 1},
        "resolution_basis": {
            "type": "string",
            "enum": sorted(VALID_RESOLUTION_BASES),
        },
        "resolution_metadata": {
            "type": "object",
            "additionalProperties": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "number"},
                    {"type": "boolean"},
                ]
            },
        },
        "idempotency_key": {"type": "string"},
    },
    "required": ["action", "topic", "reason"],
}


@dataclass(frozen=True)
class EvidenceTransitionRequest:
    """Schema-constrained transition proposed to the trusted executor.

    The application layer performs no model inference.  An LLM-facing adapter
    may only construct this finite request; ``EvidenceGovernedMemory`` remains
    the sole executor and applies all evidence and state-transition rules.
    """

    action: str
    topic: str
    source_ids: tuple[str, ...]
    evidence_locators: Mapping[str, Mapping[str, object]]
    target_card_ids: tuple[str, ...]
    card: Mapping[str, object]
    reason: str
    resolution_basis: str
    resolution_metadata: Mapping[str, object]
    idempotency_key: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "EvidenceTransitionRequest":
        if not isinstance(raw, Mapping):
            raise ValueError("Transition request must be a JSON object")
        if any(not isinstance(key, str) for key in raw):
            raise ValueError("Transition request field names must be strings")
        unknown = set(raw) - _TRANSITION_FIELDS
        if unknown:
            raise ValueError("Unsupported transition fields: " + ", ".join(sorted(unknown)))

        action = _request_string(raw, "action", required=True).upper()
        if action not in VALID_ACTIONS:
            raise ValueError(f"Unsupported transition action: {action!r}")
        topic = _request_string(raw, "topic", required=True)
        reason = _request_string(raw, "reason", required=True)

        source_ids = _string_tuple(raw.get("source_ids", ()), "source_ids")
        evidence_locators = _locator_map(raw.get("evidence_locators", {}))
        extra_locator_ids = set(evidence_locators) - set(source_ids)
        if extra_locator_ids:
            raise ValueError(
                "evidence_locators reference unrequested source_ids: "
                + ", ".join(sorted(extra_locator_ids))
            )
        target_card_ids = _string_tuple(raw.get("target_card_ids", ()), "target_card_ids")

        card = raw.get("card", {})
        if not isinstance(card, Mapping):
            raise ValueError("Transition card must be a JSON object")
        if any(not isinstance(key, str) for key in card):
            raise ValueError("Transition card field names must be strings")
        unknown_card_fields = set(card) - _TRANSITION_CARD_FIELDS
        if unknown_card_fields:
            raise ValueError(
                "Unsupported transition card fields: "
                + ", ".join(sorted(unknown_card_fields))
            )
        for field_name, value in card.items():
            if field_name == "tags":
                _string_tuple(value, "card.tags")
            elif not isinstance(value, str):
                raise ValueError(f"card.{field_name} must be a string")

        basis = _request_string(raw, "resolution_basis")
        if basis and basis not in VALID_RESOLUTION_BASES:
            raise ValueError(f"Unsupported resolution_basis: {basis!r}")
        metadata = raw.get("resolution_metadata", {})
        if not isinstance(metadata, Mapping):
            raise ValueError("resolution_metadata must be a JSON object")
        for key, value in metadata.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("resolution_metadata keys must be non-empty strings")
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError("resolution_metadata values must be JSON scalars")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("resolution_metadata numbers must be finite")

        return cls(
            action=action,
            topic=topic,
            source_ids=source_ids,
            evidence_locators=evidence_locators,
            target_card_ids=target_card_ids,
            card=dict(card),
            reason=reason,
            resolution_basis=basis,
            resolution_metadata=dict(metadata),
            idempotency_key=_request_string(raw, "idempotency_key"),
        )


def _request_string(raw: Mapping[str, object], field_name: str, *, required: bool = False) -> str:
    value = raw.get(field_name, "")
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{field_name} is required")
    return value


def _string_tuple(raw: object, field_name: str) -> tuple[str, ...]:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError(f"{field_name} must be an array of strings")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain only non-empty strings")
        value = item.strip()
        if value in values:
            raise ValueError(f"{field_name} must not contain duplicates")
        values.append(value)
    return tuple(values)


def _locator_map(raw: object) -> dict[str, dict[str, object]]:
    if not isinstance(raw, Mapping):
        raise ValueError("evidence_locators must be a JSON object")
    result: dict[str, dict[str, object]] = {}
    allowed = {"kind", "start", "end", "quote"}
    for source_id, locator in raw.items():
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("evidence_locators keys must be non-empty source IDs")
        if not isinstance(locator, Mapping):
            raise ValueError("Each evidence locator must be a JSON object")
        unknown = set(locator) - allowed
        if unknown:
            raise ValueError(
                "Unsupported evidence locator fields: " + ", ".join(sorted(unknown))
            )
        kind = locator.get("kind", "whole_entry")
        if kind not in {"whole_entry", "quote", "char_span"}:
            raise ValueError(f"Unsupported evidence locator kind: {kind!r}")
        for field_name in ("start", "end"):
            value = locator.get(field_name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"evidence locator {field_name} must be an integer")
        quote = locator.get("quote")
        if quote is not None and not isinstance(quote, str):
            raise ValueError("evidence locator quote must be a string")
        canonical_source_id = source_id.strip()
        if canonical_source_id in result:
            raise ValueError(
                "evidence_locators must not repeat a source ID after trimming"
            )
        result[canonical_source_id] = dict(locator)
    return result


def card_to_public_dict(card: KnowledgeCard, include_tag_entries: bool = False) -> dict:
    """Project a KnowledgeCard into the stable public card shape.

    Args:
        card: KnowledgeCard to project
        include_tag_entries: If True, include rich tag entries with source tracking
    """
    from .card_trace import citation_trace
    from .card_governance import memory_status

    data = card.to_dict() if hasattr(card, "to_dict") else {}
    card_id = (
        data.get("card_id")
        or getattr(card, "card_id", "")
        or getattr(card, "id", "")
    )
    evidence = data.get("evidence", getattr(card, "evidence", ""))
    if evidence is None:
        evidence = ""
    elif not isinstance(evidence, str):
        evidence = str(evidence)

    result = {
        "id": card_id,
        "card_id": card_id,
        "title": data.get("title", getattr(card, "title", "")),
        "claim": data.get("claim", getattr(card, "claim", "")),
        "evidence": evidence,
        "tags": data.get("tags", getattr(card, "tags", [])) or [],
        "confidence": data.get("confidence", getattr(card, "confidence", 0.0)),
        "source_ids": data.get("source_ids", getattr(card, "source_ids", [])) or [],
        "associations": data.get("associations", getattr(card, "associations", [])) or [],
        "provenance": data.get("provenance", getattr(card, "provenance", {})) or {},
        "created_at": data.get("created_at", getattr(card, "created_at", "")),
        "updated_at": data.get("updated_at", getattr(card, "updated_at", "")),
        "citation_trace": citation_trace(card),
    }
    extra = data.get("extra", getattr(card, "extra", {})) or {}
    status = memory_status(card)
    if status is not None:
        result["memory_status"] = status
    if extra:
        result["extra"] = extra
    # Issue #53: Rich tag entries with source tracking
    if include_tag_entries:
        result["tag_entries"] = [te.to_dict() for te in card.tag_entries]
        result["tagging_status"] = card.tagging_status
        result["summarization_status"] = card.summarization_status
    return result


def _memory(ledger_path: Path | None = None) -> EvidenceGovernedMemory:
    path = Path(ledger_path) if ledger_path is not None else (
        config.DATA_DIR / EVIDENCE_MEMORY_LEDGER_NAME
    )
    return EvidenceGovernedMemory(path)


def _read_stored_entry(entry_id: str) -> dict[str, object]:
    """Read one Entry and recompute evidence identity from its current raw body."""
    try:
        path = resolve_entry_json_path(config.ENTRIES_DIR, entry_id)
    except InvalidEntryId as exc:
        raise EvidenceValidationError("Evidence source ID is invalid") from exc
    if not path.is_file():
        raise EvidenceValidationError(f"Evidence source is not a stored Entry: {entry_id}")
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceValidationError(f"Stored Entry is unreadable: {entry_id}") from exc
    if not isinstance(entry, Mapping) or str(entry.get("id", "")) != entry_id:
        raise EvidenceValidationError(f"Stored Entry identity does not match: {entry_id}")

    trusted_entry = dict(entry)
    raw_path = config.RAW_DIR / f"{entry_id}.txt"
    raw_text = ""
    if raw_path.is_file():
        try:
            raw_text = raw_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise EvidenceValidationError(
                f"Stored Entry body is unreadable: {entry_id}"
            ) from exc
        trusted_entry["raw_text"] = raw_text

    # Entry JSON is a projection, not a trust root. Recompute both identities
    # from the body used by the transition so hand-edited metadata cannot bind
    # a different document to an existing attestation.
    trusted_entry["content_hash"] = content_hash(raw_text) if raw_text else ""
    digest = evidence_digest(raw_text)
    trusted_entry["evidence_digest"] = digest
    metadata = dict(entry.get("metadata", {})) if isinstance(entry.get("metadata"), Mapping) else {}
    metadata["content_hash"] = trusted_entry["content_hash"]
    metadata["evidence_digest"] = digest
    trusted_entry["metadata"] = metadata
    return trusted_entry


def _provenance_registry_path(path: Path | None) -> Path:
    return Path(path) if path else config.DATA_DIR / PROVENANCE_REGISTRY_NAME


def _entry_subject(entry: Mapping[str, object]) -> EvidenceSubject | None:
    """Build the exact registry subject, or ``None`` for unbindable Entries."""
    entry_id = str(entry.get("id", "")).strip()
    digest = str(entry.get("evidence_digest", "")).strip()
    try:
        parsed = urlsplit(str(entry.get("url", "")).strip())
        origin = canonicalize_origin(f"{parsed.scheme}://{parsed.netloc}")
        return EvidenceSubject(
            entry_id=entry_id,
            canonical_origin=origin,
            evidence_digest=digest,
        )
    except (RegistryValidationError, ValueError):
        return None


def _verified_duplicate_relations(entry: Mapping[str, object]) -> list[dict[str, object]]:
    """Recompute persisted duplicate edges before they influence evidence groups."""
    metadata = entry.get("metadata", {})
    if not isinstance(metadata, Mapping):
        return []
    raw_relations = metadata.get("duplicate_relations", [])
    if isinstance(raw_relations, (str, bytes)) or not isinstance(raw_relations, Sequence):
        return []
    verified: list[dict[str, object]] = []
    for relation in raw_relations:
        if not isinstance(relation, Mapping):
            continue
        related_id = str(relation.get("related_entry_id", "")).strip()
        if not related_id or related_id == str(entry.get("id", "")):
            continue
        try:
            related = _read_stored_entry(related_id)
            decision = assess_source_pair(entry, related)
        except (EvidenceValidationError, TypeError, ValueError):
            continue
        if decision.classification not in {"exact", "near_duplicate"}:
            continue
        expected = {
            "related_entry_id": related_id,
            "classification": decision.classification,
            "similarity": decision.similarity,
            "rule": decision.rule,
            "reason": decision.reason,
            "algorithm_version": SOURCE_INDEPENDENCE_VERSION,
        }
        if all(relation.get(key) == value for key, value in expected.items()):
            verified.append(expected)
    return verified


def _load_real_entries(
    source_ids: Sequence[str],
    *,
    transition: EvidenceTransitionRequest | None = None,
    provenance_registry_path: Path | None = None,
) -> dict[str, Mapping[str, object]]:
    """Load real Entries and project only registry-verified governance fields."""
    registry_path = _provenance_registry_path(provenance_registry_path)
    loaded = {entry_id: _read_stored_entry(entry_id) for entry_id in source_ids}

    corrected_subject: EvidenceSubject | None = None
    authority_source_id = ""
    topic = ""
    fact_key = ""
    corrected_entry_id = ""
    if transition is not None and transition.resolution_basis == "official_correction":
        authority_source_id = str(
            transition.resolution_metadata.get("authority_source_id", "")
        ).strip()
        corrected_entry_id = str(
            transition.resolution_metadata.get("corrects_entry_id", "")
        ).strip()
        topic = transition.topic
        fact_key = str(transition.card.get("fact_key", "")).strip()
        if corrected_entry_id:
            corrected_subject = _entry_subject(_read_stored_entry(corrected_entry_id))

    entries: dict[str, Mapping[str, object]] = {}
    for entry_id, trusted_entry in loaded.items():
        subject = _entry_subject(trusted_entry)
        resolution = (
            resolve_provenance(registry_path, subject=subject)
            if subject is not None
            else ProvenanceResolution(status="unverified")
        )
        source = (
            dict(trusted_entry.get("source", {}))
            if isinstance(trusted_entry.get("source"), Mapping)
            else {}
        )
        for field in (
            "tier",
            "is_primary",
            "authority_scope",
            "correction_relations",
            "independent_observation",
            "method_provenance",
            "observation_id",
            "experiment_id",
            "measurement_id",
            "run_id",
            "sample_id",
            "provenance",
        ):
            source.pop(field, None)
        trusted_entry.pop("source_tier", None)
        trusted_entry.pop("source_is_primary", None)
        trusted_entry.pop("is_primary", None)
        for field in (
            "independent_observation",
            "method_provenance",
            "observation_id",
            "experiment_id",
            "measurement_id",
            "run_id",
            "sample_id",
            "provenance",
        ):
            trusted_entry.pop(field, None)

        source["tier"] = resolution.evidence_tier
        source["is_primary"] = resolution.is_primary
        source["independent_observation"] = resolution.independent_observation
        source["provenance_registry"] = {
            "status": resolution.status,
            "registry_id": resolution.registry_id,
            "registry_revision": resolution.registry_revision,
            "attestations": [asdict(ref) for ref in resolution.attestation_refs],
            "integrity_model": "sha256-hash-chain-no-authentication",
        }

        # Authority pairs are deliberately projected only for the exact
        # official-correction request being executed. This avoids turning two
        # independent (topic, fact_key) grants into an accidental cross product
        # in the legacy EvidenceRef representation.
        if (
            entry_id == authority_source_id
            and subject is not None
            and corrected_subject is not None
            and resolution.authorizes_official_correction(
                topic=topic,
                fact_key=fact_key,
                corrected_subject=corrected_subject,
            )
        ):
            source["authority_scope"] = {
                "topics": [topic],
                "fact_keys": [fact_key],
            }
            source["correction_relations"] = [
                {"relation": "corrects", "entry_id": corrected_entry_id}
            ]

        metadata = dict(trusted_entry.get("metadata", {}))
        for field in (
            "independent_observation",
            "method_provenance",
            "observation_id",
            "experiment_id",
            "measurement_id",
            "run_id",
            "sample_id",
            "provenance",
        ):
            metadata.pop(field, None)
        # Recompute duplicate relations from the same governance-sanitised
        # projection that the evidence rules will consume.
        trusted_entry["source"] = source
        trusted_entry["metadata"] = metadata
        metadata["duplicate_relations"] = _verified_duplicate_relations(trusted_entry)
        metadata["duplicate_detection"] = {
            "status": "verified_at_use",
            "algorithm_version": SOURCE_INDEPENDENCE_VERSION,
        }
        trusted_entry["metadata"] = metadata
        entries[entry_id] = trusted_entry
    return entries


def _source_ids(refs) -> list[str]:
    return list(dict.fromkeys(ref.entry_id for ref in refs))


def _evidence_ref_projection(ref) -> dict[str, object]:
    return {
        "entry_id": ref.entry_id,
        "locator": asdict(ref.locator),
        "source_tier": ref.source_tier,
        "source_key": ref.source_key,
        "content_hash": ref.content_hash,
        "evidence_digest": ref.evidence_digest,
        "is_primary": ref.is_primary,
        "authority_topics": list(ref.authority_topics),
        "authority_fact_keys": list(ref.authority_fact_keys),
        "corrects_entry_ids": list(ref.corrects_entry_ids),
        "duplicate_detection_version": ref.duplicate_detection_version,
        "duplicate_relations": [
            asdict(relation) for relation in ref.duplicate_relations
        ],
        "independence_identity": ref.independence_identity,
        "provenance_registry_snapshot": {
            "status": ref.provenance_registry_status,
            "registry_id": ref.provenance_registry_id,
            "registry_revision": ref.provenance_registry_revision,
            "integrity_model": ref.provenance_integrity_model,
            "attestations": [
                asdict(attestation)
                for attestation in ref.provenance_attestation_refs
            ],
        },
    }


def _strength_projection(strength) -> dict:
    data = asdict(strength)
    data["tier_counts"] = dict(strength.tier_counts)
    data["rationale"] = list(strength.rationale)
    return data


def _proposal_projection(proposal) -> dict | None:
    if proposal is None:
        return None
    return {
        "claim": proposal.claim,
        "evidence": proposal.evidence,
        "fact_key": proposal.fact_key,
        "fact_value": proposal.fact_value,
        "source_ids": _source_ids(proposal.evidence_refs),
        "evidence_refs": [
            _evidence_ref_projection(ref) for ref in proposal.evidence_refs
        ],
        "strength": _strength_projection(proposal.strength),
    }


def project_memory_version(version: CardVersion, *, public_state: str | None = None) -> dict:
    """Project a governed version through the stable public KnowledgeCard shape."""
    state = public_state or version.state
    strength = _strength_projection(version.strength)
    proposal = _proposal_projection(getattr(version, "proposal", None))
    card = KnowledgeCard(
        card_id=version.card_id,
        title=version.title,
        claim=version.claim,
        evidence=version.evidence,
        tags=list(version.tags),
        confidence=version.strength.score,
        source_ids=_source_ids(version.evidence_refs),
        provenance={
            "topic": version.topic,
            "memory_version_id": version.version_id,
            "transition_event_id": version.event_id,
            "memory_revision": version.revision,
            "memory_state": state,
            "memory_recorded_state": version.state,
            "confidence_kind": "ordinal_evidence_strength",
            "is_probability": False,
        },
        created_at=version.created_at,
        updated_at=version.created_at,
        extra={
            "evidence_governance": {
                "state": state,
                "recorded_state": version.state,
                "version_id": version.version_id,
                "revision": version.revision,
                "parent_version_ids": list(version.parent_version_ids),
                "strength": strength,
                "fact_key": version.fact_key,
                "fact_value": version.fact_value,
                "evidence_refs": [
                    _evidence_ref_projection(ref) for ref in version.evidence_refs
                ],
                "proposed_conflict": proposal,
            }
        },
    )
    return card_to_public_dict(card)


def _event_projection(event, snapshot) -> dict:
    output_version = snapshot.versions_by_id[event.output_version_ids[0]]
    proposal = _proposal_projection(getattr(output_version, "proposal", None))
    resolution_metadata = dict(getattr(event, "resolution_metadata", ()))
    resolution_basis = getattr(event, "resolution_basis", "")
    return {
        "event_id": event.event_id,
        "action": event.action,
        "topic": event.topic,
        "parent_version_ids": list(event.parent_version_ids),
        "output_version_ids": list(event.output_version_ids),
        "source_ids": list(event.evidence_ids),
        "evidence_use_ids": list(event.evidence_use_ids),
        "algorithm_version": event.algorithm_version,
        "governance_version": event.governance_version,
        "reason": event.reason,
        "idempotency_key": event.idempotency_key,
        "request_hash": event.request_hash,
        "created_at": event.created_at,
        "conflict": asdict(event.conflict),
        "proposed_conflict": proposal,
        "resolution": {
            "basis": resolution_basis,
            "metadata": resolution_metadata,
        },
    }


def apply_evidence_transition(
    request: Mapping[str, object],
    *,
    ledger_path: Path | None = None,
    provenance_registry_path: Path | None = None,
) -> dict:
    """Validate an explicit request, load real Entries, then call the executor."""
    transition = EvidenceTransitionRequest.from_mapping(request)
    registry_path = _provenance_registry_path(provenance_registry_path)
    # Global lock order: provenance registry, then evidence-memory ledger.
    # Admin revoke/supersede operations use the same registry lock, so the
    # resolved grants cannot change before their domain commit is durable.
    with provenance_registry_lock(registry_path):
        entries = _load_real_entries(
            transition.source_ids,
            transition=transition,
            provenance_registry_path=registry_path,
        )
        memory = _memory(ledger_path)
        result = memory.apply_transition(
            transition.action,
            topic=transition.topic,
            entries=entries,
            source_ids=transition.source_ids,
            evidence_locators=transition.evidence_locators,
            card=transition.card,
            target_card_ids=transition.target_card_ids,
            reason=transition.reason,
            resolution_basis=transition.resolution_basis,
            resolution_metadata=transition.resolution_metadata,
            idempotency_key=transition.idempotency_key,
        )
        snapshot = memory.snapshot()
        version = snapshot.versions_by_id[result.version_ids[0]]
        event = next(item for item in snapshot.events if item.event_id == result.event_id)
    return {
        "applied": result.applied,
        "action": result.action,
        "event_id": result.event_id,
        "version_ids": list(result.version_ids),
        "idempotency_key": result.idempotency_key,
        "card": project_memory_version(version),
        "event": _event_projection(event, snapshot),
    }


class EvidenceMemoryAtomicBatchExecutor:
    """Production adapter from previewed policy operations to schema-v4 ledger writes."""

    def __init__(
        self,
        *,
        ledger_path: Path | None = None,
        provenance_registry_path: Path | None = None,
    ) -> None:
        self.memory = _memory(ledger_path)
        self.provenance_registry_path = provenance_registry_path

    def lookup_commit(self, decision_id: str, request_hash: str):
        return self.memory.lookup_atomic_batch(decision_id, request_hash)

    @staticmethod
    def _transition_for_operation(
        operation: PlannedOperation,
        *,
        expected_heads: Mapping[str, str],
    ) -> EvidenceTransitionRequest:
        request = dict(operation.request)
        forbidden = {"action", "target_card_ids", "idempotency_key"}.intersection(request)
        if forbidden:
            raise ValueError(
                "SPLIT operation requests cannot override executor fields: "
                + ", ".join(sorted(forbidden))
            )
        if operation.operation not in {"UPDATE", "CREATE"}:
            raise ValueError(f"Unsupported SPLIT operation: {operation.operation!r}")
        request["action"] = operation.operation
        request["target_card_ids"] = list(operation.target_card_ids)

        if operation.operation == "UPDATE":
            if len(operation.target_heads) != 1:
                raise ValueError("SPLIT UPDATE must bind exactly one target head")
            head = operation.target_heads[0]
            if expected_heads != {head.card_id: head.version_id}:
                raise ValueError("SPLIT UPDATE target head differs from the decision receipt")
            if operation.target_card_ids != (head.card_id,):
                raise ValueError("SPLIT UPDATE target card differs from its target head")
        elif operation.target_heads or operation.target_card_ids:
            raise ValueError("SPLIT CREATE cannot target an existing card")
        return EvidenceTransitionRequest.from_mapping(request)

    def execute_atomic(self, trace: DecisionTrace):
        validate_decision_trace(trace)
        if trace.suggested_operation != "SPLIT":
            raise ValueError("Atomic evidence adapter only accepts SPLIT traces")
        operations = trace.operations
        decision_id = trace.decision_id
        idempotency_key = trace.idempotency_key
        request_hash = trace.request_hash
        expected_heads = {
            head.card_id: head.version_id for head in trace.target_heads
        }
        policy_version = trace.policy_version
        algorithm_version = trace.algorithm_version
        evidence_ids = trace.evidence_ids
        manifest_hash = execution_manifest_hash(trace)
        if tuple(operation.operation for operation in operations) != ("UPDATE", "CREATE"):
            raise ValueError("SPLIT must contain exactly UPDATE followed by CREATE")
        if any(operation.decision_id != decision_id for operation in operations):
            raise ValueError("SPLIT operations do not share the decision identity")

        update = self._transition_for_operation(
            operations[0], expected_heads=expected_heads
        )
        create = self._transition_for_operation(
            operations[1], expected_heads=expected_heads
        )
        if update.topic != create.topic:
            raise ValueError("SPLIT UPDATE and CREATE must share one topic")
        operation_evidence = tuple(sorted(set(update.source_ids) | set(create.source_ids)))
        if operation_evidence != tuple(sorted(set(evidence_ids))):
            raise ValueError("SPLIT operation evidence differs from the preview trace")

        registry_path = _provenance_registry_path(self.provenance_registry_path)
        # Keep the same registry -> evidence-ledger order as single transitions.
        with provenance_registry_lock(registry_path):
            update_entries = _load_real_entries(
                update.source_ids,
                transition=update,
                provenance_registry_path=registry_path,
            )
            create_entries = _load_real_entries(
                create.source_ids,
                transition=create,
                provenance_registry_path=registry_path,
            )
            try:
                return self.memory.apply_atomic_split(
                    update=AtomicSplitOperation(
                        action="UPDATE",
                        topic=update.topic,
                        entries=update_entries,
                        source_ids=update.source_ids,
                        evidence_locators=update.evidence_locators,
                        card=update.card,
                        target_card_ids=update.target_card_ids,
                        reason=update.reason,
                        resolution_basis=update.resolution_basis,
                        resolution_metadata=update.resolution_metadata,
                    ),
                    create=AtomicSplitOperation(
                        action="CREATE",
                        topic=create.topic,
                        entries=create_entries,
                        source_ids=create.source_ids,
                        evidence_locators=create.evidence_locators,
                        card=create.card,
                        target_card_ids=create.target_card_ids,
                        reason=create.reason,
                        resolution_basis=create.resolution_basis,
                        resolution_metadata=create.resolution_metadata,
                    ),
                    decision_id=decision_id,
                    request_hash=request_hash,
                    expected_heads=expected_heads,
                    idempotency_key=idempotency_key,
                    policy_version=policy_version,
                    algorithm_version=algorithm_version,
                    execution_manifest_hash=manifest_hash,
                )
            except StaleHeadError as exc:
                raise StaleDecisionError(str(exc)) from exc


def _public_version_state(version: CardVersion, active_heads: Mapping[str, str]) -> str:
    if active_heads.get(version.card_id) == version.version_id and version.state in {"active", "contested"}:
        return version.state
    return "retired" if version.state == "retired" else "superseded"


def get_memory_snapshot(
    topic: str = "",
    *,
    ledger_path: Path | None = None,
) -> dict:
    """Return latest public projections, explicitly separated by memory state."""
    if not isinstance(topic, str):
        raise ValueError("topic must be a string")
    topic = topic.strip()
    # An initial read must not enroll the user or create an empty business ledger.
    resolved_path = Path(ledger_path) if ledger_path is not None else config.DATA_DIR / EVIDENCE_MEMORY_LEDGER_NAME
    if not resolved_path.exists():
        states = {state: [] for state in ("active", "contested", "retired", "superseded")}
        return {"topic": topic, "current_total": 0, "total_latest_cards": 0,
                "state_counts": {state: 0 for state in states}, "cards": [],
                "states": states, "event_count": 0}
    snapshot = _memory(ledger_path).snapshot()
    latest_by_card: dict[str, CardVersion] = {}
    for version in snapshot.versions:
        if topic and version.topic != topic:
            continue
        prior = latest_by_card.get(version.card_id)
        if prior is None or version.revision > prior.revision:
            latest_by_card[version.card_id] = version

    groups: dict[str, list[dict]] = {
        "active": [],
        "contested": [],
        "retired": [],
        "superseded": [],
    }
    for version in latest_by_card.values():
        state = _public_version_state(version, snapshot.active_heads)
        groups[state].append(project_memory_version(version, public_state=state))

    for cards in groups.values():
        cards.sort(key=lambda card: (card.get("updated_at", ""), card.get("id", "")), reverse=True)
    current_cards = groups["active"] + groups["contested"]
    return {
        "topic": topic,
        "current_total": len(current_cards),
        "total_latest_cards": len(latest_by_card),
        "state_counts": {state: len(cards) for state, cards in groups.items()},
        "cards": current_cards,
        "states": groups,
        "event_count": len(snapshot.events),
    }


def get_memory_history(
    topic: str = "",
    card_id: str = "",
    *,
    ledger_path: Path | None = None,
) -> dict:
    """Return public version history plus the executor's replayable audit DAG."""
    if not isinstance(topic, str) or not isinstance(card_id, str):
        raise ValueError("topic and card_id filters must be strings")
    topic = topic.strip()
    card_id = card_id.strip()
    memory = _memory(ledger_path)
    snapshot = memory.snapshot()
    selected_versions = [
        version
        for version in snapshot.versions
        if (not topic or version.topic == topic) and (not card_id or version.card_id == card_id)
    ]
    raw_graph = memory.audit_graph()
    version_ids = {version.version_id for version in selected_versions}
    if card_id:
        changed = True
        while changed:
            changed = False
            for edge in raw_graph["edges"]:
                if edge["to"] in version_ids and edge["from"] not in version_ids:
                    version_ids.add(edge["from"])
                    changed = True
    versions = [version for version in snapshot.versions if version.version_id in version_ids]
    events = [event for event in snapshot.events if event.output_version_ids[0] in version_ids]
    nodes = [node for node in raw_graph["nodes"] if node["version_id"] in version_ids]
    edges = [
        edge
        for edge in raw_graph["edges"]
        if edge["from"] in version_ids and edge["to"] in version_ids
    ]
    return {
        "topic": topic,
        "card_id": card_id,
        "events": [_event_projection(event, snapshot) for event in events],
        "versions": [project_memory_version(
            version, public_state=_public_version_state(version, snapshot.active_heads)
        ) for version in versions],
        "audit_graph": {"nodes": nodes, "edges": edges},
    }


def crystallize_cards(
    topic: str,
    min_entries: int = 3,
    max_entries: int = 10,
    max_cards: int = 5,
    model: str = None,
    provider: str = None,
    auto_embed: bool = True,
) -> list[KnowledgeCard]:
    """Crystallize and persist cards for a topic."""
    return crystallize.crystallize_and_save(
        topic=topic,
        min_entries=min_entries,
        max_entries=max_entries,
        max_cards=max_cards,
        model=model,
        provider=provider,
        auto_embed=auto_embed,
    )


def list_cards(topic: str = "", limit: int = 20) -> list[KnowledgeCard]:
    """List persisted knowledge cards."""
    return crystallize.list_crystallized(topic=topic or "", limit=limit)


def get_card_detail(card_id: str) -> Optional[KnowledgeCard]:
    """Get a single card by ID."""
    return crystallize.get_card(card_id)


def delete_card_by_id(card_id: str) -> bool:
    """Delete a card by ID."""
    return crystallize.delete_card(card_id)


def count_cards() -> int:
    """Return the exact persisted card count without pagination."""
    return crystallize.count_cards()


def get_card_topic_stats() -> dict[str, int]:
    """Return card counts grouped by topic."""
    return crystallize.get_topic_stats()


def search_cards_semantic(query: str, top_k: int = 10) -> list[dict]:
    """Return JSON-safe semantic card search results."""
    results = crystallize.semantic_search(query, top_k=top_k)
    projected = []
    for item in results:
        card = item.get("card")
        if card is None:
            continue
        projected.append({
            "score": item.get("score", 0.0),
            "card": card_to_public_dict(card),
        })
    return projected


def rebuild_card_embeddings() -> int:
    """Rebuild card embedding index."""
    return crystallize.rebuild_embeddings()
