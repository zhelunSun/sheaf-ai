"""Deterministic evidence, conflict, and resolution rules."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from itertools import combinations
from typing import Mapping, Sequence
from urllib.parse import urlparse

from sheaf_ai._evidence_memory_models import (
    ALGORITHM_VERSION,
    DIGEST_ALGORITHM_VERSION,
    GOVERNANCE_VERSION,
    LEGACY_ALGORITHM_VERSION,
    LEGACY_GOVERNANCE_VERSION,
    TIER_WEIGHTS,
    VALID_RESOLUTION_BASES,
    VALID_TIERS,
    CardVersion,
    ConflictAssessment,
    ConflictResolutionRequired,
    EvidenceLocator,
    EvidenceDuplicateRelation,
    EvidenceRef,
    EvidenceStrength,
    EvidenceValidationError,
    TransitionValidationError,
    locator_identity,
)
from sheaf_ai.source_independence import (
    SOURCE_INDEPENDENCE_VERSION,
    independent_provenance_identity,
)


_SHA256_EVIDENCE_DIGEST = re.compile(r"sha256:([0-9a-fA-F]{64})\Z")


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


def _evidence_digest(entry: Mapping[str, object]) -> str:
    value = entry.get("evidence_digest", "")
    metadata = entry.get("metadata")
    if not value and isinstance(metadata, Mapping):
        value = metadata.get("evidence_digest", "")
    match = _SHA256_EVIDENCE_DIGEST.fullmatch(str(value or "").strip())
    return f"sha256:{match.group(1).lower()}" if match else ""


def _is_primary(entry: Mapping[str, object]) -> bool:
    if entry.get("source_is_primary") is True or entry.get("is_primary") is True:
        return True
    source = entry.get("source")
    return isinstance(source, Mapping) and source.get("is_primary") is True


def _normalised_scope_values(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return ()
    return tuple(sorted({_normalise_text(item) for item in value if _normalise_text(item)}))


def _authority_fields(entry: Mapping[str, object]) -> tuple[tuple[str, ...], ...]:
    source = entry.get("source")
    if not isinstance(source, Mapping):
        return (), (), ()
    scope = source.get("authority_scope")
    topics: tuple[str, ...] = ()
    fact_keys: tuple[str, ...] = ()
    if isinstance(scope, Mapping):
        topics = _normalised_scope_values(scope.get("topics"))
        fact_keys = _normalised_scope_values(scope.get("fact_keys"))
    raw_relations = source.get("correction_relations")
    corrected: set[str] = set()
    if isinstance(raw_relations, Sequence) and not isinstance(raw_relations, (str, bytes)):
        for relation in raw_relations:
            if not isinstance(relation, Mapping):
                continue
            if _normalise_text(relation.get("relation")) != "corrects":
                continue
            entry_id = str(relation.get("entry_id", "")).strip()
            if entry_id:
                corrected.add(entry_id)
    return topics, fact_keys, tuple(sorted(corrected))


def _duplicate_relation_fields(
    entry: Mapping[str, object],
    entry_id: str,
) -> tuple[str, tuple[EvidenceDuplicateRelation, ...], str]:
    metadata = entry.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    diagnostic = metadata.get("duplicate_detection")
    detection_version = ""
    if isinstance(diagnostic, Mapping):
        detection_version = str(diagnostic.get("algorithm_version", "")).strip()
        if detection_version and detection_version != SOURCE_INDEPENDENCE_VERSION:
            raise EvidenceValidationError(
                f"Entry {entry_id} has unsupported duplicate detection version"
            )
    raw_relations = metadata.get("duplicate_relations", ())
    if isinstance(raw_relations, (str, bytes)) or not isinstance(
        raw_relations,
        Sequence,
    ):
        raise EvidenceValidationError(f"Entry {entry_id} duplicate relations must be a list")
    relations: dict[str, EvidenceDuplicateRelation] = {}
    for raw_relation in raw_relations:
        if not isinstance(raw_relation, Mapping):
            raise EvidenceValidationError(
                f"Entry {entry_id} contains an invalid duplicate relation"
            )
        relation = EvidenceDuplicateRelation.from_dict(raw_relation)
        if not relation.related_entry_id or relation.related_entry_id == entry_id:
            raise EvidenceValidationError(
                f"Entry {entry_id} duplicate relation has an invalid target"
            )
        if relation.classification not in {"exact", "near_duplicate"}:
            raise EvidenceValidationError(
                f"Entry {entry_id} duplicate relation has an invalid classification"
            )
        if (
            not math.isfinite(relation.similarity)
            or not 0.0 <= relation.similarity <= 1.0
        ):
            raise EvidenceValidationError(
                f"Entry {entry_id} duplicate relation has an invalid similarity"
            )
        if relation.algorithm_version != SOURCE_INDEPENDENCE_VERSION:
            raise EvidenceValidationError(
                f"Entry {entry_id} duplicate relation has an unsupported algorithm"
            )
        if not relation.rule or not relation.reason:
            raise EvidenceValidationError(
                f"Entry {entry_id} duplicate relation lacks audit rationale"
            )
        previous = relations.get(relation.related_entry_id)
        if previous is not None and previous != relation:
            raise EvidenceValidationError(
                f"Entry {entry_id} has conflicting duplicate relations"
            )
        relations[relation.related_entry_id] = relation
    if relations and not detection_version:
        detection_version = SOURCE_INDEPENDENCE_VERSION
    return (
        detection_version,
        tuple(sorted(relations.values())),
        independent_provenance_identity(entry),
    )


def _entry_body(entry: Mapping[str, object]) -> str | None:
    for field_name in ("raw_text", "text", "content", "body"):
        value = entry.get(field_name)
        if isinstance(value, str):
            return value
    return None


def _verified_locator(
    entry: Mapping[str, object],
    raw_locator: Mapping[str, object] | None,
) -> EvidenceLocator:
    if raw_locator is None:
        return EvidenceLocator()
    if not isinstance(raw_locator, Mapping):
        raise EvidenceValidationError("Evidence locator must be an object")
    kind = str(raw_locator.get("kind", "whole_entry")).strip()
    if kind == "whole_entry":
        if set(raw_locator) - {"kind"}:
            raise EvidenceValidationError("whole_entry locator does not accept span fields")
        return EvidenceLocator()
    if kind not in {"quote", "char_span"}:
        raise EvidenceValidationError(f"Unsupported evidence locator kind: {kind!r}")
    body = _entry_body(entry)
    if body is None:
        raise EvidenceValidationError("Quote/span locator requires the allowlisted Entry body")

    if kind == "quote":
        if set(raw_locator) - {"kind", "quote"}:
            raise EvidenceValidationError("quote locator accepts only kind and quote")
        quote = str(raw_locator.get("quote", ""))
        if not quote:
            raise EvidenceValidationError("quote locator requires non-empty quote")
        starts: list[int] = []
        cursor = 0
        while True:
            found = body.find(quote, cursor)
            if found < 0:
                break
            starts.append(found)
            cursor = found + 1
            if len(starts) > 1:
                raise EvidenceValidationError("Evidence quote is ambiguous in the Entry body")
        if not starts:
            raise EvidenceValidationError("Evidence quote was not found in the Entry body")
        start = starts[0]
        return EvidenceLocator(kind="quote", start=start, end=start + len(quote), quote=quote)

    if set(raw_locator) - {"kind", "start", "end", "quote"}:
        raise EvidenceValidationError("char_span locator contains unsupported fields")
    start = raw_locator.get("start")
    end = raw_locator.get("end")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end <= start
        or end > len(body)
    ):
        raise EvidenceValidationError("char_span locator has invalid bounds")
    quote = body[start:end]
    supplied_quote = raw_locator.get("quote")
    if supplied_quote is not None and str(supplied_quote) != quote:
        raise EvidenceValidationError("char_span quote does not match the Entry body")
    return EvidenceLocator(kind="char_span", start=start, end=end, quote=quote)


def allowlisted_evidence(
    entries: Sequence[Mapping[str, object]] | Mapping[str, Mapping[str, object]],
    requested_source_ids: Sequence[object],
    evidence_locators: Mapping[str, Mapping[str, object]] | None = None,
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

    raw_locators = dict(evidence_locators or {})
    extra_locators = set(raw_locators) - set(source_ids)
    if extra_locators:
        raise EvidenceValidationError(
            "Evidence locators reference unrequested source IDs: "
            + ", ".join(sorted(extra_locators))
        )

    refs: list[EvidenceRef] = []
    for source_id in source_ids:
        authority_topics, authority_fact_keys, corrects_entry_ids = _authority_fields(
            allowed[source_id]
        )
        duplicate_version, duplicate_relations, independence_identity = (
            _duplicate_relation_fields(allowed[source_id], source_id)
        )
        refs.append(
            EvidenceRef(
            entry_id=source_id,
            source_tier=_source_tier(allowed[source_id]),
            source_key=_source_key(allowed[source_id]),
            content_hash=_content_hash(allowed[source_id]),
            evidence_digest=_evidence_digest(allowed[source_id]),
            locator=_verified_locator(allowed[source_id], raw_locators.get(source_id)),
            is_primary=_is_primary(allowed[source_id]),
            authority_topics=authority_topics,
            authority_fact_keys=authority_fact_keys,
            corrects_entry_ids=corrects_entry_ids,
            duplicate_detection_version=duplicate_version,
            duplicate_relations=duplicate_relations,
            independence_identity=independence_identity,
        )
        )
    return tuple(refs)


def compute_evidence_strength(
    refs: Sequence[EvidenceRef],
    *,
    conflict: bool = False,
    algorithm_version: str = ALGORITHM_VERSION,
) -> EvidenceStrength:
    """Compute an explainable ordinal evidence-strength score.

    Duplicate entry IDs are removed.  Corroboration is counted by independent
    source groups.  All versions collapse a shared ``source_key``.  Version 2
    additionally collapses a shared, versioned full SHA-256 ``evidence_digest``.
    Version 3 also consumes immutable persisted exact/near-duplicate relations,
    while distinct explicit observation provenance prevents automatic collapse.
    Legacy short ``content_hash`` values are audit metadata only.  Each group
    contributes only its best tier.  Formula::

        score = 0.65 * mean(source tier weights)
                + min(0.20, 0.10 * (independent sources - 1))
                - (0.20 if conflict else 0)

    The score is useful for ordering and guardrails only.  It is not trained or
    empirically calibrated and must not be described as a probability.
    """
    if algorithm_version not in {
        LEGACY_ALGORITHM_VERSION,
        DIGEST_ALGORITHM_VERSION,
        ALGORITHM_VERSION,
    }:
        raise TransitionValidationError(
            f"Unsupported evidence-strength algorithm: {algorithm_version!r}"
        )
    unique_refs = {ref.entry_id: ref for ref in refs}
    if algorithm_version == ALGORITHM_VERSION:
        return _compute_v3_evidence_strength(
            unique_refs,
            conflict=conflict,
            algorithm_version=algorithm_version,
        )
    source_parents: dict[str, str] = {}

    def find_source(source_key: str) -> str:
        source_parents.setdefault(source_key, source_key)
        root = source_key
        while source_parents[root] != root:
            root = source_parents[root]
        while source_parents[source_key] != source_key:
            parent = source_parents[source_key]
            source_parents[source_key] = root
            source_key = parent
        return root

    def union_sources(left: str, right: str) -> None:
        left_root = find_source(left)
        right_root = find_source(right)
        if left_root != right_root:
            source_parents[right_root] = left_root

    first_source_by_digest: dict[str, str] = {}
    for ref in unique_refs.values():
        find_source(ref.source_key)
        if algorithm_version == LEGACY_ALGORITHM_VERSION:
            continue
        evidence_digest = ref.evidence_digest.strip()
        if not _SHA256_EVIDENCE_DIGEST.fullmatch(evidence_digest):
            continue
        first_source = first_source_by_digest.setdefault(evidence_digest, ref.source_key)
        union_sources(ref.source_key, first_source)

    best_by_source_group: dict[str, float] = {}
    tier_counts = {tier: 0 for tier in ("A", "B", "C", "D", "U")}
    for ref in unique_refs.values():
        tier = ref.source_tier if ref.source_tier in VALID_TIERS else "U"
        tier_counts[tier] += 1
        weight = TIER_WEIGHTS[tier]
        source_group = find_source(ref.source_key)
        best_by_source_group[source_group] = max(
            best_by_source_group.get(source_group, 0.0),
            weight,
        )

    source_count = len(best_by_source_group)
    mean_weight = (
        sum(best_by_source_group.values()) / source_count if source_count else 0.0
    )
    tier_component = 0.65 * mean_weight
    corroboration = min(0.20, 0.10 * max(0, source_count - 1))
    penalty = 0.20 if conflict else 0.0
    score = round(max(0.0, min(0.95, tier_component + corroboration - penalty)), 4)
    band = "strong" if score >= 0.65 else "moderate" if score >= 0.35 else "weak"
    counts_tuple = tuple((tier, count) for tier, count in tier_counts.items() if count)
    independence_rule = (
        "source-key deduplication"
        if algorithm_version == LEGACY_ALGORITHM_VERSION
        else "source-key and trusted SHA-256 evidence-digest deduplication"
    )
    rationale = (
        f"{source_count} independent source(s) after {independence_rule}",
        f"tier component={tier_component:.4f} from source_tier weights",
        f"corroboration bonus={corroboration:.4f}",
        f"structured-conflict penalty={penalty:.4f}",
        "ordinal rule score; not a calibrated probability",
    )
    return EvidenceStrength(
        score=score,
        band=band,
        algorithm=algorithm_version,
        independent_source_count=source_count,
        source_group_count=source_count,
        tier_counts=counts_tuple,
        conflict_penalty=penalty,
        rationale=rationale,
    )


def _compute_v3_evidence_strength(
    unique_refs: Mapping[str, EvidenceRef],
    *,
    conflict: bool,
    algorithm_version: str,
) -> EvidenceStrength:
    """Compute conservative v3 source groups without assumed independence."""
    parents = {entry_id: entry_id for entry_id in unique_refs}
    members = {entry_id: {entry_id} for entry_id in unique_refs}

    def find(entry_id: str) -> str:
        root = entry_id
        while parents[root] != root:
            root = parents[root]
        while parents[entry_id] != entry_id:
            parent = parents[entry_id]
            parents[entry_id] = root
            entry_id = parent
        return root

    def union(left_id: str, right_id: str) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root == right_root:
            return
        root, child = sorted((left_root, right_root))
        parents[child] = root
        members[root].update(members.pop(child))

    refs = [unique_refs[entry_id] for entry_id in sorted(unique_refs)]
    for left, right in combinations(refs, 2):
        if left.source_key == right.source_key:
            union(left.entry_id, right.entry_id)
        if (
            _SHA256_EVIDENCE_DIGEST.fullmatch(left.evidence_digest.strip())
            and left.evidence_digest == right.evidence_digest
        ):
            union(left.entry_id, right.entry_id)
    for ref in refs:
        for relation in ref.duplicate_relations:
            if relation.related_entry_id in unique_refs and relation.classification in {
                "exact",
                "near_duplicate",
            }:
                union(ref.entry_id, relation.related_entry_id)

    best_by_group: dict[str, float] = {}
    tier_counts = {tier: 0 for tier in ("A", "B", "C", "D", "U")}
    for ref in refs:
        tier = ref.source_tier if ref.source_tier in VALID_TIERS else "U"
        tier_counts[tier] += 1
        root = find(ref.entry_id)
        best_by_group[root] = max(best_by_group.get(root, 0.0), TIER_WEIGHTS[tier])

    source_group_count = len(best_by_group)
    # A non-duplicate document is not automatically an independent observation.
    # Until a trusted provenance registry can attest independent experiments,
    # v3 deliberately awards no corroboration credit to extra singleton groups.
    source_count = 1 if source_group_count else 0
    best_weight = max(best_by_group.values(), default=0.0)
    tier_component = 0.65 * best_weight
    corroboration = 0.0
    penalty = 0.20 if conflict else 0.0
    score = round(max(0.0, min(0.95, tier_component + corroboration - penalty)), 4)
    band = "strong" if score >= 0.65 else "moderate" if score >= 0.35 else "weak"
    counts_tuple = tuple((tier, count) for tier, count in tier_counts.items() if count)
    rationale = (
        f"{source_group_count} non-duplicate source group(s) after source-key, "
        "trusted SHA-256 digest, "
        "and persisted exact/near-duplicate relations",
        "self-declared provenance never overrides source or content deduplication",
        "undetermined groups receive no independence count or corroboration bonus",
        "trusted provenance registry is required before independent corroboration",
        f"tier component={tier_component:.4f} from source_tier weights",
        f"corroboration bonus={corroboration:.4f}",
        f"structured-conflict penalty={penalty:.4f}",
        "ordinal rule score; not a calibrated probability",
    )
    return EvidenceStrength(
        score=score,
        band=band,
        algorithm=algorithm_version,
        independent_source_count=source_count,
        source_group_count=source_group_count,
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
    algorithm_version: str = ALGORITHM_VERSION,
    governance_version: str = GOVERNANCE_VERSION,
    topic: str = "",
    fact_key: str = "",
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
        candidate = compute_evidence_strength(refs, algorithm_version=algorithm_version)
        parent_scores = [
            compute_evidence_strength(
                parent.evidence_refs,
                algorithm_version=algorithm_version,
            ).score
            for parent in parents
        ]
        parent_scores.extend(
            compute_evidence_strength(
                parent.proposal.evidence_refs,
                algorithm_version=algorithm_version,
            ).score
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
        required_metadata = {
            "authoritative_fact_value",
            "authority_source_id",
            "corrects_entry_id",
        }
        if governance_version != LEGACY_GOVERNANCE_VERSION:
            required_metadata.add("correction_relation")
        values = _require_metadata(metadata, required_metadata, basis)
        authority = next(
            (ref for ref in refs if ref.entry_id == values["authority_source_id"]),
            None,
        )
        if authority is None or not authority.is_primary:
            raise ConflictResolutionRequired(
                "official_correction authority_source_id must reference a new allowlisted "
                "entry whose source.is_primary is true"
            )
        if governance_version != LEGACY_GOVERNANCE_VERSION:
            if values["correction_relation"] != "corrects":
                raise ConflictResolutionRequired(
                    "official_correction correction relation must be 'corrects'"
                )
            if not authority.authority_topics or not authority.authority_fact_keys:
                raise ConflictResolutionRequired(
                    "official_correction requires explicit authority scope"
                )
            if _normalise_text(topic) not in authority.authority_topics:
                raise ConflictResolutionRequired(
                    "official_correction authority scope does not cover the topic"
                )
            if _normalise_text(fact_key) not in authority.authority_fact_keys:
                raise ConflictResolutionRequired(
                    "official_correction authority scope does not cover fact_key"
                )
            if values["corrects_entry_id"] not in authority.corrects_entry_ids:
                raise ConflictResolutionRequired(
                    "official_correction correction relation does not cover corrected entry"
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
    """Union references by Entry ID, enriching unknown hashes without mutation."""
    merged: dict[tuple[str, str], EvidenceRef] = {}
    for group in groups:
        for ref in group:
            key = (ref.entry_id, locator_identity(ref.locator))
            previous = merged.get(key)
            if previous is None:
                merged[key] = ref
                continue
            merged[key] = EvidenceRef(
                entry_id=previous.entry_id,
                source_tier=previous.source_tier,
                source_key=previous.source_key,
                content_hash=previous.content_hash or ref.content_hash,
                evidence_digest=previous.evidence_digest or ref.evidence_digest,
                locator=previous.locator,
                is_primary=previous.is_primary,
                authority_topics=previous.authority_topics or ref.authority_topics,
                authority_fact_keys=(
                    previous.authority_fact_keys or ref.authority_fact_keys
                ),
                corrects_entry_ids=previous.corrects_entry_ids or ref.corrects_entry_ids,
                duplicate_detection_version=(
                    previous.duplicate_detection_version
                    or ref.duplicate_detection_version
                ),
                duplicate_relations=(
                    previous.duplicate_relations or ref.duplicate_relations
                ),
                independence_identity=(
                    previous.independence_identity or ref.independence_identity
                ),
            )
    return tuple(merged.values())
