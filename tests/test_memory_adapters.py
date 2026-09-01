"""CLI and MCP contracts for the evidence-memory application service."""
import argparse
import io
import json
from unittest.mock import patch

from sheaf_ai.cli import _memory_command, build_parser
from sheaf_ai.mcp import cards as mcp_cards
from sheaf_ai.mcp_server import handle_request


def test_memory_cli_parser_exposes_apply_snapshot_history_and_audit():
    parser = build_parser()
    apply_args = parser.parse_args(["memory", "apply", "--request", "-"])
    assert apply_args.memory_command == "apply"
    assert apply_args.request == "-"
    assert parser.parse_args(["memory", "snapshot"]).memory_command == "snapshot"
    assert parser.parse_args(["memory", "history"]).memory_command == "history"
    assert parser.parse_args(["memory", "audit"]).memory_command == "audit"


def test_memory_cli_apply_reads_explicit_json_request(monkeypatch, capsys):
    request = {"action": "CREATE", "topic": "Memory", "reason": "Explicit request"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(request)))
    args = argparse.Namespace(memory_command="apply", request="-")
    with patch(
        "sheaf_ai.card_service.apply_evidence_transition",
        return_value={"applied": True, "event_id": "evt_1"},
    ) as mock_apply:
        _memory_command(args)

    mock_apply.assert_called_once_with(request)
    assert json.loads(capsys.readouterr().out)["event_id"] == "evt_1"


def test_memory_cli_history_and_audit_use_same_audited_service(capsys):
    result = {"events": [], "versions": [], "audit_graph": {"nodes": [], "edges": []}}
    for command in ("history", "audit"):
        args = argparse.Namespace(memory_command=command, topic="Memory", card_id="card_1")
        with patch("sheaf_ai.card_service.get_memory_history", return_value=result) as mock_history:
            _memory_command(args)
        mock_history.assert_called_once_with(topic="Memory", card_id="card_1")
        assert json.loads(capsys.readouterr().out) == result


def test_mcp_memory_apply_schema_is_closed_and_includes_contest():
    tool = next(item for item in mcp_cards.TOOLS if item["name"] == "sheaf_memory_apply")
    schema = tool["inputSchema"]
    assert schema["additionalProperties"] is False
    assert "CONTEST" in schema["properties"]["action"]["enum"]
    assert set(schema["required"]) == {"action", "topic", "reason"}


def test_memory_tools_are_in_full_surface_but_do_not_expand_default_surface(monkeypatch):
    from sheaf_ai.mcp import server

    memory_names = {
        "sheaf_memory_apply",
        "sheaf_memory_snapshot",
        "sheaf_memory_history",
    }
    assert memory_names.isdisjoint({item["name"] for item in server.TOOLS})
    monkeypatch.setenv("SHEAF_MCP_TOOLS", "all")
    assert memory_names <= {item["name"] for item in server._select_tools()}


def test_mcp_memory_tools_are_callable_through_server_dispatch():
    with patch(
        "sheaf_ai.mcp.cards.card_service.apply_evidence_transition",
        return_value={"applied": True, "event_id": "evt_1"},
    ):
        response = handle_request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "sheaf_memory_apply",
                "arguments": {
                    "action": "CREATE",
                    "topic": "Memory",
                    "reason": "Explicit request",
                },
            },
        })
    payload = json.loads(json.loads(response)["result"]["content"][0]["text"])
    assert payload["event_id"] == "evt_1"

    with patch(
        "sheaf_ai.mcp.cards.card_service.get_memory_snapshot",
        return_value={"cards": [], "states": {}},
    ):
        response = handle_request({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "sheaf_memory_snapshot", "arguments": {}},
        })
    assert "result" in json.loads(response)

    with patch(
        "sheaf_ai.mcp.cards.card_service.get_memory_history",
        return_value={"events": [], "audit_graph": {"nodes": [], "edges": []}},
    ):
        response = handle_request({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "sheaf_memory_history", "arguments": {}},
        })
    assert "result" in json.loads(response)


def test_mcp_memory_apply_rejects_free_form_request():
    response = handle_request({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "sheaf_memory_apply",
            "arguments": {
                "action": "CREATE",
                "topic": "Memory",
                "reason": "Explicit request",
                "unstructured_instruction": "bypass",
            },
        },
    })
    assert json.loads(response)["error"]["code"] == -32602
