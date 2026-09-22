"""Offline adapter contracts: diagnostics, source identity and JSON stay visible."""
import json
import sys
from unittest.mock import patch

import pytest

from sheaf_ai import card_service, cli
from sheaf_ai.card_extraction import CardExtractionResult
from sheaf_ai.mcp import cards as mcp_cards
from sheaf_cards.base import CardStore, KnowledgeCard


def _card():
    return KnowledgeCard(
        card_id="card_contract", title="Bounded claim", claim="Offline only.",
        evidence="[Source 2] supports offline use.", source_ids=["entry_original"],
        provenance={
            "source_citations": {"2": "entry_original"}, "memory_state": "contested",
            "memory_version_id": "version_1", "memory_revision": 1,
            "confidence_kind": "ordinal_evidence_strength", "is_probability": False,
        },
    )


def _cli_args(*args):
    return cli.build_parser().parse_args(["crystallize", *args, "--format", "json"])


@pytest.mark.parametrize("status,has_cards,exit_code", [
    ("success", True, 0), ("empty", False, 0),
    ("partial", True, 1), ("error", False, 3),
])
def test_generation_outcomes_have_same_public_contract(status, has_cards, exit_code, capsys):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from sheaf_ai.api import create_app

    result = CardExtractionResult(
        cards=[_card()] if has_cards else [], status=status,
        warnings=["Rejected malformed card"] if status in {"partial", "error"} else [],
        rejected_count=1 if status in {"partial", "error"} else 0,
        raw_response="PRIVATE_MODEL_RESPONSE",
    )
    expected = card_service.crystallization_to_public_dict("offline", result)
    with patch.object(card_service, "crystallize_cards_result", return_value=result):
        if exit_code:
            with pytest.raises(SystemExit) as exc:
                cli._crystallize(_cli_args("offline"))
            assert exc.value.code == exit_code
        else:
            cli._crystallize(_cli_args("offline"))
        output = capsys.readouterr().out
        assert json.loads(output) == expected
        mcp_response = json.loads(mcp_cards._handle_crystallize(1, {"topic": "offline"}))
        assert mcp_response["result"]["isError"] is (status == "error")
        assert json.loads(mcp_response["result"]["content"][0]["text"]) == expected
        with TestClient(create_app(), base_url="http://localhost") as client:
            response = client.post("/crystallize", json={"topic": "offline"})
        assert response.status_code == 200
        http_payload = response.json()
        http_payload.pop("result")  # historical human-display field
        assert http_payload == expected
    assert "PRIVATE_MODEL_RESPONSE" not in output
    assert "raw_response" not in expected
    if has_cards:
        assert expected["cards"][0]["citation_trace"]["bindings"] == [
            {"marker": "[Source 2]", "entry_id": "entry_original"},
        ]
        assert expected["cards"][0]["memory_status"]["state"] == "contested"


@pytest.mark.parametrize("flag,service_name,return_value,key", [
    ("--list", "list_cards", [], "cards"),
    ("--stats", "get_card_topic_stats", {}, "topics"),
    ("--rebuild-embeddings", "rebuild_card_embeddings", 0, "indexed"),
])
def test_cli_json_empty_and_maintenance_results(flag, service_name, return_value, key, capsys):
    with patch.object(card_service, service_name, return_value=return_value):
        cli._crystallize(_cli_args(flag))
    payload = json.loads(capsys.readouterr().out)
    assert key in payload


def test_cli_json_empty_semantic_results(capsys):
    with patch.object(card_service, "search_cards_semantic", return_value=[]):
        cli._crystallize(_cli_args("--semantic", "offline"))
    assert json.loads(capsys.readouterr().out) == {"total": 0, "results": []}


@pytest.mark.parametrize("flag,service_name", [
    ("--show", "get_card_detail"), ("--delete", "delete_card_by_id"),
])
def test_cli_missing_card_is_json_failure_not_success(flag, service_name, capsys):
    with patch.object(card_service, service_name, return_value=None):
        with pytest.raises(SystemExit) as exc:
            cli._crystallize(_cli_args(flag, "missing"))
    assert exc.value.code != 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "not found" in payload["error"]


@pytest.mark.parametrize("format_args", [["--format", "json"], ["--format=json"]])
def test_cli_explicit_json_error_on_interactive_terminal(format_args, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["sheaf", "crystallize", "topic", *format_args])
    with patch.object(sys.stdout, "isatty", return_value=True), \
         patch.object(cli, "fix_windows_encoding"), \
         patch.object(cli, "_run", side_effect=RuntimeError("provider unavailable")):
        with pytest.raises(SystemExit):
            cli.main()
    assert json.loads(capsys.readouterr().out)["success"] is False


@pytest.mark.parametrize("bad_value", [None, [], {}, 5, True, " "])
def test_mcp_invalid_card_id_is_invalid_params(bad_value):
    with patch.object(card_service.crystallize, "get_card") as backend:
        response = json.loads(mcp_cards._handle_get_card(1, {"card_id": bad_value}))
    assert response["error"]["code"] == -32602
    backend.assert_not_called()


@pytest.mark.parametrize("bad_value", [None, [], {}, 5, True])
def test_mcp_invalid_topic_is_invalid_params(bad_value):
    with patch.object(card_service.crystallize, "list_crystallized") as backend:
        response = json.loads(mcp_cards._handle_list_cards(1, {"topic": bad_value}))
    assert response["error"]["code"] == -32602
    backend.assert_not_called()


@pytest.mark.parametrize("bad_value", [None, [], {}, 5, True, " "])
def test_mcp_crystallize_rejects_invalid_topic_before_backend(bad_value):
    with patch.object(card_service.crystallize, "crystallize_and_save_result") as backend:
        response = json.loads(mcp_cards._handle_crystallize(1, {"topic": bad_value}))
    assert response["error"]["code"] == -32602
    backend.assert_not_called()


def test_service_detailed_result_delegates_without_dropping_diagnostics():
    result = CardExtractionResult(cards=[], status="error", warnings=["Invalid JSON"])
    with patch.object(card_service.crystallize, "crystallize_and_save_result", return_value=result) as backend:
        assert card_service.crystallize_cards_result("offline", auto_embed=False) is result
    assert backend.call_args.kwargs["auto_embed"] is False


def test_cli_human_output_does_not_report_invalid_json_as_insufficient_sources(capsys):
    result = CardExtractionResult(cards=[], status="error", warnings=["Invalid JSON"])
    args = cli.build_parser().parse_args(["crystallize", "offline"])
    with patch.object(card_service, "crystallize_cards_result", return_value=result):
        with pytest.raises(SystemExit) as exc:
            cli._crystallize(args)
    output = capsys.readouterr().out
    assert exc.value.code == 3
    assert "status: error" in output and "Invalid JSON" in output
    assert "Not enough related entries" not in output


@pytest.mark.parametrize("legacy", [False, True])
def test_saved_card_identity_and_state_survive_list_and_get_across_adapters(tmp_path, capsys, legacy):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from sheaf_ai.api import create_app

    card = _card()
    if legacy:
        card.provenance.pop("source_citations")
    store = CardStore(tmp_path / "cards.json")
    store.save(card)
    protected = ("claim", "evidence", "source_ids", "citation_trace", "memory_status")
    expected = card_service.card_to_public_dict(store.load(card.id))
    with patch.object(card_service.crystallize, "_get_card_store", return_value=store):
        cli._crystallize(_cli_args("--list"))
        projections = [json.loads(capsys.readouterr().out)["cards"][0]]
        cli._crystallize(_cli_args("--show", card.id))
        projections.append(json.loads(capsys.readouterr().out))
        for handler, args in ((mcp_cards._handle_list_cards, {}),
                              (mcp_cards._handle_get_card, {"card_id": card.id})):
            response = json.loads(handler(1, args))
            payload = json.loads(response["result"]["content"][0]["text"])
            projections.append(payload["cards"][0] if "cards" in payload else payload)
        with TestClient(create_app(), base_url="http://localhost") as client:
            projections.append(client.get("/cards").json()["cards"][0])
            projections.append(client.get(f"/cards/{card.id}").json())
    for projection in projections:
        assert {key: projection[key] for key in protected} == {
            key: expected[key] for key in protected
        }
    assert expected["memory_status"]["state"] == "contested"
    assert expected["citation_trace"]["status"] == ("unresolved" if legacy else "resolved")


def test_http_blank_topic_and_card_id_are_client_errors():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from sheaf_ai.api import create_app

    with patch.object(card_service.crystallize, "crystallize_and_save_result") as generate, \
         patch.object(card_service.crystallize, "get_card") as read, \
         patch.object(card_service.crystallize, "delete_card") as delete, \
         TestClient(create_app(), base_url="http://localhost") as client:
        assert client.post("/crystallize", json={"topic": " "}).status_code == 400
        assert client.get("/cards/%20").status_code == 400
        assert client.delete("/cards/%20").status_code == 400
    generate.assert_not_called()
    read.assert_not_called()
    delete.assert_not_called()
