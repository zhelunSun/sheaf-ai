"""Application service boundary for knowledge card use cases.

Adapters should use this module for card operations and public JSON projection.
The service delegates persistence/extraction to ``crystallize`` and does not
change the KnowledgeCard schema or card store format.
"""
from __future__ import annotations

from typing import Optional

from sheaf_ai import crystallize
from sheaf_cards.base import KnowledgeCard


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
