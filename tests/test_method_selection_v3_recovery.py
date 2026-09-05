"""Synthetic offline recovery tests; original freezes and paid evidence are untouched."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import httpx
import pytest

HERE = Path(__file__).resolve().parents[1] / "evals/method-selection-v3"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


old = module("v3_original_recovery_tests", HERE / "transport.py")
new = module("v3_output_cap_recovery_tests", HERE / "revisions/output-cap-v1/transport.py")
ORIGINAL_HASH = hashlib.sha256((HERE / "transport.py").read_bytes()).hexdigest()
FAKE_KEY = "synthetic-offline-recovery-secret"


def manifest(**changes):
    value = {"model": "test-model", "endpoint": old.ENDPOINT, "max_requests": 170,
             "max_tokens": 600000, "revision": "original", **changes}
    return {**value, "manifest_hash": new.digest(value)}


def payload(cap=6000):
    return new.make_payload("test-model", "system", "prompt", cap)


def reply(finish="stop", content="answer", usage=None, model="test-model", status=200):
    return httpx.Response(status, json={"model": model, "choices": [{"message": {"content": content},
                          "finish_reason": finish}], "usage": usage or {
                              "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})


def executor(api, campaign, run="original", cfg=None, handler=None, key=FAKE_KEY):
    raw = httpx.Client(transport=httpx.MockTransport(handler or (lambda _: reply())), trust_env=False)
    return api.ExperimentClient(campaign / run, cfg or manifest(), raw, key, campaign)


def forbidden(request):
    pytest.fail("No dispatch permitted")


def records(campaign):
    rows = []
    for path in campaign.rglob("*.intent.json"):
        intent = json.loads(path.read_text(encoding="utf-8"))
        result = json.loads(path.with_name(path.name.replace(".intent.json", ".result.json")).read_text(encoding="utf-8"))
        rows.append((intent, result))
    return sorted(rows, key=lambda row: row[0]["sequence"])


def blocked_original(campaign, second=None):
    original = executor(old, campaign, handler=lambda _: reply("length", "partial"))
    original.call("extract-x02", payload())
    if second:
        original = executor(old, campaign, handler=second)
    original.call("extract-x03", payload())
    with pytest.raises(old.RunStopped, match="Two consecutive"):
        executor(old, campaign, handler=forbidden).call("extract-x04", payload())
    return [row[1]["receipt_hash"] for row in records(campaign)[-2:]]


def recovery(hashes, **changes):
    return manifest(revision="output-cap-v1", extraction_output_cap=12000,
                    recovery_from_receipts=hashes, **changes)


def test_original_receipts_scan_and_offline_cache_without_any_modification(tmp_path):
    blocked_original(tmp_path)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert new.report_usage(tmp_path) == old.report_usage(tmp_path)
    cached = executor(new, tmp_path, handler=forbidden, key="offline").call("extract-x02", payload())
    assert cached["finish_reason"] == "length"
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*.json")} == before


def test_exact_tail_pair_allows_first_new_extraction_and_persists_consumption(tmp_path):
    hashes = blocked_original(tmp_path)
    cfg = recovery(hashes)
    seen = []

    def respond(request):
        seen.append(request)
        pending = next((tmp_path / "repair/calls").glob("*.intent.json"))
        intent = json.loads(pending.read_text(encoding="utf-8"))
        assert intent["recovery_consumed"] == hashes
        assert intent["manifest_hash"] == cfg["manifest_hash"]
        assert hashlib.sha256(request.content).hexdigest() == intent["payload_hash"]
        assert json.loads(request.content)["max_tokens"] == 12000
        return reply()

    first = executor(new, tmp_path, "repair", cfg, respond).call("extract-x01", payload(12000))
    assert first["finish_reason"] == "stop" and len(seen) == 1
    again = executor(new, tmp_path, "repair", cfg, forbidden, key="offline").call("extract-x01", payload(12000))
    assert first == again and len(seen) == 1
    executor(new, tmp_path, "repair", cfg).call("extract-x02", payload(12000))
    usage = new.report_usage(tmp_path)
    assert usage["actual_requests"] == 4 and usage["total_tokens"] == 60
    assert not usage["issues"] and not usage["uncertain"]
    rows = records(tmp_path)
    assert "recovery_consumed" not in rows[-1][0]


@pytest.mark.parametrize("change", ["missing", "reversed", "wrong", "duplicate", "short", "cap"])
def test_recovery_requires_a_well_formed_exact_ordered_receipt_pair(tmp_path, change):
    hashes = blocked_original(tmp_path)
    cfg = recovery(hashes)
    if change == "missing":
        cfg = manifest(revision="unapproved")
    elif change == "reversed":
        cfg = recovery(list(reversed(hashes)))
    elif change == "wrong":
        cfg = recovery(["a" * 64, "b" * 64])
    elif change == "duplicate":
        cfg = recovery([hashes[0], hashes[0]])
    elif change == "short":
        cfg = recovery([hashes[0]])
    else:
        value = {k: v for k, v in cfg.items() if k != "manifest_hash"}
        value["extraction_output_cap"] = 6000
        cfg = {**value, "manifest_hash": new.digest(value)}
    with pytest.raises(new.RunStopped):
        executor(new, tmp_path, "repair", cfg, forbidden).call("extract-x01", payload(12000))
    assert new.report_usage(tmp_path)["actual_requests"] == 2


@pytest.mark.parametrize("rid,cap", [("answer-q1", 12000), ("probe", 12000),
                                     ("answer-q1", 1200), ("extract-x01", 6000)])
def test_only_first_12000_cap_extraction_can_consume_recovery(tmp_path, rid, cap):
    cfg = recovery(blocked_original(tmp_path))
    with pytest.raises(new.RunStopped):
        executor(new, tmp_path, "repair", cfg, forbidden).call(rid, payload(cap))
    assert new.report_usage(tmp_path)["actual_requests"] == 2


def test_12000_cap_never_allowed_for_answer_even_after_recovery(tmp_path):
    cfg = recovery(blocked_original(tmp_path))
    executor(new, tmp_path, "repair", cfg).call("extract-x01", payload(12000))
    with pytest.raises(new.RunStopped, match="extraction request"):
        executor(new, tmp_path, "repair", cfg, forbidden).call("answer-q1", payload(12000))
    executor(new, tmp_path, "repair", cfg).call("answer-q1", payload(1200))
    assert new.report_usage(tmp_path)["actual_requests"] == 4


def test_two_new_lengths_stop_and_old_permission_cannot_be_reused_in_any_run(tmp_path):
    cfg = recovery(blocked_original(tmp_path))
    partial = executor(new, tmp_path, "repair", cfg, lambda _: reply("length", "partial"))
    partial.call("extract-x01", payload(12000))
    partial.call("extract-x02", payload(12000))
    for run in ("repair", "another-repair"):
        with pytest.raises(new.RunStopped):
            executor(new, tmp_path, run, cfg, forbidden).call("extract-x03", payload(12000))
    fresh = recovery(cfg["recovery_from_receipts"], note="new manifest with stale permission")
    with pytest.raises(new.RunStopped):
        executor(new, tmp_path, "third-repair", fresh, forbidden).call("extract-x03", payload(12000))
    assert new.report_usage(tmp_path)["actual_requests"] == 4
    assert not new.report_usage(tmp_path)["issues"]


def test_no_recovery_for_empty_stop_responses(tmp_path):
    original = executor(old, tmp_path, handler=lambda _: reply("stop", ""))
    original.call("extract-x02", payload())
    original.call("extract-x03", payload())
    hashes = [row[1]["receipt_hash"] for row in records(tmp_path)]
    with pytest.raises(new.RunStopped, match="actual trailing length"):
        executor(new, tmp_path, "repair", recovery(hashes), forbidden).call("extract-x01", payload(12000))


@pytest.mark.parametrize("limit", ["requests", "tokens"])
def test_recovery_does_not_reset_campaign_budget(tmp_path, limit):
    hashes = blocked_original(tmp_path)
    changes = {"max_requests": 2} if limit == "requests" else {"max_tokens": 30 + new.reservation(payload(12000)) - 1}
    with pytest.raises(new.RunStopped, match="budget exhausted"):
        executor(new, tmp_path, "repair", recovery(hashes, **changes), forbidden).call("extract-x01", payload(12000))
    assert new.report_usage(tmp_path)["actual_requests"] == 2


@pytest.mark.parametrize("failure", ["model", "usage", "http", "pending", "missing_result", "missing_admission"])
def test_recovery_cannot_clear_provider_or_evidence_failures(tmp_path, failure):
    hashes = blocked_original(tmp_path)
    if failure in {"model", "usage", "http"}:
        # Append an independently recorded failure to a clean prefix using the old
        # client before its two-content-failure stop, then approve those actual tails.
        campaign = tmp_path / "failure-campaign"
        first = executor(old, campaign, handler=lambda _: reply("length", "partial"))
        first.call("extract-x02", payload())
        handler = (lambda _: reply("length", model="wrong")) if failure == "model" else (
            (lambda _: reply("length", usage={"prompt_tokens": 10})) if failure == "usage"
            else (lambda _: reply("length", status=500)))
        with pytest.raises(old.RunStopped):
            executor(old, campaign, handler=handler).call("extract-x03", payload())
        hashes = [row[1]["receipt_hash"] for row in records(campaign)]
    else:
        campaign = tmp_path
        if failure == "pending" or failure == "missing_result":
            target = next((campaign / "original/calls").glob("*.result.json"))
        else:
            target = next((campaign / "admissions").glob("*.json"))
        target.rename(tmp_path.parent / (tmp_path.name + "-missing.json"))
    with pytest.raises(new.RunStopped):
        executor(new, campaign, "repair", recovery(hashes), forbidden).call("extract-x01", payload(12000))


def test_unconsumed_recovery_with_offline_key_writes_no_new_intent(tmp_path):
    cfg = recovery(blocked_original(tmp_path))
    with pytest.raises(new.RunStopped, match="credential"):
        executor(new, tmp_path, "repair", cfg, forbidden, key="offline").call("extract-x01", payload(12000))
    assert not (tmp_path / "repair").exists()


def test_relocated_recovery_remains_offline_replayable(tmp_path):
    campaign = tmp_path / "original-location"
    cfg = recovery(blocked_original(campaign))
    expected = executor(new, campaign, "repair", cfg).call("extract-x01", payload(12000))
    relocated = tmp_path / "relocated"
    shutil.copytree(campaign, relocated)
    assert executor(new, relocated, "repair", cfg, forbidden, key="offline").call("extract-x01", payload(12000)) == expected
    assert new.report_usage(relocated) == new.report_usage(campaign)


def test_original_transport_source_is_unchanged():
    assert hashlib.sha256((HERE / "transport.py").read_bytes()).hexdigest() == ORIGINAL_HASH
