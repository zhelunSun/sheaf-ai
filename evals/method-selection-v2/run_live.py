"""Budgeted Paratera execution for the frozen method-selection-v2 protocol."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


experiment = load_module("method_selection_v2", HERE / "run_experiment.py")
transport = load_module("method_selection_live_transport", ROOT / "evals/method-selection/run_live.py")


def executor_hashes():
    paths = [Path(__file__), ROOT / "evals/method-selection/run_live.py"]
    return {p.relative_to(ROOT).as_posix(): experiment.shared.file_hash(p) for p in paths}


def make_manifest(model, max_requests=50, max_tokens=150000, timeout=120):
    if not experiment.shared.text(model) or any(type(v) is not int or v < 1 for v in (
            max_requests, max_tokens, timeout)):
        raise ValueError("Explicit model and positive limits required")
    if max_requests > 50 or max_tokens > 150000 or timeout > 180:
        raise ValueError("Pilot ceiling: 50 requests, 150000 tokens, 180 seconds")
    lock = experiment.read_json(HERE / "lock.json")
    experiment.verify_lock(lock)
    value = {"version": "method-selection-v2-live-v1", "model": model, "endpoint": transport.ENDPOINT,
             "max_requests": max_requests, "max_tokens": max_tokens, "timeout_seconds": timeout,
             "retries": 0, "concurrency": 1, "context_budget_characters": 6000,
             "input_reservation": "utf8(system+prompt) bytes + 512; operational estimate, not tokenizer",
             "pricing": {"currency": "CNY", "amount": None, "status": "provider_rate_not_verified"},
             "lock": lock, "executor_code": executor_hashes()}
    return {**value, "manifest_hash": experiment.shared.digest(value)}


def unwrap(row):
    parsed = dict(row)
    original = row["text"]
    match = re.fullmatch(r"```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```[ \t]*", original.strip())
    transformation = "identity"
    if row["finish_reason"] == "stop" and match:
        try:
            json.loads(match[1])
        except ValueError:
            pass
        else:
            parsed["text"] = match[1]
            transformation = "whole_message_json_fence_removed"
    return parsed, {"request_id": row["request_id"], "transformation": transformation,
                    "original_text_hash": experiment.shared.digest(original),
                    "parsed_text_hash": experiment.shared.digest(parsed["text"])}


def source_guard(manifest):
    experiment.verify_lock(manifest["lock"])
    if executor_hashes() != manifest["executor_code"]:
        raise transport.RunStopped("Executor changed; start a new experiment revision")


def usage_report(run_dir, manifest, plan):
    rows = transport.receipts(run_dir, manifest)
    arms = {c["request_id"]: c["arm"] for c in plan["cases"]}
    totals = {"probe": [0, 0, 0], "construction": [0, 0, 0],
              **{arm: [0, 0, 0] for arm in experiment.ARMS}}
    for intent, result in rows:
        rid = intent["request"]["request_id"]
        group = "probe" if rid == "probe" else "construction" if rid.startswith("extract-") else arms[rid]
        inp, out = (result["response"]["usage"][key] for key in ("input_tokens", "output_tokens"))
        totals[group] = [x + y for x, y in zip(totals[group], [1, inp, out])]
    groups = {k: dict(zip(("calls", "input_tokens", "output_tokens"), v)) for k, v in totals.items()}
    construction = sum(totals["construction"][1:])
    return {"actual_requests": len(rows), "total_tokens": sum(v[1] + v[2] for v in totals.values()),
            "groups": groups, "standalone_arm_total_tokens": {
                arm: sum(totals[arm][1:]) + (construction if arm != "raw" else 0)
                for arm in experiment.ARMS}, "currency": "CNY", "actual_cost": None,
            "cost_status": "Provider prices/invoice not verified; token usage is not currency",
            "limitations": ["Probe excluded from arm cost", "Each deployed fact arm bears full construction cost",
                            "Provider-reported usage, not independently billed", "No equal-token input"]}


def run(manifest, run_dir, client, key):
    with transport.provenance_registry_lock(run_dir / "execution", timeout=1):
        transport.preserve(run_dir / "manifest.json", manifest)
        source_guard(manifest)

        def dispatch(request):
            source_guard(manifest)
            return transport.execute_request(request, manifest, run_dir, client, key)[0]

        probe = experiment.shared.request("probe", manifest["model"],
                                          'Return exactly the JSON object {"ok":true}; no analysis or markdown.', 128)
        probe_raw = dispatch(probe)
        probe_parsed, probe_audit = unwrap(probe_raw)
        try:
            if probe_parsed["finish_reason"] != "stop" or json.loads(probe_parsed["text"]) != {"ok": True}:
                raise ValueError
        except ValueError:
            raise transport.RunStopped("Probe failed the exact JSON contract; not proceeding") from None

        extraction = experiment.prepare_extraction(manifest["lock"], manifest["model"])
        transport.preserve(run_dir / "extraction-plan.json", extraction)
        extraction_raw = [dispatch(r) for r in extraction["requests"]]
        extraction_parsed, audit = [], [probe_audit]
        for row in extraction_raw:
            parsed, item = unwrap(row)
            extraction_parsed.append(parsed)
            audit.append(item)
        transport.preserve(run_dir / "extraction-provider-responses.json", extraction_raw)
        transport.preserve(run_dir / "extraction-parsed-responses.json", extraction_parsed)

        answers = experiment.prepare_answers(
            extraction, extraction_parsed, manifest["context_budget_characters"])
        transport.preserve(run_dir / "answer-plan.json", answers)
        answer_raw = [dispatch(r) for r in answers["requests"]]
        answer_parsed = []
        for row in answer_raw:
            parsed, item = unwrap(row)
            answer_parsed.append(parsed)
            audit.append(item)
        transport.preserve(run_dir / "answer-provider-responses.json", answer_raw)
        transport.preserve(run_dir / "answer-parsed-responses.json", answer_parsed)
        transport.preserve(run_dir / "normalization-audit.json", audit)

        report = experiment.score(answers, answer_parsed)
        originals = {r["request_id"]: r for r in answer_raw}
        for row in report["rows"]:
            row["parsed_response"] = row.pop("raw_response")
            row["raw_provider_response"] = originals.get(row["request_id"])
        for artifact, raw, parsed in zip(report["construction"], extraction_raw, extraction_parsed):
            artifact["parsed_response"] = artifact.pop("raw_response")
            artifact["raw_provider_response"] = raw
            artifact["parsed_provider_response"] = parsed
        report["normalization_audit"] = audit
        transport.preserve(run_dir / "result.json", report)
        usage = usage_report(run_dir, manifest, answers)
        transport.preserve(run_dir / "usage.json", usage)
        return {"status": "method_selection_v2_live_scored", "summary": report["summary"], "usage": usage}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--credential-config", type=Path, default=Path.home() / ".workbuddy/models.json")
    parser.add_argument("--credential-profile", default="DeepSeek-V4-Pro",
                        help="Credential record only; --model controls inference")
    parser.add_argument("--key-env", choices=["PARATERA_API_KEY"])
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-requests", type=int, default=50)
    parser.add_argument("--max-tokens", type=int, default=150000)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    manifest = make_manifest(args.model, args.max_requests, args.max_tokens, args.timeout)
    if not args.execute:
        print(json.dumps({"status": "dry_run_no_network", "manifest": manifest}, indent=2))
        return
    key = transport.load_key(args.credential_config, args.credential_profile, args.key_env)
    with httpx.Client(timeout=args.timeout, follow_redirects=False, trust_env=False) as client:
        try:
            result = run(manifest, args.run_dir, client, key)
        except transport.RunStopped as exc:
            print(json.dumps({"status": "stopped", "reason": str(exc)}), flush=True)
            raise SystemExit(2) from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
