"""
Tests for MCP server protocol compliance.

Validates JSON-RPC message format, tool schemas, and error handling.
Uses conftest.py's isolated_data_dir fixture.
"""
import json
import pytest
from sheaf_ai.mcp_server import handle_request, TOOLS


class TestMcpProtocol:
    """Test JSON-RPC protocol basics."""

    def test_initialize_response_format(self):
        resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        parsed = json.loads(resp)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert "result" in parsed
        assert "error" not in parsed

    def test_tools_list_response(self):
        resp = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        parsed = json.loads(resp)
        tools = parsed["result"]["tools"]
        assert isinstance(tools, list)
        assert len(tools) >= 6

    def test_unknown_tool_error(self):
        resp = handle_request({
            "jsonrpc": "2.0", "id": 3,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        })
        parsed = json.loads(resp)
        assert "error" in parsed
        assert parsed["error"]["code"] == -32601

    def test_unknown_method_error(self):
        resp = handle_request({"jsonrpc": "2.0", "id": 4, "method": "foo/bar"})
        parsed = json.loads(resp)
        assert "error" in parsed
        assert parsed["error"]["code"] == -32601

    def test_notification_initialized(self):
        """notifications/initialized returns None (no response needed)."""
        resp = handle_request({
            "jsonrpc": "2.0", "id": 5,
            "method": "notifications/initialized",
        })
        assert resp is None


class TestToolSchemas:
    """Validate MCP tool schemas are well-formed."""

    @pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["name"])
    def test_tool_has_required_fields(self, tool):
        assert "name" in tool
        assert "description" in tool
        assert len(tool["description"]) > 10
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"

    @pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["name"])
    def test_tool_required_params_are_in_properties(self, tool):
        """Every required param must appear in properties."""
        required = tool["inputSchema"].get("required", [])
        properties = tool["inputSchema"].get("properties", {})
        for r in required:
            assert r in properties, f"Tool {tool['name']}: required param '{r}' missing from properties"


class TestMcpWithData:
    """Test MCP tools with isolated data (empty by default from conftest)."""

    def test_search_empty_data(self, isolated_data_dir):
        """Search on empty data returns empty list."""
        resp = handle_request({
            "jsonrpc": "2.0", "id": 10,
            "method": "tools/call",
            "params": {"name": "sheaf_search", "arguments": {"query": "AI"}},
        })
        parsed = json.loads(resp)
        assert "result" in parsed
        content = parsed["result"]["content"][0]["text"]
        results = json.loads(content)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_list_empty_data(self, isolated_data_dir):
        """List on empty data returns empty list."""
        resp = handle_request({
            "jsonrpc": "2.0", "id": 11,
            "method": "tools/call",
            "params": {"name": "sheaf_list", "arguments": {}},
        })
        parsed = json.loads(resp)
        content = parsed["result"]["content"][0]["text"]
        results = json.loads(content)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_get_missing_entry(self, isolated_data_dir):
        """Get non-existent entry returns error."""
        resp = handle_request({
            "jsonrpc": "2.0", "id": 12,
            "method": "tools/call",
            "params": {"name": "sheaf_get", "arguments": {"entry_id": "nonexistent"}},
        })
        parsed = json.loads(resp)
        assert "error" in parsed
        assert "not found" in parsed["error"]["message"].lower()

    def test_search_after_store(self, isolated_data_dir):
        """Store an article via store_article, then search via MCP finds it."""
        from sheaf_ai.storage import store_article
        td = {
            "url": "https://example.com/quantum-computing",
            "fetch_result": {"success": True, "title": "Quantum Computing Breakthrough", "text": "A new paper on quantum computing.", "method": "requests"},
            "classify_result": {"topics": [{"name": "Quantum", "confidence": 0.95}], "tags": ["quantum", "physics"], "content_type": "research", "importance": "high"},
            "summary_result": {"one_liner": "Quantum computing achieves new milestone.", "original_title": "Quantum Computing Breakthrough", "source_author": "Dr. Q", "structured": {"core_argument": "Quantum supremacy", "key_data": "1000 qubits"}},
        }
        store_article(td["url"], td["fetch_result"], td["classify_result"], td["summary_result"])

        # Search via MCP
        resp = handle_request({
            "jsonrpc": "2.0", "id": 20,
            "method": "tools/call",
            "params": {"name": "sheaf_search", "arguments": {"query": "quantum"}},
        })
        parsed = json.loads(resp)
        content = parsed["result"]["content"][0]["text"]
        results = json.loads(content)
        assert len(results) >= 1
        assert any("Quantum" in r.get("title", "") for r in results)
