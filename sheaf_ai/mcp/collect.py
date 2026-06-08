"""MCP collect tools — sheaf_collect, sheaf_collect_batch."""
from __future__ import annotations

import json

from sheaf_ai.mcp.protocol import jsonrpc_response, jsonrpc_error
from sheaf_ai.pipeline import process_url


# ── Tool definitions ─────────────────────────────────────────

TOOLS = [
    {
        "name": "sheaf_collect",
        "description": "Collect a new article URL into the knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Article URL to collect"},
                "force": {"type": "boolean", "description": "Skip dedup check (default: false)", "default": False},
            },
            "required": ["url"],
        },
    },
    {
        "name": "sheaf_collect_batch",
        "description": "Collect multiple URLs in a single batch call. Returns aggregated results with per-URL status. Agent-Native preferred over multiple sheaf_collect calls.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of URLs to collect",
                },
                "concurrency": {
                    "type": "integer",
                    "description": "Max parallel workers (default: 3)",
                    "default": 3,
                },
                "on_error": {
                    "type": "string",
                    "description": "Error handling: 'continue' (default) or 'stop'",
                    "enum": ["continue", "stop"],
                    "default": "continue",
                },
                "force": {
                    "type": "boolean",
                    "description": "Skip dedup check for all URLs (default: false)",
                    "default": False,
                },
            },
            "required": ["urls"],
        },
    },
]


# ── Handlers ─────────────────────────────────────────────────

def _handle_collect(req_id: int | str, arguments: dict) -> str:
    url = arguments.get("url", "")
    force = arguments.get("force", False)
    result = process_url(url, force=force)
    return jsonrpc_response(req_id, {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
    })


def _handle_collect_batch(req_id: int | str, arguments: dict) -> str:
    from sheaf_ai.batch import batch_collect

    urls = arguments.get("urls", [])
    if not urls:
        return jsonrpc_error(req_id, -32602, "Missing required parameter: urls (non-empty array)")
    concurrency = arguments.get("concurrency", 3)
    on_error = arguments.get("on_error", "continue")
    force = arguments.get("force", False)
    batch_result = batch_collect(
        urls,
        force=force,
        concurrency=concurrency,
        on_error=on_error,  # type: ignore[arg-type]
        quiet=True,
    )
    return jsonrpc_response(req_id, {
        "content": [{"type": "text", "text": json.dumps(batch_result.to_dict(), ensure_ascii=False, indent=2)}]
    })


HANDLERS = {
    "sheaf_collect": _handle_collect,
    "sheaf_collect_batch": _handle_collect_batch,
}
