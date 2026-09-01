"""Deterministic long-document passage selection for crystallization prompts."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Mapping


PASSAGE_SELECTION_VERSION = "passage-selection-v1"
DEFAULT_PROMPT_BUDGET = 1_900
DEFAULT_CHUNK_CHARS = 620
DEFAULT_CHUNK_OVERLAP = 80
DEFAULT_MAX_PASSAGES = 3

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[\u3400-\u4dbf\u4e00-\u9fff]")
_BOUNDARY_RE = re.compile(r"[\n。！？.!?;；]")
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to",
    "was", "were", "what", "when", "where", "which", "with",
})


@dataclass(frozen=True)
class Passage:
    start: int
    end: int
    text: str
    score: float
    matched_terms: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "start": self.start,
            "end": self.end,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
        }


@dataclass(frozen=True)
class PassageSelection:
    text: str
    passages: tuple[Passage, ...]
    manifest: Mapping[str, object]


def _tokens(value: object) -> list[str]:
    return [
        token
        for token in _TOKEN_RE.findall(str(value or "").casefold())
        if token not in _STOPWORDS
    ]


def _metadata_query(topic: str, entry: Mapping[str, object]) -> str:
    values = [topic, topic, topic, entry.get("title", ""), entry.get("summary", "")]
    for item in entry.get("topics", []):
        values.append(item.get("name", "") if isinstance(item, Mapping) else item)
    values.extend(entry.get("tags", []))
    return " ".join(str(value) for value in values if str(value).strip())


def _chunk_bounds(text: str, *, chunk_chars: int, overlap: int) -> list[tuple[int, int]]:
    bounds: list[tuple[int, int]] = []
    start = 0
    length = len(text)
    while start < length:
        hard_end = min(length, start + chunk_chars)
        end = hard_end
        if hard_end < length:
            search_start = start + max(chunk_chars // 2, 1)
            candidates = list(_BOUNDARY_RE.finditer(text, search_start, hard_end))
            if candidates:
                end = candidates[-1].end()
        if end <= start:
            end = hard_end
        bounds.append((start, end))
        if end >= length:
            break
        start = max(start + 1, end - overlap)
    return bounds


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return 0.0 if not union else len(left & right) / len(union)


def _selection_hash(payload: object) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _text_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def select_passages(
    text: str,
    *,
    topic: str,
    entry: Mapping[str, object] | None = None,
    prompt_budget: int = DEFAULT_PROMPT_BUDGET,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    max_passages: int = DEFAULT_MAX_PASSAGES,
) -> PassageSelection:
    """Select exact source spans relevant to a crystallization topic.

    The result never invents or rewrites source text.  When metadata supplies no
    useful lexical signal, it samples the beginning, middle and end instead of
    silently treating the first characters as the complete document.
    """
    body = str(text or "")
    if not body:
        manifest = {
            "algorithm_version": PASSAGE_SELECTION_VERSION,
            "strategy": "empty",
            "source_text_hash": _text_hash(body),
            "full_text_chars": 0,
            "selected_chars": 0,
            "truncated": False,
            "query_terms": [],
            "passages": [],
        }
        manifest["selection_hash"] = _selection_hash(manifest)
        return PassageSelection(
            text="",
            passages=(),
            manifest=manifest,
        )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in (prompt_budget, chunk_chars, max_passages)
    ):
        raise ValueError("passage budgets must be positive integers")
    if isinstance(overlap, bool) or not isinstance(overlap, int) or not 0 <= overlap < chunk_chars:
        raise ValueError("overlap must be an integer smaller than chunk_chars")

    if len(body) <= prompt_budget:
        passage = Passage(0, len(body), body, 1.0, ())
        manifest = {
            "algorithm_version": PASSAGE_SELECTION_VERSION,
            "strategy": "full_text",
            "source_text_hash": _text_hash(body),
            "full_text_chars": len(body),
            "selected_chars": len(body),
            "truncated": False,
            "query_terms": [],
            "passages": [passage.to_dict()],
        }
        manifest["selection_hash"] = _selection_hash(manifest)
        return PassageSelection(body, (passage,), manifest)

    source_entry = entry or {}
    query = _metadata_query(topic, source_entry)
    query_terms = tuple(dict.fromkeys(_tokens(query)))
    bounds = _chunk_bounds(body, chunk_chars=chunk_chars, overlap=overlap)
    chunk_tokens = [_tokens(body[start:end]) for start, end in bounds]
    document_frequency = {
        term: sum(term in set(tokens) for tokens in chunk_tokens)
        for term in query_terms
    }
    weights = {
        term: math.log((len(bounds) + 1) / (document_frequency[term] + 1)) + 1.0
        for term in query_terms
    }
    known_weight = sum(
        weight for term, weight in weights.items() if document_frequency[term] > 0
    )
    topic_phrase = " ".join(str(topic).casefold().split())

    candidates: list[Passage] = []
    token_sets: list[set[str]] = []
    for (start, end), tokens in zip(bounds, chunk_tokens):
        token_set = set(tokens)
        token_sets.append(token_set)
        matched = tuple(term for term in query_terms if term in token_set)
        coverage = (
            sum(weights[term] for term in matched) / known_weight
            if known_weight > 0.0 else 0.0
        )
        density = len(matched) / max(1, len(token_set))
        phrase_bonus = 0.15 if topic_phrase and topic_phrase in body[start:end].casefold() else 0.0
        score = round(coverage + min(0.2, density) + phrase_bonus, 6)
        candidates.append(Passage(start, end, body[start:end], score, matched))

    selected_indexes: list[int] = []
    strategy = "relevance_mmr"
    if not candidates or max(item.score for item in candidates) <= 0.0:
        strategy = "stratified_fallback"
        anchors = (0, len(candidates) // 2, len(candidates) - 1)
        selected_indexes = list(dict.fromkeys(anchors))[:max_passages]
    else:
        remaining = set(range(len(candidates)))
        while remaining and len(selected_indexes) < max_passages:
            def utility(index: int) -> tuple[float, float, int]:
                redundancy = max(
                    (_jaccard(token_sets[index], token_sets[prior]) for prior in selected_indexes),
                    default=0.0,
                )
                return (
                    candidates[index].score - 0.35 * redundancy,
                    candidates[index].score,
                    -candidates[index].start,
                )

            chosen = max(remaining, key=utility)
            selected_indexes.append(chosen)
            remaining.remove(chosen)

    # Keep exact spans in source order and enforce the same budget consumed by
    # the downstream prompt, including separators.
    selected: list[Passage] = []
    used = 0
    for index in sorted(selected_indexes, key=lambda item: candidates[item].start):
        candidate = candidates[index]
        separator = 2 if selected else 0
        available = prompt_budget - used - separator
        if available <= 0:
            break
        if len(candidate.text) > available:
            candidate = Passage(
                candidate.start,
                candidate.start + available,
                candidate.text[:available],
                candidate.score,
                candidate.matched_terms,
            )
        selected.append(candidate)
        used += separator + len(candidate.text)

    selected_text = "\n\n".join(item.text for item in selected)
    manifest: dict[str, object] = {
        "algorithm_version": PASSAGE_SELECTION_VERSION,
        "strategy": strategy,
        "source_text_hash": _text_hash(body),
        "full_text_chars": len(body),
        "selected_chars": len(selected_text),
        "truncated": len(selected_text) < len(body),
        "query_terms": list(query_terms),
        "passages": [item.to_dict() for item in selected],
    }
    manifest["selection_hash"] = _selection_hash(manifest)
    return PassageSelection(selected_text, tuple(selected), manifest)


__all__ = [
    "DEFAULT_CHUNK_CHARS",
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_MAX_PASSAGES",
    "DEFAULT_PROMPT_BUDGET",
    "PASSAGE_SELECTION_VERSION",
    "Passage",
    "PassageSelection",
    "select_passages",
]
