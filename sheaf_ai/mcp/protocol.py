"""MCP protocol helpers — JSON-RPC response builders."""
from __future__ import annotations

import json


def jsonrpc_response(id: int | str, result: dict) -> str:
    """Build a JSON-RPC success response."""
    return json.dumps({"jsonrpc": "2.0", "id": id, "result": result})


def jsonrpc_error(id: int | str, code: int, message: str) -> str:
    """Build a JSON-RPC error response."""
    return json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})
