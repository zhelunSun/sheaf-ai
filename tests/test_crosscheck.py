"""
Tests for sheaf_crosscheck MCP tool — cross-verification of entry claims.

Covers:
  - Tool schema validation
  - Missing entry_id error
  - Entry not found error
  - Crosscheck with no related entries
  - Crosscheck with seeded related entries
  - _extract_claims helper
  - _get_domain helper
"""
import json
import os
from unittest.mock import patch, MagicMock

import pytest

from sheaf_ai.mcp.verify import (
    _crosscheck_entry,
    _extract_claims,
    _get_domain,
    TOOLS,
    HANDLERS,
)
from sheaf_ai.mcp.protocol import jsonrpc_response


# ============================================================
# Test: Tool schema
# ============================================================

class TestCrosscheckSchema:
    """Validate sheaf_crosscheck tool schema."""

    def test_tool_registered(self):
        names = [t["name"] for t in TOOLS]
        assert "sheaf_crosscheck" in names

    def test_tool_has_required_fields(self):
        tool = TOOLS[0]
        assert "name" in tool
        assert "description" in tool
        assert len(tool["description"]) > 20
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"

    def test_entry_id_is_required(self):
        tool = TOOLS[0]
        assert "entry_id" in tool["inputSchema"].get("required", [])

    def test_handler_registered(self):
        assert "sheaf_crosscheck" in HANDLERS

    def test_optional_params_exist(self):
        props = TOOLS[0]["inputSchema"]["properties"]
        assert "focus" in props
        assert "scope" in props
        assert "top_k" in props


# ============================================================
# Test: Helper functions
# ============================================================

class TestExtractClaims:
    """Test _extract_claims helper."""

    def test_extracts_from_summary(self):
        entry = {"summary": "这是一篇关于AI的文章，介绍了最新进展。"}
        claims = _extract_claims(entry)
        assert len(claims) >= 1
        assert "AI" in claims[0]

    def test_extracts_from_structured(self):
        entry = {
            "summary": "A comprehensive summary of the paper findings",
            "structured_summary": {
                "core_argument": "This paper argues that transformers are scalable.",
                "key_data": "Accuracy improved by 15%.",
            },
        }
        claims = _extract_claims(entry)
        assert len(claims) >= 3  # summary + 2 structured

    def test_empty_entry(self):
        claims = _extract_claims({})
        assert claims == []

    def test_focus_filters_claims(self):
        entry = {
            "summary": "AI is transforming healthcare",
            "structured_summary": {
                "core_argument": "Healthcare AI reduces diagnosis time",
                "key_data": "Finance sector invests heavily",
            },
        }
        claims = _extract_claims(entry, focus="healthcare")
        # Should keep claims mentioning healthcare
        assert any("healthcare" in c.lower() for c in claims)

    def test_focus_no_match_returns_all(self):
        entry = {
            "summary": "AI is transforming everything",
        }
        claims = _extract_claims(entry, focus="quantum computing")
        # Focus not in any claim → prepends focus as a claim, keeps all
        assert any("quantum computing" in c.lower() for c in claims)

    def test_claims_capped_at_six(self):
        entry = {
            "summary": "Summary text",
            "structured_summary": {
                "core_argument": "A" * 20,
                "key_data": "B" * 20,
                "action_items": ["C" * 20, "D" * 20, "E" * 20, "F" * 20, "G" * 20],
            },
        }
        claims = _extract_claims(entry)
        assert len(claims) <= 6


class TestGetDomain:
    """Test _get_domain helper."""

    def test_basic_url(self):
        assert _get_domain("https://example.com/path") == "example.com"

    def test_strips_www(self):
        assert _get_domain("https://www.example.com/path") == "example.com"

    def test_empty_url(self):
        assert _get_domain("") == ""

    def test_invalid_url(self):
        assert _get_domain("not-a-url") == ""


# ============================================================
# Test: Crosscheck with isolated data
# ============================================================

class TestCrosscheckWithData:
    """Test crosscheck with seeded entries using isolated data dir."""

    def test_entry_not_found(self, isolated_data_dir):
        result = _crosscheck_entry("nonexistent-id")
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_entry_with_no_related(self, isolated_data_dir):
        """Entry exists but no related entries — should return ❓ status."""
        from sheaf_ai.storage import store_article

        td = {
            "url": "https://example.com/test-article",
            "fetch_result": {"success": True, "title": "Test Article", "text": "A test article about AI.", "method": "manual"},
            "classify_result": {"topics": [{"name": "AI", "confidence": 0.9}], "tags": ["AI", "test"], "content_type": "reference", "importance": "medium"},
            "summary_result": {"one_liner": "This is a test article about AI.", "original_title": "Test Article", "source_author": "", "structured": {"core_argument": "AI is important"}},
        }
        entry_id = store_article(
            td["url"], td["fetch_result"],
            td["classify_result"], td["summary_result"],
        )

        # Mock search to return empty (no related entries)
        with patch("sheaf_ai.mcp.verify.search_fulltext", return_value=[]):
            result = _crosscheck_entry(entry_id)

        assert result["anchor_id"] == entry_id
        assert result["claims_checked"] >= 1
        assert result["overall_confidence"] in ("low", "unknown")
        assert result["related_count"] == 0
        # All claims should be ❓
        for fm in result["fact_matrix"]:
            assert fm["status"] == "❓"

    def test_entry_with_related_entries(self, isolated_data_dir):
        """Entry with related entries — LLM compare is mocked."""
        from sheaf_ai.storage import store_article

        # Store anchor
        anchor_td = {
            "url": "https://arxiv.org/abs/2401.00001",
            "fetch_result": {"success": True, "title": "Deep Learning Breakthrough", "text": "A new approach to deep learning achieves SOTA.", "method": "requests"},
            "classify_result": {"topics": [{"name": "Deep Learning", "confidence": 0.95}], "tags": ["deep learning", "SOTA"], "content_type": "research", "importance": "high"},
            "summary_result": {"one_liner": "New deep learning method beats all baselines.", "original_title": "Deep Learning Breakthrough", "source_author": "Dr. AI", "structured": {"core_argument": "Novel architecture"}},
        }
        anchor_id = store_article(
            anchor_td["url"], anchor_td["fetch_result"],
            anchor_td["classify_result"], anchor_td["summary_result"],
        )

        # Store a related entry (different domain)
        related_td = {
            "url": "https://techcrunch.com/deep-learning-review",
            "fetch_result": {"success": True, "title": "Deep Learning Review 2024", "text": "Review of deep learning methods.", "method": "requests"},
            "classify_result": {"topics": [{"name": "Deep Learning", "confidence": 0.9}], "tags": ["deep learning", "review"], "content_type": "analysis", "importance": "medium"},
            "summary_result": {"one_liner": "Comprehensive review of deep learning.", "original_title": "Deep Learning Review", "source_author": "Tech Writer", "structured": {}},
        }
        store_article(
            related_td["url"], related_td["fetch_result"],
            related_td["classify_result"], related_td["summary_result"],
        )

        # Mock search to return the related entry
        related_entry = {
            "id": "2024-01-02_related1",
            "title": "Deep Learning Review 2024",
            "summary": "Comprehensive review of deep learning methods.",
            "source_tier": "B",
            "url": "https://techcrunch.com/deep-learning-review",
        }
        mock_search_result = [{"entry": related_entry, "score": 5.0, "match_locations": ["title"]}]

        # Mock LLM to return a simple fact matrix
        mock_llm_result = [
            {"claim": "New deep learning method beats all baselines.", "status": "✅", "supporting": ["2024-01-02_related1"], "conflicting": [], "note": "Confirmed"},
        ]

        with patch("sheaf_ai.mcp.verify.search_fulltext", return_value=mock_search_result), \
             patch("sheaf_ai.mcp.verify._llm_compare_claims", return_value=mock_llm_result):
            result = _crosscheck_entry(anchor_id)

        assert result["anchor_id"] == anchor_id
        assert result["related_count"] == 1
        assert result["claims_checked"] >= 1
        assert result["fact_matrix"][0]["status"] == "✅"
        assert result["overall_confidence"] == "high"

    def test_crosscheck_excludes_same_domain(self, isolated_data_dir):
        """Related entries from the same domain should be filtered out."""
        from sheaf_ai.storage import store_article

        # Store anchor with a real summary (>10 chars) so claims can be extracted
        anchor_td = {
            "url": "https://arxiv.org/abs/2401.00001",
            "fetch_result": {"success": True, "title": "Paper A", "text": "Content A about deep learning.", "method": "requests"},
            "classify_result": {"topics": [{"name": "AI", "confidence": 0.9}], "tags": ["AI"], "content_type": "research", "importance": "medium"},
            "summary_result": {"one_liner": "A novel deep learning architecture achieves state-of-the-art results.", "original_title": "Paper A", "source_author": "", "structured": {"core_argument": "Transformers are scalable."}},
        }
        anchor_id = store_article(
            anchor_td["url"], anchor_td["fetch_result"],
            anchor_td["classify_result"], anchor_td["summary_result"],
        )

        # Mock search returning same-domain entries
        same_domain = {"id": "other-1", "title": "Paper B", "summary": "Summary B", "url": "https://arxiv.org/abs/2401.00002"}
        diff_domain = {"id": "other-2", "title": "Blog Post", "summary": "Summary C", "url": "https://blog.example.com/post"}
        mock_results = [
            {"entry": same_domain, "score": 5.0, "match_locations": ["title"]},
            {"entry": diff_domain, "score": 3.0, "match_locations": ["title"]},
        ]

        with patch("sheaf_ai.mcp.verify.search_fulltext", return_value=mock_results), \
             patch("sheaf_ai.mcp.verify._llm_compare_claims", return_value=[]):
            result = _crosscheck_entry(anchor_id)

        # Same-domain arxiv.org entry should be excluded
        assert result["related_count"] == 1  # Only diff_domain


# ============================================================
# Test: MCP handler
# ============================================================

class TestCrosscheckHandler:
    """Test MCP JSON-RPC handler."""

    def test_missing_entry_id_returns_error(self):
        handler = HANDLERS["sheaf_crosscheck"]
        resp = handler(1, {})
        parsed = json.loads(resp)
        assert "error" in parsed

    def test_nonexistent_entry_returns_error(self, isolated_data_dir):
        handler = HANDLERS["sheaf_crosscheck"]
        resp = handler(1, {"entry_id": "nonexistent"})
        parsed = json.loads(resp)
        assert "error" in parsed

    def test_successful_crosscheck(self, isolated_data_dir):
        from sheaf_ai.storage import store_article

        td = {
            "url": "https://example.com/test",
            "fetch_result": {"success": True, "title": "Test", "text": "Test text.", "method": "manual"},
            "classify_result": {"topics": [{"name": "Test", "confidence": 0.9}], "tags": ["test"], "content_type": "reference", "importance": "medium"},
            "summary_result": {"one_liner": "A test.", "original_title": "Test", "source_author": "", "structured": {}},
        }
        entry_id = store_article(td["url"], td["fetch_result"], td["classify_result"], td["summary_result"])

        with patch("sheaf_ai.mcp.verify.search_fulltext", return_value=[]):
            handler = HANDLERS["sheaf_crosscheck"]
            resp = handler(1, {"entry_id": entry_id})

        parsed = json.loads(resp)
        assert "result" in parsed
        content = json.loads(parsed["result"]["content"][0]["text"])
        assert content["anchor_id"] == entry_id
