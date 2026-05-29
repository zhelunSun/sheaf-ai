"""
Sheaf MCP Server — Agent-Native knowledge layer via MCP protocol (stdio transport).

Tools: sheaf_search, sheaf_list, sheaf_get, sheaf_urgent, sheaf_correct, sheaf_collect

Usage:
    sheaf --mcp
"""
import json
import sys

from sheaf_ai.config import DATA_DIR, ENTRIES_DIR, INDEX_FILE, VERSION, fix_windows_encoding
from sheaf_ai.query import query_urgent as _query_urgent
from sheaf_ai.search import search_fulltext, search_hybrid, search_quick
from sheaf_ai.pipeline import process_url
from sheaf_ai.feedback import submit_feedback
from sheaf_ai import card_service

MCP_PROTOCOL_VERSION = "2025-06-18"


# ============================================================
# Data Access Layer
# ============================================================

def _load_index() -> list:
    if not INDEX_FILE.exists():
        return []
    entries = []
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _load_entry(entry_id: str) -> dict | None:
    date_prefix = entry_id[:7]
    month_dir = ENTRIES_DIR / date_prefix
    if not month_dir.exists():
        return None
    entry_path = month_dir / f"{entry_id}.json"
    if not entry_path.exists():
        return None
    with open(entry_path, "r", encoding="utf-8") as f:
        return json.load(f)


def search_knowledge(query: str, limit: int = 10) -> list:
    entries = _load_index()
    query_lower = query.lower()
    results = []
    for entry in entries:
        topics = entry.get("topics", [])
        topic_names = " ".join(
            t.get("name", t) if isinstance(t, dict) else t for t in topics
        )
        searchable = " ".join([
            entry.get("title", ""),
            topic_names,
            entry.get("primary_category", ""),
            " ".join(entry.get("tags", [])),
            entry.get("summary", ""),
        ]).lower()
        if query_lower in searchable:
            results.append(entry)
    results.sort(key=lambda x: x.get("collected_at", ""), reverse=True)
    return results[:limit]


def list_entries(category: str = None, limit: int = 20) -> list:
    entries = _load_index()
    if category:
        entries = [e for e in entries if e.get("primary_category", "").lower() == category.lower()]
    entries.sort(key=lambda x: x.get("collected_at", ""), reverse=True)
    return entries[:limit]


def get_entry(entry_id: str) -> dict | None:
    entry = _load_entry(entry_id)
    if not entry:
        return None
    summary_path = DATA_DIR / "summaries" / f"{entry_id}.md"
    if summary_path.exists():
        entry["summary_markdown"] = summary_path.read_text(encoding="utf-8")
    return entry


# ============================================================
# MCP Protocol (stdio transport)
# ============================================================

TOOLS = [
    {
        "name": "sheaf_search",
        "description": "Search collected knowledge by keyword or semantic meaning. Supports three modes: (1) 'keyword' — weighted field matching, (2) 'hybrid' — BM25 + semantic embedding fusion for best recall+precision (recommended), (3) 'quick' — metadata-only fast path. Returns ranked results with relevance scores and match snippets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword or phrase"},
                "limit": {"type": "integer", "description": "Max results to return (default: 10)", "default": 10},
                "mode": {
                    "type": "string",
                    "description": "Search mode: 'keyword' (legacy weighted), 'hybrid' (BM25+semantic, recommended), or 'quick' (metadata-only). Default: 'keyword'.",
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
    {
        "name": "sheaf_list",
        "description": "List recent knowledge entries. Optionally filter by category.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filter by topic (matches primary topic name)"},
                "limit": {"type": "integer", "description": "Max results (default: 20)", "default": 20},
            },
        },
    },
    {
        "name": "sheaf_get",
        "description": "Get full details of a specific knowledge entry by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "Entry ID (format: YYYY-MM-DD_xxxxxxxx)"},
            },
            "required": ["entry_id"],
        },
    },
    {
        "name": "sheaf_urgent",
        "description": "Get knowledge entries with upcoming deadlines or time-sensitive information.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "sheaf_correct",
        "description": "Submit a correction to an entry's classification or summary.",
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
        "name": "sheaf_crystallize",
        "description": "Crystallize knowledge cards from collected entries about a topic. Synthesizes insights from 3+ related entries into structured knowledge cards with evidence tracing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to crystallize (e.g. 'AI', '遥感', 'open source')"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "sheaf_list_cards",
        "description": "List crystallized knowledge cards. Optionally filter by topic.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Filter by topic (optional)"},
            },
        },
    },
    {
        "name": "sheaf_get_card",
        "description": "Get full details of a specific knowledge card by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "Card ID"},
            },
            "required": ["card_id"],
        },
    },
]


def _jsonrpc_response(id: int | str, result: dict) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id, "result": result})


def _jsonrpc_error(id: int | str, code: int, message: str) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})


def handle_request(request: dict) -> str | None:
    method = request.get("method", "")
    req_id = request.get("id", 0)
    params = request.get("params", {})

    if method == "initialize":
        return _jsonrpc_response(req_id, {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "sheaf", "version": VERSION},
        })

    if method == "ping":
        return _jsonrpc_response(req_id, {})

    if method == "tools/list":
        return _jsonrpc_response(req_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "sheaf_search":
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
                    formatted.append(item)
                return _jsonrpc_response(req_id, {
                    "content": [{"type": "text", "text": json.dumps(formatted, ensure_ascii=False, indent=2)}]
                })
            elif mode == "quick":
                results = search_quick(query_str, limit=limit)
                return _jsonrpc_response(req_id, {
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
                        formatted.append(item)
                    return _jsonrpc_response(req_id, {
                        "content": [{"type": "text", "text": json.dumps(formatted, ensure_ascii=False, indent=2)}]
                    })
                else:
                    results = search_quick(query_str, limit=limit)
                    return _jsonrpc_response(req_id, {
                        "content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]
                    })

        elif tool_name == "sheaf_list":
            results = list_entries(arguments.get("category"), arguments.get("limit", 20))
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "sheaf_get":
            entry = get_entry(arguments.get("entry_id", ""))
            if not entry:
                return _jsonrpc_error(req_id, -32602, f"Entry not found: {arguments.get('entry_id')}")
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(entry, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "sheaf_urgent":
            results = _query_urgent()
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "sheaf_correct":
            result = submit_feedback(
                arguments.get("entry_id", ""),
                arguments.get("corrections", {}),
                arguments.get("user_note", ""),
            )
            if not result["success"]:
                return _jsonrpc_error(req_id, -32602, result.get("error", "Correction failed"))
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "sheaf_collect":
            url = arguments.get("url", "")
            force = arguments.get("force", False)
            # Suppress pipeline print() — they corrupt JSON-RPC stdio transport
            _stdout = sys.stdout
            sys.stdout = sys.stderr
            try:
                result = process_url(url, force=force)
            finally:
                sys.stdout = _stdout
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "sheaf_crystallize":
            topic = arguments.get("topic", "")
            if not topic:
                return _jsonrpc_error(req_id, -32602, "Missing required parameter: topic")
            try:
                cards = card_service.crystallize_cards(topic)
                card_data = [card_service.card_to_public_dict(c) for c in cards]
                return _jsonrpc_response(req_id, {
                    "content": [{"type": "text", "text": json.dumps({
                        "topic": topic,
                        "cards_generated": len(cards),
                        "cards": card_data,
                    }, ensure_ascii=False, indent=2)}]
                })
            except Exception as e:
                return _jsonrpc_error(req_id, -32603, f"Crystallization failed: {e}")

        elif tool_name == "sheaf_list_cards":
            topic = arguments.get("topic")
            cards = card_service.list_cards(topic=topic)
            card_data = [card_service.card_to_public_dict(c) for c in cards]
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps({
                    "total": len(card_data),
                    "cards": card_data,
                }, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "sheaf_get_card":
            card_id = arguments.get("card_id", "")
            card = card_service.get_card_detail(card_id)
            if not card:
                return _jsonrpc_error(req_id, -32602, f"Card not found: {card_id}")
            return _jsonrpc_response(req_id, {
                "content": [{
                    "type": "text",
                    "text": json.dumps(
                        card_service.card_to_public_dict(card),
                        ensure_ascii=False,
                        indent=2,
                    ),
                }]
            })

        else:
            return _jsonrpc_error(req_id, -32601, f"Unknown tool: {tool_name}")

    if method == "notifications/initialized":
        return None

    return _jsonrpc_error(req_id, -32601, f"Unknown method: {method}")


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
            print(_jsonrpc_error(0, -32700, "Parse error"), flush=True)
        except Exception as e:
            print(_jsonrpc_error(0, -32603, f"Internal error: {e}"), flush=True)


if __name__ == "__main__":
    main()
