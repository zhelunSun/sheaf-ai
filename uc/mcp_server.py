"""
UC MCP Server — Agent-Native knowledge layer via MCP protocol (stdio transport).

Tools: uc_search, uc_list, uc_get, uc_urgent, uc_correct, uc_collect

Usage:
    python -m uc.mcp_server
"""
import json
import sys

from uc.config import DATA_DIR, ENTRIES_DIR, INDEX_FILE, BJT, VERSION, fix_windows_encoding
from uc.query import query_collection, query_urgent as _query_urgent
from uc.search import search_fulltext, search_quick
from uc.pipeline import process_url
from uc.feedback import submit_feedback


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
        "name": "uc_search",
        "description": "Search collected knowledge by keyword. Searches across titles, categories, tags, summaries, AND full article text. Returns ranked results with relevance scores and match snippets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword or phrase"},
                "limit": {"type": "integer", "description": "Max results to return (default: 10)", "default": 10},
                "deep": {"type": "boolean", "description": "Search full article text in addition to metadata (default: true)", "default": True},
            },
            "required": ["query"],
        },
    },
    {
        "name": "uc_list",
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
        "name": "uc_get",
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
        "name": "uc_urgent",
        "description": "Get knowledge entries with upcoming deadlines or time-sensitive information.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "uc_correct",
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
        "name": "uc_collect",
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
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "sheaf", "version": VERSION},
        })

    if method == "tools/list":
        return _jsonrpc_response(req_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "uc_search":
            deep = arguments.get("deep", True)
            limit = arguments.get("limit", 10)
            query_str = arguments.get("query", "")

            if deep:
                results = search_fulltext(query_str, limit=limit, include_raw=True)
                # Format with scores and snippets for Agent consumption
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

        elif tool_name == "uc_list":
            results = list_entries(arguments.get("category"), arguments.get("limit", 20))
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "uc_get":
            entry = get_entry(arguments.get("entry_id", ""))
            if not entry:
                return _jsonrpc_error(req_id, -32602, f"Entry not found: {arguments.get('entry_id')}")
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(entry, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "uc_urgent":
            results = _query_urgent()
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "uc_correct":
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

        elif tool_name == "uc_collect":
            url = arguments.get("url", "")
            force = arguments.get("force", False)
            result = process_url(url, force=force)
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
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
