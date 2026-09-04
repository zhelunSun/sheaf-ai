"""Known-label repair regression. Never a new holdout or answer-quality benchmark."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def source_hashes() -> dict:
    paths = [*ROOT.glob("sheaf_ai/**/*.py"), *ROOT.glob("sheaf_cards/**/*.py"), Path(__file__)]
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(
        path.read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest() for path in sorted(paths)}


def run() -> dict:
    prospective = load_module("repair_prospective", ROOT / "evals/retrieval-prospective/run_benchmark.py")
    representation = load_module("repair_representation", ROOT / "evals/representation-boundary/run_diagnostic.py")
    manifest = prospective.load_manifest(prospective.FIXTURE_DIR)
    dataset = prospective.load_ranker_dataset(prospective.FIXTURE_DIR, manifest)
    frozen = prospective.import_frozen_runner()
    before = source_hashes()
    captures = {"strict-v4": {}, "review-v4": {}}
    query_ids = {row["text"]: row["query_id"] for row in dataset["queries"]}
    original_search = frozen.search.search_hybrid

    def search_and_review(text, **kwargs):
        result = original_search(text, **kwargs)
        if kwargs.get("min_evidence_score", 0) > 0:
            query_id = query_ids[text]
            captures["strict-v4"][query_id] = {
                "rankings": frozen._compact_results(result),
                "diagnostics": dict(kwargs["diagnostics"]),
            }
            review_diagnostics = {}
            review = original_search(text, **{
                **kwargs, "gate_policy": "review", "diagnostics": review_diagnostics,
            })
            captures["review-v4"][query_id] = {
                "rankings": frozen._compact_results(review),
                "diagnostics": review_diagnostics,
            }
        return result

    # Reuse the actual Entry index harness, not hand-injected semantic scores.
    with (patch.object(frozen, "ALPHAS", (0.25,)),
          patch.object(frozen.search, "search_hybrid", side_effect=search_and_review),
          patch.object(socket, "create_connection", side_effect=RuntimeError("Network prohibited")),
          patch.object(socket.socket, "connect", side_effect=RuntimeError("Network prohibited"))):
        raw = frozen.generate_rankings(dataset["corpus"], dataset["queries"], backend="local-lsa")

    methods = {name: {qid: row["rankings"] for qid, row in rows.items()}
               for name, rows in captures.items()}
    methods["fixed-linear"] = raw["methods"]["linear-0.25"]
    methods["keyword"] = raw["methods"]["keyword"]
    # Known labels remain evaluator-only inputs, but author exposure is explicit.
    qrels = prospective.load_qrels(prospective.FIXTURE_DIR, manifest, dataset)
    with patch.object(prospective, "METHODS", tuple(methods)):
        evaluation = prospective.evaluate_rankings({"methods": methods}, dataset["queries"], qrels)
    transport = representation.evaluate_current()
    from sheaf_ai.card_trace import citation_trace
    from sheaf_cards.base import KnowledgeCard

    binding_checks = []
    for case in transport["cases"]:
        for card in case["cards"]:
            restored = KnowledgeCard.from_json(card["native"]["stored_json"]["text"])
            trace = citation_trace(restored)
            expected_ids = card["parser_supported_transport"]["source_ids"]["expected"]
            binding_checks.append({
                "case_id": case["case_id"], "card_index": card["card_index"],
                "expected_source_ids": expected_ids, "trace": trace,
                "all_ids_bound": sorted(expected_ids) == sorted(
                    binding["entry_id"] for binding in trace["bindings"]
                ),
            })
    if source_hashes() != before:
        raise ValueError("Production source changed during regression")
    # Validate historical data again, without changing historical code locks.
    prospective.load_manifest(prospective.FIXTURE_DIR)
    for filename in manifest["files"]:
        prospective.verified_file(prospective.FIXTURE_DIR, manifest, filename)
    baseline_path = ROOT / "evals/retrieval-prospective/results/local-lsa-2026-09-04.1-first.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    return {
        "experiment": "repair-regression-2026-09-04.1",
        "scope": "post-hoc known-label synthetic regression; not independent holdout",
        "limitations": [
            "local-LSA, not neural embeddings; no real users or live LLM",
            "nonempty negative-query results are inspection candidates, not hallucinations",
            "strict policy unchanged; review mode trades rejection for source inspection",
            "citation identity and qualifier transport do not verify semantic support",
        ],
        "policy": {"alpha": 0.25, "min_evidence_score": 0.4, "tuned": False,
                   "version": "query-support-v4", "ranking_depth": 10},
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                text=True).strip(),
        "lf_source_sha256": before,
        "frozen_inputs": manifest["files"],
        "historical_baseline": {"path": baseline_path.relative_to(ROOT).as_posix(),
                                "sha256": prospective.sha256(baseline_path),
                                "evaluation": baseline["evaluation"]["fixed-gate"]},
        "retrieval": {"evaluation": evaluation, "captures": captures,
                      "index": raw["index"], "backend": raw["backend"], "model": raw["model"]},
        "representation": {"summary": transport["summary"], "binding_checks": binding_checks,
                           "api_or_network_attempts": transport["api_or_network_attempts"]},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Fail early and never overwrite a previous result.
    if args.output.exists():
        raise FileExistsError(args.output)
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({name: {key: value for key, value in result.items()
                            if key not in {"categories", "failures", "per_query"}}
                      for name, result in report["retrieval"]["evaluation"].items()}, indent=2))


if __name__ == "__main__":
    main()
