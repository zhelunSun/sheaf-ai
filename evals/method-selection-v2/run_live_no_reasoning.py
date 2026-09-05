"""Live v2 revision that binds the observed Paratera no-reasoning control."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load("method_selection_v2_live_base", HERE / "run_live.py")
transport = base.transport


def extension_hashes():
    paths = [Path(__file__), HERE / "reasoning_control_protocol.md"]
    return {p.relative_to(ROOT).as_posix(): base.experiment.shared.file_hash(p) for p in paths}


def make_manifest(model, max_requests=50, max_tokens=150000, timeout=120):
    value = base.make_manifest(model, max_requests, max_tokens, timeout)
    value.pop("manifest_hash")
    value.update(version="method-selection-v2-live-no-reasoning-v1",
                 request_options={"reasoning_effort": "none"}, extension_code=extension_hashes())
    return {**value, "manifest_hash": base.experiment.shared.digest(value)}


class BoundClient:
    """Inject one manifest-bound request option without changing frozen logical prompts."""

    def __init__(self, client, manifest):
        self.client = client
        self.manifest = manifest

    def post(self, url, *, headers, json):
        if extension_hashes() != self.manifest["extension_code"]:
            raise transport.RunStopped("Reasoning-control extension changed during execution")
        if self.manifest.get("request_options") != {"reasoning_effort": "none"}:
            raise transport.RunStopped("Unexpected request options")
        payload = dict(json)
        if "reasoning_effort" in payload:
            raise transport.RunStopped("Duplicate reasoning control")
        payload["reasoning_effort"] = "none"
        return self.client.post(url, headers=headers, json=payload)


def run(manifest, run_dir, client, key):
    if extension_hashes() != manifest.get("extension_code"):
        raise transport.RunStopped("Reasoning-control extension does not match manifest")
    return base.run(manifest, run_dir, BoundClient(client, manifest), key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--credential-config", type=Path, default=Path.home() / ".workbuddy/models.json")
    parser.add_argument("--credential-profile", default="DeepSeek-V4-Pro")
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
