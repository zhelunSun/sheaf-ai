"""Tests for the CardExtractionEngine boundary."""

import json
from unittest.mock import Mock

from sheaf_ai.card_extraction import (
    CardExtractionRequest,
    CardSource,
    LlmCardExtractionEngine,
    parse_card_extraction_response,
)
from sheaf_cards.base import KnowledgeCard


def _sources() -> list[CardSource]:
    return [
        CardSource(
            entry_id="entry_0",
            title="First Source",
            summary="First summary",
            text="First full text",
        ),
        CardSource(
            entry_id="entry_1",
            title="Second Source",
            summary="Second summary",
            text="Second full text",
        ),
        CardSource(
            entry_id="entry_2",
            title="Third Source",
            summary="Third summary",
            text="Third full text",
        ),
    ]


def test_parse_valid_json_array():
    """Valid JSON arrays parse into KnowledgeCard objects."""
    raw = json.dumps([
        {
            "title": "RAG Pattern",
            "claim": "RAG needs retrieval quality controls.",
            "evidence": "Supported by [Source 0]",
            "tags": ["rag"],
            "confidence": 0.9,
            "source_indices": [0],
        }
    ])

    result = parse_card_extraction_response(raw, _sources(), "RAG", "gpt-4o")

    assert result.warnings == []
    assert len(result.cards) == 1
    assert isinstance(result.cards[0], KnowledgeCard)
    assert result.cards[0].title == "RAG Pattern"
    assert result.cards[0].source_ids == ["entry_0"]


def test_parse_markdown_wrapped_json():
    """Markdown code fences are stripped before parsing."""
    raw = (
        '```json\n'
        '[{"title":"Card","claim":"Claim","evidence":"Evidence",'
        '"tags":["test"],"confidence":0.7,"source_indices":[1]}]\n'
        '```'
    )

    result = parse_card_extraction_response(raw, _sources(), "Test", "gpt-4o")

    assert len(result.cards) == 1
    assert result.cards[0].source_ids == ["entry_1"]


def test_parse_single_dict_response():
    """Single object responses are accepted as a one-card result."""
    raw = json.dumps({
        "title": "Single Card",
        "claim": "A single object can still be a valid card.",
        "evidence": "Supported by [Source 0]",
        "tags": ["compat"],
        "confidence": 0.8,
        "source_indices": [0],
    })

    result = parse_card_extraction_response(raw, _sources(), "Compat", "gpt-4o")

    assert len(result.cards) == 1
    assert result.cards[0].title == "Single Card"
    assert result.cards[0].source_ids == ["entry_0"]


def test_malformed_response_returns_warning():
    """Malformed responses fail closed with a warning."""
    result = parse_card_extraction_response("not json at all", _sources(), "Test", "gpt-4o")

    assert result.cards == []
    assert result.warnings
    assert "parse" in result.warnings[0].lower()


def test_source_indices_map_to_source_ids():
    """source_indices are mapped to CardSource.entry_id values."""
    raw = json.dumps([
        {
            "title": "Multi-source insight",
            "claim": "The insight is supported by multiple sources.",
            "evidence": "From [Source 0] and [Source 2]",
            "tags": ["synthesis"],
            "confidence": 0.85,
            "source_indices": [0, 2, 99],
        }
    ])

    result = parse_card_extraction_response(raw, _sources(), "Synthesis", "gpt-4o")

    assert result.cards[0].source_ids == ["entry_0", "entry_2"]


def test_llm_engine_extracts_cards_with_provenance():
    """The default engine calls chat and records extraction provenance."""
    raw = json.dumps([
        {
            "title": "Agent Memory",
            "claim": "Structured cards improve agent recall.",
            "evidence": "Supported by [Source 0]",
            "tags": ["agents"],
            "confidence": 0.88,
            "source_indices": [0],
        }
    ])
    chat = Mock(return_value=raw)
    engine = LlmCardExtractionEngine(chat_func=chat)

    result = engine.extract(
        CardExtractionRequest(
            topic="Agents",
            sources=_sources(),
            max_cards=3,
            model="gpt-4o",
            provider="openai",
        )
    )

    assert len(result.cards) == 1
    card = result.cards[0]
    assert card.provenance["generator"] == "crystallize"
    assert card.provenance["engine"] == "llm_v1"
    assert card.provenance["model"] == "gpt-4o"
    assert card.provenance["topic"] == "Agents"
    assert card.provenance["source_count"] == 3
    chat.assert_called_once()
