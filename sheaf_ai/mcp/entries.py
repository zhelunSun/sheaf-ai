"""MCP entry tools — sheaf_list, sheaf_get, sheaf_correct."""
from __future__ import annotations

import json

from sheaf_ai.config import DATA_DIR
from sheaf_ai.mcp.protocol import jsonrpc_response, jsonrpc_error
from sheaf_ai.mcp.data import load_index, load_entry, compute_topics_summary
from sheaf_ai.feedback import submit_feedback


# ── Re-export for deprecated handler ─────────────────────────

_load_index = load_index
_compute_topics_summary = compute_topics_summary


def _list_entries(
    category: str = None,
    limit: int = 20,
    offset: int = 0,
    filter_type: str = None,
) -> list:
    """List entries with optional filtering and pagination."""
    entries = load_index()

    if filter_type == "urgent":
        entries = [e for e in entries if e.get("urgency") in ("urgent", "upcoming")]
        entries.sort(key=lambda x: x.get("deadline_date") or "9999")
    elif filter_type == "untagged":
        entries = [e for e in entries if not e.get("tags")]
        entries.sort(key=lambda x: x.get("collected_at", ""), reverse=True)
    else:
        if category:
            entries = [e for e in entries if e.get("primary_category", "").lower() == category.lower()]
        entries.sort(key=lambda x: x.get("collected_at", ""), reverse=True)

    return entries[offset:offset + limit]


def _get_entry(entry_id: str) -> dict | None:
    """Get entry with optional summary markdown."""
    entry = load_entry(entry_id)
    if not entry:
        return None
    summary_path = DATA_DIR / "summaries" / f"{entry_id}.md"
    if summary_path.exists():
        entry["summary_markdown"] = summary_path.read_text(encoding="utf-8")
    return entry


# ── Tool definitions ─────────────────────────────────────────

TOOLS = [
    {
        "name": "sheaf_list",
        "description": (
            "Browse collected knowledge entries with pagination and filters.\n"
            "\n"
            "Returns total entry count, topics summary, and paginated entry list.\n"
            "Each entry includes: title, URL, topics, tags, content_type, summary, "
            "importance, and collection date.\n"
            "\n"
            "Filters:\n"
            "- 'urgent': entries with upcoming deadlines or time-sensitive info\n"
            "- 'untagged': entries without AI-generated tags (need review)\n"
            "- 'recent' (default): most recently collected first\n"
            "\n"
            "Examples:\n"
            "  sheaf_list()                           — recent 20 entries\n"
            "  sheaf_list(limit=5)                     — recent 5\n"
            "  sheaf_list(filter='urgent')             — deadline-sensitive\n"
            "  sheaf_list(filter='untagged', limit=10) — entries needing tags\n"
            "  sheaf_list(category='AI Agent')         — filter by primary topic"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filter by topic (matches primary topic name)"},
                "filter": {
                    "type": "string",
                    "description": "Predefined filter: 'urgent' (deadline-sensitive), 'untagged' (no tags), or omit for recent (default)",
                    "enum": ["urgent", "untagged", "recent"],
                },
                "limit": {"type": "integer", "description": "Max results (default: 20)", "default": 20},
                "offset": {"type": "integer", "description": "Skip first N results for pagination (default: 0)", "default": 0},
            },
        },
    },
    {
        "name": "sheaf_get",
        "description": (
            "Get full details of a specific knowledge entry by ID.\n"
            "\n"
            "Returns all fields: title, URL, full summary, structured summary, "
            "topics, tags, content_type, importance, quality_tier, images, "
            "and the generated summary markdown.\n"
            "\n"
            "Use this when you need detailed information about a specific article "
            "that was found via sheaf_search or sheaf_list."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "Entry ID (format: YYYY-MM-DD_xxxxxxxx)"},
            },
            "required": ["entry_id"],
        },
    },
    {
        "name": "sheaf_correct",
        "description": (
            "Correct an entry's AI-generated classification or summary.\n"
            "\n"
            "Use when the user says something like:\n"
            "- 'this should be tagged as X' → set corrections.tags\n"
            "- 'this is actually about Y' → set corrections.category_primary\n"
            "- 'the summary is wrong' → set corrections.summary\n"
            "- 'this is high priority' → set corrections.importance = 'high'\n"
            "\n"
            "Corrections are saved and used to improve future classifications."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "Entry ID to correct"},
                "corrections": {
                    "type": "object",
                    "description": "Fields to correct",
                    "properties": {
                        "category_primary": {"type": "string"},
                        "category_sub": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "importance": {"type": "string", "enum": ["high", "medium", "low"]},
                        "summary": {"type": "string"},
                    },
                },
                "user_note": {"type": "string", "description": "Optional note explaining the correction"},
            },
            "required": ["entry_id", "corrections"],
        },
    },
]


# ── Handlers ─────────────────────────────────────────────────

def _handle_list(req_id: int | str, arguments: dict) -> str:
    all_entries = load_index()
    results = _list_entries(
        category=arguments.get("category"),
        limit=arguments.get("limit", 20),
        offset=arguments.get("offset", 0),
        filter_type=arguments.get("filter"),
    )
    topics_summary = compute_topics_summary(all_entries)
    return jsonrpc_response(req_id, {
        "content": [{"type": "text", "text": json.dumps({
            "total": len(all_entries),
            "topics": topics_summary,
            "entries": results,
        }, ensure_ascii=False, indent=2)}]
    })


def _handle_get(req_id: int | str, arguments: dict) -> str:
    entry = _get_entry(arguments.get("entry_id", ""))
    if not entry:
        return jsonrpc_error(req_id, -32602, f"Entry not found: {arguments.get('entry_id')}")
    return jsonrpc_response(req_id, {
        "content": [{"type": "text", "text": json.dumps(entry, ensure_ascii=False, indent=2)}]
    })


def _handle_correct(req_id: int | str, arguments: dict) -> str:
    result = submit_feedback(
        arguments.get("entry_id", ""),
        arguments.get("corrections", {}),
        arguments.get("user_note", ""),
    )
    if not result["success"]:
        return jsonrpc_error(req_id, -32602, result.get("error", "Correction failed"))
    return jsonrpc_response(req_id, {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
    })


HANDLERS = {
    "sheaf_list": _handle_list,
    "sheaf_get": _handle_get,
    "sheaf_correct": _handle_correct,
}
