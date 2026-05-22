"""
Tests for sheaf_ai.crystallize — Knowledge crystallization engine.

Tests cover:
- find_entries_by_topic: topic matching with various field combinations
- crystallize_topic: LLM-based synthesis (mocked)
- crystallize_and_save: end-to-end with persistence
- list_crystallized / get_card / delete_card: retrieval operations
- get_topic_stats: topic statistics
- Edge cases: empty topic, too few entries, LLM failure
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sheaf_ai.crystallize import (
    find_entries_by_topic,
    crystallize_topic,
    crystallize_and_save,
    list_crystallized,
    get_card,
    delete_card,
    get_topic_stats,
    _parse_crystallized_response,
    _get_card_store,
    CARDS_DIR,
)
from sheaf_ai.config import INDEX_FILE, RAW_DIR
from sheaf_cards.base import KnowledgeCard


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_entries(tmp_path, monkeypatch):
    """Create sample index entries and raw text for testing."""
    entries_dir = tmp_path / "entries"
    raw_dir = tmp_path / "raw"
    entries_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    entries = [
        {
            "id": "2026-01-01_abcd1234",
            "title": "RAG Systems in Production",
            "topics": [{"name": "RAG", "confidence": 0.95}, {"name": "LLM", "confidence": 0.8}],
            "tags": ["rag", "retrieval", "production"],
            "summary": "A deep dive into RAG architecture patterns for production deployments",
            "primary_category": "RAG",
            "collected_at": "2026-01-01T10:00:00+08:00",
        },
        {
            "id": "2026-01-02_efgh5678",
            "title": "Vector Databases for RAG",
            "topics": [{"name": "RAG", "confidence": 0.9}, {"name": "Vector DB", "confidence": 0.85}],
            "tags": ["rag", "vector-db", "embeddings"],
            "summary": "Comparing vector database solutions for RAG pipelines",
            "primary_category": "RAG",
            "collected_at": "2026-01-02T10:00:00+08:00",
        },
        {
            "id": "2026-01-03_ijkl9012",
            "title": "Chunking Strategies for RAG",
            "topics": [{"name": "RAG", "confidence": 0.88}],
            "tags": ["rag", "chunking", "document-processing"],
            "summary": "Best practices for document chunking in RAG systems",
            "primary_category": "RAG",
            "collected_at": "2026-01-03T10:00:00+08:00",
        },
        {
            "id": "2026-01-04_mnop3456",
            "title": "Unrelated Article About Cooking",
            "topics": [{"name": "Cooking", "confidence": 0.9}],
            "tags": ["recipes", "food"],
            "summary": "How to make the perfect pasta carbonara",
            "primary_category": "Cooking",
            "collected_at": "2026-01-04T10:00:00+08:00",
        },
        {
            "id": "2026-01-05_qrst7890",
            "title": "Advanced RAG Techniques",
            "topics": [{"name": "RAG", "confidence": 0.92}, {"name": "NLP", "confidence": 0.7}],
            "tags": ["rag", "advanced", "nlp"],
            "summary": "Hybrid retrieval, re-ranking, and query decomposition for RAG",
            "primary_category": "RAG",
            "collected_at": "2026-01-05T10:00:00+08:00",
        },
    ]

    # Write index
    index_file = tmp_path / "index.jsonl"
    with open(index_file, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Write raw text files
    for entry in entries:
        raw_path = raw_dir / f"{entry['id']}.txt"
        raw_path.write_text(f"Full text content for {entry['title']}. " * 50, encoding="utf-8")

    # Patch config
    from sheaf_ai import config
    monkeypatch.setattr(config, "INDEX_FILE", index_file)
    monkeypatch.setattr(config, "RAW_DIR", raw_dir)

    # Patch crystallize module's imports
    from sheaf_ai import crystallize
    monkeypatch.setattr(crystallize, "INDEX_FILE", index_file)
    monkeypatch.setattr(crystallize, "RAW_DIR", raw_dir)

    return entries


# ============================================================
# find_entries_by_topic tests
# ============================================================

class TestFindEntriesByTopic:
    def test_finds_matching_entries(self, sample_entries):
        """Should find entries with matching topic."""
        results = find_entries_by_topic("RAG", min_entries=3)
        assert len(results) >= 4  # 4 RAG entries

    def test_respects_min_entries(self, sample_entries):
        """Should return empty if fewer than min_entries match."""
        results = find_entries_by_topic("Cooking", min_entries=3)
        assert results == []  # Only 1 cooking entry

    def test_respects_limit(self, sample_entries):
        """Should cap results at limit."""
        results = find_entries_by_topic("RAG", min_entries=1, limit=2)
        assert len(results) <= 2

    def test_empty_topic(self, sample_entries):
        """Should return empty for empty topic."""
        results = find_entries_by_topic("")
        assert results == []

    def test_no_match(self, sample_entries):
        """Should return empty for non-existent topic."""
        results = find_entries_by_topic("QuantumComputing", min_entries=1)
        assert results == []

    def test_partial_topic_match(self, sample_entries):
        """Should match partial topic names."""
        results = find_entries_by_topic("vector", min_entries=1, limit=5)
        assert len(results) >= 1


# ============================================================
# crystallize_topic tests (LLM mocked)
# ============================================================

class TestCrystallizeTopic:
    def test_crystallize_returns_cards(self, sample_entries):
        """Should return KnowledgeCard objects from crystallization."""
        mock_response = json.dumps([
            {
                "title": "RAG 需要精细的文档分块策略",
                "claim": "有效的 RAG 系统需要合理的文档分块策略，包括固定大小、语义分块和递归分块等方法",
                "evidence": "Source [1] 讨论了生产级 RAG 架构，[3] 专门研究分块策略，[5] 提出了混合检索方法",
                "tags": ["rag", "chunking", "retrieval"],
                "confidence": 0.88,
                "source_indices": [0, 2, 4],
            },
            {
                "title": "向量数据库是 RAG 的基础设施",
                "claim": "向量数据库选型直接影响 RAG 系统的检索质量和延迟",
                "evidence": "[2] 比较了不同向量数据库在 RAG 管线中的表现",
                "tags": ["rag", "vector-db", "infrastructure"],
                "confidence": 0.82,
                "source_indices": [1],
            },
        ])

        with patch("sheaf_ai.crystallize.chat", return_value=mock_response):
            cards = crystallize_topic("RAG")

        assert len(cards) >= 1
        assert all(isinstance(c, KnowledgeCard) for c in cards)
        # Check evidence tracing
        for card in cards:
            assert card.evidence != ""
            assert card.source_ids  # Must have source IDs

    def test_crystallize_insufficient_entries(self, sample_entries):
        """Should return empty list when too few entries match."""
        result = crystallize_topic("Cooking", min_entries=3)
        assert result == []

    def test_crystallize_llm_failure(self, sample_entries):
        """Should raise LLMError when LLM call fails."""
        with patch("sheaf_ai.crystallize.chat", side_effect=Exception("API Error")):
            from sheaf_ai.exceptions import LLMError
            with pytest.raises(LLMError):
                crystallize_topic("RAG")


# ============================================================
# Response parsing tests
# ============================================================

class TestParseCrystallizedResponse:
    def test_parse_valid_json(self):
        """Should parse valid JSON array response."""
        raw = json.dumps([
            {"title": "Test Card", "claim": "Test claim", "evidence": "Test evidence",
             "tags": ["test"], "confidence": 0.9, "source_indices": [0]},
        ])
        entries = [{"id": "test_123", "title": "Test"}]
        cards = _parse_crystallized_response(raw, entries, "test", "gpt-4o")
        assert len(cards) == 1
        assert cards[0].title == "Test Card"

    def test_parse_markdown_wrapped(self):
        """Should handle markdown code block wrapping."""
        raw = '```json\n[{"title": "Card", "claim": "c", "evidence": "e", "tags": [], "confidence": 0.7, "source_indices": []}]\n```'
        entries = [{"id": "test_123", "title": "Test"}]
        cards = _parse_crystallized_response(raw, entries, "test", "gpt-4o")
        assert len(cards) == 1

    def test_parse_empty_response(self):
        """Should handle empty LLM response."""
        entries = [{"id": "test_123", "title": "Test"}]
        cards = _parse_crystallized_response("[]", entries, "test", "gpt-4o")
        assert cards == []

    def test_parse_malformed_json(self):
        """Should handle malformed JSON gracefully."""
        entries = [{"id": "test_123", "title": "Test"}]
        cards = _parse_crystallized_response("not json at all", entries, "test", "gpt-4o")
        assert cards == []

    def test_source_indices_mapping(self):
        """Should correctly map source_indices to source_ids."""
        raw = json.dumps([
            {"title": "Card", "claim": "c", "evidence": "e", "tags": [],
             "confidence": 0.7, "source_indices": [0, 2]},
        ])
        entries = [
            {"id": "entry_0", "title": "First"},
            {"id": "entry_1", "title": "Second"},
            {"id": "entry_2", "title": "Third"},
        ]
        cards = _parse_crystallized_response(raw, entries, "test", "gpt-4o")
        assert "entry_0" in cards[0].source_ids
        assert "entry_2" in cards[0].source_ids
        assert "entry_1" not in cards[0].source_ids


# ============================================================
# Persistence tests
# ============================================================

def _patch_cards_dir(monkeypatch, tmp_path):
    """Helper to patch both CARDS_DIR and CARDS_STORE_FILE."""
    cards_dir = tmp_path / "cards"
    cards_store = cards_dir / "knowledge_cards.json"
    monkeypatch.setattr("sheaf_ai.crystallize.CARDS_DIR", cards_dir)
    monkeypatch.setattr("sheaf_ai.crystallize.CARDS_STORE_FILE", cards_store)
    return cards_dir


class TestCrystallizeAndSave:
    def test_saves_cards_to_store(self, sample_entries, tmp_path, monkeypatch):
        """Should save crystallized cards to the card store."""
        cards_dir = _patch_cards_dir(monkeypatch, tmp_path)

        mock_response = json.dumps([
            {"title": "RAG Pattern", "claim": "Synthesis", "evidence": "From [0][1]",
             "tags": ["rag"], "confidence": 0.85, "source_indices": [0, 1]},
        ])

        with patch("sheaf_ai.crystallize.chat", return_value=mock_response):
            saved = crystallize_and_save("RAG")

        assert len(saved) >= 1
        assert cards_dir.exists()

        # Verify persistence
        store = _get_card_store()
        listed = store.list_all()
        assert len(listed) >= 1

    def test_deduplicates_cards(self, sample_entries, tmp_path, monkeypatch):
        """Should not save duplicate cards."""
        _patch_cards_dir(monkeypatch, tmp_path)

        mock_response = json.dumps([
            {"title": "RAG Pattern", "claim": "Synthesis", "evidence": "From [0]",
             "tags": ["rag"], "confidence": 0.85, "source_indices": [0]},
        ])

        with patch("sheaf_ai.crystallize.chat", return_value=mock_response):
            saved1 = crystallize_and_save("RAG")
            saved2 = crystallize_and_save("RAG")

        # Second call should deduplicate
        assert len(saved1) >= 1
        assert len(saved2) == 0


# ============================================================
# Retrieval tests
# ============================================================

class TestRetrieval:
    def test_list_all(self, tmp_path, monkeypatch):
        """Should list all crystallized cards."""
        _patch_cards_dir(monkeypatch, tmp_path)
        store = _get_card_store()
        card = KnowledgeCard(title="Test", claim="Test claim", evidence="Evidence")
        store.save(card)

        listed = list_crystallized()
        assert len(listed) >= 1

    def test_list_filtered(self, tmp_path, monkeypatch):
        """Should filter cards by topic."""
        _patch_cards_dir(monkeypatch, tmp_path)
        store = _get_card_store()
        card = KnowledgeCard(
            title="RAG Insight",
            claim="RAG is useful",
            evidence="Evidence",
            provenance={"topic": "RAG"},
        )
        store.save(card)

        listed = list_crystallized(topic="RAG")
        assert len(listed) >= 1

    def test_get_card(self, tmp_path, monkeypatch):
        """Should retrieve a card by ID."""
        _patch_cards_dir(monkeypatch, tmp_path)
        store = _get_card_store()
        card = KnowledgeCard(title="Test", claim="Test claim")
        card_id = store.save(card)

        result = get_card(card_id)
        assert result is not None
        assert result.title == "Test"

    def test_get_nonexistent_card(self, tmp_path, monkeypatch):
        """Should return None for non-existent card."""
        _patch_cards_dir(monkeypatch, tmp_path)

        result = get_card("nonexistent_id")
        assert result is None

    def test_delete_card(self, tmp_path, monkeypatch):
        """Should delete a card."""
        _patch_cards_dir(monkeypatch, tmp_path)
        store = _get_card_store()
        card = KnowledgeCard(title="To Delete", claim="Will be deleted")
        card_id = store.save(card)

        assert delete_card(card_id) is True
        assert get_card(card_id) is None

    def test_delete_nonexistent(self, tmp_path, monkeypatch):
        """Should return False for deleting non-existent card."""
        _patch_cards_dir(monkeypatch, tmp_path)

        assert delete_card("nonexistent_id") is False


# ============================================================
# Stats tests
# ============================================================

class TestGetTopicStats:
    def test_topic_stats(self, tmp_path, monkeypatch):
        """Should return topic counts."""
        _patch_cards_dir(monkeypatch, tmp_path)
        store = _get_card_store()

        for topic in ["RAG", "RAG", "Agent"]:
            card = KnowledgeCard(
                title=f"Card about {topic}",
                claim=f"Claim about {topic}",
                provenance={"topic": topic},
            )
            store.save(card)

        stats = get_topic_stats()
        assert stats.get("RAG", 0) == 2
        assert stats.get("Agent", 0) == 1
