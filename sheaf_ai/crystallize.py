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
from pathlib import Path
from typing import Optional

from sheaf_ai.config import (
    DATA_DIR, INDEX_FILE, RAW_DIR, BJT,
    load_prompt,
)
from sheaf_ai.exceptions import LLMError
from sheaf_ai.llm_client import chat

from sheaf_cards.base import KnowledgeCard, CardStore, CardValidator


# ============================================================
# Constants
# ============================================================

CARDS_DIR = DATA_DIR / "cards"
CARDS_STORE_FILE = CARDS_DIR / "knowledge_cards.json"
EMBEDDINGS_DIR = CARDS_DIR / "embeddings"

DEFAULT_CRYSTALLIZE_MODEL = os.environ.get(
    "CRYSTALLIZE_MODEL",
    os.environ.get("OPENAI_MODEL", "deepseek-ai/DeepSeek-V3.2"),
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
        topics_str = " ".join(topic_names).lower()

        # Check tags
        tags = entry.get("tags", [])
        tags_str = " ".join(str(t) for t in tags).lower()

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


# ============================================================
# Crystallization prompt
# ============================================================

_CRYSTALLIZE_SYSTEM = """You are a knowledge synthesis engine. Your task is to analyze MULTIPLE source articles on a given topic and produce structured knowledge cards that capture patterns, insights, and evidence across sources.

For each distinct insight or pattern you discover across the sources:
- title: concise title (5-15 words)
- claim: the synthesized knowledge statement (1-3 sentences)
- evidence: specific evidence from sources, citing which source supports it (use source index like [Source 1], [Source 2])
- tags: 3-7 relevant tags/keywords
- confidence: your confidence (0.0-1.0) considering evidence quality and source agreement
- source_indices: list of source indices that support this claim

IMPORTANT RULES:
1. Synthesize ACROSS sources — prefer insights supported by multiple sources
2. Every claim MUST have evidence traced to specific sources
3. If sources contradict, note the disagreement and lower confidence
4. Output ONLY a JSON array of card objects
5. All text output in Chinese, preserve English proper nouns
6. If sources are too thin to extract meaningful patterns, return []

Output format:
```json
[
  {
    "title": "...",
    "claim": "...",
    "evidence": "...",
    "tags": ["..."],
    "confidence": 0.85,
    "source_indices": [0, 2]
  }
]
```"""


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
        List of KnowledgeCard objects.

    Raises:
        ValueError: If not enough entries found for the topic.
        LLMError: If LLM call fails.
    """
    # Step 1: Find matching entries
    entries = find_entries_by_topic(topic, min_entries=min_entries, limit=max_entries)
    if not entries:
        return []

    # Step 2: Load full texts and build source context
    sources = []
    for i, entry in enumerate(entries):
        entry_id = entry.get("id", "")
        title = entry.get("title", "Untitled")
        summary = entry.get("summary", "")
        full_text = _load_entry_full_text(entry_id)

        # Use summary + truncated full text
        content = full_text[:3000] if full_text else summary
        source_block = (
            f"[Source {i}] {title}\n"
            f"Summary: {summary}\n"
            f"Content: {content[:2000]}\n"
        )
        sources.append(source_block)

    # Step 3: Build prompt and call LLM
    prompt = (
        f"Analyze the following {len(sources)} sources about '{topic}' "
        f"and extract up to {max_cards} knowledge cards.\n\n"
        f"---\n{''.join(sources)}\n---"
    )

    try:
        model = model or DEFAULT_CRYSTALLIZE_MODEL
        raw = chat(
            prompt=prompt,
            system=_CRYSTALLIZE_SYSTEM,
            model=model,
            temperature=0.3,
            max_tokens=4096,
            provider=provider,
        )
    except Exception as e:
        raise LLMError(f"Crystallization LLM call failed: {e}") from e

    # Step 4: Parse response into KnowledgeCards
    cards = _parse_crystallized_response(
        raw=raw,
        entries=entries,
        topic=topic,
        model=model,
    )

    # Step 5: Validate
    validator = CardValidator()
    valid_cards = []
    for card in cards[:max_cards]:
        issues = validator.validate_schema(card, strict=False)
        if not issues:
            valid_cards.append(card)

    return valid_cards


def _parse_crystallized_response(
    raw: str,
    entries: list[dict],
    topic: str,
    model: str,
) -> list[KnowledgeCard]:
    """Parse LLM crystallization response into KnowledgeCards."""
    import re

    # Strip markdown code blocks
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    cleaned = re.sub(r'\s*```$', '', cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r'\[[\s\S]*\]', cleaned)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                return []
        else:
            return []

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []

    cards = []
    for item in parsed:
        if not isinstance(item, dict):
            continue

        # Map source_indices to source_ids
        source_indices = item.get("source_indices", [])
        source_ids = []
        for idx in source_indices:
            if isinstance(idx, int) and 0 <= idx < len(entries):
                eid = entries[idx].get("id", "")
                if eid:
                    source_ids.append(eid)

        # Also add any entry IDs that matched
        if not source_ids:
            source_ids = [e.get("id", "") for e in entries[:5] if e.get("id")]

        card = KnowledgeCard(
            title=item.get("title", f"Insight on {topic}"),
            claim=item.get("claim", ""),
            evidence=item.get("evidence", ""),
            tags=item.get("tags", [topic]),
            confidence=float(item.get("confidence", 0.5)),
            source_ids=source_ids,
            provenance={
                "generator": "crystallize",
                "model": model,
                "topic": topic,
                "source_count": len(entries),
            },
        )
        cards.append(card)

    return cards


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
    """Crystallize a topic and save cards to the store.

    Args:
        topic: Topic to crystallize.
        auto_embed: Whether to update embedding index after saving (default True).
            Set to False in tests or when embedding API is unavailable.

    Returns:
        List of saved KnowledgeCard objects.
    """
    cards = crystallize_topic(
        topic=topic,
        min_entries=min_entries,
        max_entries=max_entries,
        max_cards=max_cards,
        model=model,
        provider=provider,
    )

    store = _get_card_store()
    saved = []
    for card in cards:
        # Dedup check
        existing = store.search(card.title, limit=5)
        if _is_duplicate(card, existing):
            continue
        store.save(card)
        saved.append(card)

    # Update embedding index for newly saved cards
    if auto_embed and saved:
        _embed_cards(saved)

    return saved


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


# ============================================================
# Helpers
# ============================================================

def _is_duplicate(card: KnowledgeCard, existing: list[KnowledgeCard],
                  threshold: float = 0.75) -> bool:
    """Check if a card is too similar to existing cards."""
    new_text = f"{card.title} {card.claim}".lower()
    new_words = set(new_text.split())
    if not new_words:
        return False

    for ex in existing:
        ex_text = f"{ex.title} {ex.claim}".lower()
        ex_words = set(ex_text.split())
        overlap = len(new_words & ex_words) / len(new_words)
        if overlap >= threshold:
            return True
    return False


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
