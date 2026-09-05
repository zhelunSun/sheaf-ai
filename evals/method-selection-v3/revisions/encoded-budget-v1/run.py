"""Count the delivered JSON context literal; reuse only identical frozen calls."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
sys.path.insert(0, str(BASE))
import experiment as e  # noqa: E402

previous = e.load_module("v3_output_cap_wrapper", HERE.parent / "output-cap-v1/run.py")


def make_lock():
    parent = previous.verify_revision()
    value = {"revision": "encoded-budget-v1", "parent_revision_lock_hash": parent["revision_lock_hash"],
             "code": {name: e.code_hash(HERE / name) for name in ("run.py", "protocol.md")}}
    return {**value, "revision_lock_hash": e.digest(value)}


def verify_revision():
    saved = e.read(HERE / "revision-lock.json")
    if saved != make_lock():
        raise ValueError("Encoded-budget revision identity changed")
    return saved


def encoded_counter(count):
    return lambda text: count(json.dumps(text, ensure_ascii=False))


def stable_select(units, task, count, cap=800, scope=False):
    """Original scoring formula; ordered float reductions and delivered-text budget."""
    count = encoded_counter(count)
    query = set(e._tokens(task["question"] + " " + " ".join(task["options"])))
    sets = [set(e._tokens(u["text"])) for u in units]
    weights = {t: math.log((len(units) + 1) / (sum(t in ts for ts in sets) + 1)) + 1 for t in sorted(query)}
    denom = sum(w for t, w in weights.items() if any(t in ts for ts in sets)) or 1
    scores = [sum(weights[t] for t in sorted(query & ts)) / denom + min(.2, len(query & ts) / max(1, len(ts)))
              for ts in sets]
    remaining = {i for i, u in enumerate(units) if not scope or u["method_id"] is None or u["method_id"] in task["options"]}
    eligible, selected, context = sorted(remaining), [], ""
    while remaining:
        chosen = max(remaining, key=lambda i: (scores[i] - .35 * max(
            (e._jaccard(sets[i], sets[j]) for j in selected), default=0), scores[i], -i))
        remaining.remove(chosen)
        trial = "\n\n".join(units[i]["text"] for i in [*selected, chosen])
        if count(trial) <= cap:
            selected.append(chosen)
            context = trial
    tokens = count(context)
    return {"context": context, "context_tokens": tokens, "slack_tokens": cap - tokens,
            "selected_ids": [units[i]["unit_id"] for i in selected],
            "omitted_ids": [u["unit_id"] for i, u in enumerate(units) if i not in selected],
            "eligible_ids": [units[i]["unit_id"] for i in eligible],
            "visible_spans": [s for i in selected for s in units[i]["spans"]], "candidate_units": units}


def configure():
    lock = verify_revision()
    r = previous.configured_runner()
    parent_run = r.RUN
    parent_manifest = e.read(parent_run / "manifest.json")
    if parent_manifest != r.manifest(e.read(BASE / "lock.json")):
        raise ValueError("Parent output-cap manifest differs")
    old_manifest = r.manifest
    ParentClient = r.tr.ExperimentClient
    parent_plan = {p["request_id"]: p for p in e.read(parent_run / "answer-plan.json")}
    r.RUN = r.CAMPAIGN / "run-v3-encoded-budget"
    reused = {}

    e.select = stable_select

    def manifest(parent_lock):
        prior = old_manifest(parent_lock)
        value = {k: v for k, v in prior.items() if k not in {"manifest_hash", "recovery_from_receipts"}}
        value.update(revision="encoded-budget-v1", revision_lock=lock,
                     parent_revision_lock=prior["revision_lock"], parent_manifest_hash=prior["manifest_hash"],
                     context_budget_measure="exact JSON string literal embedded in answer message",
                     reused_parent_run="run-v2-output-cap")
        return {**value, "manifest_hash": r.tr.digest(value)}

    class BudgetClient(ParentClient):
        def call(self, rid, body):
            verify_revision()
            reuse = rid == "probe" or rid.startswith("extract-")
            if rid in parent_plan and parent_plan[rid]["payload"] == body:
                reuse = True
            if reuse:
                cached = ParentClient(parent_run, parent_manifest, self.client, "offline", self.campaign_dir)
                response = cached.call(rid, body)
                origin = "run-v1" if rid == "probe" else "run-v2-output-cap"
                receipt = e.read(self.campaign_dir / origin / "calls" / (r.tr.digest(rid) + ".result.json"))
                reused[rid] = {"run": origin, "receipt_hash": receipt["receipt_hash"],
                               "payload_hash": response["payload_hash"]}
                return response
            if not rid.startswith("answer-"):
                raise ValueError("Budget correction forbids new non-answer calls")
            return super().call(rid, body)

    r.tr.ExperimentClient = BudgetClient
    r.manifest = manifest
    return r, reused


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "replay"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--tokenizer", type=Path, default=e.ROOT / ".pytest-tmp/v3-assets/tokenizer.json")
    args = parser.parse_args()
    if args.command == "freeze":
        e.preserve(HERE / "revision-lock.json", make_lock())
        print("Encoded-context budget correction frozen; no API call.")
        return
    if args.command == "run" and not args.execute:
        parser.error("Paid execution requires --execute")
    r, reused = configure()
    result = r.run(e.Counter(args.tokenizer), offline=args.command == "replay")
    e.preserve(r.RUN / "reused-calls.json", reused)
    e.preserve(r.RUN / "revision-summary.json", {
        "revision_lock_hash": verify_revision()["revision_lock_hash"],
        "parent_attempts": 96, "parent_known_tokens": 206310,
        "reused_response_count": len(reused),
        "revision_requests": result["campaign_usage"]["actual_requests"] - 96,
        "revision_known_tokens": result["campaign_usage"]["total_tokens"] - 206310,
        "campaign_usage": result["campaign_usage"]})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "stopped", "error_type": type(exc).__name__,
                          "action": "Inspect preserved evidence; no further paid correction this stage."}))
        raise SystemExit(2) from None
