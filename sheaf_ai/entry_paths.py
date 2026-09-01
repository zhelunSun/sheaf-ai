"""Validated, root-confined paths for entry artifacts.

Entry IDs are persisted as file names in several interfaces (HTTP, feedback,
and MCP).  Keep validation and containment in one place so every interface has
the same compatibility and security boundary.
"""
from __future__ import annotations

import re
from pathlib import Path


# Generated IDs use ``YYYY-MM-DD_<uuid8>``.  Older callers and tests also use
# shorter opaque IDs, so retain safe alphanumeric/underscore/hyphen IDs while
# rejecting path syntax on both POSIX and Windows.
_ENTRY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class InvalidEntryId(ValueError):
    """Raised when an entry ID cannot safely name an on-disk artifact."""


def validate_entry_id(entry_id: str) -> str:
    """Return *entry_id* when it is a safe, compatible artifact identifier."""
    if not isinstance(entry_id, str) or not _ENTRY_ID_RE.fullmatch(entry_id):
        raise InvalidEntryId("Entry ID contains unsupported characters or length")
    return entry_id


def _resolve_within(root: Path, relative_path: Path) -> Path:
    """Resolve a candidate path and require it to remain below *root*."""
    resolved_root = Path(root).resolve()
    candidate = (resolved_root / relative_path).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise InvalidEntryId("Entry artifact path escapes its data directory")
    return candidate


def resolve_entry_json_path(entries_dir: Path, entry_id: str) -> Path:
    """Resolve the monthly JSON path for an entry ID."""
    safe_id = validate_entry_id(entry_id)
    return _resolve_within(Path(entries_dir), Path(safe_id[:7]) / f"{safe_id}.json")


def resolve_entry_summary_path(summaries_dir: Path, entry_id: str) -> Path:
    """Resolve the generated Markdown summary path for an entry ID."""
    safe_id = validate_entry_id(entry_id)
    return _resolve_within(Path(summaries_dir), Path(f"{safe_id}.md"))


def resolve_entry_raw_path(raw_dir: Path, entry_id: str) -> Path:
    """Resolve the captured raw-text path for an entry ID."""
    safe_id = validate_entry_id(entry_id)
    return _resolve_within(Path(raw_dir), Path(f"{safe_id}.txt"))
