"""Sheaf MCP Server — protocol layer (JSON-RPC over stdio).

Registers tools from domain modules and dispatches requests.
"""
from __future__ import annotations

import json
import os
import sys

from sheaf_ai.config import VERSION, fix_windows_encoding
from sheaf_ai.mcp.protocol import jsonrpc_response, jsonrpc_error
from sheaf_ai.mcp import collect as _collect_mod
from sheaf_ai.mcp import search as _search_mod
from sheaf_ai.mcp import entries as _entries_mod
from sheaf_ai.mcp import cards as _cards_mod
from sheaf_ai.mcp import insights as _insights_mod
from sheaf_ai.mcp import verify as _verify_mod
from sheaf_ai.mcp import resources as _resources_mod

MCP_PROTOCOL_VERSION = "2025-06-18"

# All tool definitions from domain modules (full surface).
ALL_TOOLS = (
    _search_mod.TOOLS
    + _entries_mod.TOOLS
    + _collect_mod.TOOLS
    + _cards_mod.TOOLS
    + _insights_mod.TOOLS
    + _verify_mod.TOOLS
)

# Default MCP surface — the 4 high-frequency entry points (collect / search /
# crystallize / get_card). The remaining 7 tools stay callable via tools/call
# (handler_map is full) for backward compat; agents are guided to the `sheaf`
# CLI for them by the deployed skill (sheaf-cli-extended). Set
# SHEAF_MCP_TOOLS=all to re-expose the full set (migration / power users).
# See: https://github.com/zhelunSun/sheaf-ai/issues/91
CORE_TOOL_NAMES = {"sheaf_collect", "sheaf_search", "sheaf_crystallize", "sheaf_get_card"}


def _select_tools() -> list:
    """Return the tools exposed via tools/list.

    Default: the 4 core entry points. With SHEAF_MCP_TOOLS=all: the full set.
    """
    if os.environ.get("SHEAF_MCP_TOOLS", "").lower() == "all":
        return ALL_TOOLS
    return [t for t in ALL_TOOLS if t["name"] in CORE_TOOL_NAMES]


# Module-level default snapshot (imported by tests / parametrize). Reflects the
# default 4-tool surface unless SHEAF_MCP_TOOLS=all was set at import time.
TOOLS = _select_tools()

# Deprecated tool names — still handled for backward compat
_DEPRECATED_TOOLS = {"sheaf_urgent", "sheaf_healthcheck", "sheaf_stats"}


def handle_request(request: dict) -> str | None:
    """Dispatch a JSON-RPC request to the appropriate handler."""
    method = request.get("method", "")
    req_id = request.get("id", 0)
    params = request.get("params", {})

    if method == "initialize":
        return jsonrpc_response(req_id, {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "sheaf", "version": VERSION},
        })

    if method == "ping":
        return jsonrpc_response(req_id, {})

    if method == "tools/list":
        return jsonrpc_response(req_id, {"tools": _select_tools()})

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # --- Deprecated tool fallbacks (backward compat) ---
        if tool_name in _DEPRECATED_TOOLS:
            return _handle_deprecated(req_id, tool_name)

        # --- Domain dispatchers ---
        handler_map = {
            **_search_mod.HANDLERS,
            **_entries_mod.HANDLERS,
            **_collect_mod.HANDLERS,
            **_cards_mod.HANDLERS,
            **_insights_mod.HANDLERS,
            **_verify_mod.HANDLERS,
        }

        handler = handler_map.get(tool_name)
        if handler:
            return handler(req_id, arguments)

        return jsonrpc_error(req_id, -32601, f"Unknown tool: {tool_name}")

    if method == "resources/list":
        return jsonrpc_response(req_id, {"resources": _resources_mod.list_resources()})

    if method == "resources/templates/list":
        return jsonrpc_response(req_id, {"resourceTemplates": _resources_mod.list_resource_templates()})

    if method == "resources/read":
        return _resources_mod.read_resource(req_id, params.get("uri", ""))

    if method == "notifications/initialized":
        return None

    return jsonrpc_error(req_id, -32601, f"Unknown method: {method}")


def _handle_deprecated(req_id: int | str, tool_name: str) -> str:
    """Handle deprecated tool calls with migration notice."""
    import os
    from sheaf_ai.config import DATA_DIR, INDEX_FILE
    from sheaf_ai.mcp.entries import _load_index

    if tool_name == "sheaf_urgent":
        from sheaf_ai.query import query_urgent
        results = query_urgent()
        return jsonrpc_response(req_id, {
            "content": [{"type": "text", "text": json.dumps({
                "deprecated": True,
                "message": "sheaf_urgent is deprecated. Use sheaf_list with filter='urgent'.",
                "results": results,
            }, ensure_ascii=False, indent=2)}]
        })

    if tool_name == "sheaf_healthcheck":
        entries = _load_index()
        api_key_set = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("SHEAF_API_KEY"))
        return jsonrpc_response(req_id, {
            "content": [{"type": "text", "text": json.dumps({
                "deprecated": True,
                "message": "sheaf_healthcheck is deprecated. Use HTTP /health endpoint.",
                "version": VERSION,
                "data_dir": str(DATA_DIR),
                "entry_count": len(entries),
                "index_status": "ok" if INDEX_FILE.exists() else "missing",
                "api_key_configured": api_key_set,
            }, ensure_ascii=False, indent=2)}]
        })

    if tool_name == "sheaf_stats":
        from sheaf_ai.query import get_collection_stats
        from sheaf_ai.gamification import get_progress
        entries = _load_index()
        stats = get_collection_stats()
        try:
            progress = get_progress()
            game = {
                "streak": progress.get("streak", 0),
                "next_milestone": progress.get("next_milestone", {}).get("name"),
                "basket_level": progress.get("basket_progress", {}).get("level"),
            }
        except Exception:
            game = {}
        return jsonrpc_response(req_id, {
            "content": [{"type": "text", "text": json.dumps({
                "deprecated": True,
                "message": "sheaf_stats is deprecated. Use sheaf_list (returns total + topics_summary).",
                "total_entries": len(entries),
                **stats,
                "gamification": game,
            }, ensure_ascii=False, indent=2)}]
        })

    return jsonrpc_error(req_id, -32601, f"Unknown deprecated tool: {tool_name}")


def main():
    """Run MCP server on stdio."""
    fix_windows_encoding()
    if sys.platform == "win32":
        try:
            sys.stdin.reconfigure(encoding="utf-8")
        except Exception:
            pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response:
                print(response, flush=True)
        except json.JSONDecodeError:
            print(jsonrpc_error(0, -32700, "Parse error"), flush=True)
        except Exception as e:
            print(jsonrpc_error(0, -32603, f"Internal error: {e}"), flush=True)


if __name__ == "__main__":
    main()
