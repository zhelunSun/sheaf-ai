"""
Sheaf Search Filters — structured filtering with AND/OR/NOT logic.

Issue #59: Advanced search filter operators inspired by Mem0.
Supports 12 operators + nested logical combinations.

Design decisions:
  - Filters are applied post-search (not during indexing)
  - Old format {"tags": ["AI"]} auto-converts to new format
  - Pure Python, no dependencies
  - Invalid operators/fields return clear errors
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# ============================================================
# Filter Exceptions
# ============================================================

class FilterError(Exception):
    """Raised for invalid filter syntax or unsupported operators."""
    pass


# ============================================================
# Filter Condition Model
# ============================================================

@dataclass
class FilterCondition:
    """A single filter condition: field op value."""
    field: str
    op: str
    value: Any

    # Supported operators
    VALID_OPS = {
        "eq", "ne", "in", "not_in",
        "gt", "gte", "lt", "lte",
        "contains", "icontains", "wildcard",
        "isnull", "exists",
    }

    def __post_init__(self):
        if self.op not in self.VALID_OPS:
            raise FilterError(
                f"Unsupported operator: '{self.op}'. "
                f"Valid operators: {sorted(self.VALID_OPS)}"
            )

    def evaluate(self, entry: dict) -> bool:
        """Evaluate this condition against an entry dict."""
        field_value = _get_field_value(entry, self.field)

        if self.op == "eq":
            return field_value == self.value
        elif self.op == "ne":
            return field_value != self.value
        elif self.op == "in":
            if isinstance(field_value, list):
                return any(v in field_value for v in self.value)
            return field_value in self.value
        elif self.op == "not_in":
            if isinstance(field_value, list):
                return not any(v in field_value for v in self.value)
            return field_value not in self.value
        elif self.op == "gt":
            return _safe_compare(field_value, self.value, lambda a, b: a > b)
        elif self.op == "gte":
            return _safe_compare(field_value, self.value, lambda a, b: a >= b)
        elif self.op == "lt":
            return _safe_compare(field_value, self.value, lambda a, b: a < b)
        elif self.op == "lte":
            return _safe_compare(field_value, self.value, lambda a, b: a <= b)
        elif self.op == "contains":
            if field_value is None:
                return False
            return str(self.value) in str(field_value)
        elif self.op == "icontains":
            if field_value is None:
                return False
            return str(self.value).lower() in str(field_value).lower()
        elif self.op == "wildcard":
            if field_value is None:
                return False
            # Convert wildcard pattern to regex: * → .*, ? → .
            pattern = str(self.value)
            regex = ""
            for ch in pattern:
                if ch == "*":
                    regex += ".*"
                elif ch == "?":
                    regex += "."
                else:
                    regex += re.escape(ch)
            return bool(re.match(regex, str(field_value), re.IGNORECASE))
        elif self.op == "isnull":
            return (field_value is None) == bool(self.value)
        elif self.op == "exists":
            return _field_exists(entry, self.field) == bool(self.value)

        return False


# ============================================================
# Filter Expression (AND/OR/NOT)
# ============================================================

class FilterExpression:
    """A logical filter expression: AND/OR/NOT of conditions/expressions."""

    def __init__(self, logic: str, children: list):
        if logic not in ("AND", "OR", "NOT"):
            raise FilterError(f"Unsupported logic operator: '{logic}'. Use AND/OR/NOT.")
        if logic == "NOT" and len(children) != 1:
            raise FilterError("NOT must have exactly one child.")
        self.logic = logic
        self.children = children

    def evaluate(self, entry: dict) -> bool:
        if self.logic == "AND":
            return all(c.evaluate(entry) for c in self.children)
        elif self.logic == "OR":
            return any(c.evaluate(entry) for c in self.children)
        elif self.logic == "NOT":
            return not self.children[0].evaluate(entry)
        return False


# ============================================================
# Filter Parser
# ============================================================

def parse_filter(raw: dict) -> FilterExpression | FilterCondition:
    """Parse a filter dict into a FilterExpression or FilterCondition.

    Supports:
      - New format: {"AND": [...], "OR": [...], "NOT": [...]}
      - Condition: {"field": "...", "op": "...", "value": ...}
      - Legacy format: {"tags": ["AI"], "importance": "high"} → auto-converts

    Args:
        raw: Filter dict from user input.

    Returns:
        Parsed filter tree.

    Raises:
        FilterError: On invalid filter syntax.
    """
    if not raw:
        raise FilterError("Empty filter")

    # Check for logical operators
    for logic in ("AND", "OR", "NOT"):
        if logic in raw:
            children_raw = raw[logic]
            if not isinstance(children_raw, list):
                raise FilterError(f"'{logic}' value must be a list")
            children = [parse_filter(c) for c in children_raw]
            return FilterExpression(logic, children)

    # Check for condition format
    if "field" in raw and "op" in raw:
        return FilterCondition(
            field=raw["field"],
            op=raw["op"],
            value=raw.get("value"),
        )

    # Legacy format: auto-convert
    # {"tags": ["AI"]} → {"AND": [{"field": "tags", "op": "in", "value": ["AI"]}]}
    return _convert_legacy_filter(raw)


def _convert_legacy_filter(raw: dict) -> FilterExpression:
    """Convert legacy filter format to new format.

    Legacy: {"tags": ["AI"], "importance": "high"}
    → AND of: tags in ["AI"], importance eq "high"
    """
    conditions = []
    for key, value in raw.items():
        if isinstance(value, list):
            conditions.append(FilterCondition(field=key, op="in", value=value))
        elif value is None:
            conditions.append(FilterCondition(field=key, op="isnull", value=True))
        else:
            conditions.append(FilterCondition(field=key, op="eq", value=value))

    if len(conditions) == 1:
        # Wrap single condition in AND for consistency
        return FilterExpression("AND", conditions)
    return FilterExpression("AND", conditions)


# ============================================================
# Filter Evaluator
# ============================================================

def apply_filters(
    entries: list[dict],
    filter_raw: dict,
) -> list[dict]:
    """Apply a filter to a list of entries.

    Args:
        entries: List of entry dicts (from search results).
        filter_raw: Raw filter dict.

    Returns:
        Filtered list of entries.
    """
    if not filter_raw:
        return entries

    try:
        parsed = parse_filter(filter_raw)
    except FilterError:
        # If filter is invalid, return all entries (graceful degradation)
        return entries

    return [e for e in entries if parsed.evaluate(e)]


# ============================================================
# Helpers
# ============================================================

def _get_field_value(entry: dict, field: str) -> Any:
    """Get a field value from an entry, supporting dot notation.

    Examples:
      - "title" → entry["title"]
      - "source.author" → entry["source"]["author"]
    """
    parts = field.split(".")
    current = entry
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _field_exists(entry: dict, field: str) -> bool:
    """Check if a field exists in an entry."""
    parts = field.split(".")
    current = entry
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return False
            current = current[part]
        else:
            return False
    return True


def _safe_compare(a: Any, b: Any, op) -> bool:
    """Safely compare two values, handling type mismatches."""
    try:
        if a is None:
            return False
        return op(a, b)
    except (TypeError, ValueError):
        return False
