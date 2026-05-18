"""
sheaf_cards — Shared knowledge card engine.

Used by both Sheaf (product) and PhD thesis (academic).
Core abstraction: structured knowledge assets as traceable middleware
between raw data and agent queries.
"""

from sheaf_cards.base import KnowledgeCard, CardStore, CardValidator
from sheaf_cards.embeddings import EmbeddingEngine
from sheaf_cards.generator import CardGenerator

__all__ = [
    "KnowledgeCard",
    "CardStore",
    "CardValidator",
    "EmbeddingEngine",
    "CardGenerator",
]
