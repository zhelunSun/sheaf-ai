"""Post-run descriptive tables; never sends a request or changes primary scores."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import experiment as e  # noqa: E402


def analyze(run_dir):
    run_dir = Path(run_dir).resolve()
    result = e.read(run_dir / "results.json")
    rows = result["rows"]
    reused = e.read(run_dir / "reused-calls.json") if (run_dir / "reused-calls.json").exists() else {}

    def response(rid):
        path = run_dir / "calls" / (e.digest(rid) + ".result.json")
        if path.exists():
            receipt = e.read(path)
        elif rid in reused:
            parent = reused[rid]
            receipt = e.read(run_dir.parent / parent["run"] / "calls" / (e.digest(rid) + ".result.json"))
            if receipt["receipt_hash"] != parent["receipt_hash"]:
                raise ValueError("Reused receipt identity changed")
        elif rid == "probe":
            receipt = e.read(run_dir.parent / "run-v1/calls" / (e.digest(rid) + ".result.json"))
        else:
            raise ValueError("Missing response lineage")
        if receipt["receipt_hash"] != e.digest({k: v for k, v in receipt.items() if k != "receipt_hash"}):
            raise ValueError("Receipt checksum changed")
        return receipt["response"]

    contexts = e.read(run_dir / "contexts.json")
    valid = {c["bundle_id"] for c in contexts if c["arm"] == "all_facts" and c["preparation_error"] is None}
    subset = [row for row in rows if row["bundle_id"] in valid]
    selected_contexts = {(c["task_id"], c["arm"]): c for c in contexts}
    responses = {row["request_id"]: response(row["request_id"]) for row in rows
                 if selected_contexts[(row["task_id"], row["arm"])]["preparation_error"] is None}
    bundles = [b for b in e.load_inputs() if b["bundle_id"] in valid]
    parent_runner = e.load_module("v3_analysis_cost", HERE / "run.py")
    conditional_cost = parent_runner.cost_report(
        bundles, {b["bundle_id"]: response("extract-" + b["bundle_id"]) for b in bundles},
        subset, responses, response("probe"))
    review = e.read(run_dir / "semantic-review.json")
    mapping = e.read(run_dir / "semantic-review-mapping.json")
    by_request = {row["request_id"]: row for row in rows}
    if len(review) != 72 or {item["id"] for item in review} != set(mapping):
        raise ValueError("Semantic review does not cover the frozen 72-answer packet")
    semantic = {}
    keys = ("decision_semantically_correct", "state_semantically_correct", "cited_evidence_sufficient")
    for arm in e.ARMS:
        selected = [item for item in review if by_request[mapping[item["id"]]]["arm"] == arm]
        semantic[arm] = {"denominator": len(selected),
                         **{k: sum(item[k] for item in selected) for k in keys},
                         "all_three_correct": sum(all(item[k] for k in keys) for item in selected)}
    report = {"manifest_hash": result["manifest_hash"],
              "primary_result_hash": e.file_hash(run_dir / "results.json"),
              "semantic_review_hash": e.file_hash(run_dir / "semantic-review.json"),
              "evidence_grade": "small_agent_reviewed_synthetic_with_explicit_post_run_budget_correction",
              "actual_answer_calls_used": len(responses),
              "first_draw_semantic_review": semantic,
              "failure_reasons_full_denominator": dict(Counter(row["error"] for row in rows if row["error"])),
              "conditional_analysis": {"scope": "Post-hoc accepted-construction subset; survivor-biased, not a replacement for the full denominator and not a fresh holdout.",
                  "bundle_ids": sorted(valid), "tasks": len({r["task_id"] for r in subset}),
                  "summary": {k: v for k, v in e.summarize(subset).items() if k != "paired"},
                  "cost": conditional_cost},
              "context_pairs": result["fact_arm_context_pairs"]}
    e.preserve(run_dir / "analysis.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=HERE / "campaigns/paratera-flash-20260905/run-v3-encoded-budget")
    args = parser.parse_args()
    print(analyze(args.run_dir))
