"""E1 mechanism tests use synthetic vectors only; these are not quality scores."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from sheaf_ai.entry_embeddings import entry_embedding_text

PATH = Path(__file__).resolve().parents[1] / "evals" / "production-retrieval" / "run_eval.py"
SPEC = importlib.util.spec_from_file_location("production_retrieval_eval", PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.fixture
def revision(tmp_path):
    directory = tmp_path / "revision"
    directory.mkdir()
    inputs = {"schema": 1, "evidence_kind": "synthetic-mechanism", "k": 2,
        "corpus": [
            {"id": "fixture_v2", "title": "Atlas version two", "summary": "Approval required",
             "tags": ["Atlas"], "raw_text": "Atlas version two requires explicit approval.", "source_group": "atlas", "split": "dev"},
            {"id": "fixture_v1", "title": "Atlas version one", "summary": "Approval optional",
             "tags": ["Atlas"], "raw_text": "Atlas version one makes approval optional.", "source_group": "atlas", "split": "dev"},
            {"id": "fixture_b", "title": "Birch offline mode", "summary": "Offline mode available",
             "tags": ["Birch"], "raw_text": "Birch supports local offline indexing.", "source_group": "birch", "split": "final"}],
        "queries": [
            {"id": "q_version", "text": "Atlas version two approval", "group": "atlas", "split": "dev"},
            {"id": "q_offline", "text": "Birch offline indexing", "group": "birch", "split": "final"},
            {"id": "q_absent", "text": "Birch quantum acceleration", "group": "birch", "split": "final"}]}
    gold = {
        "q_version": {"evidence": "present", "relevance": {"fixture_v2": 3}, "wrong_version_ids": ["fixture_v1"],
                      "required_conditions": {"approval": ["fixture_v2"]}},
        "q_offline": {"evidence": "present", "relevance": {"fixture_b": 3}},
        "q_absent": {"evidence": "absent", "relevance": {}, "checked_entire_corpus": True}}
    entries = runner._entries(inputs)
    texts = [entry_embedding_text(entry, raw_text=row["raw_text"]) for entry, row in zip(entries, inputs["corpus"])]
    texts += [query["text"] for query in inputs["queries"]]
    vectors = [[1.0, 0.0, 0.0], [0.8, 0.2, 0.0], [0.0, 1.0, 0.0],
               [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.3, 0.7]]
    cache = {"kind": "synthetic-mechanism", "model": "synthetic-fixture-v1",
             "provenance": "Hand-specified vectors for mechanism tests; not model output.",
             "vectors": [{"text": text, "text_sha256": runner.digest(text.encode("utf-8")), "vector": vector}
                         for text, vector in zip(texts, vectors)]}
    for name, value in (("inputs.json", inputs), ("gold.json", gold), ("embedding-cache.json", cache)):
        (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return directory


def test_production_cached_replay_and_denominators(revision, tmp_path):
    manifest = tmp_path / "freeze.json"
    runner.freeze(revision, manifest)
    report = runner.run(manifest, tmp_path / "run.json", split="final")
    assert report["status"] == "complete", report["errors"]
    assert report["live_api_calls"] == 0 and len(report["trials"]) == 4
    assert report["requested_split"] == "final"
    assert report["evidence_kind"] == "synthetic-mechanism"
    for trial in report["trials"]:
        assert trial["latency_ms"] >= 0
        if trial["arm"] == "hybrid":
            assert trial["diagnostics"]["semantic_backend"] == "entry_index"
    final = [row for row in report["scores"]["aggregates"] if row["split"] == "final"]
    assert all(row["attempted"] == 2 and row["answerable_denominator"] == 1 and row["no_evidence_denominator"] == 1 for row in final)
    assert all(row["recall_at_k"] is None for row in report["scores"]["per_query"] if row["evidence"] == "absent")


def test_drift_is_an_error_record_not_a_quality_result(revision, tmp_path):
    manifest = tmp_path / "freeze.json"
    runner.freeze(revision, manifest)
    (revision / "gold.json").write_text("{}", encoding="utf-8")
    report = runner.run(manifest, tmp_path / "drift.json")
    assert report["status"] == "error" and not report["trials"]
    assert "Frozen file drift" in report["errors"][0]["message"]


def test_cache_miss_never_calls_provider_or_falls_back(revision, tmp_path, monkeypatch):
    cache_file = revision / "embedding-cache.json"
    cache = json.loads(cache_file.read_text("utf-8"))
    cache["vectors"].pop(3)
    cache_file.write_text(json.dumps(cache), encoding="utf-8")
    from sheaf_ai import entry_embeddings
    monkeypatch.setattr(entry_embeddings, "_default_embedder", lambda *_: pytest.fail("Provider path forbidden"))
    manifest = tmp_path / "freeze.json"
    runner.freeze(revision, manifest)
    report = runner.run(manifest, tmp_path / "missing.json")
    assert report["status"] == "error" and report["trials"] == []
    assert report["planned_trials"] == 2
    assert "Missing exact cached text" in report["errors"][0]["message"]


def test_ranker_never_receives_gold_and_failures_stay_in_denominator(revision, tmp_path, monkeypatch):
    def failed_rank(inputs, embedder):
        assert "relevance" not in json.dumps(inputs)
        return [{"query_id": query["id"], "split": query["split"], "arm": arm, "status": "error", "ranked_ids": [],
                 "results": [], "error": "Injected ranker failure", "latency_ms": 1.0, "diagnostics": {}}
                for query in inputs["queries"] for arm in runner.ARMS]

    monkeypatch.setattr(runner, "rank", failed_rank)
    manifest = tmp_path / "freeze.json"
    runner.freeze(revision, manifest)
    report = runner.run(manifest, tmp_path / "failed.json")
    assert report["status"] == "partial"
    assert all(row["recall_at_k"] == 0.0 and row["failed"] == row["attempted"] for row in report["scores"]["aggregates"])


def test_output_and_freeze_are_never_overwritten(revision, tmp_path):
    manifest, output = tmp_path / "freeze.json", tmp_path / "run.json"
    runner.freeze(revision, manifest)
    with pytest.raises(FileExistsError):
        runner.freeze(revision, manifest)
    runner.run(manifest, output)
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        runner.run(manifest, output)
    assert output.read_bytes() == before


def test_group_leak_is_rejected(revision, tmp_path):
    path = revision / "inputs.json"
    inputs = json.loads(path.read_text("utf-8"))
    inputs["corpus"][0]["split"] = "final"
    path.write_text(json.dumps(inputs), encoding="utf-8")
    with pytest.raises(runner.EvalError, match="leaks"):
        runner.freeze(revision, tmp_path / "freeze.json")


def test_model_identity_and_false_real_cache_are_rejected(revision):
    cache = json.loads((revision / "embedding-cache.json").read_text("utf-8"))
    embedder = runner.CachedEmbedder(cache, "synthetic-mechanism")
    with pytest.raises(runner.EvalError, match="model mismatch"):
        embedder([cache["vectors"][0]["text"]], "other-model")
    with pytest.raises(runner.EvalError, match="provenance/type"):
        runner.CachedEmbedder(cache, "real-corpus")


def test_default_dev_run_never_passes_final_queries_to_ranker(revision, tmp_path, monkeypatch):
    seen = []
    actual = runner.rank

    def inspected(inputs, embedder):
        seen.extend(query["id"] for query in inputs["queries"])
        assert len(inputs["corpus"]) == 3  # Both arms retain the entire same corpus.
        return actual(inputs, embedder)

    monkeypatch.setattr(runner, "rank", inspected)
    manifest = tmp_path / "freeze.json"
    runner.freeze(revision, manifest)
    report = runner.run(manifest, tmp_path / "dev.json")
    assert report["status"] == "complete"
    assert report["requested_split"] == "dev" and report["planned_trials"] == 2
    assert seen == ["q_version"]
    assert {row["query_id"] for row in report["scores"]["per_query"]} == {"q_version"}


def test_real_source_provenance_required_and_production_fields_preserved(revision):
    inputs = json.loads((revision / "inputs.json").read_text("utf-8"))
    inputs["evidence_kind"] = "real-corpus"
    with pytest.raises(runner.EvalError, match="provenance"):
        runner._validate_inputs(inputs)
    for i, row in enumerate(inputs["corpus"]):
        row.update(url=f"manual://frozen-{i}", provenance="Author supplied text; captured date recorded",
                   topics=[{"name": "AI Agent", "confidence": 0.9}], entities=[{"text": "Atlas", "label": "PRODUCT"}],
                   collected_at="2026-10-03T10:00:00+08:00")
    runner._validate_inputs(inputs)
    entries = runner._entries(inputs)
    assert entries[0]["url"] == "manual://frozen-0"
    assert entries[0]["topics"] == [{"name": "AI Agent", "confidence": 0.9}]
    assert entries[0]["entities"] == [{"text": "Atlas", "label": "PRODUCT"}]
    assert entries[0]["collected_at"] == "2026-10-03T10:00:00+08:00"
