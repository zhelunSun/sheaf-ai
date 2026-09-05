"""Offline admission and evidence tests; synthetic replies are not model evidence."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import threading

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "method_selection_v3_transport_test", ROOT / "evals/method-selection-v3/transport.py")
transport = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transport)
SECRET = "fake-test-secret-transport-v3"


def manifest(**changes):
    value = {"model": "test-model", "endpoint": transport.ENDPOINT,
             "max_requests": 170, "max_tokens": 600000, "revision": "r1", **changes}
    return {**value, "manifest_hash": transport.digest(value)}


def payload(**changes):
    return transport.make_payload(**{"model": "test-model", "system": "System",
                                    "prompt": "Prompt", "max_output_tokens": 32, **changes})


def body(**changes):
    return {"model": "test-model", "choices": [{"message": {"content": "answer"},
             "finish_reason": "stop"}], "usage": {"prompt_tokens": 10,
             "completion_tokens": 5, "total_tokens": 15}, **changes}


def reply(request):
    return httpx.Response(200, json=body())


def client(campaign, handler=reply, revision="r1", cfg=None, key=SECRET):
    raw = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    return transport.ExperimentClient(campaign / revision, cfg or manifest(revision=revision),
                                      raw, key, campaign)


def forbidden(request):
    pytest.fail("No network dispatch permitted")


def only_result(campaign):
    return json.loads(next(campaign.rglob("*.result.json")).read_text(encoding="utf-8"))


def test_full_actual_payload_is_frozen_before_send_and_cache_needs_no_key(tmp_path):
    sent = []

    def respond(request):
        sent.append(request)
        frozen = json.loads(next(tmp_path.rglob("*.intent.json")).read_text(encoding="utf-8"))
        assert frozen["payload"] == json.loads(request.content) == payload()
        assert frozen["payload_hash"] == hashlib.sha256(request.content).hexdigest()
        assert frozen["manifest_hash"] == manifest()["manifest_hash"]
        assert request.headers["authorization"] == "Bearer " + SECRET
        assert frozen["payload"]["reasoning_effort"] == "none"
        return httpx.Response(200, json=body())

    first = client(tmp_path, respond).call("q1", payload())
    cached = client(tmp_path, forbidden, key="offline").call("q1", payload())
    assert first == cached and len(sent) == 1
    assert first == {"request_id": "q1", "payload_hash": transport.digest(payload()),
                     "model": "test-model", "text": "answer", "finish_reason": "stop",
                     "usage": {"input_tokens": 10, "output_tokens": 5},
                     "latency_ms": first["latency_ms"]}
    result = only_result(tmp_path)
    assert result["provider_model"] == "test-model"
    assert result["provider_usage"]["total_tokens"] == 15
    assert json.loads(result["raw_body"]) == body()
    assert result["receipt_hash"] == transport.digest({k: v for k, v in result.items()
                                                       if k != "receipt_hash"})
    artifacts = "\n".join(p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.json"))
    assert SECRET not in artifacts and "Authorization" not in artifacts
    assert transport.report_usage(tmp_path)["total_tokens"] == 15


def test_request_id_and_manifest_are_frozen_within_run(tmp_path):
    client(tmp_path).call("same-id", payload())
    with pytest.raises(transport.RunStopped, match="different payload"):
        client(tmp_path, forbidden, key="offline").call("same-id", payload(prompt="changed"))
    with pytest.raises(transport.RunStopped, match="manifest"):
        client(tmp_path, forbidden, cfg=manifest(revision="changed"), key="offline").call("same-id", payload())


@pytest.mark.parametrize("limit", ["max_requests", "max_tokens"])
def test_revisions_share_spending_and_cannot_reset_budget(tmp_path, limit):
    cfg = manifest(**{limit: 1 if limit == "max_requests" else transport.reservation(payload())})
    client(tmp_path, cfg=cfg).call("same-id", payload())
    cfg2 = manifest(revision="r2", **{limit: cfg[limit]})
    with pytest.raises(transport.RunStopped, match="budget exhausted"):
        client(tmp_path, forbidden, "r2", cfg2).call("same-id", payload())
    report = transport.report_usage(tmp_path)
    assert report["actual_requests"] == 1 and report["total_tokens"] == 15


def test_cross_revision_same_id_has_independent_cache_but_shared_usage(tmp_path):
    client(tmp_path).call("q", payload())
    client(tmp_path, revision="r2").call("q", payload(prompt="different revision"))
    assert transport.report_usage(tmp_path)["actual_requests"] == 2
    assert transport.report_usage(tmp_path)["total_tokens"] == 30


@pytest.mark.parametrize("change", [{"max_requests": 171}, {"max_tokens": 600001},
                                    {"max_requests": True}, {"endpoint": "https://other.invalid"}])
def test_manifest_cannot_raise_hard_campaign_ceiling_or_change_destination(tmp_path, change):
    with pytest.raises(transport.RunStopped):
        client(tmp_path, forbidden, cfg=manifest(**change))
    assert not list(tmp_path.rglob("*.intent.json"))


def test_manifest_checksum_is_checked_and_input_is_defensively_copied(tmp_path):
    cfg = manifest()
    cfg["max_requests"] = 2
    with pytest.raises(transport.RunStopped, match="checksum"):
        client(tmp_path, forbidden, cfg=cfg)
    cfg = manifest()
    executor = client(tmp_path, cfg=cfg)
    cfg["max_requests"] = 171
    assert executor.manifest["max_requests"] == 170
    executor.manifest["max_requests"] = 171
    with pytest.raises(transport.RunStopped, match="checksum"):
        executor.call("q", payload())


@pytest.mark.parametrize("change", [{"max_tokens": 6001}, {"max_tokens": True},
                                    {"stream": True}, {"reasoning_effort": "high"},
                                    {"extra": "credential"}, {"temperature": float("nan")}])
def test_invalid_payload_is_stopped_before_any_artifact(tmp_path, change):
    request = {**payload(), **change}
    with pytest.raises(transport.RunStopped):
        client(tmp_path, forbidden).call("q", request)
    assert not list(tmp_path.rglob("*.intent.json"))


def test_utf8_reservation_and_insufficient_remaining_budget(tmp_path):
    request = payload(system="系统", prompt="输入")
    assert transport.reservation(request) == len("系统输入".encode("utf-8")) + 512 + 32
    cfg = manifest(max_tokens=transport.reservation(request) - 1)
    with pytest.raises(transport.RunStopped, match="budget"):
        client(tmp_path, forbidden, cfg=cfg).call("q", request)
    assert transport.report_usage(tmp_path)["actual_requests"] == 0


@pytest.mark.parametrize("failure", ["http", "timeout", "model", "usage", "negative", "bool",
                                     "inconsistent", "input_overspend", "output_overspend", "json"])
def test_failed_provider_evidence_is_preserved_and_stops_new_revisions(tmp_path, failure):
    def respond(request):
        result = body()
        if failure == "timeout":
            raise httpx.ReadTimeout("Never persist exception text: " + SECRET)
        if failure == "model":
            result["model"] = "wrong-model"
        elif failure == "usage":
            result.pop("usage")
        elif failure == "negative":
            result["usage"]["prompt_tokens"] = -1
        elif failure == "bool":
            result["usage"]["completion_tokens"] = True
        elif failure == "inconsistent":
            result["usage"]["total_tokens"] = 100
        elif failure == "input_overspend":
            result["usage"] = {"prompt_tokens": 550, "completion_tokens": 0, "total_tokens": 550}
        elif failure == "output_overspend":
            result["usage"] = {"prompt_tokens": 10, "completion_tokens": 33, "total_tokens": 43}
        if failure == "json":
            return httpx.Response(200, content="not JSON")
        return httpx.Response(500 if failure == "http" else 200, json=result)

    with pytest.raises(transport.RunStopped, match="persisted"):
        client(tmp_path, respond).call("q", payload())
    result = only_result(tmp_path)
    assert result["issues"]
    assert SECRET not in json.dumps(result)
    with pytest.raises(transport.RunStopped):
        client(tmp_path, forbidden, revision="r2").call("other", payload())
    report = transport.report_usage(tmp_path)
    assert report["actual_requests"] == 1
    assert report["issues"]
    if failure in {"timeout", "usage", "negative", "bool", "inconsistent", "json"}:
        assert report["uncertain"]


@pytest.mark.parametrize("escaped", [False, True])
def test_credential_reflection_is_redacted_in_all_evidence_and_stops(tmp_path, escaped):
    def respond(request):
        result = body(echo=SECRET)
        raw = json.dumps(result)
        if escaped:
            raw = raw.replace(SECRET, "".join("\\u%04x" % ord(c) for c in SECRET))
        return httpx.Response(200, content=raw)

    with pytest.raises(transport.RunStopped, match="persisted"):
        client(tmp_path, respond).call("q", payload())
    result = only_result(tmp_path)
    assert result["raw_body_credential_redacted"]
    assert "credential_reflected_and_redacted" in result["issues"]
    assert "[REDACTED_CREDENTIAL]" in result["raw_body"]
    for path in tmp_path.rglob("*.json"):
        assert SECRET not in path.read_text(encoding="utf-8")
    with pytest.raises(transport.RunStopped):
        client(tmp_path, forbidden).call("next", payload())


def test_secret_in_payload_is_rejected_before_intent(tmp_path):
    with pytest.raises(transport.RunStopped, match="Credential detected"):
        client(tmp_path, forbidden).call("q", payload(prompt=SECRET))
    assert not list(tmp_path.rglob("*.json"))


def test_pending_intent_after_interrupt_blocks_every_revision_without_resend(tmp_path):
    def interrupt(request):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        client(tmp_path, interrupt).call("q", payload())
    assert len(list(tmp_path.rglob("*.intent.json"))) == 1
    assert not list(tmp_path.rglob("*.result.json"))
    for revision in ("r1", "r2"):
        with pytest.raises(transport.RunStopped, match="uncertain"):
            client(tmp_path, forbidden, revision=revision).call("q", payload())
    usage = transport.report_usage(tmp_path)
    assert usage["actual_requests"] == 1 and usage["uncertain_requests"] == 1
    assert usage["total_tokens"] == 0 and usage["uncertain"]


@pytest.mark.parametrize("mode", ["empty", "length", "mixed"])
def test_two_consecutive_content_failures_stop_only_before_next_new_call(tmp_path, mode):
    index = 0

    def respond(request):
        nonlocal index
        index += 1
        empty = mode == "empty" or (mode == "mixed" and index == 1)
        return httpx.Response(200, json=body(choices=[{"message": {"content": " " if empty else "partial"},
                                                       "finish_reason": "stop" if empty else "length"}]))

    first = client(tmp_path, respond).call("q1", payload())
    second = client(tmp_path, respond, revision="r2").call("q2", payload())
    assert first["text"] and second["text"]
    with pytest.raises(transport.RunStopped, match="Two consecutive"):
        client(tmp_path, forbidden, revision="r3").call("q3", payload())
    assert client(tmp_path, forbidden, revision="r2", key="offline").call("q2", payload()) == second
    assert transport.report_usage(tmp_path)["actual_requests"] == 2


def test_success_resets_consecutive_content_failure_streak(tmp_path):
    index = 0

    def respond(request):
        nonlocal index
        index += 1
        content = "answer" if index == 2 else ""
        return httpx.Response(200, json=body(choices=[{"message": {"content": content}, "finish_reason": "stop"}]))

    executor = client(tmp_path, respond)
    for i in range(4):
        executor.call(str(i), payload())
    assert transport.report_usage(tmp_path)["actual_requests"] == 4


def test_receipt_tamper_or_raw_evidence_disagreement_stops_cache_and_dispatch(tmp_path):
    client(tmp_path).call("q", payload())
    result_path = next(tmp_path.rglob("*.result.json"))
    result = only_result(tmp_path)
    result["response"]["usage"]["input_tokens"] = 0
    # Even a recomputed receipt checksum must not disguise a raw/parsed disagreement.
    result = transport._signed({k: v for k, v in result.items() if k != "receipt_hash"})
    result_path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(transport.RunStopped):
        client(tmp_path, forbidden, key="offline").call("q", payload())
    assert transport.report_usage(tmp_path)["uncertain"]


def test_missing_registered_run_cannot_erase_consumption(tmp_path):
    client(tmp_path).call("q", payload())
    # Simulate moved/lost run evidence without deleting any user data.
    (tmp_path / "r1").rename(tmp_path.parent / (tmp_path.name + "-lost-run"))
    with pytest.raises(transport.RunStopped, match="uncertain"):
        client(tmp_path, forbidden, revision="r2").call("q", payload())
    assert "missing_registered_run" in transport.report_usage(tmp_path)["issues"]
    assert transport.report_usage(tmp_path)["actual_requests"] == 1


def test_lost_terminal_calls_cannot_reset_budget_while_manifest_remains(tmp_path):
    client(tmp_path).call("q", payload())
    (tmp_path / "r1" / "calls").rename(tmp_path.parent / (tmp_path.name + "-lost-calls"))
    with pytest.raises(transport.RunStopped, match="uncertain"):
        client(tmp_path, forbidden, revision="r2").call("q", payload())
    usage = transport.report_usage(tmp_path)
    assert usage["actual_requests"] == 1
    assert usage["uncertain"] and "campaign_admission_mismatch" in usage["issues"]


def test_redirect_is_never_followed_even_if_supplied_client_enables_it(tmp_path):
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(307, headers={"Location": "https://other.invalid/secret"}, json=body())

    raw = httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=True)
    executor = transport.ExperimentClient(tmp_path / "r1", manifest(), raw, SECRET, tmp_path)
    with pytest.raises(transport.RunStopped):
        executor.call("q", payload())
    assert calls == [transport.ENDPOINT]


def test_lock_serializes_budget_admission_across_threads_and_revisions(tmp_path):
    entered, release = threading.Event(), threading.Event()
    requests = []

    def respond(request):
        requests.append(request)
        entered.set()
        assert release.wait(3)
        return httpx.Response(200, json=body())

    first = client(tmp_path, respond, cfg=manifest(max_requests=1))
    second = client(tmp_path, forbidden, revision="r2", cfg=manifest(revision="r2", max_requests=1))
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(first.call, "q", payload())
        assert entered.wait(3)
        other = pool.submit(second.call, "q", payload())
        release.set()
        pending.result(timeout=3)
        with pytest.raises(transport.RunStopped, match="budget"):
            other.result(timeout=3)
    assert len(requests) == 1


def test_run_must_remain_inside_fixed_campaign(tmp_path):
    with pytest.raises(transport.RunStopped, match="inside"):
        transport.ExperimentClient(tmp_path.parent, manifest(), None, "offline", tmp_path)
    client(tmp_path).call("q", payload())
    alternate = tmp_path / "r1" / "new-campaign"
    with pytest.raises(transport.RunStopped, match="inside"):
        transport.ExperimentClient(tmp_path / "r1", manifest(), None, "offline", alternate)


def test_caller_payload_is_not_mutated(tmp_path):
    request = payload()
    before = deepcopy(request)
    client(tmp_path).call("q", request)
    assert request == before


@pytest.mark.parametrize("explicit_identity", [False, True])
def test_relocated_campaign_replays_offline_with_unchanged_identity_and_budget(tmp_path, explicit_identity):
    original = tmp_path / "original" / "campaign"
    relocated = tmp_path / "new-location" / "renamed-campaign"
    identity = {"campaign_id": "frozen-campaign-identity"} if explicit_identity else {}
    cfg1 = manifest(**identity)
    cfg2 = manifest(revision="r2", **identity)
    expected1 = client(original, cfg=cfg1).call("q", payload())
    expected2 = client(original, revision="r2", cfg=cfg2).call("q", payload(prompt="revision 2"))
    usage = transport.report_usage(original)
    original_files = {p.relative_to(original): p.read_bytes() for p in original.rglob("*.json")}
    shutil.copytree(original, relocated)
    assert client(relocated, forbidden, cfg=cfg1, key="offline").call("q", payload()) == expected1
    assert client(relocated, forbidden, revision="r2", cfg=cfg2, key="offline").call(
        "q", payload(prompt="revision 2")) == expected2
    assert transport.report_usage(relocated) == usage
    assert not usage["uncertain"] and usage["actual_requests"] == 2
    assert {p.relative_to(relocated): p.read_bytes() for p in relocated.rglob("*.json")} == original_files
    for content in original_files.values():
        assert str(original).encode("utf-8") not in content
    # A new revision is admitted against the relocated historical usage.
    cfg3 = manifest(revision="r3", max_requests=2, **identity)
    with pytest.raises(transport.RunStopped, match="budget exhausted"):
        client(relocated, forbidden, revision="r3", cfg=cfg3).call("q", payload())


def test_explicit_campaign_identity_cannot_change_between_revisions(tmp_path):
    client(tmp_path, cfg=manifest(campaign_id="campaign-one")).call("q", payload())
    cfg = manifest(revision="r2", campaign_id="different-campaign")
    with pytest.raises(transport.RunStopped, match="campaign identity"):
        client(tmp_path, forbidden, revision="r2", cfg=cfg).call("q", payload())
    assert transport.report_usage(tmp_path)["actual_requests"] == 1


@pytest.mark.parametrize("missing", ["campaign", "registration", "binding"])
def test_relocated_campaign_missing_identity_evidence_fails_closed(tmp_path, missing):
    original, relocated = tmp_path / "original", tmp_path / "relocated"
    client(original).call("q", payload())
    shutil.copytree(original, relocated)
    targets = {"campaign": relocated / "campaign.json",
               "registration": next((relocated / "registrations").glob("*.json")),
               "binding": relocated / "r1" / "transport-binding.json"}
    targets[missing].rename(tmp_path / (missing + "-lost.json"))
    with pytest.raises(transport.RunStopped, match="uncertain"):
        client(relocated, forbidden, key="offline").call("q", payload())
    with pytest.raises(transport.RunStopped, match="uncertain"):
        client(relocated, forbidden, revision="r2").call("next", payload())
    report = transport.report_usage(relocated)
    assert report["uncertain"] and report["actual_requests"] == 1
