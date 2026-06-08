"""MCP insights tool — sheaf_insights."""
from __future__ import annotations

import json

from sheaf_ai.mcp.protocol import jsonrpc_response, jsonrpc_error
from sheaf_ai.mcp.data import load_index


# ── Tool definition ──────────────────────────────────────────

TOOLS = [
    {
        "name": "sheaf_insights",
        "description": "Discover cross-topic associations and hidden connections in your knowledge base. Requires 3+ entries.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ── Handler ──────────────────────────────────────────────────

def _handle_insights(req_id: int | str, arguments: dict) -> str:
    entries = load_index()
    if len(entries) < 3:
        return jsonrpc_error(req_id, -32602, "Insights require at least 3 entries")
    try:
        from sheaf_ai.insights import discover_associations
        result = discover_associations()
        return jsonrpc_response(req_id, {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
        })
    except Exception as e:
        return jsonrpc_error(req_id, -32603, f"Insight discovery failed: {e}")


HANDLERS = {
    "sheaf_insights": _handle_insights,
}
