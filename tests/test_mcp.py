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
        sheaf_exe = sys.executable.replace("python.exe", "Scripts/sheaf.exe")
        self._p = subprocess.Popen(
            [sheaf_exe, "mcp"],
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
            "sheaf_search", "sheaf_list", "sheaf_get", "sheaf_urgent",
            "sheaf_correct", "sheaf_collect", "sheaf_crystallize",
            "sheaf_list_cards", "sheaf_get_card",
        ]
        for name in expected:
            assert name in names, f"Missing tool: {name}"
        assert len(tools) == 9

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
