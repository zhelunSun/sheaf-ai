"""Small shared projection so interfaces do not drop retrieval uncertainty."""
from __future__ import annotations


def public_retrieval_gate(diagnostics: dict) -> dict:
    if not diagnostics.get("retrieval_gate_version"):
        return {}
    return {
        "version": diagnostics["retrieval_gate_version"],
        "policy": diagnostics.get("retrieval_gate_policy", "strict"),
        "status": diagnostics.get("retrieval_gate_status", "withheld"),
        "reason_code": diagnostics.get("retrieval_gate_reason_code", "unknown"),
        "reason": diagnostics.get("retrieval_gate_reason", ""),
        "review_available": bool(diagnostics.get("retrieval_review_available", False)),
        "answerability": "not_assessed",
    }
