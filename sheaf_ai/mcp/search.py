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
            "Search your personal knowledge base. Supports full-text, synonym expansion "
            "(cross-lingual: AI↔人工智能, deep learning↔深度学习), and semantic search.\n"
            "Modes: 'keyword' (weighted fields+synonyms), 'hybrid' (BM25+semantic, recommended), "
            "'quick' (metadata-only).\n"
            "Advanced query syntax: #tag (tag filter), is:fav (favorites only), "
            "after:YYYY-MM-DD / before:YYYY-MM-DD (date range), source:arxiv (origin filter). "
            "Combine freely: \"transformer #AI source:arxiv after:2024-01-01\".\n"
            "Returns ranked results with scores, match fields, snippets, and expanded terms."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query. Supports: plain text, #tag, is:fav, after:date, before:date, source:type. Example: \"GPT-4 #AI source:arxiv after:2024-01-01\"",
                },
                "limit": {"type": "integer", "description": "Max results to return (default: 10)", "default": 10},
                "mode": {
                    "type": "string",
                    "description": "Search mode: 'keyword' (weighted fields+synonyms), 'hybrid' (BM25+semantic fusion, recommended), or 'quick' (metadata-only). Default: 'keyword'.",
                    "enum": ["keyword", "hybrid", "quick"],
                    "default": "keyword",
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
    mode = arguments.get("mode", "keyword")
    limit = arguments.get("limit", 10)
    query_str = arguments.get("query", "")

    if mode == "hybrid":
        alpha = arguments.get("alpha", 0.6)
        results = search_hybrid(query_str, limit=limit, alpha=alpha, include_raw=True)
        formatted = []
        for r in results:
            item = r["entry"].copy()
            item["_score"] = r["score"]
            item["_bm25_score"] = r.get("bm25_score", 0.0)
            item["_semantic_score"] = r.get("semantic_score", 0.0)
            item["_match_locations"] = r["match_locations"]
            if r.get("snippet"):
                item["_snippet"] = r["snippet"]
            if r.get("expanded_terms"):
                item["_expanded_terms"] = r["expanded_terms"]
            formatted.append(item)
        return jsonrpc_response(req_id, {
            "content": [{"type": "text", "text": json.dumps(formatted, ensure_ascii=False, indent=2)}]
        })
    elif mode == "quick":
        results = search_quick(query_str, limit=limit)
        return jsonrpc_response(req_id, {
            "content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]
        })
    else:  # keyword (legacy)
        deep = arguments.get("deep", True)
        if deep:
            results = search_fulltext(query_str, limit=limit, include_raw=True)
            formatted = []
            for r in results:
                item = r["entry"].copy()
                item["_score"] = r["score"]
                item["_match_locations"] = r["match_locations"]
                if r.get("snippet"):
                    item["_snippet"] = r["snippet"]
                if r.get("expanded_terms"):
                    item["_expanded_terms"] = r["expanded_terms"]
                formatted.append(item)
            return jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(formatted, ensure_ascii=False, indent=2)}]
            })
        else:
            results = search_quick(query_str, limit=limit)
            return jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]
            })


HANDLERS = {
    "sheaf_search": _handle_search,
}
