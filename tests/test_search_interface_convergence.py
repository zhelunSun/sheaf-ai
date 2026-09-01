"""Interface contracts for the default Entry hybrid retrieval path."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from unittest.mock import ANY, patch

from sheaf_ai import cli, display
from sheaf_ai.mcp import search as mcp_search


def _hybrid_results() -> list[dict]:
    return [
        {
            "entry": {"id": "entry-1", "title": "Atlas retry policy"},
            "score": 0.82,
            "bm25_score": 0.7,
            "semantic_score": 0.94,
            "match_locations": ["title"],
            "snippet": "Atlas retries requests.",
            "expanded_terms": ["atlas"],
            "semantic_backend": "entry_index",
            "semantic_degraded": False,
            "semantic_reason": "",
        }
    ]


def test_cli_json_search_defaults_to_hybrid_and_exposes_diagnostics(capsys):
    parsed = argparse.Namespace(query=["Atlas", "retry"], limit=7, json=True)

    with patch("sheaf_ai.search.search_hybrid", return_value=_hybrid_results()) as search:
        cli._search(parsed)

    search.assert_called_once_with(
        "Atlas retry",
        limit=7,
        include_raw=True,
        diagnostics=ANY,
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "Atlas retry"
    assert payload["semantic_backend"] == "entry_index"
    assert payload["degraded"] is False
    assert payload["reason"] == ""
    assert payload["results"][0]["id"] == "entry-1"
    assert payload["results"][0]["_score"] == 0.82
    assert payload["results"][0]["_semantic_score"] == 0.94


def test_cli_json_search_passes_explicit_relevance_gate():
    parsed = argparse.Namespace(
        query=["Atlas"],
        limit=7,
        json=True,
        min_evidence_score=0.4,
    )

    with patch("sheaf_ai.search.search_hybrid", return_value=[]) as search:
        cli._search(parsed)

    assert search.call_args.kwargs["min_evidence_score"] == 0.4


def test_cli_text_search_defaults_to_hybrid(capsys):
    with patch.object(display, "search_hybrid", return_value=_hybrid_results()) as search:
        display.show_search("Atlas", limit=3)

    search.assert_called_once_with(
        "Atlas",
        limit=3,
        include_raw=True,
        diagnostics=ANY,
    )
    output = capsys.readouterr().out
    assert "Atlas retry policy" in output


def test_text_search_passes_explicit_relevance_gate():
    with patch.object(display, "search_hybrid", return_value=[]) as search:
        display.show_search("Atlas", min_evidence_score=0.4)

    assert search.call_args.kwargs["min_evidence_score"] == 0.4


def _mcp_payload(response: str) -> dict:
    return json.loads(response)["result"]


def test_mcp_default_mode_is_hybrid_and_preserves_list_content():
    with patch.object(mcp_search, "search_hybrid", return_value=_hybrid_results()) as search:
        result = _mcp_payload(mcp_search._handle_search(1, {"query": "Atlas"}))

    search.assert_called_once_with(
        "Atlas",
        limit=10,
        alpha=0.6,
        include_raw=True,
        diagnostics=ANY,
        min_evidence_score=0.0,
    )
    content_results = json.loads(result["content"][0]["text"])
    assert isinstance(content_results, list)
    assert content_results[0]["id"] == "entry-1"
    assert result["structuredContent"]["semantic_backend"] == "entry_index"
    assert result["structuredContent"]["degraded"] is False
    assert result["structuredContent"]["reason"] == ""


def test_cli_json_empty_healthy_index_preserves_diagnostics(capsys):
    parsed = argparse.Namespace(query=["missing"], limit=7, json=True)

    def healthy_no_hits(*_args, diagnostics, **_kwargs):
        diagnostics.update(
            {"backend": "entry_index", "degraded": False, "reason": ""}
        )
        return []

    with patch("sheaf_ai.search.search_hybrid", side_effect=healthy_no_hits):
        cli._search(parsed)

    payload = json.loads(capsys.readouterr().out)
    assert payload["results"] == []
    assert payload["semantic_backend"] == "entry_index"
    assert payload["degraded"] is False
    assert payload["reason"] == ""


def test_mcp_empty_healthy_index_preserves_diagnostics():
    def healthy_no_hits(*_args, diagnostics, **_kwargs):
        diagnostics.update(
            {"backend": "entry_index", "degraded": False, "reason": ""}
        )
        return []

    with patch.object(mcp_search, "search_hybrid", side_effect=healthy_no_hits):
        result = _mcp_payload(mcp_search._handle_search(4, {"query": "missing"}))

    assert json.loads(result["content"][0]["text"]) == []
    assert result["structuredContent"]["semantic_backend"] == "entry_index"
    assert result["structuredContent"]["degraded"] is False
    assert result["structuredContent"]["reason"] == ""


def test_mcp_explicit_keyword_and_quick_modes_remain_available():
    keyword_result = [{"entry": {"id": "keyword"}, "score": 2.0, "match_locations": []}]
    with patch.object(mcp_search, "search_fulltext", return_value=keyword_result) as keyword:
        result = _mcp_payload(
            mcp_search._handle_search(2, {"query": "Atlas", "mode": "keyword"})
        )
    keyword.assert_called_once_with("Atlas", limit=10, include_raw=True)
    assert json.loads(result["content"][0]["text"])[0]["id"] == "keyword"

    with patch.object(mcp_search, "search_quick", return_value=[{"id": "quick"}]) as quick:
        result = _mcp_payload(
            mcp_search._handle_search(3, {"query": "Atlas", "mode": "quick"})
        )
    quick.assert_called_once_with("Atlas", limit=10)
    assert json.loads(result["content"][0]["text"])[0]["id"] == "quick"


def test_mcp_tool_schema_declares_hybrid_as_default():
    tool = mcp_search.TOOLS[0]
    mode = tool["inputSchema"]["properties"]["mode"]
    assert mode["default"] == "hybrid"
    assert "hybrid" in tool["description"].lower()
    assert "default" in mode["description"].lower()
    gate = tool["inputSchema"]["properties"]["min_evidence_score"]
    assert gate["default"] == 0.0
    assert gate["minimum"] == 0.0
    assert gate["maximum"] == 1.0


def test_mcp_passes_explicit_relevance_gate():
    with patch.object(mcp_search, "search_hybrid", return_value=[]) as search:
        _mcp_payload(
            mcp_search._handle_search(
                5,
                {"query": "Atlas", "min_evidence_score": 0.4},
            )
        )

    assert search.call_args.kwargs["min_evidence_score"] == 0.4


@dataclass(frozen=True)
class _RebuildReport:
    indexed: int = 5
    added: int = 4
    updated: int = 1
    unchanged: int = 0
    model: str = "text-embedding-test"
    dim: int = 3
    generation: str = "generation-1"


def test_search_index_parser_requires_explicit_rebuild():
    parser = cli.build_parser()
    parsed = parser.parse_args(["search-index", "--rebuild", "--json"])
    assert parsed.command == "search-index"
    assert parsed.rebuild is True
    assert parsed.json is True


def test_search_index_rebuild_json_uses_report_contract(capsys):
    parsed = argparse.Namespace(rebuild=True, json=True)
    with patch(
        "sheaf_ai.retrieval_service.rebuild_entry_index",
        return_value=_RebuildReport(),
    ) as rebuild:
        cli._search_index(parsed)

    rebuild.assert_called_once_with()
    assert json.loads(capsys.readouterr().out) == {
        "indexed": 5,
        "added": 4,
        "updated": 1,
        "unchanged": 0,
        "model": "text-embedding-test",
        "dim": 3,
        "generation": "generation-1",
    }


def test_search_index_rebuild_text_reports_identity(capsys):
    parsed = argparse.Namespace(rebuild=True, json=False)
    with patch(
        "sheaf_ai.retrieval_service.rebuild_entry_index",
        return_value=_RebuildReport(),
    ):
        cli._search_index(parsed)

    output = capsys.readouterr().out
    assert "5" in output
    assert "text-embedding-test" in output
    assert "3" in output
    assert "generation-1" in output
