"""Deterministic evidence, conflict, and resolution rules."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Mapping, Sequence
from urllib.parse import urlparse

from sheaf_ai._evidence_memory_models import (
    ALGORITHM_VERSION,
    TIER_WEIGHTS,
    VALID_RESOLUTION_BASES,
    VALID_TIERS,
    CardVersion,
    ConflictAssessment,
    ConflictResolutionRequired,
    EvidenceRef,
    EvidenceStrength,
    EvidenceValidationError,
    TransitionValidationError,
)


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalise_text(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _dedupe_strings(values: Sequence[object]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _source_key(entry: Mapping[str, object]) -> str:
    source = entry.get("source")
    if isinstance(source, Mapping):
        domain = _normalise_text(source.get("domain"))
        if domain:
            return f"domain:{domain}"
    url = str(entry.get("url", "")).strip()
    domain = urlparse(url).netloc.casefold()
    if domain.startswith("www."):
        domain = domain[4:]
    return f"domain:{domain}" if domain else "unknown"


def _source_tier(entry: Mapping[str, object]) -> str:
    """Read credibility tier only; content ``quality_tier`` is unrelated."""
    tier = entry.get("source_tier")
    if not tier:
        source = entry.get("source")
        tier = source.get("tier") if isinstance(source, Mapping) else None
    normalised = str(tier or "U").upper()
    return normalised if normalised in VALID_TIERS else "U"


def _content_hash(entry: Mapping[str, object]) -> str:
    value = entry.get("content_hash", "")
    metadata = entry.get("metadata")
    if not value and isinstance(metadata, Mapping):
        value = metadata.get("content_hash", "")
    return str(value or "")


def _is_primary(entry: Mapping[str, object]) -> bool:
    if entry.get("source_is_primary") is True or entry.get("is_primary") is True:
        return True
    source = entry.get("source")
    return isinstance(source, Mapping) and source.get("is_primary") is True


def allowlisted_evidence(
    entries: Sequence[Mapping[str, object]] | Mapping[str, Mapping[str, object]],
    requested_source_ids: Sequence[object],
) -> tuple[EvidenceRef, ...]:
    """Resolve untrusted source IDs against current entries and deduplicate.

    Duplicate copies of the same entry ID must be byte-equivalent as canonical
    JSON.  This prevents an ambiguous duplicate from changing tier or source
    identity depending on list order.
    """
    if isinstance(entries, Mapping):
        raw_entries: list[Mapping[str, object]] = []
        for entry_id, raw_entry in entries.items():
            entry = dict(raw_entry)
            present_id = str(entry.get("id", ""))
            if present_id and present_id != str(entry_id):
                raise EvidenceValidationError(
                    f"Entry map key {entry_id!r} disagrees with entry id {present_id!r}"
                )
            entry["id"] = str(entry_id)
            raw_entries.append(entry)
    else:
        raw_entries = list(entries)

    allowed: dict[str, Mapping[str, object]] = {}
    fingerprints: dict[str, str] = {}
    for entry in raw_entries:
        if not isinstance(entry, Mapping):
            raise EvidenceValidationError("Evidence allowlist entries must be objects")
        entry_id = str(entry.get("id", "")).strip()
        if not entry_id:
            raise EvidenceValidationError("Evidence allowlist entry is missing id")
        fingerprint = _canonical_hash(entry)
        if entry_id in fingerprints and fingerprints[entry_id] != fingerprint:
            raise EvidenceValidationError(f"Conflicting duplicate entry id: {entry_id}")
        fingerprints[entry_id] = fingerprint
        allowed[entry_id] = entry

    source_ids = tuple(sorted(_dedupe_strings(requested_source_ids)))
    unknown = [source_id for source_id in source_ids if source_id not in allowed]
    if unknown:
        raise EvidenceValidationError(
            "Source IDs are not in the current evidence allowlist: " + ", ".join(unknown)
        )

    return tuple(
        EvidenceRef(
            entry_id=source_id,
            source_tier=_source_tier(allowed[source_id]),
            source_key=_source_key(allowed[source_id]),
            content_hash=_content_hash(allowed[source_id]),
            is_primary=_is_primary(allowed[source_id]),
        )
        for source_id in source_ids
    )


def compute_evidence_strength(
    refs: Sequence[EvidenceRef],
    *,
    conflict: bool = False,
) -> EvidenceStrength:
    """Compute an explainable ordinal evidence-strength score.

    Duplicate entry IDs are removed.  Corroboration is counted by independent
    ``source_key`` and each source contributes only its best tier.  Formula::

        score = 0.65 * mean(source tier weights)
                + min(0.20, 0.10 * (independent sources - 1))
                - (0.20 if conflict else 0)

    The score is useful for ordering and guardrails only.  It is not trained or
    empirically calibrated and must not be described as a probability.
    """
    unique_refs = {ref.entry_id: ref for ref in refs}
    best_by_source: dict[str, float] = {}
    tier_counts = {tier: 0 for tier in ("A", "B", "C", "D", "U")}
    for ref in unique_refs.values():
        tier = ref.source_tier if ref.source_tier in VALID_TIERS else "U"
        tier_counts[tier] += 1
        weight = TIER_WEIGHTS[tier]
        best_by_source[ref.source_key] = max(best_by_source.get(ref.source_key, 0.0), weight)

    source_count = len(best_by_source)
    mean_weight = sum(best_by_source.values()) / source_count if source_count else 0.0
    tier_component = 0.65 * mean_weight
    corroboration = min(0.20, 0.10 * max(0, source_count - 1))
    penalty = 0.20 if conflict else 0.0
    score = round(max(0.0, min(0.95, tier_component + corroboration - penalty)), 4)
    band = "strong" if score >= 0.65 else "moderate" if score >= 0.35 else "weak"
    counts_tuple = tuple((tier, count) for tier, count in tier_counts.items() if count)
    rationale = (
        f"{source_count} independent source(s) after source-key deduplication",
        f"tier component={tier_component:.4f} from source_tier weights",
        f"corroboration bonus={corroboration:.4f}",
        f"structured-conflict penalty={penalty:.4f}",
        "ordinal rule score; not a calibrated probability",
    )
    return EvidenceStrength(
        score=score,
        band=band,
        algorithm=ALGORITHM_VERSION,
        independent_source_count=source_count,
        tier_counts=counts_tuple,
        conflict_penalty=penalty,
        rationale=rationale,
    )


def assess_structured_conflict(
    parents: Sequence[CardVersion],
    fact_key: str,
    fact_value: str,
) -> ConflictAssessment:
    """Detect contradictions only for explicit ``fact_key``/``fact_value``.

    Free-text semantic contradiction is intentionally reported as ``unknown``;
    this rule does not pretend that lexical heuristics understand negation.
    """
    key = _normalise_text(fact_key)
    value = _normalise_text(fact_value)
    if not key or not value:
        return ConflictAssessment(
            state="unknown",
            rule="structured-fact-v1",
            explanation="No complete structured fact was supplied; free-text conflict is not inferred.",
        )
    comparable = {
        _normalise_text(parent.fact_value)
        for parent in parents
        if _normalise_text(parent.fact_key) == key and _normalise_text(parent.fact_value)
    }
    if not comparable:
        return ConflictAssessment(
            state="unknown",
            rule="structured-fact-v1",
            explanation=f"No prior value exists for fact key {fact_key!r}.",
        )
    if comparable == {value}:
        return ConflictAssessment(
            state="consistent",
            rule="structured-fact-v1",
            explanation=f"All comparable versions agree on fact key {fact_key!r}.",
        )
    return ConflictAssessment(
        state="conflict",
        rule="structured-fact-v1",
        explanation=(
            f"Fact key {fact_key!r} changes from {sorted(comparable)!r} "
            f"to {fact_value!r}."
        ),
    )


def assess_transition_conflict(
    action: str,
    parents: Sequence[CardVersion],
    fact_key: str,
    fact_value: str,
) -> ConflictAssessment:
    """Assess a new dispute or the explicit resolution of an existing one."""
    if action == "UPDATE" and any(parent.state == "contested" for parent in parents):
        return ConflictAssessment(
            state="conflict",
            rule="structured-fact-v1",
            explanation="This UPDATE resolves a previously preserved structured dispute.",
        )
    return assess_structured_conflict(parents, fact_key, fact_value)


def _normalise_resolution_metadata(
    metadata: Mapping[str, object] | None,
) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise TransitionValidationError("resolution_metadata must be an object")
    result: list[tuple[str, str]] = []
    for key, value in metadata.items():
        normalised_key = str(key).strip()
        if not normalised_key or isinstance(value, (dict, list, tuple, set)):
            raise TransitionValidationError("resolution_metadata values must be scalar")
        normalised_value = str(value).strip()
        if not normalised_value:
            raise TransitionValidationError(
                f"resolution_metadata value is empty: {normalised_key!r}"
            )
        result.append((normalised_key, normalised_value))
    return tuple(sorted(result))


def _require_metadata(
    metadata: tuple[tuple[str, str], ...],
    required_keys: set[str],
    basis: str,
) -> dict[str, str]:
    values = dict(metadata)
    if set(values) != required_keys:
        raise ConflictResolutionRequired(
            f"{basis} requires exactly resolution_metadata keys: "
            + ", ".join(sorted(required_keys))
        )
    return values


def _validate_iso_date_or_datetime(value: str, field: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConflictResolutionRequired(f"{field} must be an ISO date or datetime") from exc


def validate_resolution_basis(
    parents: Sequence[CardVersion],
    refs: Sequence[EvidenceRef],
    conflict: ConflictAssessment,
    basis: str,
    metadata: tuple[tuple[str, str], ...],
    resolved_fact_value: str,
    *,
    allow_unresolved: bool = False,
) -> None:
    """Validate a conflict decision without treating source tier as truth.

    ``stronger_evidence`` is the only strategy that compares the ordinal rule
    score.  The other strategies encode independent governance facts: an
    allowlisted primary source correcting a parent entry, an effective-dated
    version change, or a traceable human decision.
    """
    if conflict.state != "conflict":
        if basis or metadata:
            raise TransitionValidationError(
                "resolution_basis is only valid for a detected structured conflict"
            )
        return
    if allow_unresolved:
        if basis or metadata:
            raise TransitionValidationError("CONTEST cannot carry a resolution basis")
        if not refs:
            raise ConflictResolutionRequired("CONTEST requires new conflicting evidence")
        return
    if basis not in VALID_RESOLUTION_BASES:
        raise ConflictResolutionRequired(
            conflict.explanation + " Structured conflict requires resolution_basis: "
            + ", ".join(sorted(VALID_RESOLUTION_BASES))
        )
    if basis == "stronger_evidence":
        if not refs:
            raise ConflictResolutionRequired("stronger_evidence requires resolution evidence")
        _require_metadata(metadata, set(), basis)
        candidate = compute_evidence_strength(refs)
        parent_scores = [
            compute_evidence_strength(parent.evidence_refs).score for parent in parents
        ]
        parent_scores.extend(
            compute_evidence_strength(parent.proposal.evidence_refs).score
            for parent in parents
            if parent.proposal is not None
        )
        strongest_parent = max(parent_scores, default=0.0)
        if candidate.score <= strongest_parent:
            raise ConflictResolutionRequired(
                "stronger_evidence requires a strictly higher ordinal evidence score "
                f"({candidate.score:.4f} <= {strongest_parent:.4f})"
            )
        return

    if basis == "official_correction":
        if not refs:
            raise ConflictResolutionRequired("official_correction requires resolution evidence")
        values = _require_metadata(
            metadata,
            {"authoritative_fact_value", "authority_source_id", "corrects_entry_id"},
            basis,
        )
        authority = next(
            (ref for ref in refs if ref.entry_id == values["authority_source_id"]),
            None,
        )
        if authority is None or not authority.is_primary:
            raise ConflictResolutionRequired(
                "official_correction authority_source_id must reference a new allowlisted "
                "entry whose source.is_primary is true"
            )
        parent_evidence_ids = {
            ref.entry_id for parent in parents for ref in parent.evidence_refs
        }
        parent_evidence_ids.update(
            ref.entry_id
            for parent in parents
            if parent.proposal is not None
            for ref in parent.proposal.evidence_refs
        )
        if values["corrects_entry_id"] not in parent_evidence_ids:
            raise ConflictResolutionRequired(
                "official_correction corrects_entry_id must reference parent evidence"
            )
        if _normalise_text(values["authoritative_fact_value"]) != _normalise_text(
            resolved_fact_value
        ):
            raise ConflictResolutionRequired(
                "official_correction authoritative_fact_value must equal the output fact value"
            )
        return

    if basis == "version_change":
        if not refs:
            raise ConflictResolutionRequired("version_change requires resolution evidence")
        values = _require_metadata(
            metadata,
            {"effective_at", "effective_fact_value", "supersedes_fact_value"},
            basis,
        )
        _validate_iso_date_or_datetime(values["effective_at"], "effective_at")
        prior_values = {
            _normalise_text(parent.fact_value)
            for parent in parents
            if parent.fact_value
        }
        prior_values.update(
            _normalise_text(parent.proposal.fact_value)
            for parent in parents
            if parent.proposal is not None and parent.proposal.fact_value
        )
        if _normalise_text(values["supersedes_fact_value"]) not in prior_values:
            raise ConflictResolutionRequired(
                "version_change supersedes_fact_value must match a parent fact value"
            )
        if _normalise_text(values["effective_fact_value"]) != _normalise_text(
            resolved_fact_value
        ):
            raise ConflictResolutionRequired(
                "version_change effective_fact_value must equal the output fact value"
            )
        return

    values = _require_metadata(
        metadata,
        {"adjudicator_id", "decided_at", "decision_id"},
        basis,
    )
    _validate_iso_date_or_datetime(values["decided_at"], "decided_at")



def merge_evidence_refs(*groups: Sequence[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    """Union immutable references by entry ID while preserving first provenance."""
    merged: dict[str, EvidenceRef] = {}
    for group in groups:
        for ref in group:
            merged.setdefault(ref.entry_id, ref)
    return tuple(merged.values())
