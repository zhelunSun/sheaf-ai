"""Tests for UUID→Integer anti-hallucination mapper (Issue #56)."""

import json
from unittest.mock import Mock

from sheaf_ai.card_extraction import (
    CardExtractionRequest,
    CardSource,
    LlmCardExtractionEngine,
    UUIDMapper,
    build_extraction_prompt,
    parse_card_extraction_response,
)


# ============================================================
# Helpers
# ============================================================

def _make_sources(count: int = 3) -> list[CardSource]:
    """Create N test sources with long, realistic entry IDs."""
    return [
        CardSource(
            entry_id=f"2026-05-30_abc{i:04d}def",
            title=f"Source {i}",
            summary=f"Summary for source {i}",
            text=f"Full text of source {i}" * 10,
        )
        for i in range(count)
    ]


# ============================================================
# UUIDMapper unit tests
# ============================================================

class TestUUIDMapper:
    """Core UUIDMapper unit tests."""

    def test_register_returns_sequential_aliases(self):
        m = UUIDMapper()
        a0 = m.register("real_id_a")
        a1 = m.register("real_id_b")
        assert a0 == "0"
        assert a1 == "1"

    def test_register_idempotent(self):
        m = UUIDMapper()
        m.register("id_x")
        alias = m.register("id_x")
        assert alias == "0"
        assert m.size == 1

    def test_encode_decode_roundtrip(self):
        m = UUIDMapper()
        m.register("entry_abc")
        m.register("entry_def")
        assert m.decode(m.encode("entry_abc")) == "entry_abc"
        assert m.decode(m.encode("entry_def")) == "entry_def"

    def test_decode_unknown_returns_alias_verbatim(self):
        """Hallucinated alias returns as-is (graceful degradation)."""
        m = UUIDMapper()
        m.register("real_0")
        assert m.decode("999") == "999"  # not in map

    def test_decode_list(self):
        m = UUIDMapper()
        m.register("real_a")
        m.register("real_b")
        result = m.decode_list(["0", "1", "hallucinated"])
        assert result == ["real_a", "real_b", "hallucinated"]

    def test_build_from_sources(self):
        sources = _make_sources(5)
        m = UUIDMapper()
        m.build_from_sources(sources)
        assert m.size == 5
        for i, src in enumerate(sources):
            assert m.encode(src.entry_id) == str(i)

    def test_aliased_sources_preserves_fields(self):
        sources = _make_sources(2)
        m = UUIDMapper()
        m.build_from_sources(sources)
        aliased = m.aliased_sources(sources)
        assert aliased[0].entry_id == "0"
        assert aliased[0].title == sources[0].title
        assert aliased[1].entry_id == "1"
        assert aliased[1].summary == sources[1].summary

    def test_aliased_sources_does_not_mutate_original(self):
        sources = _make_sources(2)
        original_ids = [s.entry_id for s in sources]
        m = UUIDMapper()
        m.build_from_sources(sources)
        m.aliased_sources(sources)
        # Original sources should be unchanged
        assert [s.entry_id for s in sources] == original_ids

    def test_empty_mapper(self):
        m = UUIDMapper()
        assert m.size == 0
        assert m.encode("anything") == "anything"
        assert m.decode("anything") == "anything"
        assert m.decode_list([]) == []


# ============================================================
# Integration: prompt uses aliases
# ============================================================

class TestPromptAliasing:
    """Verify build_extraction_prompt uses aliased IDs."""

    def test_prompt_contains_short_ids(self):
        sources = _make_sources(3)
        m = UUIDMapper()
        m.build_from_sources(sources)
        aliased = m.aliased_sources(sources)
        req = CardExtractionRequest(topic="Test", sources=sources, max_cards=5)
        prompt = build_extraction_prompt(req, _sources=aliased)

        # Prompt should contain short IDs
        assert "ID=0" in prompt
        assert "ID=1" in prompt
        assert "ID=2" in prompt
        # Prompt should NOT contain real IDs
        for src in sources:
            assert src.entry_id not in prompt

    def test_prompt_without_mapper_uses_real_ids(self):
        sources = _make_sources(2)
        req = CardExtractionRequest(topic="Test", sources=sources, max_cards=5)
        prompt = build_extraction_prompt(req)

        for src in sources:
            assert src.entry_id in prompt


# ============================================================
# Integration: parse_card_extraction_response with mapper
# ============================================================

class TestParseWithMapper:
    """Verify parse resolves aliased source_ids back to real IDs."""

    def test_source_ids_decoded_via_mapper(self):
        sources = _make_sources(3)
        m = UUIDMapper()
        m.build_from_sources(sources)

        raw = json.dumps([{
            "title": "Cross-source insight",
            "claim": "An important pattern.",
            "evidence": "Seen in [Source 0] and [Source 2]",
            "tags": ["test"],
            "confidence": 0.85,
            "source_indices": [0, 2],
            "source_ids": ["0", "2"],
        }])

        result = parse_card_extraction_response(
            raw, sources, "Test", "gpt-4o", uuid_mapper=m,
        )
        assert len(result.cards) == 1
        card = result.cards[0]
        # source_ids should be the REAL entry IDs, not aliases
        assert sources[0].entry_id in card.source_ids
        assert sources[2].entry_id in card.source_ids

    def test_source_ids_without_mapper_falls_back_to_indices(self):
        sources = _make_sources(2)
        raw = json.dumps([{
            "title": "Fallback test",
            "claim": "Uses index-based resolution.",
            "evidence": "From [Source 1]",
            "tags": ["test"],
            "confidence": 0.7,
            "source_indices": [1],
        }])

        result = parse_card_extraction_response(
            raw, sources, "Test", "gpt-4o",
        )
        assert result.cards[0].source_ids == [sources[1].entry_id]

    def test_hallucinated_source_id_is_kept_as_is(self):
        """If LLM returns a source_id not in the mapper, it passes through."""
        sources = _make_sources(2)
        m = UUIDMapper()
        m.build_from_sources(sources)

        raw = json.dumps([{
            "title": "Hallucination test",
            "claim": "Some claim.",
            "evidence": "Supported by [Source 0]",
            "tags": ["test"],
            "confidence": 0.8,
            "source_indices": [0],
            "source_ids": ["0", "FAKE_999"],
        }])

        result = parse_card_extraction_response(
            raw, sources, "Test", "gpt-4o", uuid_mapper=m,
        )
        card = result.cards[0]
        # "0" decodes to real ID, "FAKE_999" passes through
        assert sources[0].entry_id in card.source_ids
        assert "FAKE_999" in card.source_ids

    def test_empty_source_ids_with_mapper_falls_back(self):
        sources = _make_sources(3)
        m = UUIDMapper()
        m.build_from_sources(sources)

        raw = json.dumps([{
            "title": "No source_ids field",
            "claim": "Missing source_ids.",
            "evidence": "From [Source 0]",
            "tags": ["test"],
            "confidence": 0.7,
            "source_indices": [0, 1],
        }])

        result = parse_card_extraction_response(
            raw, sources, "Test", "gpt-4o", uuid_mapper=m,
        )
        # Falls back to index-based resolution
        assert sources[0].entry_id in result.cards[0].source_ids
        assert sources[1].entry_id in result.cards[0].source_ids


# ============================================================
# Integration: full LlmCardExtractionEngine with UUID mapping
# ============================================================

class TestEngineWithMapping:
    """End-to-end test: engine → mapper → prompt → parse → real IDs."""

    def test_engine_produces_cards_with_real_ids(self):
        sources = _make_sources(3)
        raw = json.dumps([{
            "title": "Mapped insight",
            "claim": "IDs are correctly decoded.",
            "evidence": "Seen across [Source 0], [Source 1], [Source 2]",
            "tags": ["mapping"],
            "confidence": 0.9,
            "source_indices": [0, 1, 2],
            "source_ids": ["0", "1", "2"],
        }])

        chat_fn = Mock(return_value=raw)
        engine = LlmCardExtractionEngine(chat_func=chat_fn)

        result = engine.extract(
            CardExtractionRequest(
                topic="Mapping",
                sources=sources,
                max_cards=5,
                model="test-model",
            )
        )

        assert len(result.cards) == 1
        card = result.cards[0]
        # source_ids should contain REAL entry IDs
        for src in sources:
            assert src.entry_id in card.source_ids

    def test_engine_prompt_uses_short_ids(self):
        """Verify the prompt sent to LLM uses short IDs, not real ones."""
        sources = _make_sources(3)
        raw = json.dumps([{
            "title": "Prompt check",
            "claim": "Prompt has short IDs.",
            "evidence": "From [Source 0]",
            "tags": ["test"],
            "confidence": 0.8,
            "source_indices": [0],
            "source_ids": ["0"],
        }])

        captured_prompt = ""

        def capture_chat(**kwargs):
            nonlocal captured_prompt
            captured_prompt = kwargs.get("prompt", "")
            return raw

        engine = LlmCardExtractionEngine(chat_func=capture_chat)
        engine.extract(
            CardExtractionRequest(
                topic="PromptTest",
                sources=sources,
                max_cards=5,
                model="test",
            )
        )

        # Prompt should use short IDs
        assert "ID=0" in captured_prompt
        assert "ID=1" in captured_prompt
        assert "ID=2" in captured_prompt
        # Prompt should NOT contain real entry IDs
        for src in sources:
            assert src.entry_id not in captured_prompt

    def test_backward_compat_no_source_ids_field(self):
        """Cards that don't include source_ids still work via indices."""
        sources = _make_sources(2)
        raw = json.dumps([{
            "title": "Legacy format",
            "claim": "Works without source_ids.",
            "evidence": "From [Source 1]",
            "tags": ["legacy"],
            "confidence": 0.7,
            "source_indices": [1],
        }])

        engine = LlmCardExtractionEngine(chat_func=Mock(return_value=raw))
        result = engine.extract(
            CardExtractionRequest(topic="Legacy", sources=sources, max_cards=5),
        )

        assert len(result.cards) == 1
        assert sources[1].entry_id in result.cards[0].source_ids
