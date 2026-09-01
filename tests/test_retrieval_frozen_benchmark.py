from __future__ import annotations

import json
import hashlib
import runpy
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "evals" / "retrieval-frozen"
RUNNER = runpy.run_path(str(EVAL_ROOT / "run_benchmark.py"))
FIXTURE_DIR = RUNNER["FIXTURE_DIR"]
LEGACY_FIXTURE_DIR = RUNNER["LEGACY_FIXTURE_DIR"]


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "fixture"
    target.mkdir()
    for name in ("corpus.jsonl", "queries.jsonl", "qrels.jsonl", "manifest.json"):
        shutil.copy2(FIXTURE_DIR / name, target / name)
    return target


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _refresh_manifest_hash(fixture: Path, filename: str) -> None:
    manifest_path = fixture / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][filename]["sha256"] = hashlib.sha256(
        (fixture / filename).read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_frozen_retrieval_dataset_is_valid_and_gold_is_separate() -> None:
    dataset = RUNNER["load_and_validate_dataset"](FIXTURE_DIR)
    assert len(dataset.corpus) >= 20
    assert len(dataset.queries) >= 30
    assert set(dataset.hashes) == {"corpus", "queries", "qrels"}
    assert dataset.revision == "2026-09-01.2"
    assert all(set(query) == {"query_id", "text"} for query in dataset.queries)
    assert all("category" in qrel for qrel in dataset.qrels)


def test_legacy_revision_remains_loadable() -> None:
    dataset = RUNNER["load_and_validate_dataset"](LEGACY_FIXTURE_DIR)

    assert dataset.revision == "2026-09-01.1"
    assert all(set(query) == {"query_id", "text", "category"} for query in dataset.queries)
    assert all("category" not in qrel for qrel in dataset.qrels)


def test_rank_generation_api_cannot_receive_qrels() -> None:
    parameters = RUNNER["generate_rankings"].__annotations__
    assert "qrels" not in parameters


def test_unknown_qrel_entry_fails_closed(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    rows = _read(fixture / "qrels.jsonl")
    rows[0]["relevance"]["unknown-entry"] = 3
    _write(fixture / "qrels.jsonl", rows)
    _refresh_manifest_hash(fixture, "qrels.jsonl")
    with pytest.raises(ValueError, match="unknown entry"):
        RUNNER["load_and_validate_dataset"](fixture)


def test_query_file_rejects_gold_fields(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    rows = _read(fixture / "queries.jsonl")
    rows[0]["relevance"] = {"atlas-v1": 3}
    _write(fixture / "queries.jsonl", rows)
    _refresh_manifest_hash(fixture, "queries.jsonl")
    with pytest.raises(ValueError, match="model-visible query fields only"):
        RUNNER["load_and_validate_dataset"](fixture)


def test_rank_generation_rejects_evaluator_category() -> None:
    dataset = RUNNER["load_and_validate_ranker_inputs"](FIXTURE_DIR)
    leaked_queries = [dict(query, category="no_answer") for query in dataset.queries]

    with pytest.raises(ValueError, match="category, split, and relevance"):
        RUNNER["generate_rankings"](
            dataset.corpus,
            leaked_queries,
            backend="local-lsa",
        )


def test_frozen_fixture_drift_fails_before_evaluation(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    rows = _read(fixture / "queries.jsonl")
    rows[0]["text"] += " silently changed"
    _write(fixture / "queries.jsonl", rows)

    with pytest.raises(ValueError, match="Frozen fixture drift"):
        RUNNER["load_and_validate_ranker_inputs"](fixture)


def test_local_lsa_runs_production_entry_index_and_reports_negative_cases() -> None:
    result = RUNNER["run_benchmark"](backend="local-lsa", fixture_dir=FIXTURE_DIR)
    assert result["status"] == "completed"
    assert result["run"]["model"] == "local-lsa-v1"
    assert result["integrity"]["production_entry_index_exercised"] is True
    assert result["integrity"]["load_sequence"] == [
        "manifest",
        "ranker_inputs",
        "rankings",
        "qrels",
        "evaluation",
    ]
    assert result["revision"] == "2026-09-01.2"
    evaluation = result["evaluation"]
    assert evaluation["selected_method"] in result["run"]["methods"]
    assert 0.0 <= evaluation["selected_min_evidence_score"] <= 1.0
    assert "no_answer_false_positive_rate" in evaluation["selected_test"]
    assert set(evaluation["test"]) == {
        "keyword",
        "semantic",
        "linear-0.25",
        "linear-0.5",
        "linear-0.75",
        "rrf-60",
    }
    assert result["integrity"]["ranker_query_schema_excludes_evaluator_labels"] is True
    gate = evaluation["query_gate_v3_posthoc"]
    assert gate["eligible_for_blind_effectiveness_claim"] is False
    assert gate["method"] == "linear-0.25"
    assert gate["min_evidence_score"] == 0.4


def test_query_gate_v3_known_cases_are_posthoc_regressions() -> None:
    result = RUNNER["run_benchmark"](backend="local-lsa", fixture_dir=FIXTURE_DIR)
    rankings = result["run"]["query_gate_v3"]["rankings"]
    diagnostics = result["run"]["query_gate_v3"]["diagnostics"]

    assert {item["entry_id"] for item in rankings["q-029"][:5]} >= {
        "atlas-timeout",
        "cedar-cdn",
    }
    assert rankings["q-035"] == []
    assert rankings["q-036"] == []
    assert diagnostics["q-035"]["retrieval_gate_reason_code"] == (
        "unsupported_modifiers"
    )
    assert diagnostics["q-036"]["retrieval_gate_reason_code"] == (
        "unsupported_modifiers"
    )
    posthoc = result["evaluation"]["query_gate_v3_posthoc"]
    assert "test" not in posthoc
    assert posthoc["eligible_for_blind_effectiveness_claim"] is False


def test_run_opens_evaluator_qrels_only_after_rankings_complete(monkeypatch) -> None:
    events: list[str] = []
    run_globals = RUNNER["run_benchmark"].__globals__
    generate = run_globals["generate_rankings"]
    load_qrels = run_globals["load_and_validate_qrels"]

    def tracked_generate(*args, **kwargs):
        assert all(set(query) == {"query_id", "text"} for query in args[1])
        events.append("rankings_started")
        result = generate(*args, **kwargs)
        events.append("rankings_completed")
        return result

    def tracked_load_qrels(*args, **kwargs):
        assert events == ["rankings_started", "rankings_completed"]
        events.append("qrels_loaded")
        return load_qrels(*args, **kwargs)

    monkeypatch.setitem(run_globals, "generate_rankings", tracked_generate)
    monkeypatch.setitem(run_globals, "load_and_validate_qrels", tracked_load_qrels)

    RUNNER["run_benchmark"](backend="local-lsa", fixture_dir=FIXTURE_DIR)
    assert events == ["rankings_started", "rankings_completed", "qrels_loaded"]
