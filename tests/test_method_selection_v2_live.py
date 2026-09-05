"""Full offline transport smoke for v2. Responses are not quality evidence."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("method_v2_live", ROOT / "evals/method-selection-v2/run_live.py")
live = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(live)

CONTROL_SPEC = importlib.util.spec_from_file_location(
    "method_v2_no_reasoning", ROOT / "evals/method-selection-v2/run_live_no_reasoning.py")
control = importlib.util.module_from_spec(CONTROL_SPEC)
CONTROL_SPEC.loader.exec_module(control)


def test_full_live_path_uses_43_calls_then_replays_without_network(tmp_path, monkeypatch):
    bundles = live.experiment.load_inputs()
    call_count = 0

    def response(request):
        nonlocal call_count
        call_count += 1
        payload = json.loads(request.content)
        if call_count == 1:
            content = '```json\n{"ok":true}\n```'
        elif call_count <= 7:
            bundle = bundles[call_count - 2]
            source = bundle["sources"][0]
            facts = [{"method_id": method_id, "fact_type": "capability", "statement": source["text"],
                      "applicability_conditions": [], "measurement_scope": [], "not_evaluated_scope": [],
                      "citations": [{"source_id": source["source_id"], "quote": source["text"]}]}
                     for method_id in bundle["method_ids"]]
            content = json.dumps(facts)
        else:
            content = json.dumps({"decision": "choose", "method_id": "C", "evidence_state": "supported",
                                  "citations": [{"source_id": "p01s1", "quote": "invalid for most; unit test"}],
                                  "reason": "unit test only"})
        body = {"model": payload["model"], "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        return httpx.Response(200, json=body)

    cfg = live.make_manifest("unit-test-model")
    real_gold = live.experiment.load_gold

    def guarded_gold(*args, **kwargs):
        assert call_count == 43
        return real_gold(*args, **kwargs)

    monkeypatch.setattr(live.experiment, "load_gold", guarded_gold)
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = live.run(cfg, tmp_path, client, "test-key")
    assert call_count == result["usage"]["actual_requests"] == 43
    assert result["usage"]["total_tokens"] == 645
    assert set(result["summary"]) == set(live.experiment.ARMS)
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Replay must not call network"))) as client:
        replay = live.run(cfg, tmp_path, client, "test-key")
    assert replay == result
    assert call_count == 43


def test_reasoning_control_is_manifest_bound_and_injected(tmp_path):
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"model": body["model"], "choices": [
            {"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    cfg = control.make_manifest("unit-test-model")
    request = live.experiment.shared.request("probe-only", cfg["model"], "probe", 32)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response, sent = live.transport.execute_request(
            request, cfg, tmp_path, control.BoundClient(client, cfg), "test-key")
    assert sent and response["finish_reason"] == "stop"
    assert seen[0]["reasoning_effort"] == "none"
    assert cfg["request_options"] == {"reasoning_effort": "none"}
    changed = dict(cfg)
    changed["request_options"] = {"reasoning_effort": "low"}
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("must fail before network"))) as client:
        with pytest.raises(control.transport.RunStopped, match="Unexpected request options"):
            control.BoundClient(client, changed).post("https://example.invalid", headers={}, json={})
