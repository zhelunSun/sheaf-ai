"""Offline transport/accounting tests. Synthetic replies are not quality evidence."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("live_method", ROOT / "evals/method-selection/run_live.py")
live = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(live)


def manifest():
    return live.make_manifest("unit-test-not-a-model")


def req():
    return live.experiment.request("test", "unit-test-not-a-model", "test input", 32)


def provider_body(payload, content='{"ok": true}', **changes):
    return {"model": payload["model"], "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, **changes}


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_credential_reads_exact_profile_and_never_falls_back_to_anthropic(tmp_path, monkeypatch):
    path = tmp_path / "models.json"
    live.save(path, [{"id": "selected", "url": live.ENDPOINT, "apiKey": "fake-test-secret"},
                     {"id": "selected", "url": "https://other.invalid/v1/chat/completions", "apiKey": "other"}])
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "do-not-use")
    monkeypatch.delenv("PARATERA_API_KEY", raising=False)
    assert live.load_key(path, "selected") == "fake-test-secret"
    with pytest.raises(ValueError):
        live.load_key(path, "missing")
    with pytest.raises(ValueError):
        live.load_key(path, "selected", "ANTHROPIC_AUTH_TOKEN")
    with pytest.raises(ValueError):
        live.load_key(path, "selected", "PARATERA_API_KEY")


def test_success_reuses_saved_response_without_network_or_credential_leak(tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        body = json.loads(request.content)
        assert set(body) == {"model", "messages", "temperature", "max_tokens", "stream"}
        assert body["max_tokens"] == 32
        return httpx.Response(200, json=provider_body(body))

    with client(respond) as transport:
        first, sent = live.execute_request(req(), manifest(), tmp_path, transport, "fake-test-secret")
        second, resent = live.execute_request(req(), manifest(), tmp_path, transport, "fake-test-secret")
    assert first == second and sent and not resent and len(calls) == 1
    assert all("fake-test-secret" not in p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.json"))


@pytest.mark.parametrize("limit", ["requests", "tokens"])
def test_budget_stops_before_dispatch(tmp_path, limit):
    cfg = manifest()
    with client(lambda r: httpx.Response(200, json=provider_body(json.loads(r.content)))) as transport:
        live.execute_request(req(), cfg, tmp_path, transport, "test-key")
    cfg["max_" + limit] = 1
    with client(lambda _: pytest.fail("Budget must prevent network")) as transport:
        with pytest.raises(live.RunStopped, match="Budget exhausted"):
            live.execute_request(live.experiment.request("next", cfg["model"], "next", 32), cfg, tmp_path, transport, "test-key")


@pytest.mark.parametrize("failure", ["http", "timeout", "identity", "usage", "inconsistent", "overspend", "redaction"])
def test_provider_failures_persist_and_stop_retries(tmp_path, failure):
    secret = "fake-test-secret"

    def respond(request):
        body = provider_body(json.loads(request.content))
        if failure == "timeout":
            raise httpx.ReadTimeout("Do not log credentials: " + secret)
        if failure == "identity":
            body["model"] = "wrong-model"
        elif failure == "usage":
            body.pop("usage")
        elif failure == "inconsistent":
            body["usage"]["total_tokens"] = 999
        elif failure == "overspend":
            body["usage"] = {"prompt_tokens": 9999, "completion_tokens": 1, "total_tokens": 10000}
        elif failure == "redaction":
            body["echo"] = secret
        return httpx.Response(401 if failure == "http" else 200, json=body)

    with client(respond) as transport, pytest.raises(live.RunStopped):
        live.execute_request(req(), manifest(), tmp_path, transport, secret)
    results = list(tmp_path.rglob("*.result.json"))
    assert len(results) == 1
    value = live.experiment.read_json(results[0])
    assert value["issues"]
    assert secret not in results[0].read_text(encoding="utf-8")
    with client(lambda _: pytest.fail("No automatic retry")) as transport, pytest.raises(live.RunStopped):
        live.execute_request(req(), manifest(), tmp_path, transport, secret)


def test_uncertain_intent_never_resent(tmp_path):
    cfg, request = manifest(), req()
    intent = live.signed({"request": request, "manifest_hash": cfg["manifest_hash"],
                          "reserved_tokens_estimate": live.reservation(request), "started_at": live.now()})
    live.save(tmp_path / "calls" / (request["request_hash"] + ".intent.json"), intent)
    with client(lambda _: pytest.fail("Uncertain call must not be sent again")) as transport:
        with pytest.raises(live.RunStopped, match="Uncertain prior call"):
            live.execute_request(request, cfg, tmp_path, transport, "test-key")


def test_tampered_request_or_receipt_rejected(tmp_path):
    request = req()
    request["prompt"] += " changed"
    with pytest.raises(ValueError, match="hash"):
        live.validate_request(request, manifest())
    row = live.signed({"a": 1})
    row["a"] = 2
    with pytest.raises(live.RunStopped, match="checksum"):
        live.check_receipt(row)


def test_full_run_and_resume_keep_failures_and_all_denominators(tmp_path, monkeypatch):
    # Deliberately bad extraction: only raw gets answer calls. Still 12 tasks per arm.
    calls = []
    gold_reads = []
    original_gold = live.experiment.load_gold

    def counted_gold(*args, **kwargs):
        assert len(calls) == 19  # probe + 6 failed extractions + 12 raw answers
        gold_reads.append(True)
        return original_gold(*args, **kwargs)

    monkeypatch.setattr(live.experiment, "load_gold", counted_gold)

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        content = '{"ok": true}' if len(calls) == 1 else "not JSON; unit test only"
        return httpx.Response(200, json=provider_body(payload, content))

    cfg = manifest()
    with client(respond) as transport:
        result = live.run(cfg, tmp_path, transport, "test-key")
    assert result["usage"]["actual_requests"] == 19
    assert all(s["tasks"] == s["failed"] == 12 for s in result["summary"].values())
    assert result["usage"]["standalone_arm_total_tokens"] == {"raw": 180, "text_card": 90, "structured_card": 90}
    with client(lambda _: pytest.fail("Completed run must use saved responses")) as transport:
        resumed = live.run(cfg, tmp_path, transport, "test-key")
    assert resumed["new_requests"] == 0 and len(gold_reads) == 2


def test_manifest_change_refuses_existing_directory_before_network(tmp_path):
    cfg = manifest()
    live.save(tmp_path / "manifest.json", cfg)
    changed = deepcopy(cfg)
    changed["model"] = "another-model"
    with client(lambda _: pytest.fail("Changed manifest must not run")) as transport:
        with pytest.raises(live.RunStopped, match="artifact differs"):
            live.run(changed, tmp_path, transport, "test-key")
