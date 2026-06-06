"""Tests for search filter system (Issue #59).

Covers:
  - All 12 operators (eq, ne, in, not_in, gt, gte, lt, lte,
    contains, icontains, wildcard, isnull, exists)
  - Logical operators (AND, OR, NOT)
  - Legacy filter auto-conversion
  - Nested filter expressions
  - Integration with search_fulltext
"""
from __future__ import annotations

import pytest


# ============================================================
# Unit Tests — FilterCondition
# ============================================================

class TestFilterCondition:
    def _make_entry(self, **kwargs):
        return kwargs

    def test_eq(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="status", op="eq", value="active")
        assert c.evaluate({"status": "active"}) is True
        assert c.evaluate({"status": "deleted"}) is False
        assert c.evaluate({}) is False

    def test_ne(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="status", op="ne", value="deleted")
        assert c.evaluate({"status": "active"}) is True
        assert c.evaluate({"status": "deleted"}) is False

    def test_in_with_list_field(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="tags", op="in", value=["AI", "ML"])
        assert c.evaluate({"tags": ["AI", "Python"]}) is True
        assert c.evaluate({"tags": ["Python", "Rust"]}) is False

    def test_in_with_scalar_field(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="importance", op="in", value=["high", "medium"])
        assert c.evaluate({"importance": "high"}) is True
        assert c.evaluate({"importance": "low"}) is False

    def test_not_in(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="tags", op="not_in", value=["spam"])
        assert c.evaluate({"tags": ["AI", "ML"]}) is True
        assert c.evaluate({"tags": ["spam"]}) is False

    def test_gt(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="year", op="gt", value=2023)
        assert c.evaluate({"year": 2024}) is True
        assert c.evaluate({"year": 2023}) is False
        assert c.evaluate({"year": 2022}) is False

    def test_gte(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="year", op="gte", value=2023)
        assert c.evaluate({"year": 2024}) is True
        assert c.evaluate({"year": 2023}) is True
        assert c.evaluate({"year": 2022}) is False

    def test_lt(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="year", op="lt", value=2025)
        assert c.evaluate({"year": 2024}) is True
        assert c.evaluate({"year": 2025}) is False

    def test_lte(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="year", op="lte", value=2025)
        assert c.evaluate({"year": 2025}) is True
        assert c.evaluate({"year": 2026}) is False

    def test_contains(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="title", op="contains", value="agent")
        assert c.evaluate({"title": "Multi-agent systems"}) is True
        assert c.evaluate({"title": "Multi-Agent systems"}) is False  # case sensitive

    def test_icontains(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="title", op="icontains", value="AGENT")
        assert c.evaluate({"title": "Multi-agent systems"}) is True
        assert c.evaluate({"title": "Multi-Agent systems"}) is True

    def test_wildcard(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="title", op="wildcard", value="trans*er")
        assert c.evaluate({"title": "Transformer architecture"}) is True
        assert c.evaluate({"title": "transfer learning"}) is True
        assert c.evaluate({"title": "RNN models"}) is False

    def test_isnull_true(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="entities", op="isnull", value=True)
        assert c.evaluate({}) is True
        assert c.evaluate({"entities": []}) is False

    def test_isnull_false(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="entities", op="isnull", value=False)
        assert c.evaluate({"entities": []}) is True
        assert c.evaluate({}) is False

    def test_exists_true(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="tags", op="exists", value=True)
        assert c.evaluate({"tags": []}) is True
        assert c.evaluate({}) is False

    def test_exists_false(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="tags", op="exists", value=False)
        assert c.evaluate({}) is True
        assert c.evaluate({"tags": []}) is False

    def test_invalid_operator(self):
        from sheaf_ai.filters import FilterCondition, FilterError
        with pytest.raises(FilterError, match="Unsupported operator"):
            FilterCondition(field="x", op="invalid", value=1)

    def test_none_field_value(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="year", op="gt", value=2020)
        assert c.evaluate({}) is False

    def test_dot_notation(self):
        from sheaf_ai.filters import FilterCondition
        c = FilterCondition(field="source.platform", op="eq", value="arxiv")
        assert c.evaluate({"source": {"platform": "arxiv"}}) is True
        assert c.evaluate({"source": {"platform": "github"}}) is False


# ============================================================
# Unit Tests — FilterExpression (AND/OR/NOT)
# ============================================================

class TestFilterExpression:
    def _cond(self, field, op, value):
        from sheaf_ai.filters import FilterCondition
        return FilterCondition(field=field, op=op, value=value)

    def test_and_all_true(self):
        from sheaf_ai.filters import FilterExpression
        expr = FilterExpression("AND", [
            self._cond("tags", "in", ["AI"]),
            self._cond("importance", "eq", "high"),
        ])
        assert expr.evaluate({"tags": ["AI"], "importance": "high"}) is True

    def test_and_one_false(self):
        from sheaf_ai.filters import FilterExpression
        expr = FilterExpression("AND", [
            self._cond("tags", "in", ["AI"]),
            self._cond("importance", "eq", "high"),
        ])
        assert expr.evaluate({"tags": ["AI"], "importance": "low"}) is False

    def test_or_one_true(self):
        from sheaf_ai.filters import FilterExpression
        expr = FilterExpression("OR", [
            self._cond("tags", "in", ["AI"]),
            self._cond("importance", "eq", "high"),
        ])
        assert expr.evaluate({"tags": ["AI"], "importance": "low"}) is True

    def test_or_all_false(self):
        from sheaf_ai.filters import FilterExpression
        expr = FilterExpression("OR", [
            self._cond("tags", "in", ["AI"]),
            self._cond("importance", "eq", "high"),
        ])
        assert expr.evaluate({"tags": ["Rust"], "importance": "low"}) is False

    def test_not(self):
        from sheaf_ai.filters import FilterExpression
        expr = FilterExpression("NOT", [self._cond("status", "eq", "deleted")])
        assert expr.evaluate({"status": "active"}) is True
        assert expr.evaluate({"status": "deleted"}) is False

    def test_not_requires_single_child(self):
        from sheaf_ai.filters import FilterExpression, FilterError
        with pytest.raises(FilterError, match="exactly one"):
            FilterExpression("NOT", [
                self._cond("a", "eq", 1),
                self._cond("b", "eq", 2),
            ])

    def test_invalid_logic(self):
        from sheaf_ai.filters import FilterExpression, FilterError
        with pytest.raises(FilterError, match="Unsupported logic"):
            FilterExpression("XOR", [self._cond("a", "eq", 1)])

    def test_nested_and_or(self):
        """AND [tags in AI, OR [year >= 2024, importance eq high]]"""
        from sheaf_ai.filters import FilterExpression
        expr = FilterExpression("AND", [
            self._cond("tags", "in", ["AI"]),
            FilterExpression("OR", [
                self._cond("year", "gte", 2024),
                self._cond("importance", "eq", "high"),
            ]),
        ])
        # AI + recent year → True
        assert expr.evaluate({"tags": ["AI"], "year": 2024, "importance": "medium"}) is True
        # AI + old but high importance → True
        assert expr.evaluate({"tags": ["AI"], "year": 2023, "importance": "high"}) is True
        # AI + old + low → False
        assert expr.evaluate({"tags": ["AI"], "year": 2023, "importance": "medium"}) is False
        # Not AI → False (short-circuit)
        assert expr.evaluate({"tags": ["Rust"], "year": 2024, "importance": "high"}) is False


# ============================================================
# Unit Tests — parse_filter
# ============================================================

class TestParseFilter:
    def test_parse_condition(self):
        from sheaf_ai.filters import parse_filter, FilterCondition
        result = parse_filter({"field": "tags", "op": "in", "value": ["AI"]})
        assert isinstance(result, FilterCondition)
        assert result.field == "tags"
        assert result.op == "in"

    def test_parse_and(self):
        from sheaf_ai.filters import parse_filter, FilterExpression
        result = parse_filter({
            "AND": [
                {"field": "tags", "op": "in", "value": ["AI"]},
                {"field": "year", "op": "gte", "value": 2024},
            ]
        })
        assert isinstance(result, FilterExpression)
        assert result.logic == "AND"
        assert len(result.children) == 2

    def test_parse_nested(self):
        from sheaf_ai.filters import parse_filter, FilterExpression
        result = parse_filter({
            "AND": [
                {"field": "tags", "op": "in", "value": ["AI"]},
                {"OR": [
                    {"field": "year", "op": "gte", "value": 2024},
                    {"field": "importance", "op": "eq", "value": "high"},
                ]}
            ]
        })
        assert isinstance(result, FilterExpression)
        assert result.logic == "AND"
        # Second child is an OR expression
        assert isinstance(result.children[1], FilterExpression)
        assert result.children[1].logic == "OR"

    def test_parse_legacy_tags(self):
        from sheaf_ai.filters import parse_filter, FilterExpression
        result = parse_filter({"tags": ["AI", "ML"]})
        assert isinstance(result, FilterExpression)
        assert result.logic == "AND"

    def test_parse_legacy_mixed(self):
        from sheaf_ai.filters import parse_filter, FilterExpression
        result = parse_filter({"tags": ["AI"], "importance": "high"})
        assert isinstance(result, FilterExpression)
        assert result.logic == "AND"
        assert len(result.children) == 2

    def test_parse_empty_raises(self):
        from sheaf_ai.filters import parse_filter, FilterError
        with pytest.raises(FilterError):
            parse_filter({})

    def test_parse_not(self):
        from sheaf_ai.filters import parse_filter, FilterExpression
        result = parse_filter({
            "NOT": [{"field": "status", "op": "eq", "value": "deleted"}]
        })
        assert isinstance(result, FilterExpression)
        assert result.logic == "NOT"


# ============================================================
# Unit Tests — apply_filters
# ============================================================

class TestApplyFilters:
    def _entries(self):
        return [
            {"id": "1", "tags": ["AI", "Python"], "importance": "high", "year": 2024},
            {"id": "2", "tags": ["Rust", "Systems"], "importance": "medium", "year": 2023},
            {"id": "3", "tags": ["AI", "ML"], "importance": "high", "year": 2025},
            {"id": "4", "tags": ["Web", "Frontend"], "importance": "low", "year": 2024},
        ]

    def test_filter_by_tags(self):
        from sheaf_ai.filters import apply_filters
        result = apply_filters(self._entries(), {"tags": ["AI"]})
        ids = {e["id"] for e in result}
        assert ids == {"1", "3"}

    def test_filter_by_importance(self):
        from sheaf_ai.filters import apply_filters
        result = apply_filters(self._entries(), {"importance": "high"})
        ids = {e["id"] for e in result}
        assert ids == {"1", "3"}

    def test_filter_and(self):
        from sheaf_ai.filters import apply_filters
        result = apply_filters(self._entries(), {
            "AND": [
                {"field": "tags", "op": "in", "value": ["AI"]},
                {"field": "year", "op": "gte", "value": 2024},
            ]
        })
        ids = {e["id"] for e in result}
        assert ids == {"1", "3"}

    def test_filter_or(self):
        from sheaf_ai.filters import apply_filters
        result = apply_filters(self._entries(), {
            "OR": [
                {"field": "importance", "op": "eq", "value": "high"},
                {"field": "year", "op": "eq", "value": 2023},
            ]
        })
        ids = {e["id"] for e in result}
        assert ids == {"1", "2", "3"}

    def test_filter_not(self):
        from sheaf_ai.filters import apply_filters
        result = apply_filters(self._entries(), {
            "NOT": [{"field": "importance", "op": "eq", "value": "low"}]
        })
        ids = {e["id"] for e in result}
        assert "4" not in ids

    def test_filter_empty_returns_all(self):
        from sheaf_ai.filters import apply_filters
        result = apply_filters(self._entries(), {})
        assert len(result) == 4

    def test_filter_none_returns_all(self):
        from sheaf_ai.filters import apply_filters
        result = apply_filters(self._entries(), None)
        assert len(result) == 4

    def test_filter_contains(self):
        from sheaf_ai.filters import apply_filters
        entries = [
            {"id": "1", "title": "Multi-agent systems"},
            {"id": "2", "title": "Reinforcement learning"},
        ]
        result = apply_filters(entries, {
            "AND": [{"field": "title", "op": "icontains", "value": "agent"}]
        })
        ids = {e["id"] for e in result}
        assert ids == {"1"}


# ============================================================
# Integration Tests — Search with Filters
# ============================================================

class TestSearchWithFilters:
    @pytest.fixture(autouse=True)
    def _setup(self, isolated_data_dir):
        pass

    def _store(self, url, title, text, tags=None, importance="medium"):
        from sheaf_ai.storage import store_article
        fetch = {
            "success": True, "title": title, "text": text,
            "method": "requests", "url": url,
        }
        classify = {
            "topics": [], "tags": tags or [],
            "content_type": "reference", "importance": importance,
        }
        summary = {
            "one_liner": title, "original_title": title,
            "source_author": "Test", "structured": {},
        }
        store_article(url, fetch, classify, summary)

    def test_search_with_tag_filter(self):
        from sheaf_ai.search import search_fulltext

        self._store("https://example.com/ai", "AI Paper", "About AI", tags=["AI", "ML"])
        self._store("https://example.com/rust", "Rust Guide", "About Rust", tags=["Rust"])

        # Search for "paper" with tag filter
        results = search_fulltext("Paper", include_raw=False,
                                  filters={"tags": ["AI"]})
        assert len(results) >= 1
        assert all("AI" in r["entry"].get("tags", []) for r in results)

    def test_search_with_importance_filter(self):
        from sheaf_ai.search import search_fulltext

        self._store("https://example.com/high", "Important Article",
                    "Very important content", importance="high")
        self._store("https://example.com/low", "Minor Article",
                    "Minor content", importance="low")

        results = search_fulltext("Article", include_raw=False,
                                  filters={"importance": "high"})
        assert len(results) >= 1
        assert all(r["entry"].get("importance") == "high" for r in results)

    def test_search_with_no_filter(self):
        from sheaf_ai.search import search_fulltext

        self._store("https://example.com/test", "Test Article", "Some content")

        results = search_fulltext("Test", include_raw=False)
        assert len(results) >= 1

    def test_search_filter_removes_all(self):
        from sheaf_ai.search import search_fulltext

        self._store("https://example.com/test", "Test Article", "Some content")

        # Filter that matches nothing
        results = search_fulltext("Test", include_raw=False,
                                  filters={"importance": "nonexistent"})
        assert len(results) == 0
