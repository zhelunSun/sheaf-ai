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

from sheaf_ai import config, crystallize
from sheaf_ai.entry_paths import InvalidEntryId, resolve_entry_json_path
from sheaf_ai.evidence_memory import (
    VALID_ACTIONS,
    VALID_RESOLUTION_BASES,
    CardVersion,
    EvidenceGovernedMemory,
    EvidenceValidationError,
)
from sheaf_cards.base import KnowledgeCard


EVIDENCE_MEMORY_LEDGER_NAME = "evidence_memory_ledger.json"
_TRANSITION_FIELDS = frozenset(
    {
        "action",
        "topic",
        "source_ids",
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


def card_to_public_dict(card: KnowledgeCard, include_tag_entries: bool = False) -> dict:
    """Project a KnowledgeCard into the stable public card shape.

    Args:
        card: KnowledgeCard to project
        include_tag_entries: If True, include rich tag entries with source tracking
    """
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
    }
    extra = data.get("extra", getattr(card, "extra", {})) or {}
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


def _load_real_entries(source_ids: Sequence[str]) -> dict[str, Mapping[str, object]]:
    """Load the requested evidence from Sheaf storage, never caller payloads."""
    entries: dict[str, Mapping[str, object]] = {}
    for entry_id in source_ids:
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
        entries[entry_id] = entry
    return entries


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
        "source_ids": [ref.entry_id for ref in proposal.evidence_refs],
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
        source_ids=[ref.entry_id for ref in version.evidence_refs],
        provenance={
            "topic": version.topic,
            "memory_version_id": version.version_id,
            "transition_event_id": version.event_id,
            "memory_revision": version.revision,
            "memory_state": state,
            "confidence_kind": "ordinal_evidence_strength",
            "is_probability": False,
        },
        created_at=version.created_at,
        updated_at=version.created_at,
        extra={
            "evidence_governance": {
                "state": state,
                "version_id": version.version_id,
                "revision": version.revision,
                "parent_version_ids": list(version.parent_version_ids),
                "strength": strength,
                "fact_key": version.fact_key,
                "fact_value": version.fact_value,
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
) -> dict:
    """Validate an explicit request, load real Entries, then call the executor."""
    transition = EvidenceTransitionRequest.from_mapping(request)
    entries = _load_real_entries(transition.source_ids)
    memory = _memory(ledger_path)
    result = memory.apply_transition(
        transition.action,
        topic=transition.topic,
        entries=entries,
        source_ids=transition.source_ids,
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


def get_memory_snapshot(
    topic: str = "",
    *,
    ledger_path: Path | None = None,
) -> dict:
    """Return latest public projections, explicitly separated by memory state."""
    if not isinstance(topic, str):
        raise ValueError("topic must be a string")
    topic = topic.strip()
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
        is_current = snapshot.active_heads.get(version.card_id) == version.version_id
        if is_current and version.state in {"active", "contested"}:
            state = version.state
        elif version.state == "retired":
            state = "retired"
        else:
            state = "superseded"
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
        "versions": [project_memory_version(version) for version in versions],
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
