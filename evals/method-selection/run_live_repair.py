"""Post-hoc protocol repair: explicit extraction IDs, outer-fence parsing, cached raw baseline."""
from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re

import httpx

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("live_method_v1", HERE / "run_live.py")
live = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(live)
experiment = live.experiment
REVISION = "method-selection-post-hoc-interface-repair-v1"


def repair_hashes():
    return {p.relative_to(live.ROOT).as_posix(): experiment.file_hash(p) for p in (
        Path(__file__), HERE / "repair_protocol.md")}


def unwrap(row):
    """Only a single whole-message JSON fence. No ID mapping, quote edits or JSON repair."""
    result = deepcopy(row)
    original = row["text"]
    match = re.fullmatch(r"```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```[ \t]*", original.strip())
    transformation = "identity"
    if row["finish_reason"] == "stop" and match:
        try:
            json.loads(match[1])
        except ValueError:
            pass
        else:
            result["text"] = match[1]
            transformation = "whole_message_json_fence_removed"
    return result, {"request_id": row["request_id"], "transformation": transformation,
                    "original_text_hash": experiment.digest(original),
                    "parsed_text_hash": experiment.digest(result["text"])}


def parent_state(parent):
    cfg = experiment.read_json(parent / "manifest.json")
    expected = live.make_manifest(cfg["model"], cfg["max_requests"], cfg["max_tokens"], cfg["timeout_seconds"])
    if cfg != expected:
        raise live.RunStopped("Parent manifest/source mismatch")
    rows = live.receipts(parent, cfg)
    plans = {phase: experiment.read_json(parent / f"{phase}-plan.json") for phase in ("extraction", "answer")}
    for plan in plans.values():
        experiment.verify_plan(plan)
    replies = {phase: experiment.read_json(parent / f"{phase}-responses.json") for phase in plans}
    by_receipt = {i["request"]["request_id"]: (i["request"], r["response"]) for i, r in rows}
    for phase, plan in plans.items():
        by_id = experiment.load_responses(plan, replies[phase])
        for request in plan["requests"]:
            if by_receipt.get(request["request_id"]) != (request, by_id[request["request_id"]]):
                raise live.RunStopped("Parent exports differ from original provider receipts")
    raw_requests = {r["request_id"]: r for r in plans["answer"]["requests"] if r["request_id"].endswith("-raw")}
    if len(raw_requests) != 12:
        raise live.RunStopped("Expected twelve completed raw baseline requests")
    raw_replies = {r["request_id"]: r for r in replies["answer"] if r["request_id"] in raw_requests}
    spent = sum(sum(r["response"]["usage"].values()) for _, r in rows)
    files = [parent / "manifest.json", *[parent / f"{p}-{suffix}.json" for p in plans for suffix in ("plan", "responses")],
             *sorted((parent / "calls").glob("*.json"))]
    return {"manifest": cfg, "requests": raw_requests, "responses": raw_replies,
            "spent_requests": len(rows), "spent_tokens": spent,
            "files": {p.relative_to(parent).as_posix(): experiment.file_hash(p) for p in files}}


def repair_manifest(state):
    original = state["manifest"]
    # The same user-authorized cap covers BOTH the failed pilot and the repair.
    remaining_calls = original["max_requests"] - state["spent_requests"]
    remaining_tokens = original["max_tokens"] - state["spent_tokens"]
    if remaining_calls < 1 or remaining_tokens < 1:
        raise live.RunStopped("No remaining campaign budget")
    cfg = live.make_manifest(original["model"], remaining_calls, remaining_tokens, original["timeout_seconds"])
    cfg.pop("manifest_hash")
    cfg.update(version=REVISION, repair_code=repair_hashes(), parent_manifest_hash=original["manifest_hash"],
               parent_files=state["files"], parent_spent_requests=state["spent_requests"],
               parent_spent_tokens=state["spent_tokens"], evidence_grade="post_hoc_synthetic_development_only",
               probe_policy="reuse_parent_probe; no new call", baseline_policy="reuse_exact_raw_requests_and_responses")
    return {**cfg, "manifest_hash": experiment.digest(cfg)}


def extraction_plan(cfg):
    plan = experiment.prepare_extraction(cfg["lock"], cfg["model"])
    plan.pop("plan_hash")
    inputs = experiment.load_inputs()
    for request, bundle in zip(plan["requests"], inputs):
        options = sorted({o for task in bundle["tasks"] for o in task["options"]})
        prompt = request["prompt"] + "\nAllowed method_id strings: " + json.dumps(options)
        prompt += ". Use these exact IDs, not names such as Method A. Emit bare JSON, without Markdown fences."
        request.update(experiment.request(request["request_id"], cfg["model"], prompt, request["max_output_tokens"]))
    plan["protocol_revision"] = {"revision": REVISION, "manifest_hash": cfg["manifest_hash"]}
    return experiment.seal(plan)


def run(parent, run_dir, client, key):
    if parent.resolve() == run_dir.resolve():
        raise ValueError("Repair needs a separate output directory")
    with live.provenance_registry_lock(parent / "execution", timeout=1):
        state = parent_state(parent)
        cfg = repair_manifest(state)
        with live.provenance_registry_lock(run_dir / "execution", timeout=1):
            live.preserve(run_dir / "manifest.json", cfg)
            new_calls = 0

            def dispatch(request):
                nonlocal new_calls
                if repair_hashes() != cfg["repair_code"] or live.source_hashes() != cfg["executor_code"]:
                    raise live.RunStopped("Executor source changed during repair")
                experiment.verify_lock(cfg["lock"])
                response, sent = live.execute_request(request, cfg, run_dir, client, key)
                new_calls += int(sent)
                return response

            extraction = extraction_plan(cfg)
            live.preserve(run_dir / "extraction-plan.json", extraction)
            provider_extraction = [dispatch(r) for r in extraction["requests"]]
            parsed_extraction, audit = [], []
            for response in provider_extraction:
                parsed, entry = unwrap(response)
                parsed_extraction.append(parsed)
                audit.append(entry)
            live.preserve(run_dir / "extraction-provider-responses.json", provider_extraction)
            live.preserve(run_dir / "extraction-parsed-responses.json", parsed_extraction)
            answers = experiment.prepare_answers(extraction, parsed_extraction, cfg["context_budget_characters"])
            answers.pop("plan_hash")
            answers["protocol_revision"] = extraction["protocol_revision"]
            answers = experiment.seal(answers)
            live.preserve(run_dir / "answer-plan.json", answers)
            provider_answers, parsed_answers = [], []
            for request in answers["requests"]:
                rid = request["request_id"]
                if rid.endswith("-raw"):
                    if request != state["requests"].get(rid):
                        raise live.RunStopped("Raw baseline changed; cached response cannot be used")
                    response = state["responses"][rid]
                else:
                    response = dispatch(request)
                provider_answers.append(response)
                parsed, entry = unwrap(response)
                parsed_answers.append(parsed)
                audit.append(entry)
            live.preserve(run_dir / "answer-provider-responses.json", provider_answers)
            live.preserve(run_dir / "answer-parsed-responses.json", parsed_answers)
            live.preserve(run_dir / "normalization-audit.json", audit)
            # Do not present normalized text as raw model output in the report.
            report = experiment.score(answers, parsed_answers)
            report.update(protocol_revision=answers["protocol_revision"], evidence_grade=cfg["evidence_grade"],
                          normalization_audit=audit, reused_raw_baseline_requests=12)
            originals = {r["request_id"]: r for r in provider_answers}
            for row in report["rows"]:
                row["parsed_response"] = row.pop("raw_response")
                row["raw_provider_response"] = originals.get(row["request_id"])
            for artifact, raw in zip(report["construction"], provider_extraction):
                artifact["parsed_response"] = artifact.pop("raw_response")
                artifact["raw_provider_response"] = raw
            report["limitations"] += ["Interface repair designed after seeing v1 failures; not an independent replication",
                                       "Raw answers reused by exact request hash; not newly sampled"]
            live.preserve(run_dir / "result.json", report)
            usage = live.usage_report(run_dir, cfg, answers)
            raw_in = sum(r["usage"]["input_tokens"] for r in state["responses"].values())
            raw_out = sum(r["usage"]["output_tokens"] for r in state["responses"].values())
            usage["reused_raw_baseline"] = {"calls": 12, "input_tokens": raw_in, "output_tokens": raw_out}
            usage["standalone_arm_total_tokens"]["raw"] = raw_in + raw_out
            usage["campaign_total_requests"] = state["spent_requests"] + usage["actual_requests"]
            usage["campaign_total_tokens"] = state["spent_tokens"] + usage["total_tokens"]
            usage["limitations"] += ["Campaign total includes failed v1 construction and probe",
                                      "Standalone card costs use repaired construction; failed v1 is setup overhead"]
            live.preserve(run_dir / "usage.json", usage)
            return {"status": "post_hoc_interface_repair_scored", "new_requests": new_calls,
                    "summary": report["summary"], "usage": usage}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-run", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--credential-config", type=Path, default=Path.home() / ".workbuddy/models.json")
    parser.add_argument("--credential-profile", default="DeepSeek-V4-Pro")
    parser.add_argument("--key-env", choices=["PARATERA_API_KEY"])
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    state = parent_state(args.parent_run)
    cfg = repair_manifest(state)
    if not args.execute:
        print(json.dumps({"status": "dry_run_no_network", "manifest": cfg}, indent=2))
        return
    key = live.load_key(args.credential_config, args.credential_profile, args.key_env)
    with httpx.Client(timeout=cfg["timeout_seconds"], follow_redirects=False, trust_env=False) as client:
        try:
            result = run(args.parent_run, args.run_dir, client, key)
        except live.RunStopped as exc:
            print(json.dumps({"status": "stopped", "reason": str(exc)}), flush=True)
            raise SystemExit(2) from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
