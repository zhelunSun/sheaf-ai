"""HTTP MCP concurrency checks through the real ASGI route and dispatcher."""
from __future__ import annotations

import asyncio
import json
import threading

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed (optional [server] dep)")
httpx = pytest.importorskip("httpx", reason="httpx not installed (optional [server] dep)")


async def _wait_until_set(event: threading.Event) -> None:
    while not event.is_set():
        await asyncio.sleep(0.005)


@pytest.mark.parametrize("mode", ["json", "sse", "error"])
def test_blocked_mcp_tool_keeps_health_and_independent_request_responsive(monkeypatch, mode):
    from sheaf_ai.api import create_app
    from sheaf_ai.mcp import server
    from sheaf_ai.mcp.protocol import jsonrpc_error, jsonrpc_response

    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    expected_result = {"content": [{"type": "text", "text": "ready\n完成"}]}

    def blocked_tool(request_id, arguments):
        assert arguments == {"fixture": True}
        entered.set()
        # Only the test (after health + ping) should release this wait. The
        # watchdog also releases it so a regressed, blocking route cannot hang CI.
        release.wait()
        finished.set()
        if mode == "error":
            return jsonrpc_error(request_id, -32603, "fixture failure")
        return jsonrpc_response(request_id, expected_result)

    monkeypatch.setitem(server._search_mod.HANDLERS, "fixture_blocking_tool", blocked_tool)

    async def scenario():
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            headers = {"accept": "text/event-stream"} if mode != "json" else {}
            watchdog = threading.Timer(8, release.set)
            watchdog.daemon = True
            watchdog.start()
            slow_request = asyncio.create_task(client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": "blocked", "method": "tools/call",
                "params": {"name": "fixture_blocking_tool", "arguments": {"fixture": True}},
            }))
            try:
                await asyncio.wait_for(_wait_until_set(entered), timeout=3)
                assert not release.is_set(), "watchdog released tool: dispatcher blocked event loop"
                health, ping = await asyncio.wait_for(asyncio.gather(
                    client.get("/health"),
                    client.post("/mcp", json={"jsonrpc": "2.0", "id": "independent", "method": "ping"}),
                ), timeout=3)
                assert health.status_code == 200
                assert health.json()["status"] == "ok"
                assert ping.status_code == 200
                assert ping.json() == {"jsonrpc": "2.0", "id": "independent", "result": {}}
                assert not release.is_set(), "responsive requests only completed after tool release"
                assert not finished.is_set()
                assert not slow_request.done()
            finally:
                release.set()
                watchdog.cancel()
                # Drain the in-flight request before closing the transport or
                # undoing monkeypatches, including when a responsiveness check fails.
                slow_response = await asyncio.wait_for(slow_request, timeout=3)
            assert finished.is_set()
            assert slow_response.status_code == 200
            assert slow_response.headers["mcp-protocol-version"] == server.MCP_PROTOCOL_VERSION
            if mode == "sse":
                assert slow_response.headers["content-type"].startswith("text/event-stream")
                assert slow_response.headers["mcp-session-id"] == ""
                event_id, data, empty_one, empty_two = slow_response.text.split("\n")
                assert event_id.startswith("id: ") and len(event_id[4:]) == 16
                assert empty_one == empty_two == ""
                assert data.startswith("data: ")
                payload = json.loads(data[6:])
            else:
                # JSON-RPC errors retain JSON framing even for an SSE request.
                assert slow_response.headers["content-type"].startswith("application/json")
                payload = slow_response.json()
            if mode == "error":
                assert payload == {
                    "jsonrpc": "2.0", "id": "blocked",
                    "error": {"code": -32603, "message": "fixture failure"},
                }
            else:
                assert payload == {"jsonrpc": "2.0", "id": "blocked", "result": expected_result}

    asyncio.run(scenario())


def test_mcp_session_notification_and_sse_contracts():
    from sheaf_ai.api import create_app
    from sheaf_ai.mcp.server import MCP_PROTOCOL_VERSION

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://localhost",
        ) as client:
            initialized = await client.post("/mcp", headers={"accept": "text/event-stream"}, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {},
                           "clientInfo": {"name": "fixture", "version": "1"}},
            })
            assert initialized.status_code == 200
            assert initialized.headers["content-type"].startswith("application/json")
            session_id = initialized.headers["mcp-session-id"]
            assert len(session_id) == 32
            assert initialized.json()["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
            headers = {"mcp-session-id": session_id, "accept": "text/event-stream"}
            notification = await client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "method": "notifications/initialized",
            })
            assert notification.status_code == 202
            assert notification.content == b""
            reply = await client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 2, "method": "ping",
            })
            assert reply.headers["mcp-session-id"] == session_id
            assert reply.text.endswith("\n\n")
            assert json.loads(reply.text.split("data: ", 1)[1]) == {
                "jsonrpc": "2.0", "id": 2, "result": {},
            }
            heartbeat = await client.get("/mcp", headers=headers)
            assert heartbeat.text == 'data: {"jsonrpc": "2.0", "method": "ping"}\n\n'
            assert (await client.delete("/mcp", headers=headers)).status_code == 204
            expired = await client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 3, "method": "ping",
            })
            assert expired.status_code == 404
            assert expired.text == "Session not found"

    asyncio.run(scenario())


def test_unhandled_tool_exception_retains_http_error(monkeypatch):
    from sheaf_ai.api import create_app
    from sheaf_ai.mcp import server

    def failing_tool(_request_id, _arguments):
        raise RuntimeError("fixture failure")

    monkeypatch.setitem(server._search_mod.HANDLERS, "fixture_failing_tool", failing_tool)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(), raise_app_exceptions=False),
            base_url="http://localhost",
        ) as client:
            response = await client.post("/mcp", headers={"accept": "text/event-stream"}, json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "fixture_failing_tool", "arguments": {}},
            })
            assert response.status_code == 500
            assert response.text == "Internal Server Error"
            assert not response.headers["content-type"].startswith("text/event-stream")

    asyncio.run(scenario())
