"""
Tests for MCP server protocol compliance.

Validates JSON-RPC message format, tool schemas, error handling,
and end-to-end stdio transport (real subprocess).
Uses conftest.py's isolated_data_dir fixture.
"""
import json
import os
import subprocess
import sys
import time
from unittest.mock import patch

import pytest
from sheaf_ai.mcp_server import handle_request, TOOLS
from sheaf_cards.base import KnowledgeCard


RUN_E2E = os.environ.get("SHEAF_RUN_E2E") == "1"


# --- Helper for subprocess stdio E2E ---

class McpProcess:
    """Manage a `sheaf mcp` subprocess for stdio E2E testing."""

    def __init__(self):
        # Use python -m for cross-platform compatibility — no need to locate
        # sheaf.exe (Windows) or sheaf (Linux/macOS) in the venv's Scripts/ dir.
        self._p = subprocess.Popen(
            [sys.executable, "-m", "sheaf_ai.cli", "mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.3)
        assert self._p.poll() is None, f"Server died immediately: {self._p.stderr.read()}"

    def send(self, req: dict) -> dict:
        self._p.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
        self._p.stdin.flush()
        line = self._p.stdout.readline()
        if not line:
            rc = self._p.poll()
            if rc is not None:
                err = self._p.stderr.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"MCP server died (exit={rc}). stderr: {err[:300]}")
            raise RuntimeError(f"Empty response for: {req}")
        return json.loads(line)

    def notify(self, method: str, params: dict = None):
        """Send notification (no response expected)."""
        msg = {"jsonrpc": "2.0", "method": method}
        if params:
            msg["params"] = params
        self._p.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self._p.stdin.flush()

    def close(self):
        self._p.stdin.close()
        self._p.wait(timeout=5)
        return self._p.stderr.read().decode("utf-8", errors="replace")


@pytest.fixture(scope="module")
def mcp() -> McpProcess:
    p = McpProcess()
    yield p
    p.close()


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
        assert isinstance(results, dict)
        assert results["total"] == 0
        assert results["entries"] == []

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

    def test_crystallize_card_shape(self, isolated_data_dir):
        """MCP crystallize returns the shared public card projection."""
        card = KnowledgeCard(
            card_id="card-1",
            title="Service Card",
            claim="Shared card shape",
            evidence="Evidence string",
        )
        with patch("sheaf_ai.mcp_server.card_service.crystallize_cards", return_value=[card]):
            resp = handle_request({
                "jsonrpc": "2.0", "id": 30,
                "method": "tools/call",
                "params": {"name": "sheaf_crystallize", "arguments": {"topic": "AI"}},
            })

        parsed = json.loads(resp)
        payload = json.loads(parsed["result"]["content"][0]["text"])
        assert payload["cards_generated"] == 1
        assert payload["cards"][0]["id"] == "card-1"
        assert payload["cards"][0]["card_id"] == "card-1"
        assert isinstance(payload["cards"][0]["evidence"], str)

    def test_list_cards_shape(self, isolated_data_dir):
        """MCP list cards returns the shared public card projection."""
        card = KnowledgeCard(
            card_id="card-1",
            title="Service Card",
            claim="Shared card shape",
            evidence="Evidence string",
        )
        with patch("sheaf_ai.mcp_server.card_service.list_cards", return_value=[card]):
            resp = handle_request({
                "jsonrpc": "2.0", "id": 31,
                "method": "tools/call",
                "params": {"name": "sheaf_list_cards", "arguments": {}},
            })

        parsed = json.loads(resp)
        payload = json.loads(parsed["result"]["content"][0]["text"])
        assert payload["total"] == 1
        assert payload["cards"][0]["id"] == "card-1"
        assert payload["cards"][0]["card_id"] == "card-1"
        assert isinstance(payload["cards"][0]["evidence"], str)

    def test_get_card_shape(self, isolated_data_dir):
        """MCP get card returns the shared public card projection."""
        card = KnowledgeCard(
            card_id="card-1",
            title="Service Card",
            claim="Shared card shape",
            evidence="Evidence string",
        )
        with patch("sheaf_ai.mcp_server.card_service.get_card_detail", return_value=card):
            resp = handle_request({
                "jsonrpc": "2.0", "id": 32,
                "method": "tools/call",
                "params": {"name": "sheaf_get_card", "arguments": {"card_id": "card-1"}},
            })

        parsed = json.loads(resp)
        payload = json.loads(parsed["result"]["content"][0]["text"])
        assert payload["id"] == "card-1"
        assert payload["card_id"] == "card-1"
        assert isinstance(payload["evidence"], str)


# ============================================================
# E2E tests — real subprocess stdio transport
# ============================================================

@pytest.mark.skipif(not RUN_E2E, reason="set SHEAF_RUN_E2E=1 to run subprocess MCP E2E")
class TestMcpE2E:
    """End-to-end tests via real `sheaf mcp` subprocess (stdio transport).

    This is what WorkBuddy does when registering sheaf as an MCP connector.
    """

    def test_initialize(self, mcp):
        resp = mcp.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert "error" not in resp
        result = resp["result"]
        assert result["serverInfo"]["name"] == "sheaf"
        assert result["protocolVersion"] == "2025-06-18"
        assert result["capabilities"]["tools"] == {}

    def test_tools_list(self, mcp):
        mcp.notify("notifications/initialized")
        resp = mcp.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = resp["result"]["tools"]
        names = [t["name"] for t in tools]
        expected = [
            "sheaf_search", "sheaf_list", "sheaf_get",
            "sheaf_correct", "sheaf_collect", "sheaf_collect_batch",
            "sheaf_crystallize",
            "sheaf_list_cards", "sheaf_get_card",
            "sheaf_insights",
        ]
        for name in expected:
            assert name in names, f"Missing tool: {name}"
        assert len(tools) == 10
        # Deprecated tools should NOT appear in tools/list
        deprecated = ["sheaf_urgent", "sheaf_healthcheck", "sheaf_stats"]
        for d in deprecated:
            assert d not in names, f"Deprecated tool {d} should not be in tools/list"

    def test_search_remote_sensing(self, mcp):
        resp = mcp.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "sheaf_search", "arguments": {"query": "遥感", "deep": False}}})
        results = json.loads(resp["result"]["content"][0]["text"])
        assert len(results) >= 1, "Should find at least 1 entry for '遥感'"

    def test_list_entries(self, mcp):
        resp = mcp.send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "sheaf_list", "arguments": {"limit": 5}}})
        entries = json.loads(resp["result"]["content"][0]["text"])
        assert len(entries) >= 1

    def test_get_entry(self, mcp):
        resp = mcp.send({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "sheaf_list", "arguments": {"limit": 1}}})
        entries = json.loads(resp["result"]["content"][0]["text"])
        assert len(entries) >= 1

        entry_id = entries[0]["id"]
        resp = mcp.send({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "sheaf_get", "arguments": {"entry_id": entry_id}}})
        entry = json.loads(resp["result"]["content"][0]["text"])
        assert entry["id"] == entry_id
        assert "topics" in entry

    def test_get_missing_entry(self, mcp):
        resp = mcp.send({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "sheaf_get", "arguments": {"entry_id": "nonexistent"}}})
        assert "error" in resp
        assert "not found" in resp["error"]["message"].lower()

    def test_urgent(self, mcp):
        resp = mcp.send({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {"name": "sheaf_urgent", "arguments": {}}})
        items = json.loads(resp["result"]["content"][0]["text"])
        assert isinstance(items, list)

    def test_list_cards(self, mcp):
        resp = mcp.send({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {"name": "sheaf_list_cards", "arguments": {}}})
        data = json.loads(resp["result"]["content"][0]["text"])
        assert "total" in data
        assert isinstance(data["cards"], list)

    def test_get_card(self, mcp):
        resp = mcp.send({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {"name": "sheaf_list_cards", "arguments": {}}})
        data = json.loads(resp["result"]["content"][0]["text"])
        if data["total"] > 0:
            card_id = data["cards"][0]["id"]
            resp = mcp.send({"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                "params": {"name": "sheaf_get_card", "arguments": {"card_id": card_id}}})
            card = json.loads(resp["result"]["content"][0]["text"])
            assert "id" in card
        else:
            pytest.skip("No cards available")

    def test_collect_duplicate(self, mcp):
        """Collect known duplicate URL — should detect without LLM call."""
        resp = mcp.send({"jsonrpc": "2.0", "id": 12, "method": "tools/call",
            "params": {"name": "sheaf_collect", "arguments": {
                "url": "https://mp.weixin.qq.com/s/8xKqgqT0fUP3scCgWZTc3w"
            }}})
        result = json.loads(resp["result"]["content"][0]["text"])
        assert not result["success"], "Expected duplicate detection"
        assert result["stage"] == "dedup"

    def test_ping(self, mcp):
        resp = mcp.send({"jsonrpc": "2.0", "id": 13, "method": "ping"})
        assert "error" not in resp
        assert "result" in resp

    def test_unknown_tool(self, mcp):
        resp = mcp.send({"jsonrpc": "2.0", "id": 14, "method": "tools/call",
            "params": {"name": "nonexistent", "arguments": {}}})
        assert "error" in resp
        assert resp["error"]["code"] == -32601


class TestToolDescriptions:
    """Test MCP tool descriptions have useful documentation (Issue #54)."""

    def test_search_tool_has_advanced_syntax(self):
        """sheaf_search description should mention advanced query syntax."""
        search_tool = next((t for t in TOOLS if t["name"] == "sheaf_search"), None)
        assert search_tool is not None
        desc = search_tool["description"]
        # Must mention key syntax elements
        assert "#tag" in desc, "Missing #tag syntax in search description"
        assert "after:" in desc or "before:" in desc, "Missing date filter syntax"
        assert "source:" in desc, "Missing source filter syntax"
        assert "is:fav" in desc, "Missing is:fav syntax"
        # Must mention synonym expansion
        assert "synonym" in desc.lower() or "同义" in desc, "Missing synonym expansion mention"
        # Description should be concise but informative
        assert len(desc) <= 800, f"Description too long ({len(desc)} chars), should be concise"

    def test_search_query_param_has_examples(self):
        """sheaf_search query parameter description should include usage examples."""
        search_tool = next((t for t in TOOLS if t["name"] == "sheaf_search"), None)
        query_schema = search_tool["inputSchema"]["properties"]["query"]
        desc = query_schema["description"]
        assert "example" in desc.lower() or "#tag" in desc, "Query param should have examples"

    def test_all_tools_have_descriptions(self):
        """Every tool must have a non-empty description."""
        for tool in TOOLS:
            assert tool.get("description", "").strip(), f"Tool {tool['name']} has empty description"

    def test_all_tools_have_required_params_documented(self):
        """Every required parameter must have a description."""
        for tool in TOOLS:
            schema = tool.get("inputSchema", {})
            required = schema.get("required", [])
            props = schema.get("properties", {})
            for req_param in required:
                assert req_param in props, f"Tool {tool['name']}: required param '{req_param}' missing from properties"
                assert props[req_param].get("description", "").strip(), \
                    f"Tool {tool['name']}: required param '{req_param}' has no description"



# ============================================================
# E2E-only subprocess tests — deprecated tool fallbacks + list filters
# ============================================================

@pytest.mark.skipif(not RUN_E2E, reason="set SHEAF_RUN_E2E=1 to run subprocess MCP E2E")
class TestDeprecatedToolFallbacks:
    """Test deprecated tool fallbacks and enhanced list filters via real subprocess.

    Requires SHEAF_RUN_E2E=1 because these spawn a real `sheaf mcp` process.
    Moved from TestToolDescriptions to ensure CI doesn't fail on platforms
    where the entry point binary is unavailable.
    """

    def test_deprecated_urgent_returns_data(self, mcp):
        """sheaf_urgent fallback still returns data with deprecation notice."""
        resp = mcp.send({"jsonrpc": "2.0", "id": 50, "method": "tools/call",
            "params": {"name": "sheaf_urgent", "arguments": {}}})
        data = json.loads(resp["result"]["content"][0]["text"])
        assert data.get("deprecated") is True
        assert "results" in data

    def test_deprecated_healthcheck_returns_data(self, mcp):
        """sheaf_healthcheck fallback still returns data with deprecation notice."""
        resp = mcp.send({"jsonrpc": "2.0", "id": 51, "method": "tools/call",
            "params": {"name": "sheaf_healthcheck", "arguments": {}}})
        data = json.loads(resp["result"]["content"][0]["text"])
        assert data.get("deprecated") is True
        assert "version" in data

    def test_deprecated_stats_returns_data(self, mcp):
        """sheaf_stats fallback still returns data with deprecation notice."""
        resp = mcp.send({"jsonrpc": "2.0", "id": 52, "method": "tools/call",
            "params": {"name": "sheaf_stats", "arguments": {}}})
        data = json.loads(resp["result"]["content"][0]["text"])
        assert data.get("deprecated") is True
        assert "total_entries" in data

    def test_list_returns_total_and_topics(self, mcp):
        """sheaf_list response includes total count and topics summary."""
        resp = mcp.send({"jsonrpc": "2.0", "id": 53, "method": "tools/call",
            "params": {"name": "sheaf_list", "arguments": {}}})
        data = json.loads(resp["result"]["content"][0]["text"])
        assert "total" in data
        assert "topics" in data
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_list_filter_urgent(self, mcp):
        """sheaf_list with filter='urgent' returns only deadline entries."""
        resp = mcp.send({"jsonrpc": "2.0", "id": 54, "method": "tools/call",
            "params": {"name": "sheaf_list", "arguments": {"filter": "urgent"}}})
        data = json.loads(resp["result"]["content"][0]["text"])
        assert "entries" in data
        # All returned entries should have urgency set
        for e in data["entries"]:
            assert e.get("urgency") in ("urgent", "upcoming")

    def test_list_filter_untagged(self, mcp):
        """sheaf_list with filter='untagged' returns entries without tags."""
        resp = mcp.send({"jsonrpc": "2.0", "id": 55, "method": "tools/call",
            "params": {"name": "sheaf_list", "arguments": {"filter": "untagged"}}})
        data = json.loads(resp["result"]["content"][0]["text"])
        assert "entries" in data
        for e in data["entries"]:
            assert not e.get("tags") or len(e.get("tags", [])) == 0
