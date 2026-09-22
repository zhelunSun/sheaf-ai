"""
Sheaf Crystallize — Knowledge crystallization engine.

Takes multiple collected entries on a topic, uses LLM to synthesize
structured knowledge cards with evidence tracing. This is the core
differentiator: turning a dusty bookmark folder into Agent-consumable
knowledge assets.

Usage:
    from sheaf_ai.crystallize import crystallize_topic, list_crystallized

    cards = crystallize_topic("RAG")
    for card in cards:
        print(f"[{card.confidence:.0%}] {card.title}")
        print(f"   {card.claim}")
"""
from __future__ import annotations

import json
import os
from typing import Optional

from sheaf_ai.config import (
    DATA_DIR, INDEX_FILE, RAW_DIR,
)
from sheaf_ai.card_extraction import (
    CRYSTALLIZE_SYSTEM_PROMPT,
    CardExtractionRequest,
    CardExtractionResult,
    CardSource,
    LlmCardExtractionEngine,
    parse_card_extraction_response,
)
from sheaf_ai.exceptions import LLMError
from sheaf_ai.llm_client import chat
from sheaf_ai.passage_selection import select_passages

from sheaf_cards.base import KnowledgeCard, CardStore, CardValidator


# ============================================================
# Constants
# ============================================================

CARDS_DIR = DATA_DIR / "cards"
CARDS_STORE_FILE = CARDS_DIR / "knowledge_cards.json"
EMBEDDINGS_DIR = CARDS_DIR / "embeddings"

DEFAULT_CRYSTALLIZE_MODEL = (
    os.environ.get("CRYSTALLIZE_MODEL")
    or os.environ.get("DEFAULT_MODEL")
    or None
)


# ============================================================
# Topic entry retrieval
# ============================================================

def _load_index_entries() -> list[dict]:
    """Load all entries from index.jsonl."""
    if not INDEX_FILE.exists():
        return []
    entries = []
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def find_entries_by_topic(topic: str, min_entries: int = 3, limit: int = 20) -> list[dict]:
    """Find entries matching a topic string.

    Searches across title, topics, tags, and summary fields.
    Returns up to `limit` entries, or empty list if fewer than `min_entries`.

    Args:
        topic: Topic keyword or phrase to search for.
        min_entries: Minimum entries required to proceed with crystallization.
        limit: Maximum entries to include in crystallization.

    Returns:
        List of matching index entries (dicts).
    """
    if not topic or not topic.strip():
        return []

    topic_lower = topic.strip().lower()
    all_entries = _load_index_entries()

    scored = []
    for entry in all_entries:
        score = 0.0
        title = entry.get("title", "").lower()
        summary = entry.get("summary", "").lower()

        # Check topics list
        topics = entry.get("topics", [])
        topic_names = [
            t.get("name", t) if isinstance(t, dict) else str(t)
            for t in topics
        ]
        " ".join(topic_names).lower()

        # Check tags
        tags = entry.get("tags", [])
        " ".join(str(t) for t in tags).lower()

        # Score: exact topic name match is highest
        for tn in topic_names:
            if topic_lower == tn.lower():
                score += 15.0
            elif topic_lower in tn.lower():
                score += 8.0

        # Tag match
        for tag in tags:
            if topic_lower == str(tag).lower():
                score += 6.0
            elif topic_lower in str(tag).lower():
                score += 3.0

        # Title / summary match
        if topic_lower in title:
            score += 10.0
        if topic_lower in summary:
            score += 2.0

        # Primary category match
        primary = entry.get("primary_category", "").lower()
        if topic_lower == primary:
            score += 12.0
        elif topic_lower in primary:
            score += 5.0

        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    if len(scored) < min_entries:
        return []

    return [entry for _, entry in scored[:limit]]


def _load_entry_full_text(entry_id: str) -> str:
    """Load full article text for an entry from raw/ directory."""
    raw_path = RAW_DIR / f"{entry_id}.txt"
    if raw_path.exists():
        try:
            return raw_path.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


def _build_card_sources(entries: list[dict], *, topic: str = "") -> list[CardSource]:
    """Build extraction sources from index entries and raw text files."""
    sources = []
    for entry in entries:
        entry_id = entry.get("id", "")
        title = entry.get("title", "Untitled")
        summary = entry.get("summary", "")
        full_text = _load_entry_full_text(entry_id)
        selection = select_passages(
            full_text,
            topic=topic,
            entry=entry,
        ) if full_text else None
        text = selection.text if selection is not None else summary
        metadata = {"entry": entry}
        if selection is not None:
            metadata["passage_selection"] = dict(selection.manifest)
        sources.append(
            CardSource(
                entry_id=entry_id,
                title=title,
                summary=summary,
                text=text,
                url=entry.get("url", ""),
                collected_at=entry.get("collected_at", ""),
                metadata=metadata,
            )
        )
    return sources


# Kept for compatibility with internal callers/tests that import the old name.
_CRYSTALLIZE_SYSTEM = CRYSTALLIZE_SYSTEM_PROMPT


# ============================================================
# Core crystallization
# ============================================================

def crystallize_topic(
    topic: str,
    min_entries: int = 3,
    max_entries: int = 10,
    max_cards: int = 5,
    model: str = None,
    provider: str = None,
) -> list[KnowledgeCard]:
    """Compatibility list view; use ``crystallize_topic_result`` for diagnostics."""
    return crystallize_topic_result(
        topic=topic, min_entries=min_entries, max_entries=max_entries,
        max_cards=max_cards, model=model, provider=provider,
    ).cards


def crystallize_topic_result(
    topic: str,
    min_entries: int = 3,
    max_entries: int = 10,
    max_cards: int = 5,
    model: str = None,
    provider: str = None,
) -> CardExtractionResult:
    """Crystallize knowledge cards from entries on a given topic.

    This is the main entry point. It:
    1. Searches for entries matching the topic
    2. Loads full text for each entry
    3. Sends to LLM for synthesis
    4. Returns structured KnowledgeCard objects

    Args:
        topic: Topic to crystallize.
        min_entries: Minimum entries required (default 3).
        max_entries: Max entries to include (default 10).
        max_cards: Max cards to generate (default 5).
        model: LLM model to use (default from config).
        provider: LLM provider to use (default from config).

    Returns:
        Cards plus explicit empty/error/partial outcome and extraction warnings.

    Raises:
        ValueError: If not enough entries found for the topic.
        LLMError: If LLM call fails.
    """
    # Step 1: Find matching entries
    entries = find_entries_by_topic(topic, min_entries=min_entries, limit=max_entries)
    if not entries:
        return CardExtractionResult(
            cards=[], status="empty", warnings=["Not enough matching entries to crystallize"],
        )

    # Step 2: Build extraction request and delegate to the default engine.
    sources = _build_card_sources(entries, topic=topic)
    model = model or DEFAULT_CRYSTALLIZE_MODEL
    engine = LlmCardExtractionEngine(
        system_prompt=_CRYSTALLIZE_SYSTEM,
        chat_func=chat,
    )
    try:
        result = engine.extract(
            CardExtractionRequest(
                topic=topic,
                sources=sources,
                max_cards=max_cards,
                model=model,
                provider=provider,
            )
        )
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"Crystallization LLM call failed: {e}") from e

    cards = result.cards

    # Step 3: Validate
    validator = CardValidator()
    valid_cards = []
    for card in cards[:max_cards]:
        # Batch crystallization promises source-backed cards. Missing evidence,
        # unresolvable source IDs, or sub-threshold confidence must fail closed
        # rather than becoming decorative provenance in the public card store.
        issues = validator.validate_schema(card, strict=True)
        if not issues:
            valid_cards.append(card)
        else:
            result.rejected_count += 1
            result.warnings.extend(f"Skipped invalid card: {issue}" for issue in issues)

    valid_ids = {card.card_id for card in valid_cards}
    for card in valid_cards:
        card.associations = [related for related in card.associations if related in valid_ids]
    result.cards = valid_cards
    if cards and not valid_cards:
        result.status = "error"
    elif valid_cards and result.warnings:
        result.status = "partial"
    return result


def _parse_crystallized_response(
    raw: str,
    entries: list[dict],
    topic: str,
    model: str,
) -> list[KnowledgeCard]:
    """Compatibility wrapper for the old crystallize parser helper."""
    sources = [
        CardSource(
            entry_id=entry.get("id", ""),
            title=entry.get("title", "Untitled"),
            summary=entry.get("summary", ""),
            text=entry.get("summary", ""),
            url=entry.get("url", ""),
            collected_at=entry.get("collected_at", ""),
            metadata={"entry": entry},
        )
        for entry in entries
    ]
    result = parse_card_extraction_response(
        raw=raw,
        sources=sources,
        topic=topic,
        model=model,
        engine="llm_v1",
        citation_mode="legacy",
    )
    return result.cards


# ============================================================
# Card persistence
# ============================================================

def _get_card_store() -> CardStore:
    """Get the default card store for crystallized cards."""
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    return CardStore(CARDS_STORE_FILE)


def crystallize_and_save(
    topic: str,
    min_entries: int = 3,
    max_entries: int = 10,
    max_cards: int = 5,
    model: str = None,
    provider: str = None,
    auto_embed: bool = True,
) -> list[KnowledgeCard]:
    """Compatibility list view; use ``crystallize_and_save_result`` for diagnostics."""
    return crystallize_and_save_result(
        topic=topic, min_entries=min_entries, max_entries=max_entries,
        max_cards=max_cards, model=model, provider=provider, auto_embed=auto_embed,
    ).cards


def crystallize_and_save_result(
    topic: str,
    min_entries: int = 3,
    max_entries: int = 10,
    max_cards: int = 5,
    model: str = None,
    provider: str = None,
    auto_embed: bool = True,
) -> CardExtractionResult:
    """Crystallize a topic and save cards to the store.

    Args:
        topic: Topic to crystallize.
        auto_embed: Whether to update embedding index after saving (default True).
            Set to False in tests or when embedding API is unavailable.

    Returns:
        Saved cards and diagnostics. Empty/model-invalid outputs do not open the store.
    """
    result = crystallize_topic_result(
        topic=topic,
        min_entries=min_entries,
        max_entries=max_entries,
        max_cards=max_cards,
        model=model,
        provider=provider,
    )
    cards = result.cards
    if not cards:
        return result

    store = _get_card_store()
    saved = []
    omitted_ids = set()
    for card in cards:
        # Dedup check
        existing = store.search(card.title, limit=5)
        if _is_duplicate(card, [*existing, *saved]):
            omitted_ids.add(card.card_id)
            continue
        saved.append(card)
    if omitted_ids:
        result.warnings.append(f"Skipped {len(omitted_ids)} duplicate card(s) before saving")
    for card in saved:
        # A generated duplicate has a fresh ID that will never be persisted.
        # Do not save a relationship to that absent object.
        card.associations = [related for related in card.associations if related not in omitted_ids]
    # One card-store transaction: never publish a prefix of a related-card batch.
    # Embeddings below are still an explicitly separate best-effort operation.
    store.save_many(saved)

    # Update embedding index for newly saved cards
    if auto_embed and saved:
        embedded_count = _embed_cards(saved)
        if embedded_count != len(saved):
            result.warnings.append("Cards saved but the embedding index was not fully updated")
            result.status = "partial"

    # Update gamification streak after crystallization
    if saved:
        try:
            from sheaf_ai.gamification import update_after_crystallize
            update_after_crystallize(topic, card_count=len(saved))
        except Exception:
            pass  # Gamification is best-effort

    result.cards = saved
    if not saved and result.status != "partial":
        result.status = "empty"
    return result


def _embed_cards(cards: list[KnowledgeCard]) -> int:
    """Add crystallized cards to the embedding index.

    Uses the shared EmbeddingEngine from sheaf_cards.
    Silently skips if embedding API is unavailable.

    Args:
        cards: List of KnowledgeCard objects to embed.

    Returns:
        Number of cards successfully indexed.
    """
    try:
        from sheaf_cards.embeddings import EmbeddingEngine
        EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
        engine = EmbeddingEngine(EMBEDDINGS_DIR)
        engine.update_index(cards)
        return len(cards)
    except Exception:
        # Embedding is best-effort — don't block crystallization
        return 0


def list_crystallized(topic: str = "", limit: int = 20) -> list[KnowledgeCard]:
    """List crystallized knowledge cards, optionally filtered by topic.

    Args:
        topic: Filter by topic (empty = all).
        limit: Max cards to return.

    Returns:
        List of KnowledgeCard objects.
    """
    store = _get_card_store()
    if topic:
        return store.search(topic, limit=limit)
    return store.list_all(limit=limit)


def get_card(card_id: str) -> Optional[KnowledgeCard]:
    """Get a single knowledge card by ID."""
    store = _get_card_store()
    return store.load(card_id)


def delete_card(card_id: str) -> bool:
    """Delete a knowledge card. Returns True if found."""
    store = _get_card_store()
    return store.delete(card_id)


def count_cards() -> int:
    """Return the exact number of persisted cards."""
    return _get_card_store().count()


# ============================================================
# Helpers
# ============================================================

def _is_duplicate(card: KnowledgeCard, existing: list[KnowledgeCard],
                  threshold: float = 0.75) -> bool:
    """Collapse exact content copies, never infer semantic equivalence.

    ``threshold`` remains accepted for call compatibility but has no effect.
    Word overlap loses negation, scope and versions; identical prose with a new
    source or input trace is also new evidence and must remain available.
    """
    def content(value: KnowledgeCard) -> dict:
        output = value.to_dict()
        for key in ("card_id", "created_at", "updated_at"):
            output.pop(key, None)
        # These timestamps record tag creation, not a different scientific claim
        # or source. Keep tag names/ownership and every other extra field intact.
        entries = output.get("extra", {}).get("tag_entries", [])
        for entry in entries:
            if isinstance(entry, dict):
                entry.pop("attached_at", None)
        return output

    current = content(card)
    return any(content(other) == current for other in existing)


def get_topic_stats() -> dict[str, int]:
    """Get count of crystallized cards per topic.

    Returns:
        Dict mapping topic name to card count.
    """
    store = _get_card_store()
    all_cards = store.list_all(limit=1000)

    topic_counts: dict[str, int] = {}
    for card in all_cards:
        topic = card.provenance.get("topic", "unknown")
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    return dict(sorted(topic_counts.items(), key=lambda x: x[1], reverse=True))


# ============================================================
# Embedding integration
# ============================================================

def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """Search crystallized cards using semantic similarity.

    Args:
        query: Natural language query.
        top_k: Number of results to return.

    Returns:
        List of dicts with 'card' (KnowledgeCard) and 'score' (float).
    """
    try:
        from sheaf_cards.embeddings import EmbeddingEngine
        EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
        engine = EmbeddingEngine(EMBEDDINGS_DIR)
        results = engine.search(query, top_k=top_k)

        store = _get_card_store()
        output = []
        for card_id, score in results:
            card = store.load(card_id)
            if card:
                output.append({"card": card, "score": round(score, 4)})
        return output
    except Exception:
        return []


def rebuild_embeddings() -> int:
    """Rebuild the entire embedding index from stored cards.

    Returns:
        Number of cards indexed.
    """
    from sheaf_cards.embeddings import EmbeddingEngine
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    engine = EmbeddingEngine(EMBEDDINGS_DIR)
    store = _get_card_store()
    all_cards = store.list_all(limit=10000)
    if all_cards:
        engine.build_index(all_cards)
    return len(all_cards)
