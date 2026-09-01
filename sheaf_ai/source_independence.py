"""Deterministic near-duplicate decisions for evidence-source independence.

This module deliberately makes a conservative lexical decision.  It can prove
that two captured bodies are exact or near-duplicate copies, and it can honor
structured provenance that identifies separate observations.  Ambiguous and
short pairs remain ``undetermined`` rather than receiving invented semantic
confidence.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from itertools import combinations
from typing import Literal, Mapping, Sequence
from urllib.parse import urlsplit


SourceIndependenceLabel = Literal[
    "exact",
    "near_duplicate",
    "independent",
    "undetermined",
]

SOURCE_INDEPENDENCE_VERSION = "source-independence-v1"
DEFAULT_NEAR_DUPLICATE_THRESHOLD = 0.82
DEFAULT_INDEPENDENT_THRESHOLD = 0.35
DEFAULT_MIN_CONTENT_CHARS = 80
MAX_COMPARISON_CHARS = 50_000

_HTML_TAG = re.compile(r"</?[A-Za-z][^>]{0,200}>")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9]+|[\u3400-\u4dbf\u4e00-\u9fff]")
_TEXT_FIELDS = ("raw_text", "text", "content", "body", "evidence_text")
_PROVENANCE_ID_FIELDS = (
    "observation_id",
    "experiment_id",
    "measurement_id",
    "run_id",
    "sample_id",
)
_TRUE_MARKERS = frozenset({"1", "true", "yes", "independent", "separate"})


@dataclass(frozen=True)
class SourceIndependenceDecision:
    """Explain one pairwise source-independence decision."""

    left_id: str
    right_id: str
    classification: SourceIndependenceLabel
    similarity: float
    rule: str
    reason: str

    @property
    def should_collapse(self) -> bool:
        """Whether the pair is safe to count as one evidence source."""
        return self.classification in {"exact", "near_duplicate"}

    def to_dict(self) -> dict[str, object]:
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "classification": self.classification,
            "similarity": self.similarity,
            "rule": self.rule,
            "reason": self.reason,
            "should_collapse": self.should_collapse,
        }


@dataclass(frozen=True)
class SourceGroup:
    """One connected component of proven duplicate source bodies."""

    group_id: str
    members: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"group_id": self.group_id, "members": list(self.members)}


@dataclass(frozen=True)
class SourceIndependenceGraph:
    """Stable groups plus every auditable pairwise decision edge.

    Only ``exact`` and ``near_duplicate`` edges join a group.  Independent and
    undetermined pairs remain separate; consumers can inspect ``edges`` before
    deciding whether undetermined singletons may add corroboration credit.
    """

    groups: tuple[SourceGroup, ...]
    edges: tuple[SourceIndependenceDecision, ...]

    def group_for(self, source_id: str) -> str:
        requested = str(source_id).strip()
        for group in self.groups:
            if requested in group.members:
                return group.group_id
        raise KeyError(requested)

    @property
    def collapse_edges(self) -> tuple[SourceIndependenceDecision, ...]:
        return tuple(edge for edge in self.edges if edge.should_collapse)

    @property
    def undetermined_edges(self) -> tuple[SourceIndependenceDecision, ...]:
        return tuple(
            edge for edge in self.edges if edge.classification == "undetermined"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "groups": [group.to_dict() for group in self.groups],
            "edges": [edge.to_dict() for edge in self.edges],
        }


@dataclass(frozen=True)
class _PreparedSource:
    source_id: str
    text: str
    domain: str
    provenance_identity: str
    fingerprint: str


def normalize_source_text(text: object) -> str:
    """Normalize Chinese and English text without language-specific models."""
    value = html.unescape(str(text or ""))
    value = unicodedata.normalize("NFKC", value).casefold()
    value = _HTML_TAG.sub(" ", value)
    value = _URL.sub(" ", value)
    normalized: list[str] = []
    previous_space = True
    for character in value:
        category = unicodedata.category(character)
        keep = category[0] in {"L", "N"}
        if keep:
            normalized.append(character)
            previous_space = False
        elif not previous_space:
            normalized.append(" ")
            previous_space = True
    return "".join(normalized).strip()


def content_similarity(left_text: object, right_text: object) -> float:
    """Return a deterministic lexical containment score in ``[0, 1]``.

    Character shingles preserve local wording for both unsegmented Chinese and
    English.  Token containment adds tolerance for small edits and reordered
    clauses.  Using the smaller feature set as denominator makes boilerplate
    prefixes and suffixes cheap, which is useful for detecting repost wrappers.
    """
    left = normalize_source_text(left_text)
    right = normalize_source_text(right_text)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    left = _comparison_view(left)
    right = _comparison_view(right)
    left_compact = left.replace(" ", "")
    right_compact = right.replace(" ", "")
    five_gram = _overlap_coefficient(
        _shingles(left_compact, 5),
        _shingles(right_compact, 5),
    )
    nine_gram = _overlap_coefficient(
        _shingles(left_compact, 9),
        _shingles(right_compact, 9),
    )
    token_overlap = _overlap_coefficient(
        set(_TOKEN.findall(left)),
        set(_TOKEN.findall(right)),
    )
    similarity = 0.50 * five_gram + 0.30 * nine_gram + 0.20 * token_overlap
    return round(max(0.0, min(1.0, similarity)), 6)


def assess_source_pair(
    left: Mapping[str, object],
    right: Mapping[str, object],
    *,
    near_duplicate_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
    independent_threshold: float = DEFAULT_INDEPENDENT_THRESHOLD,
    min_content_chars: int = DEFAULT_MIN_CONTENT_CHARS,
) -> SourceIndependenceDecision:
    """Classify whether two captured sources should share an evidence group."""
    near_threshold, low_threshold, minimum = _validate_parameters(
        near_duplicate_threshold,
        independent_threshold,
        min_content_chars,
    )
    prepared_left = _prepare_source(left)
    prepared_right = _prepare_source(right)
    if prepared_left.source_id == prepared_right.source_id:
        raise ValueError("Source pair must contain two different source ids")
    if prepared_right.source_id < prepared_left.source_id:
        prepared_left, prepared_right = prepared_right, prepared_left

    similarity = content_similarity(prepared_left.text, prepared_right.text)
    normalized_left = normalize_source_text(prepared_left.text)
    normalized_right = normalize_source_text(prepared_right.text)
    if not normalized_left or not normalized_right:
        return _decision(
            prepared_left,
            prepared_right,
            "undetermined",
            similarity,
            "missing_text",
            "At least one source has no comparable text.",
        )
    if normalized_left == normalized_right:
        return _decision(
            prepared_left,
            prepared_right,
            "exact",
            1.0,
            "normalized_exact_match",
            "The complete normalized source bodies are identical.",
        )

    if not _has_substantial_text(normalized_left, minimum) or not _has_substantial_text(
        normalized_right,
        minimum,
    ):
        return _decision(
            prepared_left,
            prepared_right,
            "undetermined",
            similarity,
            "insufficient_text",
            "At least one source is too short for a safe near-duplicate decision.",
        )
    if similarity >= near_threshold:
        return _decision(
            prepared_left,
            prepared_right,
            "near_duplicate",
            similarity,
            "high_content_containment",
            f"Normalized lexical containment {similarity:.6f} meets the "
            f"near-duplicate threshold {near_threshold:.6f}.",
        )
    if (
        prepared_left.provenance_identity
        and prepared_right.provenance_identity
        and prepared_left.provenance_identity != prepared_right.provenance_identity
    ):
        return _decision(
            prepared_left,
            prepared_right,
            "independent",
            similarity,
            "explicit_independent_provenance",
            "Distinct structured observation provenance supports separate "
            "experiments after exact and near-duplicate checks passed.",
        )
    if (
        similarity <= low_threshold
        and prepared_left.domain
        and prepared_right.domain
        and prepared_left.domain != prepared_right.domain
    ):
        return _decision(
            prepared_left,
            prepared_right,
            "undetermined",
            similarity,
            "low_similarity_without_provenance",
            f"Substantial bodies from distinct domains have low lexical containment "
            f"{similarity:.6f}, but this disproves copying only weakly and does not "
            "prove independent observation provenance.",
        )
    return _decision(
        prepared_left,
        prepared_right,
        "undetermined",
        similarity,
        "ambiguous_similarity",
        f"Lexical containment {similarity:.6f} proves neither duplication nor "
        "independence under the configured rules.",
    )


def build_source_groups(
    sources: Sequence[Mapping[str, object]],
    *,
    near_duplicate_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
    independent_threshold: float = DEFAULT_INDEPENDENT_THRESHOLD,
    min_content_chars: int = DEFAULT_MIN_CONTENT_CHARS,
) -> SourceIndependenceGraph:
    """Build stable duplicate groups and a complete pairwise decision graph."""
    _validate_parameters(
        near_duplicate_threshold,
        independent_threshold,
        min_content_chars,
    )
    prepared_by_id: dict[str, _PreparedSource] = {}
    raw_by_id: dict[str, Mapping[str, object]] = {}
    for source in sources:
        prepared = _prepare_source(source)
        previous = prepared_by_id.get(prepared.source_id)
        if previous is not None and previous.fingerprint != prepared.fingerprint:
            raise ValueError(f"Conflicting duplicate source id: {prepared.source_id}")
        prepared_by_id[prepared.source_id] = prepared
        raw_by_id[prepared.source_id] = source

    source_ids = sorted(prepared_by_id)
    parents = {source_id: source_id for source_id in source_ids}

    def find(source_id: str) -> str:
        root = source_id
        while parents[root] != root:
            root = parents[root]
        while parents[source_id] != source_id:
            parent = parents[source_id]
            parents[source_id] = root
            source_id = parent
        return root

    def union(left_id: str, right_id: str) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root == right_root:
            return
        root, child = sorted((left_root, right_root))
        parents[child] = root

    edges: list[SourceIndependenceDecision] = []
    for left_id, right_id in combinations(source_ids, 2):
        edge = assess_source_pair(
            raw_by_id[left_id],
            raw_by_id[right_id],
            near_duplicate_threshold=near_duplicate_threshold,
            independent_threshold=independent_threshold,
            min_content_chars=min_content_chars,
        )
        edges.append(edge)
        if edge.should_collapse:
            union(edge.left_id, edge.right_id)

    members_by_root: dict[str, list[str]] = {}
    for source_id in source_ids:
        members_by_root.setdefault(find(source_id), []).append(source_id)
    member_sets = sorted(tuple(sorted(members)) for members in members_by_root.values())
    groups = tuple(
        SourceGroup(group_id=_group_id(members), members=members)
        for members in member_sets
    )
    return SourceIndependenceGraph(groups=groups, edges=tuple(edges))


def _prepare_source(source: Mapping[str, object]) -> _PreparedSource:
    if not isinstance(source, Mapping):
        raise TypeError("Source must be a mapping")
    source_id = str(
        source.get("id") or source.get("entry_id") or source.get("source_id") or ""
    ).strip()
    if not source_id:
        raise ValueError("Source is missing id")
    text = _source_text(source)
    domain = _source_domain(source)
    provenance_identity = independent_provenance_identity(source)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "id": source_id,
                "text": normalize_source_text(text),
                "domain": domain,
                "provenance_identity": provenance_identity,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return _PreparedSource(
        source_id=source_id,
        text=text,
        domain=domain,
        provenance_identity=provenance_identity,
        fingerprint=fingerprint,
    )


def _source_text(source: Mapping[str, object]) -> str:
    for field in _TEXT_FIELDS:
        value = source.get(field)
        if isinstance(value, str) and value.strip():
            return value
    fetch_result = source.get("fetch_result")
    if isinstance(fetch_result, Mapping):
        value = fetch_result.get("text")
        if isinstance(value, str) and value.strip():
            return value
    summary = source.get("summary")
    return str(summary) if isinstance(summary, str) else ""


def _source_domain(source: Mapping[str, object]) -> str:
    source_metadata = source.get("source")
    if isinstance(source_metadata, Mapping):
        domain = str(source_metadata.get("domain", "")).strip().casefold()
        if domain:
            return domain.removeprefix("www.")
    url = str(source.get("url", "")).strip()
    try:
        hostname = urlsplit(url).hostname or ""
    except ValueError:
        hostname = ""
    return hostname.casefold().removeprefix("www.")


def independent_provenance_identity(source: Mapping[str, object]) -> str:
    """Return a stable identity only for explicitly supplied provenance."""
    candidates: list[Mapping[str, object]] = [source]
    for field in ("source", "provenance", "metadata"):
        value = source.get(field)
        if isinstance(value, Mapping):
            candidates.append(value)
            nested = value.get("provenance")
            if isinstance(nested, Mapping):
                candidates.append(nested)

    asserted = False
    identity: dict[str, object] = {}
    for candidate in candidates:
        marker = candidate.get("independent_observation")
        if marker is True or str(marker).strip().casefold() in _TRUE_MARKERS:
            asserted = True
        for field in _PROVENANCE_ID_FIELDS:
            value = str(candidate.get(field, "")).strip()
            if value:
                identity[field] = value.casefold()
        method = candidate.get("method_provenance")
        if isinstance(method, Mapping) and method:
            identity["method_provenance"] = _json_safe(method)
        elif isinstance(method, str) and method.strip():
            identity["method_provenance"] = method.strip().casefold()
    if not asserted or not identity:
        return ""
    identity["independent_observation"] = asserted
    return hashlib.sha256(
        json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _json_safe(value: Mapping[str, object]) -> object:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError):
        return str(value)


def _has_substantial_text(normalized: str, minimum: int) -> bool:
    compact = normalized.replace(" ", "")
    if len(compact) < minimum:
        return False
    tokens = set(_TOKEN.findall(normalized))
    contains_cjk = any("\u3400" <= character <= "\u9fff" for character in compact)
    return contains_cjk or len(tokens) >= 12


def _comparison_view(normalized: str) -> str:
    """Bound feature cost while sampling the beginning, middle, and end."""
    if len(normalized) <= MAX_COMPARISON_CHARS:
        return normalized
    third = MAX_COMPARISON_CHARS // 3
    middle = len(normalized) // 2
    return " ".join((
        normalized[:third],
        normalized[middle - third // 2:middle + third // 2],
        normalized[-third:],
    ))


def _shingles(text: str, width: int) -> set[str]:
    if not text:
        return set()
    if len(text) <= width:
        return {text}
    return {text[index:index + width] for index in range(len(text) - width + 1)}


def _overlap_coefficient(left: set[str], right: set[str]) -> float:
    denominator = min(len(left), len(right))
    if denominator == 0:
        return 0.0
    return len(left & right) / denominator


def _validate_parameters(
    near_duplicate_threshold: float,
    independent_threshold: float,
    min_content_chars: int,
) -> tuple[float, float, int]:
    for name, value in (
        ("near_duplicate_threshold", near_duplicate_threshold),
        ("independent_threshold", independent_threshold),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a finite number in [0, 1]")
        if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"{name} must be a finite number in [0, 1]")
    near = float(near_duplicate_threshold)
    low = float(independent_threshold)
    if low >= near:
        raise ValueError("independent_threshold must be below near_duplicate_threshold")
    if isinstance(min_content_chars, bool) or not isinstance(min_content_chars, int):
        raise ValueError("min_content_chars must be a positive integer")
    if min_content_chars <= 0:
        raise ValueError("min_content_chars must be a positive integer")
    return near, low, min_content_chars


def _decision(
    left: _PreparedSource,
    right: _PreparedSource,
    classification: SourceIndependenceLabel,
    similarity: float,
    rule: str,
    reason: str,
) -> SourceIndependenceDecision:
    return SourceIndependenceDecision(
        left_id=left.source_id,
        right_id=right.source_id,
        classification=classification,
        similarity=similarity,
        rule=rule,
        reason=reason,
    )


def _group_id(members: tuple[str, ...]) -> str:
    digest = hashlib.sha256("\x1f".join(members).encode("utf-8")).hexdigest()[:16]
    return f"source-group:{digest}"


__all__ = [
    "DEFAULT_INDEPENDENT_THRESHOLD",
    "DEFAULT_MIN_CONTENT_CHARS",
    "DEFAULT_NEAR_DUPLICATE_THRESHOLD",
    "SOURCE_INDEPENDENCE_VERSION",
    "SourceGroup",
    "SourceIndependenceDecision",
    "SourceIndependenceGraph",
    "SourceIndependenceLabel",
    "assess_source_pair",
    "build_source_groups",
    "content_similarity",
    "independent_provenance_identity",
    "normalize_source_text",
]
