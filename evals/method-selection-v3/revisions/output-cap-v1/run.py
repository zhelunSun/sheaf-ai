"""Source-frozen output-envelope amendment; never overwrite the parent experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
sys.path.insert(0, str(BASE))
import experiment as e  # noqa: E402

RECOVERY = ["38615da68c349bf4889b9be33b006b8465781437bc3b61345e86d305accf5d5d",
            "6e3bef74178524a7de74a27fc42ad81be401b9f425a0d9653440b6c9eb2529f3"]
PROBE_RECEIPT = "770b7066b8229621519b452f36b415f6a7275ac9b971599a51335108b1aca0cb"


def make_lock():
    parent = e.read(BASE / "lock.json")
    e.verify_lock(parent)
    value = {"parent_lock_hash": parent["lock_hash"], "revision": "output-cap-v1",
             "code": {name: e.code_hash(HERE / name) for name in ("run.py", "transport.py", "protocol.md")}}
    return {**value, "revision_lock_hash": e.digest(value)}


def verify_revision():
    saved = e.read(HERE / "revision-lock.json")
    if saved != make_lock():
        raise ValueError("Output-cap revision source identity changed")
    return saved


def configured_runner():
    lock = verify_revision()
    r = e.load_module("v3_parent_runner", BASE / "run.py")
    tr = e.load_module("v3_output_transport", HERE / "transport.py")
    base_manifest = r.manifest
    parent_run = r.RUN
    parent_manifest = e.read(parent_run / "manifest.json")
    if parent_manifest != base_manifest(e.read(BASE / "lock.json")):
        raise ValueError("Parent manifest differs from original frozen execution")
    r.RUN = r.CAMPAIGN / "run-v2-output-cap"
    r.tr = tr

    def revised_manifest(parent_lock):
        old = base_manifest(parent_lock)
        value = {k: v for k, v in old.items() if k != "manifest_hash"}
        value.update(revision="output-cap-v1", revision_lock=lock,
                     extraction_output_cap=12000, recovery_from_receipts=RECOVERY,
                     parent_manifest_hash=parent_manifest["manifest_hash"],
                     reused_probe={"run": "run-v1", "request_id": "probe", "receipt_hash": PROBE_RECEIPT})
        return {**value, "manifest_hash": tr.digest(value)}

    OriginalClient = tr.ExperimentClient

    class GuardedClient(OriginalClient):
        def call(self, rid, body):
            verify_revision()
            if rid == "probe":
                receipt = e.read(parent_run / "calls" / (tr.digest("probe") + ".result.json"))
                if receipt["receipt_hash"] != PROBE_RECEIPT:
                    raise ValueError("Reused probe receipt changed")
                cached = OriginalClient(parent_run, parent_manifest, self.client, "offline", self.campaign_dir)
                return cached.call(rid, body)
            return super().call(rid, body)

    tr.ExperimentClient = GuardedClient
    r.manifest = revised_manifest

    def extraction_payload(bundle):
        return r.payload(e.EXTRACT + json.dumps({k: bundle[k] for k in ("method_ids", "sources")},
                                                ensure_ascii=False), 12000)

    r.extraction_payload = extraction_payload
    return r


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "replay"))
    parser.add_argument("--tokenizer", type=Path, default=e.ROOT / ".pytest-tmp/v3-assets/tokenizer.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze":
        e.preserve(HERE / "revision-lock.json", make_lock())
        print("Output-cap amendment frozen; no API call.")
        return
    if args.command == "run" and not args.execute:
        parser.error("Paid execution requires --execute")
    r = configured_runner()
    result = r.run(e.Counter(args.tokenizer), offline=args.command == "replay")
    e.preserve(r.RUN / "revision-summary.json", {
        "revision_lock_hash": verify_revision()["revision_lock_hash"],
        "parent_attempts": 4, "parent_known_tokens": 22045,
        "probe_reused_not_billed_twice": True,
        "revision_requests": result["campaign_usage"]["actual_requests"] - 4,
        "revision_known_tokens": result["campaign_usage"]["total_tokens"] - 22045,
        "campaign_usage": result["campaign_usage"]})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "stopped", "error_type": type(exc).__name__,
                          "action": "Inspect saved evidence; no implicit retry or further cap repair."}))
        raise SystemExit(2) from None
