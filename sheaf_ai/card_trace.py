"""Source identity transport, not source authority or semantic verification."""
from __future__ import annotations

import re

from sheaf_cards.base import KnowledgeCard


SOURCE_MARKER = re.compile(r"\[\s*Source\s+(\d+)\s*\]", re.IGNORECASE)


def citation_trace(card: KnowledgeCard) -> dict:
    """Resolve only persisted bindings; old source-ID order is not an alias map."""
    indexes = sorted({int(m) for m in SOURCE_MARKER.findall(
        f"{card.claim}\n{card.evidence}"
    )})
    mapping = card.provenance.get("source_citations", {})
    mapping = mapping if isinstance(mapping, dict) else {}
    bindings = []
    unresolved = []
    for index in indexes:
        marker = f"[Source {index}]"
        entry_id = mapping.get(str(index))
        if isinstance(entry_id, str) and entry_id and entry_id in card.source_ids:
            bindings.append({"marker": marker, "entry_id": entry_id})
        else:
            unresolved.append(marker)
    return {
        "status": "unresolved" if unresolved else ("resolved" if indexes else "not_present"),
        "bindings": bindings,
        "unresolved_markers": unresolved,
        "verification": "source_identity_only; entailment_not_checked",
    }


def citation_trace_text(card: KnowledgeCard) -> str:
    trace = citation_trace(card)
    parts = [f"{item['marker']} -> {item['entry_id']}" for item in trace["bindings"]]
    if trace["unresolved_markers"]:
        parts.append("unresolved: " + ", ".join(trace["unresolved_markers"]))
    if not parts:
        return ""
    return "Citation mapping (not semantic verification): " + "; ".join(parts)
