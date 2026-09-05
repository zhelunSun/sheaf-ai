"""Explicit opt-in execution; replay verifies the same payloads without credentials."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import experiment as e  # noqa: E402
import transport as tr  # noqa: E402

MODEL = "DeepSeek-V4-Flash"
CAMPAIGN = HERE / "campaigns/paratera-flash-20260905"
RUN = CAMPAIGN / "run-v1"


def manifest(lock):
    value = {"model": MODEL, "endpoint": tr.ENDPOINT, "max_requests": 170,
             "max_tokens": 600000, "lock": lock, "context_cap": 800,
             "draws": 2, "seed": 20260905, "temperature": .2, "timeout_seconds": 120,
             "extraction_output_cap": 6000, "answer_output_cap": 1200,
             "currency_cost": None, "evidence_grade": "agent_reviewed_synthetic"}
    return {**value, "manifest_hash": tr.digest(value)}


def load_key(path):
    # Explicit profile AND destination. Never inspect unrelated provider credentials.
    records = e.read(path)
    matches = [r for r in records if r.get("id") == "DeepSeek-V4-Pro" and r.get("url") == tr.ENDPOINT]
    if len(matches) != 1:
        raise ValueError("Expected one explicit Paratera profile")
    key = matches[0].get("apiKey")
    if not isinstance(key, str) or not key.strip() or any(c in key for c in "\r\n"):
        raise ValueError("Paratera credential unavailable")
    return key.strip()


def payload(prompt, cap):
    return tr.make_payload(MODEL, e.SYSTEM, prompt, cap)


def extraction_payload(bundle):
    # Tasks and evaluation labels are deliberately absent from this construction.
    return payload(e.EXTRACT + json.dumps({k: bundle[k] for k in ("method_ids", "sources")},
                                          ensure_ascii=False), 6000)


def answer_plan(contexts):
    plan = []
    for c in contexts:
        for draw in (1, 2):
            rid = f"answer-{c['task_id']}-{c['arm']}-r{draw}"
            body = None if c["preparation_error"] else payload(
                e.ANSWER + json.dumps({"task": {k: c["task"][k] for k in ("question", "options")},
                                       "context": c["context"]}, ensure_ascii=False), 1200)
            plan.append({"request_id": rid, "task_id": c["task_id"], "arm": c["arm"], "draw": draw,
                         "payload": body, "payload_hash": tr.payload_digest(body) if body else None})
    random.Random(20260905).shuffle(plan)
    return plan


def validate_response(response, rid, body):
    if (response["request_id"] != rid or response["payload_hash"] != tr.payload_digest(body)
            or response["model"] != MODEL or not isinstance(response["text"], str)
            or any(type(response["usage"].get(k)) is not int or response["usage"][k] < 0
                   for k in ("input_tokens", "output_tokens"))):
        raise ValueError("Response identity or usage differs from frozen request")


def cost_report(bundles, extraction, cases, responses, probe):
    def tokens(r):
        return sum(r["usage"].values())
    construction = {bid: tokens(r) for bid, r in extraction.items()}
    table = {}
    for arm in e.ARMS:
        rows = [c for c in cases if c["arm"] == arm]
        actual = sum(tokens(responses[c["request_id"]]) for c in rows if c["request_id"] in responses)
        table[arm] = {"actual_answer_tokens_two_draws": actual,
                      "construction_tokens": 0 if arm == "raw_passages" else sum(construction.values()),
                      "scenario_total_tokens": {}}
        for n in (1, 5, 20):
            total = 0
            for b in bundles:
                sampled = [responses[c["request_id"]] for c in rows if c["bundle_id"] == b["bundle_id"]
                           and c["request_id"] in responses]
                # Do not impute cheap zero-cost successful deployment after preparation failure.
                if len(sampled) != 2 * len(b["tasks"]):
                    total = None
                    break
                total += n * sum(tokens(r) for r in sampled) / len(sampled)
                if arm != "raw_passages":
                    total += construction[b["bundle_id"]]
            table[arm]["scenario_total_tokens"][str(n)] = total
    return {"arms": table, "shared_construction_by_bundle": construction,
            "probe_tokens": tokens(probe), "currency_cost": None,
            "scenario_definition": "N future queries per bundle at the mean usage of its three tasks and two draws; not additional live measurements. Full shared construction charged to each standalone fact deployment. Token total is not a money estimate."}


def cache_usage():
    groups = {}
    for path in sorted((RUN / "calls").glob("*.result.json")):
        receipt = e.read(path)
        rid = receipt["response"]["request_id"]
        group = next((arm for arm in e.ARMS if f"-{arm}-" in rid), "construction" if rid.startswith("extract-") else "probe")
        row = groups.setdefault(group, {"requests": 0, "reported_requests": 0, "known_cached_input_tokens": 0})
        row["requests"] += 1
        usage = receipt.get("provider_usage") or {}
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        if type(cached) is int and 0 <= cached <= usage["prompt_tokens"]:
            row["reported_requests"] += 1
            row["known_cached_input_tokens"] += cached
    return groups


def oracle_budget_check(bundles, gold, count):
    """Evaluator-only possibility check; never used by extraction or selection."""
    report = {}
    for b in bundles:
        units = e.raw_units(b, count)
        for task in b["tasks"]:
            candidates = []
            for support in gold[task["task_id"]]["support_sets"]:
                required = e.citation_spans(support, b)
                needed = [u for u in units if any(
                    s["source_id"] == q["source_id"] and max(s["start"], q["start"]) < min(s["end"], q["end"])
                    for s in u["spans"] for q in required)]
                if all(e.covered(q, [s for u in needed for s in u["spans"]]) for q in required):
                    candidates.append(count("\n\n".join(u["text"] for u in needed)))
            report[task["task_id"]] = min(candidates) if candidates else None
    if any(v is None or v > 800 for v in report.values()):
        raise ValueError("A gold sufficient set cannot fit the raw whole-unit allowance")
    return report


def run(count, offline=False):
    lock = e.read(HERE / "lock.json")
    e.verify_lock(lock)
    bundles = e.load_inputs()
    m = manifest(lock)
    key = "offline" if offline else load_key(Path.home() / ".workbuddy/models.json")

    def forbidden(_request):
        raise AssertionError("Offline replay attempted a network call")

    transport = httpx.MockTransport(forbidden) if offline else httpx.HTTPTransport(retries=0)
    with httpx.Client(transport=transport, timeout=120, trust_env=False, follow_redirects=False) as http:
        client = tr.ExperimentClient(RUN, m, http, key, CAMPAIGN)

        def call(rid, body):
            e.verify_lock(lock)
            result = client.call(rid, body)
            validate_response(result, rid, body)
            return result

        probe = call("probe", payload('Return exactly {"ok":true}.', 32))
        if e.parse_text(probe)[0] != {"ok": True}:
            raise ValueError("Probe content failed; no experiment call sent")
        extraction = {}
        for b in bundles:
            extraction[b["bundle_id"]] = call("extract-" + b["bundle_id"], extraction_payload(b))
            print(json.dumps({"extracted": b["bundle_id"]}), flush=True)
        contexts, facts = e.prepare_contexts(bundles, extraction, count)
        e.preserve(RUN / "contexts.json", contexts)
        e.preserve(RUN / "extracted-facts.json", facts)
        plan = answer_plan(contexts)
        e.preserve(RUN / "answer-plan.json", plan)
        lookup = {(c["task_id"], c["arm"]): c for c in contexts}
        cases, responses = [], {}
        for i, item in enumerate(plan):
            cases.append({**lookup[(item["task_id"], item["arm"])],
                          "request_id": item["request_id"], "draw": item["draw"]})
            if item["payload"] is not None:
                responses[item["request_id"]] = call(item["request_id"], item["payload"])
            if (i + 1) % 12 == 0:
                print(json.dumps({"answers_processed": i + 1, "planned": len(plan)}), flush=True)
    # Every cached/live response was bound to its actual payload above, before gold is loaded.
    e.verify_lock(lock, include_gold=True)
    gold = e.load_gold(HERE, bundles)
    rows = e.score_rows(cases, responses, gold, bundles)
    context_pairs = [{"task_id": t["task_id"],
                      "same_context": lookup[(t["task_id"], "all_facts")]["context"] ==
                                      lookup[(t["task_id"], "scoped_facts")]["context"]}
                     for b in bundles for t in b["tasks"]]
    result = {"manifest_hash": m["manifest_hash"], "summary": e.summarize(rows), "rows": rows,
              "fact_arm_context_pairs": context_pairs,
              "cost": cost_report(bundles, extraction, cases, responses, probe),
              "provider_cache_usage": cache_usage(),
              "campaign_usage": tr.report_usage(CAMPAIGN)}
    e.preserve(RUN / "results.json", result)
    # Hide arms/automatic scores from the independent semantic reviewer, preserving lookup separately.
    shuffled = [row for row in rows if row["draw"] == 1]
    random.Random(1741).shuffle(shuffled)
    packet, mapping = [], {}
    for i, row in enumerate(shuffled):
        anonymous = f"a{i + 1:03d}"
        packet.append({"id": anonymous, "task_id": row["task_id"], "answer": row["answer"],
                       "error": row["error"]})
        mapping[anonymous] = row["request_id"]
    e.preserve(RUN / "semantic-review-packet.json", packet)
    e.preserve(RUN / "semantic-review-mapping.json", mapping)
    print(json.dumps({"summary": result["summary"], "usage": result["campaign_usage"]}, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "preflight", "run", "replay"))
    parser.add_argument("--tokenizer", type=Path, default=e.ROOT / ".pytest-tmp/v3-assets/tokenizer.json")
    parser.add_argument("--execute", action="store_true", help="Required for paid live requests")
    args = parser.parse_args()
    if args.command == "freeze":
        e.preserve(HERE / "lock.json", e.freeze())
        print("Frozen inputs, labels, protocol, tokenizer identity and code; no API call.")
    elif args.command == "preflight":
        lock = e.read(HERE / "lock.json")
        e.verify_lock(lock, include_gold=True)
        count = e.Counter(args.tokenizer)
        bundles = e.load_inputs()
        gold = e.load_gold(HERE, bundles)
        report = {"lock_hash": lock["lock_hash"], "bundles": len(bundles), "tasks": sum(len(b["tasks"]) for b in bundles),
                          "source_tokens": {b["bundle_id"]: count("\n".join(s["text"] for s in b["sources"]))
                                            for b in bundles}, "oracle_whole_unit_tokens": oracle_budget_check(bundles, gold, count),
                          "intended_calls": 153,
                          "max_calls": 170, "max_tokens": 600000}
        e.preserve(HERE / "preflight.json", report)
        print(json.dumps(report, indent=2))
    elif args.command == "run" and not args.execute:
        parser.error("Live mode requires explicit --execute")
    else:
        run(e.Counter(args.tokenizer), offline=args.command == "replay")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, tr.RunStopped, OSError) as exc:
        # Never echo arbitrary exception content from credential parsing or network libraries.
        print(json.dumps({"status": "stopped", "error_type": type(exc).__name__,
                          "action": "Inspect frozen artifacts; do not automatically retry or delete intents."}))
        raise SystemExit(2) from None
