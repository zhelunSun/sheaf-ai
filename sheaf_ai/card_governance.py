"""Read-only notices for projected version cards; never an authorization check."""
from __future__ import annotations

import math

from sheaf_cards.base import KnowledgeCard


_WARNINGS = {
    "active": "Current recorded version; source support and applicability still need checking.",
    "contested": "Unresolved disagreement: inspect both claims before using this conclusion.",
    "retired": "Retired conclusion: do not use as a current recommendation.",
    "superseded": "Historical version: inspect the current head before reuse.",
}


def memory_status(card: KnowledgeCard) -> dict | None:
    """Keep incomplete or inconsistent metadata visible, without guessing a state.

    Ordinary cards are not enrolled in the governed ledger by this projection.
    Even a valid-looking record is NOT proof of authority or a live ledger read.
    """
    provenance = card.provenance if isinstance(card.provenance, dict) else {}
    extra = card.extra if isinstance(card.extra, dict) else {}
    keys = ("memory_state", "memory_version_id", "memory_revision")
    if not any(key in provenance for key in keys) and "evidence_governance" not in extra:
        return None
    state = provenance.get("memory_state")
    version_id = provenance.get("memory_version_id")
    revision = provenance.get("memory_revision")
    recorded_state = provenance.get("memory_recorded_state")
    issues = []
    if recorded_state is not None and (not isinstance(recorded_state, str) or recorded_state not in _WARNINGS):
        issues.append("invalid_recorded_state")
    if not isinstance(state, str) or state not in _WARNINGS:
        issues.append("missing_or_unknown_state")
    if not isinstance(version_id, str) or not version_id.strip():
        issues.append("missing_version_id")
    if type(revision) is not int or revision < 1:
        issues.append("invalid_revision")
    if provenance.get("confidence_kind") != "ordinal_evidence_strength" or provenance.get("is_probability") is not False:
        issues.append("missing_or_conflicting_strength_semantics")
    governance = extra.get("evidence_governance")
    if "evidence_governance" in extra:
        if not isinstance(governance, dict):
            issues.append("invalid_governance_record")
        else:
            if governance.get("recorded_state") != recorded_state:
                issues.append("conflicting_recorded_state")
            for field, value in (("state", state), ("version_id", version_id), ("revision", revision)):
                if governance.get(field) != value or type(governance.get(field)) is not type(value):
                    issues.append(f"conflicting_{field}")
            strength = governance.get("strength")
            if not isinstance(strength, dict) or strength.get("is_probability") is not False:
                issues.append("invalid_strength_record")
            else:
                score = strength.get("score")
                if (type(score) not in (int, float) or not math.isfinite(score)
                        or not 0 <= score <= 1 or score != card.confidence):
                    issues.append("conflicting_strength_score")
    valid = not issues
    return {
        "state": state if valid else "unknown",
        "recorded_state": recorded_state if isinstance(recorded_state, str) else None,
        "version_id": version_id if isinstance(version_id, str) else None,
        "revision": revision if type(revision) is int else None,
        "metadata_valid": valid,
        "state_requires_review": not valid or state != "active",
        "evidence_strength": {"score": card.confidence if valid else None,
                              "kind": "ordinal_evidence_strength", "is_probability": False},
        "warning": _WARNINGS[state] if valid else "Incomplete or conflicting version metadata: inspect the ledger before reuse.",
        "verification": "recorded_metadata_only; ledger_not_revalidated; entailment_not_checked",
        "issues": issues,
    }


def memory_status_text(card: KnowledgeCard) -> str:
    status = memory_status(card)
    if status is None:
        return ""
    score = status["evidence_strength"]["score"]
    strength = f"{score:.2f}" if score is not None else "unknown"
    return (
        f"Memory state: {status['state']} | version: {status['version_id']} | revision: {status['revision']}\n"
        f"Evidence strength: {strength} (ordinal, not a probability)\n"
        f"{status['warning']} Ledger not revalidated by this view."
    )
