"""Tests for Sheaf HTTP API layer."""
import json
import pytest
from unittest.mock import patch, MagicMock

# fastapi is an optional [server] dependency — skip entire module if missing
pytest.importorskip("fastapi", reason="fastapi not installed (optional [server] dep)")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    """Create a test client for the API."""
    from sheaf_ai.api import create_app
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_index_file(tmp_path, monkeypatch):
    """Create a mock index.jsonl with sample data."""
    from sheaf_ai import config
    index = tmp_path / "index.jsonl"
    entries = [
        {"id": "2026-05-01", "title": "Test AI Article", "topics": ["AI", "LLM"], "category": "tech"},
        {"id": "2026-05-02", "title": "Test Remote Sensing", "topics": ["Remote Sensing"], "category": "science"},
        {"id": "2026-05-03", "title": "Another AI Piece", "topics": ["AI"], "category": "tech"},
    ]
    with open(index, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    monkeypatch.setattr(config, "INDEX_FILE", index)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ENTRIES_DIR", tmp_path / "entries")
    return index


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"]  # version string present


class TestStatsEndpoint:
    def test_stats_returns_counts(self, client, mock_index_file):
        resp = client.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_entries"] == 3
        assert isinstance(data["topics"], dict)
        assert data["version"]


class TestSearchEndpoint:
    def test_search_with_query(self, client, mock_index_file):
        resp = client.get("/search", params={"q": "AI"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "AI"
        assert isinstance(data["results"], list)

    def test_search_missing_query(self, client):
        resp = client.get("/search")
        assert resp.status_code == 422  # Validation error


class TestEntriesEndpoint:
    def test_list_entries(self, client, mock_index_file):
        resp = client.get("/entries", params={"limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["entries"]) <= 10

    def test_list_entries_pagination(self, client, mock_index_file):
        resp = client.get("/entries", params={"limit": 2, "offset": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 2

    def test_get_entry_not_found(self, client, mock_index_file, tmp_path):
        resp = client.get("/entries/nonexistent-id")
        assert resp.status_code == 404


class TestCollectEndpoint:
    @patch("sheaf_ai.api.process_url")
    def test_collect_success(self, mock_process, client):
        mock_process.return_value = {
            "success": True,
            "entry_id": "2026-05-test",
            "url": "https://example.com",
            "topics": ["AI"],
            "one_liner": "Test summary",
        }
        resp = client.post("/collect", json={"url": "https://example.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["entry_id"] == "2026-05-test"

    @patch("sheaf_ai.api.process_url")
    def test_collect_failure(self, mock_process, client):
        mock_process.return_value = {
            "success": False,
            "error": "Fetch failed",
        }
        resp = client.post("/collect", json={"url": "https://bad-url.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    @patch("sheaf_ai.api.process_url")
    def test_collect_with_force(self, mock_process, client):
        mock_process.return_value = {"success": True, "entry_id": "test"}
        resp = client.post("/collect", json={"url": "https://example.com", "force": True})
        assert resp.status_code == 200
        mock_process.assert_called_once_with(
            url="https://example.com", manual_text=None, force=True,
        )


class TestCrystallizeEndpoint:
    @patch("sheaf_ai.api.crystallize_and_save")
    def test_crystallize_success(self, mock_cryst, client):
        mock_cryst.return_value = [MagicMock(title="Test Card", confidence=0.9)]
        resp = client.post("/crystallize", json={"topic": "AI"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @patch("sheaf_ai.api.crystallize_and_save")
    def test_crystallize_error(self, mock_cryst, client):
        mock_cryst.side_effect = Exception("No API key")
        resp = client.post("/crystallize", json={"topic": "AI"})
        assert resp.status_code == 500


class TestCardsEndpoint:
    @patch("sheaf_ai.api.list_crystallized")
    def test_list_cards(self, mock_list, client):
        mock_card = MagicMock()
        mock_card.card_id = "card-1"
        mock_card.title = "Test Card"
        mock_card.confidence = 0.9
        mock_card.evidence = []
        mock_list.return_value = [mock_card]

        resp = client.get("/cards")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["cards"][0]["title"] == "Test Card"

    @patch("sheaf_ai.api.get_card")
    def test_get_card_detail(self, mock_get, client):
        mock_card = MagicMock()
        mock_card.card_id = "card-1"
        mock_card.title = "Test Card"
        mock_card.confidence = 0.9
        mock_card.evidence = []
        mock_get.return_value = mock_card

        resp = client.get("/cards/card-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Card"

    @patch("sheaf_ai.api.get_card")
    def test_get_card_not_found(self, mock_get, client):
        mock_get.return_value = None
        resp = client.get("/cards/nonexistent")
        assert resp.status_code == 404


class TestDocsEndpoint:
    def test_openapi_docs(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_openapi_json(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        assert "/health" in schema["paths"]
        assert "/collect" in schema["paths"]
        assert "/search" in schema["paths"]
        assert "/cards" in schema["paths"]


class TestServeCLI:
    def test_serve_command_in_parser(self):
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        # Parse serve command
        args = parser.parse_args(["serve", "--port", "9000"])
        assert args.command == "serve"
        assert args.port == 9000
        assert args.host == "127.0.0.1"

    def test_serve_default_port(self):
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["serve"])
        assert args.port == 8321


class TestMCPTransport:
    """Test MCP Streamable HTTP transport endpoints."""

    def _init_session(self, client):
        """Helper: initialize an MCP session and return session ID."""
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        })
        assert resp.status_code == 200
        sid = resp.headers.get("mcp-session-id")
        assert sid, "Session ID should be returned"
        data = resp.json()
        assert data["result"]["serverInfo"]["name"] == "sheaf"
        return sid

    def test_initialize_creates_session(self, client):
        sid = self._init_session(client)
        assert len(sid) == 32  # token_hex(16) = 32 chars

    def test_protocol_version_header(self, client):
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "t", "version": "1"}},
        })
        assert resp.headers.get("mcp-protocol-version") == "2025-06-18"

    def test_tools_list(self, client):
        sid = self._init_session(client)
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
        }, headers={"mcp-session-id": sid})
        assert resp.status_code == 200
        tools = resp.json()["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "sheaf_search" in tool_names
        assert "sheaf_collect" in tool_names
        assert "sheaf_crystallize" in tool_names

    def test_tool_call_search(self, client, mock_index_file):
        sid = self._init_session(client)
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "sheaf_search", "arguments": {"query": "AI", "limit": 5}},
        }, headers={"mcp-session-id": sid})
        assert resp.status_code == 200
        content = resp.json()["result"]["content"]
        assert len(content) > 0

    def test_notification_returns_202(self, client):
        sid = self._init_session(client)
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "method": "notifications/initialized",
        }, headers={"mcp-session-id": sid})
        assert resp.status_code == 202

    def test_get_opens_sse_stream(self, client):
        sid = self._init_session(client)
        resp = client.get("/mcp", headers={"mcp-session-id": sid})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_delete_terminates_session(self, client):
        sid = self._init_session(client)
        resp = client.delete("/mcp", headers={"mcp-session-id": sid})
        assert resp.status_code == 204

        # Subsequent request with same session should 404
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/list",
        }, headers={"mcp-session-id": sid})
        assert resp.status_code == 404

    def test_invalid_session_rejected(self, client):
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/list",
        }, headers={"mcp-session-id": "nonexistent"})
        assert resp.status_code == 404

    def test_origin_security_blocks_remote(self, client):
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "evil", "version": "1"}},
        }, headers={"origin": "https://evil.com"})
        assert resp.status_code == 403

    def test_origin_allows_localhost(self, client):
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "good", "version": "1"}},
        }, headers={"origin": "http://localhost:3000"})
        assert resp.status_code == 200

    def test_mcp_endpoint_in_openapi(self, client):
        resp = client.get("/openapi.json")
        paths = resp.json()["paths"]
        assert "/mcp" in paths
