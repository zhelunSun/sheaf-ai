"""
Sheaf MCP Server — Backward-compatible wrapper.

.. deprecated::
    Use ``from sheaf_ai.mcp import handle_request, main, TOOLS`` instead.
    This module re-exports everything for backward compatibility.

10 active tools:
  sheaf_search, sheaf_list, sheaf_get, sheaf_correct,
  sheaf_collect, sheaf_collect_batch, sheaf_crystallize,
  sheaf_list_cards, sheaf_get_card, sheaf_insights

3 deprecated tools (fallback only, not in tools/list):
  sheaf_urgent → use sheaf_list with filter="urgent"
  sheaf_healthcheck → use HTTP /health endpoint
  sheaf_stats → use sheaf_list (returns total + topics_summary)

Usage:
    sheaf --mcp
"""
# Re-export everything from the new mcp subpackage
from sheaf_ai.mcp.server import (  # noqa: F401
    handle_request,
    main,
    TOOLS,
    MCP_PROTOCOL_VERSION,
)
from sheaf_ai.mcp.protocol import jsonrpc_response as _jsonrpc_response, jsonrpc_error as _jsonrpc_error  # noqa: F401
from sheaf_ai.mcp.entries import (  # noqa: F401
    _load_index,
    _list_entries as list_entries,
    _compute_topics_summary,
    _get_entry as get_entry,
)
from sheaf_ai.mcp.search import search_fulltext as _sf, search_hybrid as _sh, search_quick as _sq  # noqa: F401
from sheaf_ai.mcp.data import load_index, load_entry  # noqa: F401

# Legacy aliases for any code that imports from this module
_jsonrpc_response = _jsonrpc_response
_jsonrpc_error = _jsonrpc_error
_DEPRECATED_TOOLS = {"sheaf_urgent", "sheaf_healthcheck", "sheaf_stats"}

# Data access backward compat
search_knowledge = None  # removed in refactor; use sheaf_search tool


def _deprecated_response(req_id, tool_name, replacement):
    """Return a deprecation notice for removed tools."""
    return _jsonrpc_response(req_id, {
        "content": [{
            "type": "text",
            "text": _jsonrpc_error(0, -32601, f"{tool_name} is deprecated. Use {replacement}"),
        }]
    })


if __name__ == "__main__":
    main()
