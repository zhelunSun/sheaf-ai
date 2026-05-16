"""
Universal Collector — MCP Server

Agent-Native knowledge layer: lets any MCP-compatible agent query the collection.

Tools provided:
  - uc_search: Keyword search across collected knowledge
  - uc_list: List recent entries (with optional category filter)
  - uc_get: Get full details of a specific entry
  - uc_urgent: Get entries with upcoming deadlines

Usage:
  python mcp_server.py

MCP Transport: stdio (compatible with Claude Desktop, WorkBuddy, etc.)
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

DATA_DIR = PROJECT_ROOT / "data"
ENTRIES_DIR = DATA_DIR / "entries"
INDEX_FILE = DATA_DIR / "index.jsonl"
BJT = timezone(timedelta(hours=8))


# ============================================================
# Data Access Layer
# ============================================================

def _load_index() -> list:
    """Load all entries from index.jsonl"""
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
    """Load a full entry JSON by ID"""
    # Extract date prefix (YYYY-MM) to find the right directory
    date_prefix = entry_id[:7]  # "2026-05"
    month_dir = ENTRIES_DIR / date_prefix
    if not month_dir.exists():
        return None

    entry_path = month_dir / f"{entry_id}.json"
    if not entry_path.exists():
        return None

    with open(entry_path, "r", encoding="utf-8") as f:
        return json.load(f)


def search_knowledge(query: str, limit: int = 10) -> list:
    """Keyword search across collection"""
    entries = _load_index()
    query_lower = query.lower()
    results = []

    for entry in entries:
        searchable = " ".join([
            entry.get("title", ""),
            entry.get("primary_category", ""),
            entry.get("sub_category", ""),
            " ".join(entry.get("tags", [])),
            entry.get("summary", ""),
        ]).lower()
        if query_lower in searchable:
            results.append(entry)

    results.sort(key=lambda x: x.get("collected_at", ""), reverse=True)
    return results[:limit]


def list_entries(category: str = None, limit: int = 20) -> list:
    """List recent entries, optionally filtered by category"""
    entries = _load_index()

    if category:
        entries = [e for e in entries if e.get("primary_category", "").lower() == category.lower()]

    entries.sort(key=lambda x: x.get("collected_at", ""), reverse=True)
    return entries[:limit]


def get_entry(entry_id: str) -> dict | None:
    """Get full entry details by ID"""
    entry = _load_entry(entry_id)
    if not entry:
        return None

    # Also try to load the summary markdown
    summary_path = DATA_DIR / "summaries" / f"{entry_id}.md"
    if summary_path.exists():
        entry["summary_markdown"] = summary_path.read_text(encoding="utf-8")

    return entry


def get_urgent() -> list:
    """Get entries with upcoming/urgent deadlines"""
    entries = _load_index()
    results = [e for e in entries if e.get("urgency") in ("urgent", "upcoming")]
    results.sort(key=lambda x: x.get("deadline_date", "9999"), reverse=False)
    return results


# ============================================================
# MCP Protocol (stdio transport)
# ============================================================

# Tool definitions
TOOLS = [
    {
        "name": "uc_search",
        "description": "Search collected knowledge by keyword. Searches across titles, categories, tags, and summaries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keyword or phrase"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "uc_list",
        "description": "List recent knowledge entries. Optionally filter by category.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by topic (matches primary topic name)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 20)",
                    "default": 20
                }
            }
        }
    },
    {
        "name": "uc_get",
        "description": "Get full details of a specific knowledge entry by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID (format: YYYY-MM-DD_xxxxxxxx)"
                }
            },
            "required": ["entry_id"]
        }
    },
    {
        "name": "uc_urgent",
        "description": "Get knowledge entries with upcoming deadlines or time-sensitive information.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "uc_correct",
        "description": "Submit a correction to an entry's classification or summary. Used when the user disagrees with the auto-classification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID to correct"
                },
                "corrections": {
                    "type": "object",
                    "description": "Fields to correct",
                    "properties": {
                        "category_primary": {
                            "type": "string",
                            "description": "Override primary topic classification"
                        },
                        "category_sub": {"type": "string"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "importance": {
                            "type": "string",
                            "enum": ["high", "medium", "low"]
                        },
                        "summary": {"type": "string"}
                    }
                },
                "user_note": {
                    "type": "string",
                    "description": "Optional note explaining the correction"
                }
            },
            "required": ["entry_id", "corrections"]
        }
    },
    {
        "name": "uc_collect",
        "description": "Collect a new article URL into the knowledge base. Fetches, classifies, summarizes, and stores the article.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Article URL to collect"
                },
                "force": {
                    "type": "boolean",
                    "description": "Skip dedup check and force collect (default: false)",
                    "default": False
                }
            },
            "required": ["url"]
        }
    }
]


def _jsonrpc_response(id: int | str, result: dict) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id, "result": result})


def _jsonrpc_error(id: int | str, code: int, message: str) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})


def handle_request(request: dict) -> str:
    """Handle a single JSON-RPC request"""
    method = request.get("method", "")
    req_id = request.get("id", 0)
    params = request.get("params", {})

    # Initialize
    if method == "initialize":
        return _jsonrpc_response(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "universal-collector",
                "version": "0.3.1a"
            }
        })

    # List tools
    if method == "tools/list":
        return _jsonrpc_response(req_id, {"tools": TOOLS})

    # Call tool
    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "uc_search":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 10)
            results = search_knowledge(query, limit)
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "uc_list":
            category = arguments.get("category")
            limit = arguments.get("limit", 20)
            results = list_entries(category, limit)
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "uc_get":
            entry_id = arguments.get("entry_id", "")
            entry = get_entry(entry_id)
            if not entry:
                return _jsonrpc_error(req_id, -32602, f"Entry not found: {entry_id}")
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(entry, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "uc_urgent":
            results = get_urgent()
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "uc_correct":
            from feedback import submit_feedback
            entry_id = arguments.get("entry_id", "")
            corrections = arguments.get("corrections", {})
            user_note = arguments.get("user_note", "")
            result = submit_feedback(entry_id, corrections, user_note)
            if not result["success"]:
                return _jsonrpc_error(req_id, -32602, result.get("error", "Correction failed"))
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
            })

        elif tool_name == "uc_collect":
            from pipeline import process_url
            url = arguments.get("url", "")
            force = arguments.get("force", False)
            result = process_url(url, force=force)
            return _jsonrpc_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
            })

        else:
            return _jsonrpc_error(req_id, -32601, f"Unknown tool: {tool_name}")

    # Notifications (no response needed)
    if method == "notifications/initialized":
        return None

    return _jsonrpc_error(req_id, -32601, f"Unknown method: {method}")


def main():
    """Run MCP server on stdio"""
    # Reconfigure stdout for UTF-8 on Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")

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
            error = _jsonrpc_error(0, -32700, "Parse error")
            print(error, flush=True)
        except Exception as e:
            error = _jsonrpc_error(0, -32603, f"Internal error: {e}")
            print(error, flush=True)


if __name__ == "__main__":
    main()
