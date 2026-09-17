"""Incremental knowledge consolidation — evidence-governed state transition.

Sprint 1 (minimal closed loop):

    new evidence + existing cards
        -> LLM decides on a finite edit-operation set
           {create, update, merge, retire}   (standing on Mem0's ADD/UPDATE/DELETE/NOOP)
        -> apply the transition (versioned, supersede chain preserved)
        -> recalibrate confidence from structured evidence features.

The differentiator vs Mem0 / A-MEM / Zep is the *evidence governance* dimension:
every transition keeps provenance and a traceable ``superseded_by`` audit chain,
and confidence is a reproducible function of evidence features, not an LLM scalar.
"""
from __future__ import annotations

import json

from sheaf_ai.crystallize import (
    find_entries_by_topic,
    _load_entry_full_text,
    _get_card_store,
)
from sheaf_ai.calibration import calibrate_card
from sheaf_ai.llm_client import chat
from sheaf_cards.base import KnowledgeCard, CardStore


# ============================================================
# Consolidation decision prompt
# ============================================================

CONSOLIDATE_SYSTEM_PROMPT = """\
You are an evidence-governed knowledge consolidation engine. Given a topic's \
existing knowledge cards and newly collected evidence, decide how to integrate \
the new evidence while keeping the knowledge base trustworthy and auditable.

## Core principle

You are NOT re-summarizing from scratch. You are deciding how NEW evidence \
changes the EXISTING knowledge state: reinforce it, refine it, merge it, or \
replace it. Prefer updating existing cards over creating duplicates.

## Output schema (JSON object)

```json
{
  "operations": [
    {
      "action": "create" | "update" | "merge" | "retire",
      "target_card_id": "<existing card_id for update/merge/retire>",
      "card": {
        "title": "...",
        "claim": "...",
        "evidence": "...",
        "tags": ["..."],
        "source_ids": ["<source id>", ...]
      },
      "supersede_card_ids": ["<old card_id>", ...],
      "supersede_reason": "..."
    }
  ]
}
```

## Actions

- **create**: new insight with no existing card. Fill ``card``.
- **update**: new evidence reinforces/refines an existing card. Fill \
``target_card_id`` + ``card`` (the refined content, keeping the strongest \
evidence). The system bumps the version automatically.
- **merge**: the new evidence and an existing card describe the SAME insight \
from different angles. Fill ``target_card_id`` + ``card`` (the merged, \
evidence-strongest content) and list the redundant old cards in \
``supersede_card_ids`` so they are linked into the audit chain.
- **retire**: an existing card is contradicted or outdated. Fill \
``target_card_id`` + ``supersede_reason``. Optionally also ``create`` a \
replacement card in the same response.

## Evidence discipline (strict)

- Every claim MUST cite sources via ``source_ids`` copied VERBATIM from the \
input source headers — never invent IDs.
- When evidence conflicts, the stronger evidence wins (more sources, higher \
tier A > B > C, more recent). Retire the weaker card and record the reason.
- Do NOT output confidence — the system computes it from evidence features.

If nothing needs to change, return {"operations": []}.
"""


# ============================================================
# Helpers
# ============================================================

def _load_topic_cards(store: CardStore, topic: str) -> list[KnowledgeCard]:
    """Return existing cards belonging to ``topic`` (by provenance topic)."""
    out: list[KnowledgeCard] = []
    for card in store.list_all(limit=1000):
        card_topic = (card.provenance or {}).get("topic", "")
        if card_topic == topic and not card.superseded_by:
            out.append(card)
    return out


def _card_from_dict(data: dict, topic: str) -> KnowledgeCard:
    """Build a KnowledgeCard from an operation's ``card`` payload."""
    return KnowledgeCard(
        title=data.get("title", f"Insight on {topic}"),
        claim=data.get("claim", ""),
        evidence=data.get("evidence", ""),
        tags=data.get("tags", [topic]),
        source_ids=data.get("source_ids", []),
        provenance={
            "generator": "consolidate",
            "engine": "llm_v1",
            "topic": topic,
        },
    )


def _apply_content(card: KnowledgeCard, data: dict) -> None:
    """Overwrite content fields from an operation payload (keep identity)."""
    if data.get("title"):
        card.title = data["title"]
    if data.get("claim"):
        card.claim = data["claim"]
    if data.get("evidence"):
        card.evidence = data["evidence"]
    if data.get("tags"):
        card.tags = data["tags"]
    if data.get("source_ids"):
        card.source_ids = data["source_ids"]


def _build_decision_prompt(
    topic: str,
    entries: list[dict],
    cards: list[KnowledgeCard],
) -> str:
    """Render new evidence + existing cards (with evidence features) for the LLM."""
    source_blocks = []
    for i, e in enumerate(entries):
        eid = e.get("id", "")
        text = _load_entry_full_text(eid)[:1500] or e.get("summary", "")
        source_blocks.append(
            f"[Source {eid}] tier={e.get('quality_tier', 'B')} "
            f"— {e.get('title', 'Untitled')}\n{e.get('summary', '')}\n{text}\n"
        )

    card_blocks = []
    for c in cards:
        card_blocks.append(
            f"[Card {c.card_id}] v{c.version} strength={c.evidence_strength:.2f} "
            f"sources={len(c.source_ids)}\n"
            f"title: {c.title}\nclaim: {c.claim}\n"
            f"evidence: {c.evidence}\n"
        )

    return (
        f"Topic: {topic}\n\n"
        f"=== EXISTING CARDS ({len(card_blocks)}) ===\n"
        f"{''.join(card_blocks) or '(none)'}\n\n"
        f"=== NEW EVIDENCE ({len(source_blocks)}) ===\n"
        f"{''.join(source_blocks)}\n\n"
        "Decide the operations to consolidate the new evidence into the "
        "knowledge state. Return JSON only."
    )


def _parse_operations(raw: str) -> list[dict]:
    """Parse the LLM JSON response into an operations list (best-effort)."""
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fall back to the first {...} or [...] block
        import re
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return []
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        ops = data.get("operations", [])
    elif isinstance(data, list):
        ops = data
    else:
        return []
    return [o for o in ops if isinstance(o, dict)]


# ============================================================
# Main entry point
# ============================================================

def consolidate_topic(
    topic: str,
    min_entries: int = 1,
    max_entries: int = 10,
    model: str = None,
    provider: str = None,
) -> list[dict]:
    """Consolidate a topic's new evidence into the existing card store.

    Returns a list of result dicts describing the applied operations, e.g.
    ``{"action": "update", "card_id": "...", "version": 2}``.
    """
    entries = find_entries_by_topic(topic, min_entries=min_entries, limit=max_entries)
    if not entries:
        return []

    store = _get_card_store()
    cards = _load_topic_cards(store, topic)

    entries_by_id = {e.get("id", ""): e for e in entries}

    prompt = _build_decision_prompt(topic, entries, cards)
    raw = chat(
        prompt=prompt,
        system=CONSOLIDATE_SYSTEM_PROMPT,
        model=model,
        temperature=0.3,
        max_tokens=4096,
        provider=provider,
    )
    operations = _parse_operations(raw)

    return _apply_operations(store, operations, entries_by_id, topic)


def _apply_operations(
    store: CardStore,
    operations: list[dict],
    entries_by_id: dict,
    topic: str,
) -> list[dict]:
    """Execute the operation sequence and return a result summary."""
    results: list[dict] = []

    for op in operations:
        action = op.get("action", "")
        target_id = op.get("target_card_id", "")
        card_payload = op.get("card") or {}
        supersede_ids = op.get("supersede_card_ids") or []
        reason = op.get("supersede_reason", "")

        if action == "create":
            card = _card_from_dict(card_payload, topic)
            card = calibrate_card(card, entries_by_id)
            store.save(card)
            results.append({"action": "create", "card_id": card.card_id, "version": 1})

        elif action == "update" and target_id:
            existing = store.load(target_id)
            if existing:
                _apply_content(existing, card_payload)
                existing.version += 1
                existing = calibrate_card(existing, entries_by_id)
                store.save(existing)
                results.append({"action": "update", "card_id": target_id, "version": existing.version})

        elif action == "merge" and target_id:
            target = store.load(target_id)
            if target:
                _apply_content(target, card_payload)
                target.version += 1
                target = calibrate_card(target, entries_by_id)
                store.save(target)
                results.append({"action": "merge", "card_id": target_id, "version": target.version})
                for sid in supersede_ids:
                    old = store.load(sid)
                    if old and old.card_id != target.card_id:
                        old.superseded_by = target.card_id
                        old.supersede_reason = reason or "merged"
                        store.save(old)
                        results.append({"action": "superseded", "card_id": sid, "by": target.card_id})

        elif action == "retire" and target_id:
            existing = store.load(target_id)
            if existing:
                existing.superseded_by = op.get("superseded_by", "")
                existing.supersede_reason = reason or "retired"
                store.save(existing)
                results.append({"action": "retire", "card_id": target_id})

    return results


def card_history(card_id: str, store: CardStore = None) -> list[KnowledgeCard]:
    """Return the supersede audit chain containing ``card_id`` (oldest first).

    ``superseded_by`` points from a card to the card that replaced it, so the
    chain is reconstructed by first walking forward to the latest card, then
    walking back through predecessors. Sprint 1 exposes the chain; Sprint 2
    adds the CLI view.
    """
    store = store or _get_card_store()
    all_cards = store.list_all(limit=10000)

    # Step 1: walk forward (superseded_by) to the latest card in the chain.
    latest = store.load(card_id)
    if latest is None:
        return []
    seen: set[str] = set()
    while latest.superseded_by and latest.superseded_by not in seen:
        seen.add(latest.card_id)
        nxt = store.load(latest.superseded_by)
        if nxt is None:
            break
        latest = nxt

    # Step 2: index predecessors (cards whose superseded_by points at a card).
    predecessors: dict[str, list[KnowledgeCard]] = {}
    for c in all_cards:
        if c.superseded_by:
            predecessors.setdefault(c.superseded_by, []).append(c)

    # Step 3: walk back from latest through predecessors.
    chain: list[KnowledgeCard] = []
    current = latest
    walked: set[str] = set()
    while current and current.card_id not in walked:
        walked.add(current.card_id)
        chain.append(current)
        preds = [
            c for c in predecessors.get(current.card_id, [])
            if c.card_id not in walked
        ]
        current = preds[0] if preds else None

    chain.reverse()
    return chain
