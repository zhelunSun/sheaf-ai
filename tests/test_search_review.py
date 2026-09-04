"""Review mode restores inspectability, not semantic answerability."""
import argparse
import json
from unittest.mock import patch

import pytest

from sheaf_ai import cli, display
from sheaf_ai.mcp import search as mcp_search
from sheaf_ai.search import _review_candidate_available, search_hybrid


FEATURES = {
    "effective_evidence_mode": "coverage_semantic", "semantic_backend": "entry_index",
    "semantic_degraded": False, "query_identities": ["arbitrary"],
    "supported_modifier_count": 2, "top_evidence_score": 0.7, "top_semantic_score_raw": 0.8,
}


@pytest.mark.parametrize("reason", [
    "top_identity_mismatch", "incomplete_identity_coverage", "invalid_filter",
    "absolute_support_below_threshold", "no_candidates_in_scope", "accepted",
])
def test_review_never_overrides_other_failures(reason):
    assert not _review_candidate_available(FEATURES, reason, 0.4)


@pytest.mark.parametrize("overrides", [
    {"semantic_degraded": True}, {"semantic_backend": "card_fallback"},
    {"effective_evidence_mode": "keyword_coverage"}, {"query_identities": []},
    {"supported_modifier_count": 0}, {"top_evidence_score": 0.39},
    {"top_semantic_score_raw": 0.0},
])
def test_review_requires_healthy_scoped_evidence(overrides):
    assert not _review_candidate_available({**FEATURES, **overrides}, "unsupported_modifiers", 0.4)


@pytest.mark.parametrize("policy,threshold", [("typo", 0.4), ("review", 0.0)])
def test_invalid_review_request_fails_before_io(policy, threshold):
    with pytest.raises(ValueError, match="gate_policy"):
        search_hybrid("x", gate_policy=policy, min_evidence_score=threshold)


@pytest.mark.parametrize("contents,query,reason", [
    (None, "x", "missing_collection_index"),
    ("", "x", "empty_corpus"),
    ("", " ", "empty_query"),
])
def test_early_empty_paths_preserve_review_policy(tmp_path, monkeypatch, contents, query, reason):
    from sheaf_ai import search

    path = tmp_path / "index.jsonl"
    if contents is not None:
        path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(search, "INDEX_FILE", path)
    diagnostics = {}
    assert search_hybrid(query, min_evidence_score=0.4, gate_policy="review", diagnostics=diagnostics) == []
    assert diagnostics["retrieval_gate_policy"] == "review"
    assert diagnostics["retrieval_gate_reason_code"] == reason
    assert diagnostics["retrieval_review_available"] is False


def _withheld(*_args, diagnostics, **_kwargs):
    diagnostics.update({
        "backend": "entry_index", "degraded": False, "reason": "",
        "retrieval_gate_version": "query-support-v4", "retrieval_gate_status": "withheld",
        "retrieval_gate_policy": "strict", "retrieval_gate_reason_code": "unsupported_modifiers",
        "retrieval_gate_reason": "Lexical mismatch", "retrieval_review_available": True,
    })
    return []


def test_cli_json_and_text_do_not_lose_empty_result_reason(capsys):
    with patch("sheaf_ai.search.search_hybrid", side_effect=_withheld):
        cli._search(argparse.Namespace(query=["x"], json=True, min_evidence_score=0.4))
    gate = json.loads(capsys.readouterr().out)["retrieval_gate"]
    assert gate["reason_code"] == "unsupported_modifiers"
    assert gate["review_available"] is True
    with patch.object(display, "search_hybrid", side_effect=_withheld):
        display.show_search("x", min_evidence_score=0.4)
    text = capsys.readouterr().out
    assert "unsupported_modifiers" in text
    assert "--gate-policy review" in text
    assert "Answerability not assessed" in text


def test_mcp_text_only_and_structured_clients_both_receive_warning():
    with patch.object(mcp_search, "search_hybrid", side_effect=_withheld):
        result = json.loads(mcp_search._handle_search(1, {"query": "x"}))["result"]
    assert json.loads(result["content"][0]["text"]) == []
    text_gate = json.loads(result["content"][1]["text"])["retrieval_gate"]
    assert text_gate == result["structuredContent"]["retrieval_gate"]
    assert text_gate["answerability"] == "not_assessed"


def test_review_policy_reaches_cli_and_mcp_core(capsys):
    parsed = cli.build_parser().parse_args([
        "search", "x", "--gate-policy", "review", "--min-evidence-score", "0.4", "--json",
    ])
    with patch("sheaf_ai.search.search_hybrid", return_value=[]) as core:
        cli._search(parsed)
        assert core.call_args.kwargs["gate_policy"] == "review"
    with patch.object(mcp_search, "search_hybrid", return_value=[]) as core:
        mcp_search._handle_search(1, {"query": "x", "gate_policy": "review", "min_evidence_score": 0.4})
        assert core.call_args.kwargs["gate_policy"] == "review"


def test_review_status_survives_flattening():
    gate = {"status": "review_required", "answerability": "not_assessed"}
    result = {"entry": {"id": "e", "_retrieval_gate": "fake"}, "score": 0.8,
              "retrieval_gate": gate}
    assert mcp_search._format_ranked_results([result], hybrid=True)[0]["_retrieval_gate"] == gate
