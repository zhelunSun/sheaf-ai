"""Offline checks for the prospective v2 protocol; no model-quality claims."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import socket

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("method_v2", ROOT / "evals/method-selection-v2/run_experiment.py")
method = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(method)


@pytest.fixture
def fixture_dir(tmp_path):
    for name in ("inputs.json", "gold.json", "protocol.md"):
        shutil.copyfile(method.HERE / name, tmp_path / name)
    return tmp_path


def reply(request, payload):
    return {"request_id": request["request_id"], "request_hash": request["request_hash"],
            "model": request["model"], "text": json.dumps(payload), "finish_reason": "stop",
            "usage": {"input_tokens": 10, "output_tokens": 5}, "latency_ms": 1}


def facts(bundle):
    source = bundle["sources"][0]
    result = [{"method_id": method_id, "fact_type": "capability", "statement": source["text"],
               "applicability_conditions": [], "measurement_scope": [], "not_evaluated_scope": [],
               "citations": [{"source_id": source["source_id"], "quote": source["text"]}]}
              for method_id in bundle["method_ids"]]
    result.append({"method_id": None, "fact_type": "unreported_dimension", "statement": "bundle-wide test fact",
                   "applicability_conditions": [], "measurement_scope": [], "not_evaluated_scope": [],
                   "citations": [{"source_id": source["source_id"], "quote": source["text"]}]})
    return result


def prepared(directory):
    lock = method.make_lock(directory)
    plan = method.prepare_extraction(lock, "unit-test-model", directory)
    bundles = method.load_inputs(directory)
    responses = [reply(request, facts(bundle)) for request, bundle in zip(plan["requests"], bundles)]
    return plan, responses


def test_extraction_is_task_and_gold_blind(fixture_dir, monkeypatch):
    lock = method.make_lock(fixture_dir)
    real_read, real_hash = method.read_json, method.shared.file_hash

    def read(path):
        assert Path(path).name != "gold.json"
        return real_read(path)

    def hashed(path):
        assert Path(path).name != "gold.json"
        return real_hash(path)

    monkeypatch.setattr(method, "read_json", read)
    monkeypatch.setattr(method.shared, "file_hash", hashed)
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("Unexpected network"))
    plan = method.prepare_extraction(lock, "unit-test-model", fixture_dir)
    assert len(plan["requests"]) == 6
    assert all("evidence_state" not in request["prompt"] for request in plan["requests"])
    for request, bundle in zip(plan["requests"], method.load_inputs(fixture_dir)):
        assert all(task["question"] not in request["prompt"] for task in bundle["tasks"])


def test_scope_projection_removes_only_other_methods_and_keeps_bundle_facts(fixture_dir):
    extraction, responses = prepared(fixture_dir)
    plan = method.prepare_answers(extraction, responses, directory=fixture_dir)
    assert len(plan["cases"]) == len(plan["requests"]) == 36
    p01q1 = next(r for r in plan["requests"] if r["request_id"] == "answer-p01q1-scoped_facts")
    scoped = json.loads(p01q1["prompt"].split("\nContext:\n", 1)[1])
    assert {fact["method_id"] for fact in scoped} == {"D", None}
    all_request = next(r for r in plan["requests"] if r["request_id"] == "answer-p01q1-all_facts")
    assert {fact["method_id"] for fact in json.loads(all_request["prompt"].split("\nContext:\n", 1)[1])} == {
        "C", "D", None}


@pytest.mark.parametrize("mutation,error", [
    (("method_id", None), "bundle-wide"), (("fact_type", "unknown"), "fact type"),
    (("measurement_scope", ["photos"]), "measurements"),
])
def test_fact_contract_fails_closed(fixture_dir, mutation, error):
    bundle = method.load_inputs(fixture_dir)[0]
    value = facts(bundle)[0]
    value[mutation[0]] = mutation[1]
    if mutation[0] == "method_id":
        value["fact_type"] = "capability"
    with pytest.raises(ValueError, match=error):
        method.parse_facts({"finish_reason": "stop", "text": json.dumps([value])}, bundle)


def test_extraction_failure_preserves_raw_and_denominators(fixture_dir):
    extraction, responses = prepared(fixture_dir)
    responses[0]["text"] = "invalid"
    plan = method.prepare_answers(extraction, responses, directory=fixture_dir)
    assert len(plan["cases"]) == 36 and len(plan["requests"]) == 32
    assert sum(c["preparation_error"] is not None for c in plan["cases"]) == 4
    assert all(c["preparation_error"] is None for c in plan["cases"] if c["arm"] == "raw")


def test_score_loads_gold_only_after_complete_response_identity(fixture_dir, monkeypatch):
    extraction, responses = prepared(fixture_dir)
    plan = method.prepare_answers(extraction, responses, directory=fixture_dir)
    answers = []
    bundles = {b["bundle_id"]: b for b in method.load_inputs(fixture_dir)}
    cases = {c["request_id"]: c for c in plan["cases"]}
    for request in plan["requests"]:
        case = cases[request["request_id"]]
        bundle = bundles[case["bundle_id"]]
        task = next(t for t in bundle["tasks"] if t["task_id"] == case["task_id"])
        source = bundle["sources"][0]
        answers.append(reply(request, {"decision": "choose", "method_id": task["options"][0],
                                      "evidence_state": "supported", "reason": "unit test only",
                                      "citations": [{"source_id": source["source_id"], "quote": source["text"]}]}))
    bad = deepcopy(answers)
    bad.pop()
    monkeypatch.setattr(method, "load_gold", lambda *_: pytest.fail("Gold read before identity validation"))
    with pytest.raises(ValueError, match="cover every request"):
        method.score(plan, bad, fixture_dir)
    monkeypatch.undo()
    report = method.score(plan, answers, fixture_dir)
    assert all(summary["tasks"] == 12 for summary in report["summary"].values())
    assert "not independent holdout" in report["limitations"][0]


def test_label_leakage_gold_drift_and_plan_tampering_rejected(fixture_dir):
    data = method.load_inputs(fixture_dir)
    data[0]["tasks"][0]["evidence_state"] = "supported"
    (fixture_dir / "inputs.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="leaked"):
        method.load_inputs(fixture_dir)
    shutil.copyfile(method.HERE / "inputs.json", fixture_dir / "inputs.json")
    extraction, responses = prepared(fixture_dir)
    plan = method.prepare_answers(extraction, responses, directory=fixture_dir)
    plan["cases"][1]["arm"] = "raw"
    with pytest.raises(ValueError, match="Plan hash"):
        method.score(plan, [], fixture_dir)
    gold = method.read_json(fixture_dir / "gold.json")
    gold[0]["method_id"] = None
    (fixture_dir / "gold.json").write_text(json.dumps(gold), encoding="utf-8")
    with pytest.raises(ValueError, match="Gold drift"):
        method.load_gold(fixture_dir, method.load_inputs(fixture_dir), extraction["lock"]["files"]["gold.json"])
