"""Fail-closed validation for untrusted crystallization model output."""

from __future__ import annotations

import json

import pytest

from sheaf_ai.card_extraction import CardSource, parse_card_extraction_response


@pytest.fixture
def sources() -> list[CardSource]:
    return [
        CardSource(
            entry_id=f"entry-{index}",
            title=f"Source {index}",
            summary=f"Summary {index}",
            text=f"Evidence text {index}",
        )
        for index in range(2)
    ]


def _item(**overrides) -> dict:
    item = {
        "title": "Grounded claim",
        "claim": "The claim is scoped to the supplied evidence.",
        "evidence": "Supported by [Source 0].",
        "tags": ["evaluation"],
        "confidence": 0.8,
        "source_indices": [0],
    }
    item.update(overrides)
    return item


@pytest.mark.parametrize("confidence", [9.0, -0.1, 0.49, "0.8", True, None])
def test_rejects_invalid_raw_confidence(confidence, sources):
    result = parse_card_extraction_response(
        json.dumps([_item(confidence=confidence)]),
        sources,
        "evaluation",
        "frozen-model",
    )

    assert result.cards == []
    assert any("confidence" in warning for warning in result.warnings)


def test_rejects_non_finite_raw_confidence(sources):
    # Python's JSON decoder accepts NaN by default, so the parser must reject it.
    raw = json.dumps([_item()]).replace("0.8", "NaN")

    result = parse_card_extraction_response(
        raw,
        sources,
        "evaluation",
        "frozen-model",
    )

    assert result.cards == []
    assert any("finite" in warning for warning in result.warnings)


def test_rejects_confidence_that_overflows_float_conversion(sources):
    result = parse_card_extraction_response(
        json.dumps([_item(confidence=10**400)]),
        sources,
        "evaluation",
        "frozen-model",
    )

    assert result.cards == []
    assert any("representable" in warning for warning in result.warnings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", 7),
        ("claim", ["not", "text"]),
        ("evidence", {"text": "not text"}),
        ("tags", "not-a-list"),
        ("tags", ["valid", 3]),
        ("source_indices", [True]),
        ("source_ids", [3]),
        ("related_to", "0"),
        ("related_to", [False]),
        ("related_to", [0.5]),
    ],
)
def test_rejects_wrong_raw_field_types(field, value, sources):
    result = parse_card_extraction_response(
        json.dumps([_item(**{field: value})]),
        sources,
        "evaluation",
        "frozen-model",
    )

    assert result.cards == []
    assert any(field in warning for warning in result.warnings)


def test_rejects_explicit_citation_outside_source_bundle(sources):
    result = parse_card_extraction_response(
        json.dumps([_item(evidence="Invented support [Source 9].")]),
        sources,
        "evaluation",
        "frozen-model",
    )

    assert result.cards == []
    assert any("citation" in warning for warning in result.warnings)


def test_rejects_explicit_citation_missing_from_declared_sources(sources):
    result = parse_card_extraction_response(
        json.dumps([_item(evidence="Claims support from [Source 1].")]),
        sources,
        "evaluation",
        "frozen-model",
    )

    assert result.cards == []
    assert any("declared sources" in warning for warning in result.warnings)


def test_rejects_missing_explicit_citation(sources):
    result = parse_card_extraction_response(
        json.dumps([_item(evidence="No citation marker is present.")]),
        sources,
        "evaluation",
        "frozen-model",
    )

    assert result.cards == []
    assert any("explicit" in warning for warning in result.warnings)


def test_rejects_declared_source_without_matching_citation(sources):
    result = parse_card_extraction_response(
        json.dumps([_item(source_indices=[0, 1])]),
        sources,
        "evaluation",
        "frozen-model",
    )

    assert result.cards == []
    assert any("exactly match" in warning for warning in result.warnings)


def test_accepts_finite_confidence_and_matching_explicit_citation(sources):
    result = parse_card_extraction_response(
        json.dumps([_item()]),
        sources,
        "evaluation",
        "frozen-model",
    )

    assert len(result.cards) == 1
    assert result.cards[0].confidence == 0.8
    assert result.cards[0].source_ids == ["entry-0"]


def test_related_indices_keep_raw_response_identity_when_an_item_is_rejected(sources):
    raw = [
        _item(title="First", related_to=[2]),
        _item(title="Rejected", confidence=3),
        _item(title="Third", related_to=[0]),
    ]

    result = parse_card_extraction_response(
        json.dumps(raw),
        sources,
        "evaluation",
        "frozen-model",
    )

    assert [card.title for card in result.cards] == ["First", "Third"]
    assert result.cards[0].associations == [result.cards[1].card_id]
    assert result.cards[1].associations == [result.cards[0].card_id]
