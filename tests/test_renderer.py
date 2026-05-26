"""
Tests for sheaf_ai.renderer — Configurable card output rendering.

Tests cover:
- CardOutputConfig: defaults, compact(), detailed(), list_view(), apply_field_filter()
- CardRenderer.render(): text, json, detailed formats
- CardRenderer.render_list(): text, json, detailed formats
- render_with_jinja2(): custom template rendering
- Edge cases: empty cards, missing fields, special characters
"""
import json
import pytest

from sheaf_ai.renderer import (
    CardOutputConfig,
    CardRenderer,
    render_with_jinja2,
    _confidence_bar,
)
from sheaf_cards.base import KnowledgeCard


def _has_jinja2() -> bool:
    """Check if Jinja2 is available and functional for import."""
    try:
        from jinja2 import Template  # noqa: F401
        return True
    except (ImportError, Exception):
        return False


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_card():
    """A well-formed sample card."""
    return KnowledgeCard(
        card_id="card_abc123",
        title="RAG 系统分块策略优化",
        claim="有效的 RAG 系统需要合理文档分块策略，包括固定大小、语义分块和递归分块。",
        evidence="[Source 0] 讨论了生产级 RAG 架构，[Source 1] 专门研究分块策略。",
        tags=["rag", "chunking", "retrieval"],
        confidence=0.85,
        source_ids=["entry_001", "entry_002"],
        provenance={
            "generator": "crystallize",
            "model": "deepseek-v3",
            "topic": "RAG",
            "source_count": 5,
        },
    )


@pytest.fixture
def empty_card():
    """A card with minimal fields."""
    return KnowledgeCard(
        title="",
        claim="",
        evidence="",
        tags=[],
        confidence=0.0,
    )


@pytest.fixture
def card_list():
    """A list of sample cards."""
    return [
        KnowledgeCard(
            card_id="card_001",
            title="向量数据库选型",
            claim="向量数据库选型直接影响 RAG 系统的检索质量。",
            evidence="[Source 1] 比较了不同向量数据库表现。",
            tags=["vector-db", "rag"],
            confidence=0.82,
            provenance={"topic": "RAG"},
        ),
        KnowledgeCard(
            card_id="card_002",
            title="LLM Agent 编排模式",
            claim="多 Agent 系统需要明确的编排模式来确保可靠性。",
            evidence="[Source 2] 分析了不同编排模式的优劣。",
            tags=["agent", "orchestration"],
            confidence=0.78,
            provenance={"topic": "Agent"},
        ),
        KnowledgeCard(
            card_id="card_003",
            title="遥感基础模型发展趋势",
            claim="遥感基础模型正从监督学习向自监督预训练范式转变。",
            evidence="[Source 3] 综述了遥感基础模型的发展历程。",
            tags=["remote-sensing", "foundation-model"],
            confidence=0.91,
            provenance={"topic": "遥感"},
        ),
    ]


# ============================================================
# CardOutputConfig tests
# ============================================================

class TestCardOutputConfig:
    def test_defaults(self):
        """Default config should enable core display fields."""
        config = CardOutputConfig()
        assert config.include_title is True
        assert config.include_claim is True
        assert config.include_evidence is True
        assert config.include_tags is True
        assert config.include_confidence is True
        # Hidden by default
        assert config.include_id is False
        assert config.include_associations is False
        assert config.include_source_ids is False
        assert config.include_provenance is False

    def test_compact_mode(self):
        """Compact mode should show only title + claim."""
        config = CardOutputConfig.compact()
        assert config.include_title is True
        assert config.include_claim is True
        assert config.include_evidence is False
        assert config.include_tags is False
        assert config.include_confidence is False

    def test_detailed_mode(self):
        """Detailed mode should show all fields."""
        config = CardOutputConfig.detailed()
        assert config.include_id is True
        assert config.include_title is True
        assert config.include_claim is True
        assert config.include_evidence is True
        assert config.include_associations is True
        assert config.include_source_ids is True
        assert config.include_provenance is True
        assert config.include_timestamps is True

    def test_list_view(self):
        """List view should show title + claim + confidence."""
        config = CardOutputConfig.list_view()
        assert config.include_claim is True
        assert config.include_evidence is False
        assert config.include_confidence is True

    def test_list_view_compact(self):
        """Compact list view should truncate claims shorter."""
        config = CardOutputConfig.list_view(compact=True)
        assert config.max_claim_length == 80

    def test_apply_field_filter_include(self):
        """Field include filter should enable only requested fields."""
        config = CardOutputConfig.compact()
        config.apply_field_filter(fields_include=["confidence", "tags"])
        assert config.include_confidence is True
        assert config.include_tags is True
        assert config.include_title is False  # Reset by filter
        assert config.include_claim is False

    def test_apply_field_filter_exclude(self):
        """Field exclude filter should disable specific fields."""
        config = CardOutputConfig()
        config.apply_field_filter(fields_exclude=["evidence"])
        assert config.include_evidence is False
        assert config.include_title is True  # Unchanged

    def test_enabled_fields(self):
        """Should return list of enabled field names."""
        config = CardOutputConfig.compact()  # Only title + claim
        enabled = config.enabled_fields()
        assert "title" in enabled
        assert "claim" in enabled
        assert "evidence" not in enabled

    def test_max_claim_length_truncation(self):
        """Should truncate claim at configured length."""
        config = CardOutputConfig(max_claim_length=20, include_evidence=False,
                                   include_tags=False, include_confidence=False)
        renderer = CardRenderer(config)
        card = KnowledgeCard(
            title="Test",
            claim="A very long claim that should be truncated at twenty characters",
        )
        output = renderer.render(card, format="text")
        assert "A very long claim th..." in output
        assert "twenty characters" not in output


# ============================================================
# CardRenderer.render() tests
# ============================================================

class TestCardRendererRender:
    def test_render_text_default(self, sample_card):
        """Default text render should show core fields."""
        renderer = CardRenderer()
        output = renderer.render(sample_card, format="text")
        assert "Title: RAG 系统分块策略优化" in output
        assert "Claim:" in output
        assert "Evidence:" in output
        assert "Tags: rag, chunking, retrieval" in output
        assert "Confidence: 85%" in output
        # Hidden by default
        assert "ID:" not in output
        assert "card_abc123" not in output

    def test_render_text_with_id(self, sample_card):
        """Should show ID when config includes it."""
        config = CardOutputConfig(include_id=True)
        renderer = CardRenderer(config)
        output = renderer.render(sample_card, format="text")
        assert "ID: card_abc123" in output

    def test_render_json(self, sample_card):
        """JSON render should be valid JSON with all details."""
        renderer = CardRenderer(CardOutputConfig.detailed())
        output = renderer.render(sample_card, format="json")
        parsed = json.loads(output)
        assert parsed["id"] == "card_abc123"
        assert parsed["title"] == "RAG 系统分块策略优化"
        assert parsed["confidence"] == 0.85
        assert "rag" in parsed["tags"]
        assert "source_ids" in parsed

    def test_render_json_compact(self, sample_card):
        """JSON with compact config should omit hidden fields."""
        renderer = CardRenderer(CardOutputConfig.compact())
        output = renderer.render(sample_card, format="json")
        parsed = json.loads(output)
        assert "title" in parsed
        assert "claim" in parsed
        assert "tags" not in parsed
        assert "confidence" not in parsed

    def test_render_detailed(self, sample_card):
        """Detailed render should show all fields with formatting."""
        config = CardOutputConfig(include_id=True, include_source_ids=True,
                                   include_provenance=True, include_timestamps=True)
        renderer = CardRenderer(config)
        output = renderer.render(sample_card, format="detailed")
        assert "Title:" in output
        assert "ID:" in output
        assert "Claim:" in output
        assert "Evidence:" in output
        assert "Tags:" in output
        assert "Confidence:" in output
        assert "Sources:" in output
        assert "Provenance:" in output
        assert "Created:" in output
        # Should have confidence bar
        assert "█" in output
        assert "░" in output

    def test_render_empty_card(self, empty_card):
        """Should handle cards with empty fields gracefully."""
        renderer = CardRenderer()
        output = renderer.render(empty_card, format="text")
        assert "Title:" in output
        assert "Claim:" in output
        assert "Confidence: 0%" in output

    def test_render_special_characters(self):
        """Should handle special characters in card fields."""
        card = KnowledgeCard(
            title="Test with \"quotes\" & <tags>",
            claim="Claim with 中文 and emoji 🎉",
            tags=["tag<1>", "tag&2"],
        )
        renderer = CardRenderer()
        output = renderer.render(card, format="text")
        assert "quotes" in output
        assert "中文" in output
        assert "🎉" in output


# ============================================================
# CardRenderer.render_list() tests
# ============================================================

class TestCardRendererRenderList:
    def test_render_list_text(self, card_list):
        """Should render card list in text format."""
        renderer = CardRenderer()
        output = renderer.render_list(card_list, format="text")
        assert "向量数据库选型" in output
        assert "LLM Agent 编排模式" in output
        assert "Total: 3 cards" in output

    def test_render_list_text_with_title(self, card_list):
        """Should include title header when provided."""
        renderer = CardRenderer()
        output = renderer.render_list(card_list, format="text",
                                       title="My Cards")
        assert "=== My Cards (3 cards) ===" in output

    def test_render_list_json(self, card_list):
        """Should render card list as valid JSON."""
        renderer = CardRenderer(CardOutputConfig.detailed())
        output = renderer.render_list(card_list, format="json",
                                       title="Test Cards")
        parsed = json.loads(output)
        assert parsed["total"] == 3
        assert len(parsed["cards"]) == 3
        assert parsed["cards"][0]["id"] == "card_001"
        assert parsed["_title"] == "Test Cards"

    def test_render_list_detailed(self, card_list):
        """Detailed list should show full detail for each card."""
        config = CardOutputConfig(include_id=True)
        renderer = CardRenderer(config)
        output = renderer.render_list(card_list, format="detailed")
        assert "card_001" in output
        assert "card_002" in output
        assert "card_003" in output
        assert "Total: 3 cards" in output

    def test_render_list_empty(self):
        """Should handle empty card list."""
        renderer = CardRenderer()
        output = renderer.render_list([], format="text")
        assert "Total: 0 cards" in output

    def test_render_list_empty_json(self):
        """Should handle empty list in JSON format."""
        renderer = CardRenderer()
        output = renderer.render_list([], format="json")
        parsed = json.loads(output)
        assert parsed["total"] == 0
        assert parsed["cards"] == []

    def test_render_list_truncated_claim(self, card_list):
        """Should truncate claims in list views."""
        config = CardOutputConfig.list_view(compact=True)  # max_claim_length=80
        config.include_confidence = True
        renderer = CardRenderer(config)
        output = renderer.render_list(card_list, format="text")
        # Check that at least one claim is in the output
        assert "向量数据库选型" in output


# ============================================================
# render_with_jinja2 tests
# ============================================================

class TestRenderWithJinja2:
    @pytest.mark.skipif(
        not _has_jinja2(),
        reason="Jinja2 not installed (optional dependency)"
    )
    def test_basic_template(self, sample_card):
        """Should render a basic Jinja2 template."""
        template = "Card: {{ card.title }} — {{ card.claim[:50] }}..."
        result = render_with_jinja2(sample_card, template)
        assert "Card: RAG 系统分块策略优化" in result

    @pytest.mark.skipif(
        not _has_jinja2(),
        reason="Jinja2 not installed (optional dependency)"
    )
    def test_confidence_formatting(self, sample_card):
        """Should format confidence as percentage."""
        template = "Confidence: {{ '%.0f' | format(card.confidence * 100) }}%"
        result = render_with_jinja2(sample_card, template)
        assert "Confidence: 85%" in result

    @pytest.mark.skipif(
        not _has_jinja2(),
        reason="Jinja2 not installed (optional dependency)"
    )
    def test_cond_loop(self, sample_card):
        """Should handle Jinja2 conditionals and loops."""
        template = """{{ card.title }}
{% if card.tags %}Tags: {{ card.tags | join(', ') }}{% endif %}
{% for sid in card.source_ids %}- {{ sid }}
{% endfor %}"""
        result = render_with_jinja2(sample_card, template)
        assert "RAG 系统分块策略优化" in result
        assert "Tags: rag, chunking, retrieval" in result
        assert "- entry_001" in result
        assert "- entry_002" in result

    def test_jinja2_not_installed(self, sample_card, monkeypatch):
        """Should raise ImportError when Jinja2 is not installed."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "jinja2" or name.startswith("jinja2."):
                raise ImportError("No module named 'jinja2'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        with pytest.raises(ImportError, match="Jinja2 is required"):
            render_with_jinja2(sample_card, "{{ card.title }}")


# ============================================================
# _confidence_bar tests
# ============================================================

class TestConfidenceBar:
    def test_full_confidence(self):
        """1.0 should show full bar."""
        bar = _confidence_bar(1.0, width=5)
        assert bar == "[█████]"

    def test_zero_confidence(self):
        """0.0 should show empty bar."""
        bar = _confidence_bar(0.0, width=5)
        assert bar == "[░░░░░]"

    def test_partial_confidence(self):
        """0.5 should show half-filled bar."""
        bar = _confidence_bar(0.5, width=10)
        assert bar.count("█") == 5
        assert bar.count("░") == 5

    def test_rounding(self):
        """Should round correctly."""
        bar = _confidence_bar(0.33, width=3)
        # 0.33 * 3 = 0.99 → round → 1
        assert bar.count("█") == 1
        assert bar.count("░") == 2

    def test_default_width(self):
        """Default width should be 10."""
        bar = _confidence_bar(0.85)
        assert bar.count("█") == 8  # 0.85*10=8.5→8
        assert bar.count("░") == 2


# ============================================================
# CardOutputConfig.apply_field_filter edge cases
# ============================================================

class TestFieldFilterEdgeCases:
    def test_empty_include_resets_nothing(self):
        """Empty include list should not modify config."""
        config = CardOutputConfig()
        config.apply_field_filter(fields_include=[])
        assert config.include_title is True

    def test_none_filters_do_nothing(self):
        """None filters should be a no-op."""
        config = CardOutputConfig()
        config.apply_field_filter()
        assert config.include_title is True
        assert config.include_claim is True

    def test_invalid_field_names_ignored(self):
        """Invalid field names should be silently ignored."""
        config = CardOutputConfig()
        config.apply_field_filter(fields_include=["title", "nonexistent_field"])
        assert config.include_title is True
        assert config.include_evidence is False

    def test_exclude_removes_from_enabled(self):
        """Exclude should remove from enabled fields."""
        config = CardOutputConfig()
        config.apply_field_filter(fields_exclude=["title", "claim"])
        assert config.include_title is False
        assert config.include_claim is False
        assert config.include_evidence is True  # Unchanged
