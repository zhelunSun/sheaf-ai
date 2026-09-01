"""MCP search tools — sheaf_search."""
from __future__ import annotations

import json

from sheaf_ai.mcp.protocol import jsonrpc_response
from sheaf_ai.search import search_fulltext, search_hybrid, search_quick

# ── Tool definition ──────────────────────────────────────────

TOOLS = [
    {
        "name": "sheaf_search",
        "description": (
            "Search the user's personal knowledge base — articles, notes, and research "
            "they have collected via Sheaf.\n"
            "\n"
            "Supports three search modes:\n"
            "- 'hybrid' (default): BM25 keyword + semantic vector fusion.\n"
            "  Best for natural language queries. Returns combined relevance score.\n"
            "- 'keyword': weighted field matching with synonym expansion.\n"
            "  Cross-lingual synonyms work automatically (AI↔人工智能, deep learning↔深度学习).\n"
            "- 'quick': metadata-only, fastest. Good for 'does anything about X exist?'.\n"
            "\n"
            "Advanced query syntax (keyword/hybrid modes):\n"
            "  #tag          — filter by tag (#AI, #遥感)\n"
            "  is:fav        — favorites only\n"
            "  after:DATE    — collected after date (after:2025-01-01)\n"
            "  before:DATE   — collected before date\n"
            "  source:TYPE   — origin filter (source:arxiv, source:github)\n"
            "\n"
            "Combine freely: \"transformer #AI source:arxiv after:2024-01-01\"\n"
            "\n"
            "Examples:\n"
            "  sheaf_search(query=\"RAG 检索增强\")         — basic search\n"
            "  sheaf_search(query=\"AI Agent\", mode=\"hybrid\") — hybrid BM25+semantic\n"
            "  sheaf_search(query=\"#遥感 source:arxiv\")    — tag + source filter\n"
            "  sheaf_search(query=\"融资\", limit=5)          — limit results\n"
            "\n"
            "Returns ranked results with relevance scores, match locations, "
            "snippets, expanded synonym terms, and semantic backend diagnostics."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query. Supports: plain text, #tag, is:fav, after:YYYY-MM-DD, before:YYYY-MM-DD, source:type. Combine freely.",
                },
                "limit": {"type": "integer", "description": "Max results to return (default: 10)", "default": 10},
                "mode": {
                    "type": "string",
                    "description": "Search mode: 'hybrid' (default; BM25+semantic fusion), 'keyword' (weighted fields+synonyms), or 'quick' (metadata-only).",
                    "enum": ["keyword", "hybrid", "quick"],
                    "default": "hybrid",
                },
                "deep": {"type": "boolean", "description": "Search full article text in addition to metadata (default: true). Only for keyword mode.", "default": True},
                "alpha": {
                    "type": "number",
                    "description": "BM25 vs semantic weight for hybrid mode (0.0-1.0, default: 0.6). Higher = more keyword-biased.",
                    "default": 0.6,
                },
            },
            "required": ["query"],
        },
    },
]


# ── Handler ──────────────────────────────────────────────────

def _handle_search(req_id: int | str, arguments: dict) -> str:
    mode = arguments.get("mode", "hybrid")
    limit = arguments.get("limit", 10)
    query_str = arguments.get("query", "")

    if mode == "hybrid":
        alpha = arguments.get("alpha", 0.6)
        raw_diagnostics: dict[str, object] = {}
        results = search_hybrid(
            query_str,
            limit=limit,
            alpha=alpha,
            include_raw=True,
            diagnostics=raw_diagnostics,
        )
        formatted = _format_ranked_results(results, hybrid=True)
        diagnostics = _semantic_diagnostics(results, raw_diagnostics)
        return _search_response(req_id, formatted, diagnostics)
    elif mode == "quick":
        results = search_quick(query_str, limit=limit)
        return _search_response(
            req_id,
            results,
            {
                "semantic_backend": "disabled",
                "degraded": False,
                "reason": "quick mode explicitly requested",
            },
        )
    else:  # keyword (legacy)
        deep = arguments.get("deep", True)
        if deep:
            results = search_fulltext(query_str, limit=limit, include_raw=True)
            formatted = _format_ranked_results(results, hybrid=False)
            return _search_response(
                req_id,
                formatted,
                {
                    "semantic_backend": "disabled",
                    "degraded": False,
                    "reason": "keyword mode explicitly requested",
                },
            )
        else:
            results = search_quick(query_str, limit=limit)
            return _search_response(
                req_id,
                results,
                {
                    "semantic_backend": "disabled",
                    "degraded": False,
                    "reason": "keyword mode with deep=false uses quick search",
                },
            )


def _format_ranked_results(results: list[dict], *, hybrid: bool) -> list[dict]:
    """Preserve the legacy flattened MCP result shape."""
    formatted: list[dict] = []
    for result in results:
        item = result["entry"].copy()
        item["_score"] = result["score"]
        item["_match_locations"] = result.get("match_locations", [])
        if hybrid:
            item["_bm25_score"] = result.get("bm25_score", 0.0)
            item["_semantic_score"] = result.get("semantic_score", 0.0)
        if result.get("snippet"):
            item["_snippet"] = result["snippet"]
        if result.get("expanded_terms"):
            item["_expanded_terms"] = result["expanded_terms"]
        formatted.append(item)
    return formatted


def _semantic_diagnostics(
    results: list[dict],
    diagnostics: dict[str, object] | None = None,
) -> dict[str, object]:
    if diagnostics:
        return {
            "semantic_backend": str(
                diagnostics.get(
                    "semantic_backend",
                    diagnostics.get("backend", "unknown"),
                )
            ),
            "degraded": bool(diagnostics.get("degraded", False)),
            "reason": str(diagnostics.get("reason", "")),
        }
    if not results:
        return {
            "semantic_backend": "unknown",
            "degraded": True,
            "reason": "No result-level semantic diagnostics are available",
        }
    first = results[0]
    return {
        "semantic_backend": str(first.get("semantic_backend", "unknown")),
        "degraded": bool(first.get("semantic_degraded", False)),
        "reason": str(first.get("semantic_reason", "")),
    }


def _search_response(
    req_id: int | str,
    results: list[dict],
    diagnostics: dict[str, object],
) -> str:
    """Keep text-list compatibility while adding structured diagnostics."""
    return jsonrpc_response(
        req_id,
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(results, ensure_ascii=False, indent=2),
                }
            ],
            "structuredContent": {"results": results, **diagnostics},
        },
    )


HANDLERS = {
    "sheaf_search": _handle_search,
}
