"""Opt-in, budgeted Paratera execution of the frozen method-selection v1 protocol."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("frozen_method_selection", HERE / "run_experiment.py")
experiment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(experiment)

from sheaf_ai.provenance_registry import provenance_registry_lock  # noqa: E402

ENDPOINT = "https://llmapi.paratera.com/v1/chat/completions"


class RunStopped(RuntimeError):
    """A persisted failure or budget boundary requires inspection, not a retry."""


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    """Exclusive creation plus fsync. Partial writes fail closed on the next read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def preserve(path, value):
    if path.exists():
        if experiment.read_json(path) != value:
            raise RunStopped(f"Existing artifact differs: {path.name}")
    else:
        save(path, value)


def load_key(config_path, profile, key_env=None):
    """Read only the explicitly selected credential; never use an Anthropic fallback."""
    if key_env:
        if key_env != "PARATERA_API_KEY":
            raise ValueError("Only PARATERA_API_KEY is accepted as an environment credential")
        key = os.environ.get(key_env, "").strip()
    else:
        profiles = experiment.read_json(config_path)
        matches = [p for p in profiles if p.get("id") == profile and p.get("url") == ENDPOINT]
        if len(matches) != 1:
            raise ValueError("Expected one matching Paratera credential profile")
        key = str(matches[0].get("apiKey") or "").strip()
    if not key or "\n" in key or "\r" in key:
        raise ValueError("Paratera credential missing or invalid")
    return key


def source_hashes():
    return {p.relative_to(ROOT).as_posix(): experiment.file_hash(p) for p in (
        Path(__file__), HERE / "live_protocol.md", ROOT / "sheaf_ai/provenance_registry.py")}


def make_manifest(model, max_requests=50, max_tokens=150000, timeout=90):
    if not experiment.text(model) or any(type(v) is not int or v < 1 for v in (max_requests, max_tokens, timeout)):
        raise ValueError("Explicit model and positive integer limits required")
    if max_requests > 50 or max_tokens > 150000 or timeout > 180:
        raise ValueError("Pilot ceiling: 50 requests, 150000 tokens, 180 seconds per request")
    lock = experiment.read_json(HERE / "lock.json")
    experiment.verify_lock(lock)  # Never read gold while preparing or sending requests.
    value = {"version": "method-selection-live-v1", "model": model, "endpoint": ENDPOINT,
             "max_requests": max_requests, "max_tokens": max_tokens, "timeout_seconds": timeout,
             "retries": 0, "concurrency": 1, "context_budget_characters": 6000,
             "input_reservation": "utf8(system+prompt) bytes + 512; operational estimate, not tokenizer",
             "pricing": {"currency": "CNY", "amount": None, "status": "provider_rate_not_verified"},
             "lock": lock, "executor_code": source_hashes()}
    return {**value, "manifest_hash": experiment.digest(value)}


def reservation(req):
    return len((req["system"] + req["prompt"]).encode("utf-8")) + 512 + req["max_output_tokens"]


def validate_request(req, manifest):
    fields = {"request_id", "model", "system", "prompt", "temperature", "max_output_tokens", "request_hash"}
    if set(req) != fields or not all(experiment.text(req.get(k)) for k in ("request_id", "model", "system", "prompt")):
        raise ValueError("Invalid request schema")
    if req["request_hash"] != experiment.digest({k: v for k, v in req.items() if k != "request_hash"}):
        raise ValueError("Request hash mismatch")
    if req["model"] != manifest["model"] or req["temperature"] != 0:
        raise ValueError("Request model/temperature differs from the frozen plan")
    if type(req["max_output_tokens"]) is not int or not 1 <= req["max_output_tokens"] <= 4096:
        raise ValueError("Unexpected output cap")


def response_record(req, status, body, elapsed):
    """Keep raw provider identity and usage; malformed envelopes never become successes."""
    envelope = {"request_id": req["request_id"], "request_hash": req["request_hash"],
                "model": req["model"], "text": "", "finish_reason": "error",
                "usage": {"input_tokens": None, "output_tokens": None}, "latency_ms": elapsed}
    issues, provider_model, provider_usage = [], None, None
    try:
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        provider_model = data.get("model")
        provider_usage = data.get("usage")
        if isinstance(provider_usage, dict):
            for dest, src in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens")):
                value = provider_usage.get(src)
                if type(value) is int and value >= 0:
                    envelope["usage"][dest] = value
        if status != 200:
            issues.append("http_error")
        else:
            if provider_model != req["model"]:
                issues.append("provider_model_mismatch")
                # Do not relabel a different/missing reported model to pass the importer.
                envelope["model"] = provider_model if isinstance(provider_model, str) else "unreported"
            choices = data.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError("expected exactly one choice")
            choice = choices[0]
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("expected text content")
            envelope["text"] = content
            finish = choice.get("finish_reason")
            if finish not in {"stop", "length", "content_filter"}:
                issues.append("unknown_finish_reason")
            else:
                envelope["finish_reason"] = finish
    except (ValueError, TypeError, KeyError):
        issues.append("invalid_provider_envelope")
    if any(v is None for v in envelope["usage"].values()):
        issues.append("unknown_usage")
    if isinstance(provider_usage, dict) and "total_tokens" in provider_usage:
        total = provider_usage["total_tokens"]
        if (type(total) is not int or any(v is None for v in envelope["usage"].values())
                or total != sum(envelope["usage"].values())):
            issues.append("inconsistent_usage")
    return {"response": envelope, "provider_model": provider_model, "provider_usage": provider_usage,
            "issues": issues}


def check_receipt(value):
    if value.get("receipt_hash") != experiment.digest({k: v for k, v in value.items() if k != "receipt_hash"}):
        raise RunStopped("Receipt checksum mismatch")
    return value


def receipts(run_dir, manifest):
    rows = []
    intents = sorted((run_dir / "calls").glob("*.intent.json"))
    results = list((run_dir / "calls").glob("*.result.json"))
    if len(results) > len(intents):
        raise RunStopped("Orphaned result")
    for path in intents:
        intent = check_receipt(experiment.read_json(path))
        req = intent["request"]
        validate_request(req, manifest)
        if intent["manifest_hash"] != manifest["manifest_hash"] or path.name != req["request_hash"] + ".intent.json":
            raise RunStopped("Intent identity mismatch")
        result_path = path.with_name(req["request_hash"] + ".result.json")
        if not result_path.exists():
            raise RunStopped("Uncertain prior call; inspect intent before any further API use; no automatic resend")
        result = check_receipt(experiment.read_json(result_path))
        if result["intent_hash"] != intent["receipt_hash"]:
            raise RunStopped("Result does not match intent")
        if result["issues"]:
            raise RunStopped("Prior provider/usage failure requires inspection: " + ", ".join(result["issues"]))
        rows.append((intent, result))
    expected_results = {p.name.replace(".intent.json", ".result.json") for p in intents}
    if {p.name for p in results} != expected_results:
        raise RunStopped("Orphaned result")
    return rows


def signed(value):
    return {**value, "receipt_hash": experiment.digest(value)}


def execute_request(req, manifest, run_dir, client, key):
    validate_request(req, manifest)
    previous = receipts(run_dir, manifest)
    for intent, result in previous:
        if intent["request"]["request_id"] == req["request_id"]:
            if intent["request"] != req:
                raise RunStopped("Request ID reused for different contents")
            return result["response"], False
    spent = sum(sum(r["response"]["usage"].values()) for _, r in previous)
    reserved = reservation(req)
    if len(previous) >= manifest["max_requests"] or spent + reserved > manifest["max_tokens"]:
        raise RunStopped("Budget exhausted before dispatch; no request sent")
    intent = signed({"request": req, "manifest_hash": manifest["manifest_hash"],
                     "reserved_tokens_estimate": reserved, "started_at": now()})
    calls = run_dir / "calls"
    save(calls / (req["request_hash"] + ".intent.json"), intent)
    payload = {"model": req["model"], "messages": [{"role": "system", "content": req["system"]},
               {"role": "user", "content": req["prompt"]}], "temperature": req["temperature"],
               "max_tokens": req["max_output_tokens"], "stream": False}
    start, body, status, transport_error = time.monotonic(), "", None, None
    try:
        response = client.post(ENDPOINT, headers={"Authorization": "Bearer " + key}, json=payload)
        status, body = response.status_code, response.text
    except httpx.HTTPError as exc:
        transport_error = type(exc).__name__  # Never record exception strings/headers/credential values.
    elapsed = round((time.monotonic() - start) * 1000, 3)
    redacted = bool(key and key in body)
    if redacted:
        body = body.replace(key, "[REDACTED_CREDENTIAL]")
    parsed = response_record(req, status, body, elapsed)
    if transport_error:
        parsed["issues"].append("transport_error")
    if redacted:
        parsed["issues"].append("credential_reflected_and_redacted")
    if not parsed["issues"] and sum(parsed["response"]["usage"].values()) > reserved:
        parsed["issues"].append("usage_exceeded_reservation")
    result = signed({**parsed, "intent_hash": intent["receipt_hash"], "finished_at": now(),
                     "http_status": status, "transport_error_type": transport_error,
                     "raw_body": body, "raw_body_credential_redacted": redacted})
    save(calls / (req["request_hash"] + ".result.json"), result)
    print(json.dumps({"request_id": req["request_id"], "http_status": status,
                      "finish_reason": parsed["response"]["finish_reason"],
                      "usage": parsed["response"]["usage"], "issues": parsed["issues"]}), flush=True)
    if parsed["issues"]:
        raise RunStopped("Provider/usage failure persisted; no automatic retry: " + ", ".join(parsed["issues"]))
    return parsed["response"], True


def usage_report(run_dir, manifest, plan):
    rows = receipts(run_dir, manifest)
    usage = {"probe": [0, 0, 0], "construction": [0, 0, 0],
             **{arm: [0, 0, 0] for arm in experiment.ARMS}}
    arms = {c["request_id"]: c["arm"] for c in plan["cases"]}
    for intent, result in rows:
        rid = intent["request"]["request_id"]
        group = "probe" if rid == "probe" else "construction" if rid.startswith("extract-") else arms[rid]
        inp, out = (result["response"]["usage"][k] for k in ("input_tokens", "output_tokens"))
        usage[group] = [x + y for x, y in zip(usage[group], [1, inp, out])]
    groups = {k: dict(zip(("calls", "input_tokens", "output_tokens"), v)) for k, v in usage.items()}
    return {"actual_requests": len(rows), "total_tokens": sum(v[1] + v[2] for v in usage.values()),
            "groups": groups, "standalone_arm_total_tokens": {
                arm: sum(usage[arm][1:]) + (sum(usage["construction"][1:]) if arm != "raw" else 0)
                for arm in experiment.ARMS}, "currency": "CNY", "actual_cost": None,
            "cost_status": "No verified provider prices or invoice; tokens are not money",
            "limitations": ["Probe excluded from standalone arm cost", "Shared extraction charged in full to each standalone card arm",
                            "Provider-reported token usage; no independent billing verification",
                            "Operational reservation is not a tokenizer or equal-token comparison"]}


def run(manifest, run_dir, client, key, *, probe_only=False, max_new_requests=None):
    # Lock the whole run, not individual calls: budgets must survive simultaneous invocations.
    with provenance_registry_lock(run_dir / "execution", timeout=1):
        preserve(run_dir / "manifest.json", manifest)
        if source_hashes() != manifest["executor_code"]:
            raise RunStopped("Executor source changed; start a new revision")
        experiment.verify_lock(manifest["lock"])
        new_calls = 0

        def dispatch(req):
            nonlocal new_calls
            if source_hashes() != manifest["executor_code"]:
                raise RunStopped("Executor source changed during run")
            experiment.verify_lock(manifest["lock"])
            if max_new_requests is not None and new_calls >= max_new_requests:
                raise RunStopped("Requested pause after new calls; resume with the same run directory")
            reply, sent = execute_request(req, manifest, run_dir, client, key)
            new_calls += int(sent)
            return reply

        probe = experiment.request("probe", manifest["model"], 'Return exactly {"ok": true}.', 32)
        probe_reply = dispatch(probe)
        if probe_reply["finish_reason"] != "stop" or json.loads(probe_reply["text"]) != {"ok": True}:
            raise RunStopped("Probe did not produce the requested object; not proceeding to the experiment")
        if probe_only:
            return {"status": "probe_passed", "new_requests": new_calls}
        extraction = experiment.prepare_extraction(manifest["lock"], manifest["model"])
        preserve(run_dir / "extraction-plan.json", extraction)
        extraction_responses = [dispatch(r) for r in extraction["requests"]]
        preserve(run_dir / "extraction-responses.json", extraction_responses)
        answers = experiment.prepare_answers(extraction, extraction_responses, manifest["context_budget_characters"])
        preserve(run_dir / "answer-plan.json", answers)
        answer_responses = [dispatch(r) for r in answers["requests"]]
        preserve(run_dir / "answer-responses.json", answer_responses)
        report = experiment.score(answers, answer_responses)  # First gold read in the live workflow.
        preserve(run_dir / "result.json", report)
        usage = usage_report(run_dir, manifest, answers)
        preserve(run_dir / "usage.json", usage)
        return {"status": "live_development_run_scored", "new_requests": new_calls,
                "summary": report["summary"], "usage": usage}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--credential-config", type=Path, default=Path.home() / ".workbuddy/models.json")
    parser.add_argument("--credential-profile", default="DeepSeek-V4-Pro")
    parser.add_argument("--key-env", choices=["PARATERA_API_KEY"])
    parser.add_argument("--execute", action="store_true", help="Required opt-in for paid calls")
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--max-new-requests", type=int)
    parser.add_argument("--max-requests", type=int, default=50)
    parser.add_argument("--max-tokens", type=int, default=150000)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    if args.max_new_requests is not None and args.max_new_requests < 1:
        parser.error("--max-new-requests must be positive")
    manifest = make_manifest(args.model, args.max_requests, args.max_tokens, args.timeout)
    if not args.execute:
        print(json.dumps({"status": "dry_run_no_network", "manifest": manifest}, indent=2))
        return
    if urlsplit(ENDPOINT).hostname != "llmapi.paratera.com":
        raise ValueError("Unexpected credential destination")
    key = load_key(args.credential_config, args.credential_profile, args.key_env)
    # No redirects, provider fallback, SDK retries, proxy auto-discovery, or SSL bypass.
    with httpx.Client(timeout=args.timeout, follow_redirects=False, trust_env=False) as client:
        try:
            result = run(manifest, args.run_dir, client, key, probe_only=args.probe_only,
                         max_new_requests=args.max_new_requests)
        except RunStopped as exc:
            print(json.dumps({"status": "stopped", "reason": str(exc)}), flush=True)
            raise SystemExit(2) from None
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
