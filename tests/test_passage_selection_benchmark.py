from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = REPO_ROOT / "evals" / "passage-selection"
MANIFEST_PATH = BENCHMARK_DIR / "manifest.json"


def _load_runner() -> ModuleType:
    module_name = "_test_passage_selection_benchmark_runner"
    spec = importlib.util.spec_from_file_location(module_name, BENCHMARK_DIR / "run_benchmark.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load passage-selection benchmark runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner()


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_manifest_locks_physically_separate_ranker_and_evaluator_inputs() -> None:
    manifest = RUNNER.verify_manifest(MANIFEST_PATH)
    ranker_files = manifest["ranker_visible_files"]
    evaluator_files = manifest["evaluator_only_files"]

    assert set(ranker_files).isdisjoint(evaluator_files)
    assert ranker_files == ["ranker_inputs.jsonl"]
    assert evaluator_files == ["evaluator_gold.jsonl"]

    ranker_rows = _read_jsonl(BENCHMARK_DIR / "ranker_inputs.jsonl")
    gold_rows = _read_jsonl(BENCHMARK_DIR / "evaluator_gold.jsonl")
    assert all("gold_spans" not in row and "required_facts" not in row for row in ranker_rows)
    assert all("body" not in row and "entry" not in row for row in gold_rows)


def test_manifest_rejects_input_byte_drift(tmp_path: Path) -> None:
    copied = tmp_path / "passage-selection"
    shutil.copytree(BENCHMARK_DIR, copied)
    ranker_path = copied / "ranker_inputs.jsonl"
    ranker_path.write_text(ranker_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Manifest hash mismatch"):
        RUNNER.verify_manifest(copied / "manifest.json")


def test_gold_spans_resolve_exactly_without_being_present_in_ranker_schema() -> None:
    ranker_rows = {
        row["case_id"]: row for row in _read_jsonl(BENCHMARK_DIR / "ranker_inputs.jsonl")
    }
    gold_rows = _read_jsonl(BENCHMARK_DIR / "evaluator_gold.jsonl")

    for gold in gold_rows:
        body = ranker_rows[gold["case_id"]]["body"]
        assert isinstance(body, str)
        for span in gold["gold_spans"]:
            assert body[span["start"] : span["end"]] == span["text"]


def test_frozen_ablation_reports_hits_recall_budget_and_determinism() -> None:
    first = RUNNER.run_benchmark(MANIFEST_PATH)
    second = RUNNER.run_benchmark(MANIFEST_PATH)
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second
    assert first["status"] == "synthetic_diagnostic"
    assert first["isolation"]["gold_loaded_after_ranking"] is True

    results = {item["strategy"]: item for item in first["results"]}
    assert set(results) == {
        "head_truncation",
        "stratified_fallback",
        "current_relevance_mmr",
    }
    expected = {
        "head_truncation": (0.5, 3 / 7),
        "stratified_fallback": (0.25, 1 / 7),
        "current_relevance_mmr": (1.0, 4 / 7),
    }
    for strategy, (evidence_hit, span_recall) in expected.items():
        aggregate = results[strategy]["aggregate"]
        assert aggregate["evidence_hit_rate"] == pytest.approx(evidence_hit)
        assert aggregate["span_recall"] == pytest.approx(span_recall)
        assert aggregate["required_fact_recall"] == pytest.approx(span_recall)
        assert aggregate["budget_compliance_rate"] == 1.0
        assert aggregate["determinism_rate"] == 1.0
        assert 0.0 < aggregate["mean_budget_utilisation"] <= 1.0

    current_cases = {case["case_id"]: case for case in results["current_relevance_mmr"]["cases"]}
    assert current_cases["no_lexical_signal"]["observed_strategy"] == "stratified_fallback"
