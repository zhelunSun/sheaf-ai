"""Synthetic responses validate the harness only; never committed as model results."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import socket

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("method_selection", ROOT / "evals/method-selection/run_experiment.py")
experiment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(experiment)


@pytest.fixture
def fixture_dir(tmp_path):
    for name in ("inputs.json", "gold.json", "protocol.md"):
        shutil.copyfile(experiment.HERE / name, tmp_path / name)
    return tmp_path


def reply(req, payload):
    return {"request_id": req["request_id"], "request_hash": req["request_hash"], "model": req["model"],
            "text": json.dumps(payload), "finish_reason": "stop", "usage": {"input_tokens": None, "output_tokens": None},
            "latency_ms": None}


def prepared(directory):
    lock = experiment.make_lock(directory)
    plan = experiment.prepare_extraction(lock, "unit-test-not-a-model", directory)
    inputs = experiment.load_inputs(directory)
    responses = []
    for req, bundle in zip(plan["requests"], inputs, strict=True):
        responses.append(reply(req, [{"method_id": "A", "claim": source["text"],
                                     "conditions": ["Keep all stated conditions"], "exceptions": [],
                                     "citations": [{"source_id": source["source_id"], "quote": source["text"]}]}
                                    for source in bundle["sources"]]))
    return plan, responses


def dummy_answers(plan, directory):
    # Intentionally simplistic and frequently wrong; no evaluator labels read.
    tasks = {t["task_id"]: (t, b) for b in experiment.load_inputs(directory) for t in b["tasks"]}
    responses = []
    for req in plan["requests"]:
        task_id = next(c["task_id"] for c in plan["cases"] if c["request_id"] == req["request_id"])
        task, bundle = tasks[task_id]
        source = bundle["sources"][0]
        responses.append(reply(req, {"decision": "choose", "method_id": task["options"][0],
                                    "evidence_state": "supported", "reason": "UNIT TEST ONLY",
                                    "citations": [{"source_id": source["source_id"], "quote": source["text"]}]}))
    return responses


def test_prepare_never_reads_gold_or_calls_network_and_preserves_equal_card_information(fixture_dir, monkeypatch):
    extraction, responses = prepared(fixture_dir)
    read_json, file_hash = experiment.read_json, experiment.file_hash

    def guarded(func):
        def checked(path):
            assert path.name != "gold.json"
            return func(path)
        return checked

    monkeypatch.setattr(experiment, "read_json", guarded(read_json))
    monkeypatch.setattr(experiment, "file_hash", guarded(file_hash))
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("Unexpected network use"))
    experiment.prepare_extraction(extraction["lock"], "unit-test-not-a-model", fixture_dir)
    plan = experiment.prepare_answers(extraction, responses, directory=fixture_dir)
    assert len(plan["requests"]) == 36
    assert plan["budget"]["unit"] == "characters"
    for artifact in plan["artifacts"]:
        cards = artifact["cards"]
        assert json.loads(artifact["contexts"]["structured_card"]) == cards
        for card in cards:
            plain = artifact["contexts"]["text_card"]
            assert card["claim"] in plain
            assert all(v in plain for k in ("conditions", "exceptions") for v in card[k])
            assert all(c["quote"] in plain and c["source_id"] in plain for c in card["citations"])


def test_full_import_scoring_keeps_negative_cases_and_unknown_costs(fixture_dir):
    extraction, responses = prepared(fixture_dir)
    plan = experiment.prepare_answers(extraction, responses, directory=fixture_dir)
    report = experiment.score(plan, dummy_answers(plan, fixture_dir), fixture_dir)
    assert report["evidence_grade"] == "synthetic_development_only"
    for summary in report["summary"].values():
        assert summary["tasks"] == 12
        assert 0 < summary["decision_correct"] < 1
    assert report["rows"][0]["raw_response"]["usage"]["input_tokens"] is None
    assert "quotes verify identity only" in report["limitations"][0]


@pytest.mark.parametrize("failure", ["error", "length", "content_filter", "bad_json", "invented_quote"])
def test_extraction_failure_keeps_raw_running_and_all_arms_in_denominator(fixture_dir, failure):
    extraction, responses = prepared(fixture_dir)
    if failure in {"error", "length", "content_filter"}:
        responses[0]["finish_reason"] = failure
    elif failure == "bad_json":
        responses[0]["text"] = "invalid"
    else:
        cards = json.loads(responses[0]["text"])
        cards[0]["citations"][0]["quote"] = "Never present in the source"
        responses[0]["text"] = json.dumps(cards)
    plan = experiment.prepare_answers(extraction, responses, directory=fixture_dir)
    assert len(plan["cases"]) == 36
    assert len(plan["requests"]) == 32
    report = experiment.score(plan, dummy_answers(plan, fixture_dir), fixture_dir)
    assert report["summary"]["raw"]["failed"] == 0
    assert report["summary"]["text_card"]["failed"] == 2


def test_budget_failure_never_truncates_and_never_drops_denominators(fixture_dir):
    extraction, responses = prepared(fixture_dir)
    plan = experiment.prepare_answers(extraction, responses, 1, fixture_dir)
    assert not plan["requests"]
    assert len(plan["artifacts"][0]["contexts"]["raw"]) > 1
    report = experiment.score(plan, [], fixture_dir)
    assert all(s["tasks"] == s["failed"] == 12 for s in report["summary"].values())


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "model", "hash", "usage"])
def test_bad_response_identity_refuses_before_gold_read(fixture_dir, monkeypatch, mutation):
    extraction, responses = prepared(fixture_dir)
    plan = experiment.prepare_answers(extraction, responses, directory=fixture_dir)
    answers = dummy_answers(plan, fixture_dir)
    if mutation == "missing":
        answers.pop()
    elif mutation == "duplicate":
        answers[1] = deepcopy(answers[0])
    elif mutation == "unknown":
        answers[0]["request_id"] = "unknown"
    elif mutation == "model":
        answers[0]["model"] = "another-model"
    elif mutation == "hash":
        answers[0]["request_hash"] = "0" * 64
    else:
        answers[0]["usage"]["input_tokens"] = True
    monkeypatch.setattr(experiment, "load_gold", lambda *_: pytest.fail("Gold read before complete responses"))
    with pytest.raises(ValueError):
        experiment.score(plan, answers, fixture_dir)


def test_label_leakage_drift_and_output_overwrite_are_rejected(fixture_dir):
    data = experiment.load_inputs(fixture_dir)
    data[0]["tasks"][0]["category"] = "supported"
    (fixture_dir / "inputs.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="labels"):
        experiment.load_inputs(fixture_dir)
    path = fixture_dir / "artifact.json"
    experiment.write_new(path, {"first": True})
    with pytest.raises(FileExistsError):
        experiment.write_new(path, {"first": False})
    assert experiment.read_json(path) == {"first": True}


def test_gold_change_after_requests_is_not_accepted(fixture_dir):
    extraction, responses = prepared(fixture_dir)
    plan = experiment.prepare_answers(extraction, responses, directory=fixture_dir)
    gold = experiment.read_json(fixture_dir / "gold.json")
    gold[0]["method_id"] = "B"
    (fixture_dir / "gold.json").write_text(json.dumps(gold), encoding="utf-8")
    with pytest.raises(ValueError, match="Gold drift"):
        experiment.score(plan, dummy_answers(plan, fixture_dir), fixture_dir)


def test_plan_tampering_rejected(fixture_dir):
    extraction, responses = prepared(fixture_dir)
    extraction["requests"][0]["prompt"] += " altered"
    with pytest.raises(ValueError, match="Plan hash"):
        experiment.prepare_answers(extraction, responses, directory=fixture_dir)


def test_lock_cannot_omit_code_dependencies(fixture_dir):
    lock = experiment.make_lock(fixture_dir)
    lock["code"].clear()
    with pytest.raises(ValueError, match="Incomplete"):
        experiment.prepare_extraction(lock, "unit-test-not-a-model", fixture_dir)
