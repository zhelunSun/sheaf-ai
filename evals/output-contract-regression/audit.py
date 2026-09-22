"""Read-only diagnosis of frozen v3 output contracts; no generation or gold access.

This does not repair old answers, rescore method quality, or enable partial facts
in production. It separates batch limits from individual evidence failures so
the next experiment can target a measured failure rather than add more fields.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
V3 = ROOT / "evals/method-selection-v3"
CAMPAIGN = V3 / "campaigns/paratera-flash-20260905"
CONSTRUCTION = CAMPAIGN / "run-v2-output-cap"
FINAL = CAMPAIGN / "run-v3-encoded-budget"
MANIFEST_IDENTITIES = {
    "run-v2-output-cap": "66b5943edaeb6c737a940d2c38b6fe630f029b021fb5a1301ea69d21c93a369e",
    "run-v3-encoded-budget": "241c61e390699fda559642f67acadfb03aeadbda6ffeebc48fd498b35083be02",
}
spec = importlib.util.spec_from_file_location("frozen_v3_contract_audit", V3 / "experiment.py")
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_receipt(run, request_id):
    """Verify the immutable response and its complete original request binding."""
    stem = run / "calls" / frozen.digest(request_id)
    intent = read(stem.with_suffix(".intent.json"))
    result = read(stem.with_suffix(".result.json"))
    for record in (intent, result):
        if record.get("receipt_hash") != frozen.digest(
            {k: v for k, v in record.items() if k != "receipt_hash"}
        ):
            raise ValueError("Receipt checksum mismatch")
    response = result["response"]
    payload_hash = frozen.digest(intent["payload"])
    if (intent["request_id"] != request_id or response["request_id"] != request_id
            or result["intent_hash"] != intent["receipt_hash"]
            or result["manifest_hash"] != intent["manifest_hash"]
            or any(record["payload_hash"] != payload_hash for record in (intent, result, response))
            or result["issues"] or result["transport_error"] is not False
            or result["http_status"] != 200):
        raise ValueError("Incomplete or mismatched response binding")
    return intent, result


def fact_issues(fact, bundle):
    """Mechanical issues only. A matching quote is not semantic support."""
    keys = {"method_id", "fact_type", "statement", "applicability_conditions",
            "measurement_scope", "not_evaluated_scope", "citations"}
    if not isinstance(fact, dict) or set(fact) != keys:
        return ["fact_schema"]
    issues = []
    if (not isinstance(fact["fact_type"], str) or fact["fact_type"] not in frozen.TYPES
            or fact["method_id"] is not None and fact["method_id"] not in bundle["method_ids"]
            or not isinstance(fact["statement"], str) or not fact["statement"].strip()):
        issues.append("fact_schema")
    for name in ("applicability_conditions", "measurement_scope", "not_evaluated_scope"):
        if not isinstance(fact[name], list) or not all(
            isinstance(value, str) and value.strip() for value in fact[name]
        ):
            issues.append("condition_schema")
    citations = fact["citations"]
    if not isinstance(citations, list) or not citations:
        return sorted(set([*issues, "citation_schema"]))
    sources = {s["source_id"]: s["text"] for s in bundle["sources"]}
    for citation in citations:
        if not isinstance(citation, dict) or set(citation) != {"source_id", "quote"}:
            issues.append("citation_schema")
            continue
        sid, quote = citation["source_id"], citation["quote"]
        if not isinstance(sid, str) or sid not in sources:
            issues.append("unknown_source")
        elif not isinstance(quote, str) or not quote.strip():
            issues.append("citation_schema")
        else:
            occurrences = sources[sid].count(quote)
            if occurrences == 0:
                issues.append("quote_not_verbatim")
            elif occurrences != 1:
                issues.append("quote_ambiguous")
    return sorted(set(issues))


def audit_extraction(response, bundle):
    try:
        facts, _ = frozen.parse_text(response)
    except (ValueError, TypeError, KeyError):
        return {"bundle_id": bundle["bundle_id"], "batch_issues": ["invalid_or_incomplete_json"],
                "emitted_facts": None, "mechanically_valid_indices": [], "rejected_facts": []}
    if not isinstance(facts, list):
        return {"bundle_id": bundle["bundle_id"], "batch_issues": ["expected_array"],
                "emitted_facts": None, "mechanically_valid_indices": [], "rejected_facts": []}
    batch_issues = ["empty_batch"] if not facts else ["fact_count_exceeded"] if len(facts) > 40 else []
    valid, rejected = [], []
    for index, fact in enumerate(facts):
        issues = fact_issues(fact, bundle)
        if issues:
            rejected.append({"index": index, "issues": issues})
        else:
            valid.append(index)
    # Count errors must never hide problems in later individual facts.
    if rejected:
        batch_issues.append("invalid_facts")
    return {"bundle_id": bundle["bundle_id"], "batch_issues": batch_issues,
            "emitted_facts": len(facts), "mechanically_valid_indices": valid,
            "rejected_facts": rejected}


def decision_issues(answer, options):
    """Check only logical field consistency; never guess a decision from prose."""
    keys = {"decision", "method_id", "evidence_state", "citations", "reason"}
    if (not isinstance(answer, dict) or set(answer) != keys
            or answer["decision"] not in ("choose", "abstain")
            or answer["evidence_state"] not in tuple(frozen.STATES)
            or not isinstance(answer["reason"], str) or not answer["reason"].strip()
            or not isinstance(answer["citations"], list)):
        return ["answer_schema"]
    issues = []
    if answer["decision"] == "choose":
        if answer["method_id"] not in options:
            issues.append("invalid_chosen_method")
        if answer["evidence_state"] != "supported":
            issues.append("choose_without_supported_state")
    else:
        if answer["method_id"] is not None:
            issues.append("abstain_with_method")
        if answer["evidence_state"] == "supported":
            issues.append("abstain_with_supported_state")
    return issues


def expected_payload(prompt, cap, manifest):
    return {"model": manifest["model"], "messages": [
        {"role": "system", "content": frozen.SYSTEM}, {"role": "user", "content": prompt}],
        "temperature": manifest["temperature"], "max_tokens": cap,
        "stream": False, "reasoning_effort": "none"}


def validate_plan(plan, tasks, contexts, failed_tasks, manifest):
    expected = {f"answer-{tid}-{arm}-r{draw}": (tid, arm, draw)
                for tid in tasks for arm in frozen.ARMS for draw in (1, 2)}
    if (not isinstance(plan, list) or len(plan) != len(expected)
            or len({p["request_id"] for p in plan}) != len(expected)
            or {p["request_id"] for p in plan} != set(expected)):
        raise ValueError("Answer plan must cover each task/arm/draw exactly once")
    expected_contexts = {(tid, arm) for tid in tasks for arm in frozen.ARMS}
    if (len(contexts) != len(expected_contexts)
            or {(c["task_id"], c["arm"]) for c in contexts} != expected_contexts):
        raise ValueError("Context coverage differs from tasks")
    lookup = {(c["task_id"], c["arm"]): c for c in contexts}
    for item in plan:
        tid, arm, draw = expected[item["request_id"]]
        if (item["task_id"], item["arm"], item["draw"]) != (tid, arm, draw):
            raise ValueError("Answer plan identity differs")
        context = lookup[(tid, arm)]
        if context["task"] != tasks[tid]:
            raise ValueError("Context belongs to another task")
        preparation_failed = (arm != "raw_passages" and tid in failed_tasks) or not context["context"]
        if bool(context["preparation_error"]) != preparation_failed:
            raise ValueError("Preparation failure differs from original extraction")
        prompt = frozen.ANSWER + json.dumps({"task": {k: tasks[tid][k] for k in ("question", "options")},
                                            "context": context["context"]}, ensure_ascii=False)
        payload = None if preparation_failed else expected_payload(prompt, 1200, manifest)
        if (item["payload"] != payload
                or item["payload_hash"] != (frozen.digest(payload) if payload else None)):
            raise ValueError("Answer plan payload or preparation failure differs")


def build_report():
    lock = read(V3 / "lock.json")
    frozen.verify_lock(lock, include_gold=False)
    bundles = frozen.load_inputs()
    tasks = {t["task_id"]: t for b in bundles for t in b["tasks"]}
    bound_files = {V3 / "inputs.json", V3 / "lock.json", FINAL / "answer-plan.json", FINAL / "contexts.json",
                   FINAL / "reused-calls.json"}
    manifests = {}
    for run in (CONSTRUCTION, FINAL):
        m = read(run / "manifest.json")
        if (m["manifest_hash"] != MANIFEST_IDENTITIES[run.name]
                or frozen.digest({k: v for k, v in m.items() if k != "manifest_hash"}) != m["manifest_hash"]):
            raise ValueError("Manifest differs from frozen campaign")
        manifests[run.name] = m
        bound_files.add(run / "manifest.json")

    def receipt(run, rid):
        intent, result = checked_receipt(run, rid)
        manifest = manifests[run.name]
        if (intent["manifest_hash"] != manifest["manifest_hash"]
                or result["response"]["model"] != manifest["model"]
                or result["provider_model"] != manifest["model"]):
            raise ValueError("Receipt differs from frozen model/manifest")
        stem = run / "calls" / frozen.digest(rid)
        bound_files.update((stem.with_suffix(".intent.json"), stem.with_suffix(".result.json")))
        return intent, result

    extraction, failed_tasks = [], set()
    for bundle in bundles:
        intent, result = receipt(CONSTRUCTION, "extract-" + bundle["bundle_id"])
        prompt = frozen.EXTRACT + json.dumps({k: bundle[k] for k in ("method_ids", "sources")}, ensure_ascii=False)
        if intent["payload"] != expected_payload(prompt, 12000, manifests[CONSTRUCTION.name]):
            raise ValueError("Extraction request differs from current frozen sources")
        row = audit_extraction(result["response"], bundle)
        extraction.append(row)
        if row["batch_issues"]:
            failed_tasks.update(t["task_id"] for t in bundle["tasks"])
    reuse = read(FINAL / "reused-calls.json")
    plan = read(FINAL / "answer-plan.json")
    validate_plan(plan, tasks, read(FINAL / "contexts.json"), failed_tasks, manifests[FINAL.name])
    answer_rows = []
    for item in plan:
        row = {k: item[k] for k in ("request_id", "task_id", "arm", "draw")}
        if item["payload"] is None:
            row.update(status="preparation_failed", issues=[])
        else:
            rid = item["request_id"]
            reused = reuse.get(rid)
            if reused and reused["run"] != "run-v2-output-cap":
                raise ValueError("Unexpected reuse source")
            intent, result = receipt(CONSTRUCTION if reused else FINAL, rid)
            if (intent["payload"] != item["payload"]
                    or intent["payload_hash"] != item["payload_hash"]
                    or reused and (reused["receipt_hash"] != result["receipt_hash"]
                                   or reused["payload_hash"] != result["payload_hash"])):
                raise ValueError("Answer plan/reuse differs from original request")
            try:
                answer, _ = frozen.parse_text(result["response"])
                issues = decision_issues(answer, tasks[item["task_id"]]["options"])
            except (ValueError, TypeError, KeyError):
                issues = ["invalid_or_incomplete_json"]
            row.update(status="review_required" if issues else "field_consistent", issues=issues)
        answer_rows.append(row)
    count = Counter(issue for r in extraction for issue in r["batch_issues"])
    invalid = Counter(issue for r in extraction for f in r["rejected_facts"] for issue in f["issues"])
    answer_count = Counter(issue for r in answer_rows for issue in r["issues"])
    return {
        "version": "output-contract-regression-v1",
        "evidence_grade": "post_hoc_mechanical_diagnosis_of_known_synthetic_outputs",
        "source_code_commit": "063cd98", "new_model_calls": 0, "gold_loaded": False,
        "automatic_repair": False, "reason_semantics": "not_assessed",
        "partial_fact_policy": "diagnostic_only; overflow remains rejected; no silent truncation or promotion",
        "limits": ["Exact quotes do not establish entailment or correct fact types.",
                   "Field consistency does not establish a correct answer or coherent reason.",
                   "No altered contexts were sent to a model; old method scores are unchanged.",
                   "This audits the experiment adapter, not production crystallization accuracy."],
        "source_files": {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(bound_files)},
        "audit_code_sha256": hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "summary": {"bundles": len(extraction), "original_contract_accepted": sum(
            not r["batch_issues"] for r in extraction),
            "emitted_facts": sum(r["emitted_facts"] or 0 for r in extraction),
            "mechanically_valid_facts": sum(len(r["mechanically_valid_indices"]) for r in extraction),
            "rejected_facts": sum(len(r["rejected_facts"]) for r in extraction),
            "batch_issues": dict(sorted(count.items())), "fact_issues": dict(sorted(invalid.items())),
            "bounded_isolation_candidate": {
                "scope": "Not executed; quarantine invalid facts only within the original count bound",
                "bundles_with_remaining_facts": sum(
                    bool(r["mechanically_valid_indices"]) and r["emitted_facts"] <= 40 for r in extraction),
                "remaining_facts": sum(len(r["mechanically_valid_indices"]) for r in extraction
                                       if r["emitted_facts"] is not None and r["emitted_facts"] <= 40),
                "quality_effect": "not_measured; missing evidence can change downstream decisions",
            },
            "answer_positions": len(answer_rows), "answer_statuses": dict(sorted(Counter(
                r["status"] for r in answer_rows).items())), "answer_issues": dict(sorted(answer_count.items()))},
        "extractions": extraction, "answers": answer_rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=Path, help="Compare against an existing report without writing")
    args = parser.parse_args()
    report = build_report()
    if args.check:
        if read(args.check) != report:
            raise SystemExit("Saved diagnosis differs; preserve it and create a new revision.")
        print(json.dumps({"replay": "matched", "new_model_calls": 0, "summary": report["summary"]}))
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    sys.exit(main())
