"""MCP Resources — expose the knowledge base as browsable ``sheaf://`` URIs.

Complements the 4 MCP tools (write / act) with a read / browse surface: an
agent can ``resources/list`` to see the KB structure and ``resources/read`` to
fetch content without a tool side-effect. See Issue #89 and design Principle F
(AGENT-NATIVE-DESIGN-PRINCIPLES.md).

All four resources reuse existing data-access functions — no new data code.
"""
from __future__ import annotations

import json
import re

from sheaf_ai.mcp.protocol import jsonrpc_response, jsonrpc_error

# Static, always-present resources (returned by resources/list).
RESOURCES = [
    {
        "uri": "sheaf://entries/recent",
        "name": "Recent entries",
        "description": "The 10 most recently collected entries (index metadata: id, title, topics, tags, summary, collected_at).",
        "mimeType": "application/json",
    },
    {
        "uri": "sheaf://stats",
        "name": "Collection stats",
        "description": "Aggregate counts: total entries, topic counts, content-type counts, tag counts.",
        "mimeType": "application/json",
    },
    {
        "uri": "sheaf://tags",
        "name": "Tag frequency",
        "description": "Tags ranked by frequency (canonical name, count, first/last seen, aliases).",
        "mimeType": "application/json",
    },
]

# Parameterized resource templates (returned by resources/templates/list).
RESOURCE_TEMPLATES = [
    {
        "uriTemplate": "sheaf://entries/{id}",
        "name": "Entry detail",
        "description": "Full detail of one entry by id (e.g. 2026-06-01_58fb4a92). Discover ids via sheaf://entries/recent.",
        "mimeType": "application/json",
    },
]

# Entry ids are ``YYYY-MM-DD_<hex>``. Restrict to URL-safe alphanumerics so a
# crafted id can't traverse out of the entries dir (load_entry builds a path
# from entry_id[:7] + entry_id + ".json").
_ENTRY_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

_ENTRIES_PREFIX = "sheaf://entries/"


def list_resources() -> list:
    """Static resource descriptors for ``resources/list``."""
    return RESOURCES


def list_resource_templates() -> list:
    """Parameterized resource templates for ``resources/templates/list``."""
    return RESOURCE_TEMPLATES


def _content(uri: str, payload) -> dict:
    """Wrap a JSON-serializable payload as one MCP resource content block."""
    return {
        "uri": uri,
        "mimeType": "application/json",
        "text": json.dumps(payload, ensure_ascii=False, indent=2),
    }


def read_resource(req_id, uri: str) -> str:
    """Handle ``resources/read`` — route a ``sheaf://`` URI to its data."""
    if uri == "sheaf://entries/recent":
        from sheaf_ai.mcp.data import load_index
        recent = load_index()[-10:][::-1]  # newest first
        return jsonrpc_response(req_id, {"contents": [_content(uri, recent)]})

    if uri == "sheaf://stats":
        from sheaf_ai.query import get_collection_stats
        return jsonrpc_response(req_id, {"contents": [_content(uri, get_collection_stats())]})

    if uri == "sheaf://tags":
        from sheaf_ai.query import tag_stats
        return jsonrpc_response(req_id, {"contents": [_content(uri, tag_stats(sort_by="count"))]})

    # Parameterized: sheaf://entries/{id}
    if uri.startswith(_ENTRIES_PREFIX):
        entry_id = uri[len(_ENTRIES_PREFIX):]
        if not entry_id or not _ENTRY_ID_RE.fullmatch(entry_id):
            return jsonrpc_error(req_id, -32602, f"Invalid entry id in URI: {uri}")
        from sheaf_ai.mcp.data import load_entry
        entry = load_entry(entry_id)
        if entry is None:
            return jsonrpc_error(req_id, -32602, f"Entry not found: {entry_id}")
        return jsonrpc_response(req_id, {"contents": [_content(uri, entry)]})

    return jsonrpc_error(req_id, -32602, f"Unknown resource URI: {uri}")
