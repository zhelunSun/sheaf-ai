"""Post-hoc adapter checks; no real model calls or quality claims."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("method_repair", ROOT / "evals/method-selection/run_live_repair.py")
repair = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repair)
live = repair.live


def reply(text):
    return {"request_id": "unit", "text": text, "finish_reason": "stop"}


@pytest.mark.parametrize("text,changed", [
    ('```json\n{"method_id":"Method A","quote":"unchanged"}\n```', True),
    ('```\n[1, 2]\n```', True), ('{"x": 1}', False),
    ('Explanation\n```json\n{"x": 1}\n```', False),
    ('```json\n{"x":\n```', False), ('```json\n{}\n```\n```json\n{}\n```', False),
])
def test_unwrap_only_single_complete_json_fence(text, changed):
    original = reply(text)
    parsed, audit = repair.unwrap(original)
    assert original["text"] == text
    assert (audit["transformation"] != "identity") is changed
    if changed:
        assert "```" not in parsed["text"]
        if "Method A" in text:
            assert json.loads(parsed["text"]) == {"method_id": "Method A", "quote": "unchanged"}


def test_repair_full_run_reuses_raw_and_inherits_budget(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    target = tmp_path / "repair"
    cfg = live.make_manifest("unit-test-not-a-model")
    parent_calls = []

    def response(payload, text):
        return httpx.Response(200, json={"model": payload["model"], "choices": [
            {"message": {"content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

    def failed_parent(request):
        payload = json.loads(request.content)
        parent_calls.append(payload)
        return response(payload, '{"ok": true}' if len(parent_calls) == 1 else "invalid; unit test only")

    with httpx.Client(transport=httpx.MockTransport(failed_parent)) as client:
        live.run(cfg, parent, client, "test-key")
    assert len(parent_calls) == 19
    state = repair.parent_state(parent)
    remaining = repair.repair_manifest(state)
    assert remaining["max_requests"] == 31 and remaining["max_tokens"] == 150000 - 285
    plan = repair.extraction_plan(remaining)
    assert all("Allowed method_id strings" in r["prompt"] for r in plan["requests"])
    new_calls = []
    inputs = live.experiment.load_inputs()

    def model(request):
        payload = json.loads(request.content)
        assert "-raw" not in payload["messages"][-1]["content"]  # IDs aren't injected into prompts.
        new_calls.append(payload)
        if len(new_calls) <= 6:
            bundle = inputs[len(new_calls) - 1]
            source = bundle["sources"][0]
            data = [{"method_id": "A", "claim": source["text"], "conditions": [], "exceptions": [],
                     "citations": [{"source_id": source["source_id"], "quote": source["text"]}]}]
            return response(payload, "```json\n" + json.dumps(data) + "\n```")
        return response(payload, "invalid answer; unit test only")

    original_gold = live.experiment.load_gold

    def gold_after_calls(*args, **kwargs):
        assert len(new_calls) == 30
        return original_gold(*args, **kwargs)

    monkeypatch.setattr(live.experiment, "load_gold", gold_after_calls)
    with httpx.Client(transport=httpx.MockTransport(model)) as client:
        result = repair.run(parent, target, client, "test-key")
    assert result["new_requests"] == 30
    assert result["usage"]["campaign_total_requests"] == 49
    assert result["usage"]["campaign_total_tokens"] == 49 * 15
    assert result["usage"]["standalone_arm_total_tokens"] == {"raw": 180, "text_card": 270, "structured_card": 270}
    report = live.experiment.read_json(target / "result.json")
    assert report["evidence_grade"] == "post_hoc_synthetic_development_only"
    assert report["construction"][0]["raw_provider_response"]["text"].startswith("```json")
    assert not report["construction"][0]["parsed_response"]["text"].startswith("```json")
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("No repeat API calls"))) as client:
        replay = repair.run(parent, target, client, "test-key")
    assert replay["new_requests"] == 0
    assert all(s["tasks"] == 12 for s in replay["summary"].values())
