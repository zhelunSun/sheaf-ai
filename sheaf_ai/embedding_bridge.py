"""
sheaf_ai/embedding_bridge.py — Bridge between Sheaf entries and knowledge card engine.

Connects Sheaf's entry system with sheaf_cards for:
  1. Converting entries → knowledge cards (via LLM generator)
  2. Building/maintaining embedding index over cards
  3. Semantic search across collected knowledge

Usage:
    from sheaf_ai.embedding_bridge import EmbeddingBridge

    bridge = EmbeddingBridge()
    bridge.process_entry(entry)              # entry → cards → index
    results = bridge.search("remote sensing") # semantic search
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from sheaf_ai.config import DATA_DIR

from sheaf_cards.base import KnowledgeCard, CardStore, CardValidator
from sheaf_cards.embeddings import EmbeddingEngine
from sheaf_cards.generator import CardGenerator


# Default paths
CARDS_DIR = DATA_DIR / "cards"
CARDS_STORE_FILE = CARDS_DIR / "cards.json"
EMBEDDINGS_DIR = CARDS_DIR / "embeddings"


class EmbeddingBridge:
    """Bridge between Sheaf entries and sheaf_cards engine.

    Manages the lifecycle:
        Entry → generate cards → validate → save → embed → search
    """

    def __init__(self, cards_dir: Path = None, model: str = None):
        # Paths
        self.cards_dir = cards_dir or CARDS_DIR
        self.cards_dir.mkdir(parents=True, exist_ok=True)

        store_path = self.cards_dir / "cards.json"
        emb_dir = self.cards_dir / "embeddings"

        # Core components
        self.store = CardStore(store_path)
        self.engine = EmbeddingEngine(emb_dir)
        self.generator = CardGenerator(model=model)
        self.validator = CardValidator()

    def process_entry(self, entry: dict, auto_embed: bool = True) -> list[KnowledgeCard]:
        """Process a single entry: extract cards + save + optionally embed.

        Args:
            entry: UC entry dict with 'content', 'title', 'summary', 'url', etc.
            auto_embed: Whether to immediately update embedding index.

        Returns:
            List of newly created KnowledgeCard objects.
        """
        # Build input text from entry
        text = self._entry_to_text(entry)
        if not text or len(text.strip()) < 50:
            return []

        source_id = entry.get("url", "") or entry.get("id", "")

        # Generate and save cards
        cards = self.generator.generate_and_save(
            text,
            store=self.store,
            source_id=source_id,
            max_cards=3,
            validate=True,
            strict=False,  # Sheaf mode: lenient
        )

        # Update embedding index
        if auto_embed and cards:
            self.engine.update_index(cards)

        return cards

    def process_entries_batch(self, entries: list[dict]) -> dict:
        """Process multiple entries. Returns summary stats.

        Args:
            entries: List of UC entry dicts.

        Returns:
            Dict with total_entries, cards_created, errors.
        """
        all_cards = []
        errors = 0

        for entry in entries:
            try:
                cards = self.process_entry(entry, auto_embed=False)
                all_cards.extend(cards)
            except Exception as e:
                errors += 1
                print(f"  Error processing entry: {e}")

        # Single batch embed at the end
        if all_cards:
            self.engine.update_index(all_cards)

        return {
            "total_entries": len(entries),
            "cards_created": len(all_cards),
            "errors": errors,
        }

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Semantic search across knowledge cards.

        Args:
            query: Natural language query.
            top_k: Number of results.

        Returns:
            List of dicts with card data + similarity score.
        """
        results = self.engine.search(query, top_k=top_k)
        output = []

        for card_id, score in results:
            card = self.store.load(card_id)
            if card:
                output.append({
                    "card": card.to_dict(),
                    "score": round(score, 4),
                })

        return output

    def search_text(self, query: str, limit: int = 10) -> list[KnowledgeCard]:
        """Fast text search (no embedding, uses CardStore.search).

        Useful when embedding index is not yet built.
        """
        return self.store.search(query, limit=limit)

    def rebuild_index(self):
        """Full rebuild of embedding index from all stored cards."""
        cards = self.store.list_all(limit=10000)
        if cards:
            self.engine.build_index(cards)
        return len(cards)

    def stats(self) -> dict:
        """Return bridge statistics."""
        return {
            "total_cards": self.store.count(),
            "indexed_vectors": self.engine.count(),
            "cards_dir": str(self.cards_dir),
        }

    def link_cards(self, card_a: str, card_b: str) -> None:
        """Create bidirectional link between two cards."""
        self.store.link(card_a, card_b)

    def get_card(self, card_id: str) -> Optional[KnowledgeCard]:
        """Load a single card by ID."""
        return self.store.load(card_id)

    def list_cards(self, limit: int = 50) -> list[KnowledgeCard]:
        """List recent cards."""
        return self.store.list_all(limit=limit)

    # --- Internal ---

    @staticmethod
    def _entry_to_text(entry: dict) -> str:
        """Convert a UC entry to text suitable for card generation."""
        parts = []

        title = entry.get("title", "")
        if title:
            parts.append(f"# {title}")

        summary = entry.get("summary", "")
        if summary:
            parts.append(summary)

        # Raw content if available
        content = entry.get("content", "") or entry.get("raw_content", "")
        if content:
            # Truncate to avoid token limits (keep first ~3000 chars)
            if len(content) > 3000:
                content = content[:3000] + "..."
            parts.append(content)

        # Tags as context
        tags = entry.get("tags", []) or entry.get("topics", [])
        if tags:
            parts.append(f"Tags: {', '.join(tags)}")

        return "\n\n".join(parts)
