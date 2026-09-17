"""Structured evidence calibration for knowledge cards.

Replaces the LLM self-reported confidence (which the literature shows to be
systematically unreliable) with a reproducible, explainable evidence score
computed from structured features of the card's supporting sources.

Sprint 1 (rule-based): source_count + source tier + conflict penalty.
Sprint 3 (planned): fit on small human labels via isotonic regression, report
ECE / reliability diagram.
"""
from __future__ import annotations

from sheaf_cards.base import KnowledgeCard


# Tier → strength bonus. A = high-quality source, B = default, C = low.
_TIER_BONUS = {"A": 0.30, "B": 0.15, "C": 0.0}

_CONFLICT_PENALTY = 0.30
_BASE = 0.10
_SOURCE_CAP = 3  # source_count saturates at 3 for the strength score


def compute_evidence_strength(
    source_count: int,
    tier: str = "B",
    conflict: bool = False,
) -> float:
    """Compute a reproducible evidence-strength score in [0.05, 0.95].

    The score is a function of structured evidence features only, so it can be
    recomputed at any time (e.g. after a state transition changes the evidence
    base) and explained to a user.

    Args:
        source_count: number of independent sources backing the claim.
        tier: highest quality tier among the sources ("A", "B", or "C").
        conflict: whether the claim is in semantic conflict with other cards.

    Returns:
        Evidence strength in [0.05, 0.95].
    """
    tier = (tier or "B").upper()
    score = _BASE
    score += min(source_count / _SOURCE_CAP, 1.0) * 0.5
    score += _TIER_BONUS.get(tier, _TIER_BONUS["B"])
    if conflict:
        score -= _CONFLICT_PENALTY
    return max(0.05, min(0.95, score))


def top_tier_for(source_tiers: list[str]) -> str:
    """Return the highest tier in a list, defaulting to "B"."""
    tiers = {(t or "B").upper() for t in source_tiers}
    for t in ("A", "B", "C"):
        if t in tiers:
            return t
    return "B"


def calibrate_card(
    card: KnowledgeCard,
    entries_by_id: dict | None = None,
    conflict: bool = False,
) -> KnowledgeCard:
    """Recompute a card's evidence_strength and derived confidence in place.

    ``entries_by_id`` maps entry_id -> entry dict; the entry's ``quality_tier``
    is used as the source tier. Falls back to "B" for unknown entries.

    The calibrated confidence is set equal to evidence_strength, so that the
    card's reported confidence is always traceable to a reproducible evidence
    score rather than a black-box LLM scalar.
    """
    entries_by_id = entries_by_id or {}
    tiers = [
        entries_by_id.get(sid, {}).get("quality_tier", "B")
        for sid in card.source_ids
    ]
    card.evidence_strength = compute_evidence_strength(
        source_count=len(card.source_ids),
        tier=top_tier_for(tiers),
        conflict=conflict,
    )
    card.confidence = card.evidence_strength
    return card
