"""Governance notices survive compact views; no metadata becomes authority."""
import argparse
from dataclasses import replace
import json
from unittest.mock import patch

import pytest

from sheaf_ai.card_governance import memory_status
from sheaf_ai.card_service import project_memory_version
from sheaf_ai._evidence_memory_models import CardVersion, EvidenceStrength
from sheaf_ai.renderer import CardOutputConfig, CardRenderer
from sheaf_cards.base import KnowledgeCard


def projected_card(state="contested"):
    strength = EvidenceStrength(0.7, "medium", "evidence-rule-v3", 1, 1, (("B", 1),), 0, ())
    version = CardVersion("v-test", "card-test", 1, "Methods", "A claim", "Use method A.",
                          "Review source", (), (), state, (), "evt-test", "2026-09-04", strength)
    return project_memory_version(version)


@pytest.mark.parametrize("state", ["active", "contested", "retired", "superseded"])
@pytest.mark.parametrize("config", [CardOutputConfig(), CardOutputConfig.compact(),
                                   CardOutputConfig.list_view(), CardOutputConfig.detailed(),
                                   CardOutputConfig().apply_field_filter(fields_include=["title"])])
def test_version_state_and_strength_survive_every_builtin_view(state, config):
    public = projected_card(state)
    card = KnowledgeCard.from_dict(public)
    renderer = CardRenderer(replace(config))
    assert public["memory_status"]["state"] == state
    assert public["memory_status"]["metadata_valid"] is True
    for render in (renderer.render, lambda c, format: renderer.render_list([c], format=format)):
        for format in ("text", "detailed", "json"):
            output = render(card, format=format)
            assert state in output and "v-test" in output
            assert "70%" not in output
            if format == "json":
                data = json.loads(output)
                data = data["cards"][0] if "cards" in data else data
                assert data["memory_status"]["evidence_strength"]["is_probability"] is False
            else:
                assert "not a probability" in output


@pytest.mark.parametrize("change", [
    lambda c: c.provenance.pop("memory_state"),
    lambda c: c.provenance.update(memory_state="invented"),
    lambda c: c.provenance.update(memory_revision=True),
    lambda c: c.provenance.update(is_probability=True),
    lambda c: c.extra["evidence_governance"].update(state="active"),
    lambda c: c.extra["evidence_governance"]["strength"].update(score=0.9),
])
def test_incomplete_or_inconsistent_metadata_is_visible_not_silently_active(change):
    card = KnowledgeCard.from_dict(projected_card())
    change(card)
    status = memory_status(card)
    assert status["state"] == "unknown"
    assert status["metadata_valid"] is False
    assert status["state_requires_review"] is True
    assert status["evidence_strength"]["score"] is None
    assert "inspect the ledger" in CardRenderer().render(card)


def test_ordinary_card_not_enrolled_and_recorded_status_not_live_authority():
    ordinary = KnowledgeCard(claim="Simple card", confidence=0.7)
    assert memory_status(ordinary) is None
    assert "memory_status" not in json.loads(CardRenderer().render(ordinary, "json"))
    governed = KnowledgeCard.from_dict(projected_card("active"))
    assert "ledger_not_revalidated" in memory_status(governed)["verification"]
    assert "source support" in CardRenderer().render(governed).lower()


def test_cli_mcp_and_http_preserve_public_notice(capsys):
    from sheaf_ai.cli import _memory_command
    from sheaf_ai.mcp.cards import _handle_memory_snapshot

    payload = {"cards": [projected_card()], "states": {"contested": [projected_card()]}}
    with patch("sheaf_ai.card_service.get_memory_snapshot", return_value=payload):
        _memory_command(argparse.Namespace(memory_command="snapshot", topic="Methods"))
        assert json.loads(capsys.readouterr().out)["cards"][0]["memory_status"]["state"] == "contested"
        mcp = json.loads(_handle_memory_snapshot(1, {"topic": "Methods"}))["result"]
        assert json.loads(mcp["content"][0]["text"])["cards"][0]["memory_status"]["state"] == "contested"
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from sheaf_ai.api import create_app

        response = TestClient(create_app(), base_url="http://localhost").get(
            "/memory/snapshot", params={"topic": "Methods"}
        )
        assert response.status_code == 200
        assert response.json()["cards"][0]["memory_status"]["state"] == "contested"


def test_initial_snapshot_read_does_not_create_ledger(isolated_data_dir):
    from sheaf_ai.card_service import get_memory_snapshot, EVIDENCE_MEMORY_LEDGER_NAME

    assert get_memory_snapshot()["event_count"] == 0
    assert not (isolated_data_dir / EVIDENCE_MEMORY_LEDGER_NAME).exists()


def test_http_snapshot_fails_closed_on_corrupt_ledger(isolated_data_dir):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from sheaf_ai.api import create_app
    from sheaf_ai.card_service import EVIDENCE_MEMORY_LEDGER_NAME

    path = isolated_data_dir / EVIDENCE_MEMORY_LEDGER_NAME
    path.write_text("corrupt", encoding="utf-8")
    response = TestClient(create_app(), base_url="http://localhost").get("/memory/snapshot")
    assert response.status_code == 500
    assert path.read_text() == "corrupt"
