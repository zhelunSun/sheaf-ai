"""Sheaf MCP subpackage — domain-split MCP tools.

Import ``handle_request`` and ``main`` from ``sheaf_ai.mcp.server``,
or use the backward-compatible ``sheaf_ai.mcp_server`` wrapper.
"""
from sheaf_ai.mcp.server import handle_request, main, TOOLS

__all__ = ["handle_request", "main", "TOOLS"]
