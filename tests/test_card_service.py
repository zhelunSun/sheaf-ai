"""Tests for the card application service boundary."""

from unittest.mock import patch

from sheaf_ai.card_service import (
    card_to_public_dict,
    crystallize_cards,
    delete_card_by_id,
    get_card_detail,
    list_cards,
    search_cards_semantic,
)
from sheaf_cards.base import KnowledgeCard


def _card() -> KnowledgeCard:
    return KnowledgeCard(
        card_id="card_123",
        title="Service Card",
        claim="Card service stabilizes adapter output.",
        evidence="Evidence stays a string.",
        tags=["service"],
        confidence=0.82,
        source_ids=["entry_1"],
        provenance={"topic": "Architecture"},
    )


def test_card_to_public_dict_has_stable_shape():
    data = card_to_public_dict(_card())

    assert data["id"] == "card_123"
    assert data["card_id"] == "card_123"
    assert data["title"] == "Service Card"
    assert isinstance(data["evidence"], str)
    assert data["source_ids"] == ["entry_1"]
    assert data["provenance"]["topic"] == "Architecture"


def test_crystallize_cards_delegates_to_crystallize():
    card = _card()
    with patch(
        "sheaf_ai.card_service.crystallize.crystallize_and_save",
        return_value=[card],
    ) as mock_crystallize:
        result = crystallize_cards("Architecture", max_cards=2, auto_embed=False)

    assert result == [card]
    mock_crystallize.assert_called_once_with(
        topic="Architecture",
        min_entries=3,
        max_entries=10,
        max_cards=2,
        model=None,
        provider=None,
        auto_embed=False,
    )


def test_list_get_delete_card_delegates_to_crystallize():
    card = _card()
    with patch("sheaf_ai.card_service.crystallize.list_crystallized", return_value=[card]):
        assert list_cards(topic="Architecture") == [card]

    with patch("sheaf_ai.card_service.crystallize.get_card", return_value=card):
        assert get_card_detail("card_123") == card

    with patch("sheaf_ai.card_service.crystallize.get_card", return_value=None):
        assert get_card_detail("missing") is None

    with patch("sheaf_ai.card_service.crystallize.delete_card", return_value=True):
        assert delete_card_by_id("card_123") is True


def test_search_cards_semantic_returns_json_safe_results():
    card = _card()
    with patch(
        "sheaf_ai.card_service.crystallize.semantic_search",
        return_value=[{"score": 0.91, "card": card}],
    ):
        results = search_cards_semantic("service boundary", top_k=3)

    assert results == [{
        "score": 0.91,
        "card": card_to_public_dict(card),
    }]
