"""MCP collect tools — sheaf_collect, sheaf_collect_batch."""
from __future__ import annotations

import json
import uuid

from sheaf_ai.mcp.protocol import jsonrpc_response, jsonrpc_error
from sheaf_ai.pipeline import process_url


# ── Tool definitions ─────────────────────────────────────────

TOOLS = [
    {
        "name": "sheaf_collect",
        "description": (
            "Collect into the user's knowledge base — either a URL or freeform text.\n"
            "\n"
            "Provide ONE of:\n"
            "- url: fetch + classify + summarize a web article/paper/repo (web articles, "
            "arxiv, GitHub, PDFs, WeChat, ChatGPT shares, …). Automatically deduplicates.\n"
            "- text: store a pasted insight/note directly (no fetch). Tagged content_type "
            "'note', gets an AI-generated title + summary, bypasses the short-content gate. "
            "For most agents this is the MOST FREQUENT capture — users express decisions, "
            "facts, and takeaways in conversation far more often than they paste URLs. Capture "
            "proactively when the user shares something worth recalling; don't wait to be asked.\n"
            "\n"
            "After collection, the entry can be found via sheaf_search, listed, or "
            "synthesized into knowledge cards via sheaf_crystallize.\n"
            "\n"
            "Examples:\n"
            "  sheaf_collect(url='https://arxiv.org/abs/2401.00001')\n"
            "  sheaf_collect(text='RAG retrieval quality is the main bottleneck; CRAG adds a retrieval evaluator.')"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Article URL to collect (mutually exclusive with text)"},
                "text": {"type": "string", "description": "Freeform note/insight to store directly, no fetch (mutually exclusive with url)"},
                "force": {"type": "boolean", "description": "Skip dedup check (default: false)", "default": False},
            },
            # url OR text required — validated in the handler (JSON Schema can't express cleanly here).
        },
    },
    {
        "name": "sheaf_collect_batch",
        "description": (
            "Collect multiple URLs in a single batch call.\n"
            "\n"
            "Preferred over multiple sheaf_collect calls when the user wants to "
            "collect several URLs at once. Returns aggregated results with "
            "per-URL success/failure status.\n"
            "\n"
            "Examples:\n"
            "  sheaf_collect_batch(urls=['https://url1.com', 'https://url2.com'])\n"
            "  sheaf_collect_batch(urls=[...], concurrency=3, force=True)"
        ),
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
    url = (arguments.get("url") or "").strip()
    text = (arguments.get("text") or "").strip()
    force = arguments.get("force", False)

    # Validate: exactly one of url / text.
    if url and text:
        return jsonrpc_error(req_id, -32602, "Provide either 'url' OR 'text', not both.")
    if not url and not text:
        return jsonrpc_error(req_id, -32602, "Missing required parameter: provide 'url' (to fetch) or 'text' (to store a note).")

    if text:
        # Freeform note: synthesize a manual:// key (pipeline needs a url), bypass fetch.
        url = f"manual://{uuid.uuid4().hex[:8]}"
        result = process_url(url, manual_text=text, force=force)
    else:
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
