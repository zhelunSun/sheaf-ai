"""Prospective evaluation integrity tests, isolated from any old gold fixtures."""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("retrieval_prospective", ROOT / "evals/retrieval-prospective/run_benchmark.py")
prospective = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prospective
SPEC.loader.exec_module(prospective)


def empty_rankings(queries):
    return {"methods": {method: {query["query_id"]: [] for query in queries} for method in prospective.METHODS},
            "diagnostics": {query["query_id"]: {"semantic_backend": "entry_index", "semantic_degraded": False}
                            for query in queries}}


def test_frozen_design_and_evaluator_only_labels():
    manifest = prospective.load_manifest(prospective.FIXTURE_DIR)
    dataset = prospective.load_ranker_dataset(prospective.FIXTURE_DIR, manifest)
    assert len(dataset["corpus"]) == 28
    assert len(dataset["queries"]) == 24
    assert all(set(row) == {"query_id", "text"} for row in dataset["queries"])
    qrels = prospective.load_qrels(prospective.FIXTURE_DIR, manifest, dataset)
    assert sum(not row["relevance"] for row in qrels) == 8
    assert {row["split"] for row in qrels} == {"holdout"}
    assert all(set(row) == {"query_id", "split", "category", "relevance"} for row in qrels)


def test_no_qrels_open_or_hash_until_every_ranking_finishes(monkeypatch):
    phase = {"rankings_complete": False, "gold_opens": 0}
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if path.name == "qrels.jsonl":
            assert phase["rankings_complete"], "qrels accessed before all rankings finished"
            phase["gold_opens"] += 1
        return original_open(path, *args, **kwargs)

    def rank(corpus, queries):
        assert phase["gold_opens"] == 0
        assert all(set(query) == {"query_id", "text"} for query in queries)
        result = empty_rankings(queries)
        assert len(corpus) == 28
        assert all(len(rows) == 24 for rows in result["methods"].values())
        phase["rankings_complete"] = True
        return result

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(prospective, "generate_rankings", rank)
    monkeypatch.setattr(prospective, "code_snapshot", lambda: {})
    report = prospective.run_benchmark()
    assert phase["gold_opens"] >= 2  # Hashing and parsing must both be guarded.
    assert report["integrity"]["load_sequence"].index("all_rankings") < report["integrity"]["load_sequence"].index("qrels")
    assert report["evaluation"]["fixed-gate"]["false_rejection_count"] == 16


def test_incomplete_rankings_fail_before_gold(monkeypatch):
    def rank(corpus, queries):
        result = empty_rankings(queries)
        result["methods"]["fixed-gate"].pop("q-024")
        return result

    def forbidden_gold(*args, **kwargs):
        pytest.fail("Incomplete rankings must not reach qrels")

    monkeypatch.setattr(prospective, "generate_rankings", rank)
    monkeypatch.setattr(prospective, "load_qrels", forbidden_gold)
    monkeypatch.setattr(prospective, "code_snapshot", lambda: {})
    with pytest.raises(ValueError, match="All query rankings"):
        prospective.run_benchmark()


@pytest.mark.parametrize("label", ["category", "split", "relevance"])
def test_ranker_rejects_evaluator_labels_before_import(label, monkeypatch):
    def forbidden_import():
        pytest.fail("Labels must be rejected before importing the ranking implementation")

    monkeypatch.setattr(prospective, "import_frozen_runner", forbidden_import)
    with pytest.raises(ValueError, match="only query_id and text"):
        prospective.generate_rankings([], [{"query_id": "q-001", "text": "query", label: "leaked"}])


def test_ranker_loader_rejects_label_bearing_queries(monkeypatch):
    manifest = prospective.load_manifest(prospective.FIXTURE_DIR)
    original_read = prospective.read_jsonl

    def read(path):
        rows = original_read(path)
        if path.name == "queries.jsonl":
            rows = tuple({**row, "category": "leaked"} for row in rows)
        return rows

    monkeypatch.setattr(prospective, "read_jsonl", read)
    with pytest.raises(ValueError, match="evaluator labels prohibited"):
        prospective.load_ranker_dataset(prospective.FIXTURE_DIR, manifest)


def test_fixed_parameters_and_no_other_alpha_execution(monkeypatch):
    query = {"query_id": "q-001", "text": "example"}
    fake = SimpleNamespace(QUERY_GATE_V3_ALPHA=0.25, QUERY_GATE_V3_THRESHOLD=0.4,
                           TOP_K=5, RANKING_DEPTH=10, ALPHAS=(0.25, 0.5, 0.75))

    def generate(corpus, queries, *, backend):
        assert fake.ALPHAS == (0.25,)
        assert backend == "local-lsa"
        return {"backend": backend, "model": "local-lsa-v1", "index": {}, "diagnostics": {},
                "methods": {key: {"q-001": []} for key in ("keyword", "semantic", "linear-0.25", "rrf-60")},
                "query_gate_v3": {"rankings": {"q-001": []},
                    "diagnostics": {"q-001": {"retrieval_gate_version": "query-support-v3"}}}}

    fake.generate_rankings = generate
    monkeypatch.setattr(prospective, "import_frozen_runner", lambda: fake)
    result = prospective.generate_rankings([], [query])
    assert set(result["methods"]) == set(prospective.METHODS)
    assert fake.ALPHAS == (0.25, 0.5, 0.75)
    assert prospective.fixed_policy()["parameter_selection"] is False
    fake.QUERY_GATE_V3_THRESHOLD = 0.3
    with pytest.raises(ValueError, match="policy constants changed"):
        prospective.generate_rankings([], [query])


def test_manifest_rejects_fixture_and_policy_drift(monkeypatch):
    manifest = prospective.load_manifest(prospective.FIXTURE_DIR)
    manifest["files"]["corpus.jsonl"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Frozen data drift"):
        prospective.load_ranker_dataset(prospective.FIXTURE_DIR, manifest)
    monkeypatch.setattr(prospective, "THRESHOLD", 0.3)
    with pytest.raises(ValueError, match="policy differs"):
        prospective.load_manifest(prospective.FIXTURE_DIR)


def test_code_hashes_match_freeze_and_reject_drift(monkeypatch):
    # Test the historical lock mechanism, not whether today's checkout still
    # implements the historical algorithm. Real CLI runs retain strict checks.
    lock = json.loads((prospective.EVAL_ROOT / "code-lock.json").read_text(encoding="utf-8"))
    historical_hashes = {ROOT / name: value for name, value in lock["files"].items()}
    historical_files = "\n".join(name for name in lock["files"] if name.startswith("sheaf_ai/"))
    git_outputs = {
        ("ls-files", "sheaf_ai/*.py"): historical_files,
        ("status", "--porcelain=v1", "--untracked-files=all"): "?? evals/new-experiment/",
        ("rev-parse", "HEAD"): "f" * 40,
    }
    original_hash = prospective.sha256

    def historical_hash(path):
        if path in historical_hashes:
            return historical_hashes[path]
        return original_hash(path)  # The new adapter itself is not historical code.

    monkeypatch.setattr(prospective, "sha256", historical_hash)
    monkeypatch.setattr(prospective, "git", lambda *args: git_outputs[args])
    snapshot = prospective.code_snapshot()
    assert snapshot["frozen_commit"] == lock["commit"]
    assert snapshot["commit"] == "f" * 40
    assert snapshot["dirty"] is True
    assert snapshot["fixed_file_sha256"] == lock["files"]
    assert snapshot["line_ending_only_drift_files"] == []
    git_outputs[("ls-files", "sheaf_ai/*.py")] += "\nsheaf_ai/new_algorithm.py"
    with pytest.raises(ValueError, match="production Python file set changed"):
        prospective.code_snapshot()
    git_outputs[("ls-files", "sheaf_ai/*.py")] = historical_files
    historical_hashes[ROOT / "sheaf_ai/search.py"] = "0" * 64
    original_read_bytes = Path.read_bytes
    monkeypatch.setattr(prospective, "git_blob", lambda commit, name: b"historical source\n")
    monkeypatch.setattr(Path, "read_bytes", lambda path: b"changed source\n"
                        if path == ROOT / "sheaf_ai/search.py" else original_read_bytes(path))
    with pytest.raises(ValueError, match="Frozen code drift"):
        prospective.code_snapshot()


@pytest.mark.parametrize("current_bytes,accepted", [
    (b"policy = 1\r\nunchanged = True\r\n", True),
    (b"policy = 1\r\nunchanged = True\n", True),
    (b"policy = 1\nunchanged = True\n", True),
    (b"policy = 2\r\nunchanged = True\r\n", False),
    (b"policy = 1 \r\nunchanged = True\r\n", False),
])
def test_code_snapshot_only_accepts_newline_drift_against_fixed_blob(monkeypatch, current_bytes, accepted):
    lock = json.loads((prospective.EVAL_ROOT / "code-lock.json").read_text(encoding="utf-8"))
    target = "sheaf_ai/search.py"
    historical_hashes = {ROOT / name: value for name, value in lock["files"].items()}
    historical_hashes[ROOT / target] = "0" * 64  # Force the exact-byte mismatch path.
    git_outputs = {
        ("ls-files", "sheaf_ai/*.py"): "\n".join(name for name in lock["files"] if name.startswith("sheaf_ai/")),
        ("status", "--porcelain=v1", "--untracked-files=all"): "",
        ("rev-parse", "HEAD"): "f" * 40,
    }
    original_hash, original_read_bytes = prospective.sha256, Path.read_bytes
    blob_requests = []

    def historical_hash(path):
        return historical_hashes[path] if path in historical_hashes else original_hash(path)

    def fixed_blob(commit, name):
        blob_requests.append((commit, name))
        assert commit == lock["commit"]  # A later HEAD must not authorize changes.
        assert name == target
        return b"policy = 1\nunchanged = True\n"

    monkeypatch.setattr(prospective, "sha256", historical_hash)
    monkeypatch.setattr(prospective, "git", lambda *args: git_outputs[args])
    monkeypatch.setattr(prospective, "git_blob", fixed_blob)
    monkeypatch.setattr(Path, "read_bytes", lambda path: current_bytes
                        if path == ROOT / target else original_read_bytes(path))
    if accepted:
        snapshot = prospective.code_snapshot()
        assert snapshot["line_ending_only_drift_files"] == [target]
        assert snapshot["fixed_file_sha256"][target] == "0" * 64
        assert snapshot["frozen_file_sha256"] == lock["files"]
    else:
        with pytest.raises(ValueError, match="Frozen code drift"):
            prospective.code_snapshot()
    assert blob_requests == [(lock["commit"], target)]


def test_analytical_metrics_and_rank10_cutoff():
    metrics = prospective.query_metrics(["x", "b", "a"], {"a": 3, "b": 1})
    assert metrics["recall_at_5"] == 1
    assert metrics["mrr_at_10"] == 0.5
    assert metrics["ndcg_at_5"] == pytest.approx((1 / math.log2(3) + 7 / 2) / (7 + 1 / math.log2(3)))
    assert prospective.query_metrics(["x"] * 10 + ["a"], {"a": 3})["mrr_at_10"] == 0
    assert prospective.query_metrics([], {"a": 3}) == {"recall_at_5": 0, "mrr_at_10": 0, "ndcg_at_5": 0}


def test_refusals_and_all_failure_types_are_retained():
    queries = [{"query_id": f"q-{index:03d}", "text": "text"} for index in range(1, 4)]
    qrels = [{"query_id": queries[0]["query_id"], "category": "answerable", "relevance": {"a": 3}},
             {"query_id": queries[1]["query_id"], "category": "no_answer", "relevance": {}},
             {"query_id": queries[2]["query_id"], "category": "no_answer", "relevance": {}}]
    output = empty_rankings(queries)
    for rankings in output["methods"].values():
        rankings["q-002"] = [{"entry_id": "b"}]
    result = prospective.evaluate_rankings(output, queries, qrels)
    assert set(result) == set(prospective.METHODS)  # No selected arm or tuning output.
    for metrics in result.values():
        assert metrics["recall_at_5"] == metrics["mrr_at_10"] == metrics["ndcg_at_5"] == 0
        assert metrics["refusal_rate"] == pytest.approx(2 / 3, abs=1e-6)
        assert metrics["no_answer_refusal_rate"] == 0.5
        assert metrics["no_answer_false_positive_rate"] == 0.5
        assert metrics["false_rejection_count"] == 1
        assert metrics["false_rejection_rate"] == 1
        assert metrics["failure_query_count"] == 2
        reasons = {failure for row in metrics["failures"] for failure in row["failures"]}
        assert reasons == {"answerable_false_rejection", "no_answer_false_positive",
                           "relevant_entry_missing_at_5", "relevant_top_1_miss"}


def test_output_is_exclusive_and_scoped(tmp_path, monkeypatch):
    experiment = tmp_path / "experiment"
    monkeypatch.setattr(prospective, "EVAL_ROOT", experiment)
    output = experiment / "results" / "first.json"
    prospective.write_report(output, {"immutable": True})
    with pytest.raises(FileExistsError):
        prospective.write_report(output, {"immutable": False})
    assert json.loads(output.read_text(encoding="utf-8")) == {"immutable": True}
    with pytest.raises(ValueError, match="inside the new"):
        prospective.write_report(tmp_path / "outside.json", {})
