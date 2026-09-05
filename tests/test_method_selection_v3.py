"""Offline v3 method controls. No tokenizer installation, keys or live calls required."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1] / "evals/method-selection-v3"
spec = importlib.util.spec_from_file_location("v3_experiment_test", HERE / "experiment.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


def bundle():
    return {"bundle_id": "b", "method_ids": ["A", "B"],
            "sources": [{"source_id": "s", "title": "Trial", "text": "A version 2 passed cold. B failed heat. Neither tested rain."}],
            "tasks": [{"task_id": "q", "question": "cold version 2", "options": ["A"]}]}


def citation(quote):
    return {"source_id": "s", "quote": quote}


def response(value):
    return {"finish_reason": "stop", "text": json.dumps(value)}


def fact(method="A"):
    return {"method_id": method, "fact_type": "measurement", "statement": "cold pass",
            "applicability_conditions": [], "measurement_scope": ["v2"], "not_evaluated_scope": [],
            "citations": [citation("A version 2 passed cold.")]}


def test_support_sets_are_or_of_complete_and_not_cross_set_fragments():
    b = bundle()
    supports = [[citation("A version 2"), citation("passed cold.")],
                [citation("B failed"), citation("heat.")]]
    mixed = e.citation_spans([citation("A version 2"), citation("heat.")], b)
    assert not e.sufficient(supports, mixed, b)
    assert e.sufficient(supports, e.citation_spans(supports[1], b), b)


def test_coverage_merges_adjacent_intervals_but_not_gaps():
    target = {"source_id": "s", "start": 0, "end": 10}
    assert e.covered(target, [{**target, "end": 5}, {**target, "start": 5}])
    assert not e.covered(target, [{**target, "end": 4}, {**target, "start": 5}])
    assert not e.covered(target, [{**target, "source_id": "other"}])


def test_invisible_original_quote_does_not_count_as_grounded_answer():
    b = bundle()
    quote = citation("A version 2 passed cold.")
    gold = {"q": {"decision": "choose", "method_id": "A", "evidence_state": "supported", "support_sets": [[quote]]}}
    case = {"request_id": "r", "task_id": "q", "bundle_id": "b", "arm": "all_facts", "draw": 1,
            "context_tokens": 4, "preparation_error": None, "task": b["tasks"][0],
            "visible_spans": e.citation_spans([citation("B failed heat.")], b)}
    answer = {"decision": "choose", "method_id": "A", "evidence_state": "supported", "citations": [quote], "reason": "pass"}
    row = e.score_rows([case], {"r": response(answer)}, gold, [b])[0]
    assert row["decision_correct"] and row["support_covered"] and row["citation_identity_valid"]
    assert not row["citations_visible"] and not row["all_correct"] and not row["context_sufficient"]


def test_selector_keeps_whole_units_and_exact_render_budget():
    b = bundle()
    units = e.fact_units(b, [fact(), fact(None), fact("B")])
    cap = len(units[0]["text"])
    selected = e.select(units, b["tasks"][0], len, cap=cap, scope=True)
    assert selected["context_tokens"] <= cap
    assert len(selected["selected_ids"]) == 1
    assert len(selected["eligible_ids"]) == 2
    assert units[2]["unit_id"] in selected["omitted_ids"]
    assert selected["context"] in [u["text"] for u in units]
    assert e.select(units, b["tasks"][0], len, cap=1)["context"] == ""


def test_scope_keeps_shared_constraints_and_same_ranking_for_same_candidates():
    b = bundle()
    units = e.fact_units(b, [fact(), fact(None)])
    assert e.select(units, b["tasks"][0], len, cap=2000) == e.select(units, b["tasks"][0], len, cap=2000, scope=True)


def test_raw_units_preserve_original_offsets_and_whole_sentences():
    b = bundle()
    b["sources"][0]["text"] = "First complete sentence. " * 20 + "Final sentence.\n\nAnother paragraph."
    units = e.raw_units(b, len)
    for u in units:
        span = u["spans"][0]
        original = b["sources"][0]["text"][span["start"]:span["end"]]
        assert u["text"].endswith(original)
        assert original.strip().endswith(".")
    assert len(units) > 2


def test_invalid_extraction_preserves_raw_arm_and_fact_failure_denominators():
    contexts, facts = e.prepare_contexts([bundle()], {"b": response([])}, len)
    assert len(contexts) == 3
    assert contexts[0]["preparation_error"] is None
    assert all(c["preparation_error"] for c in contexts[1:])
    assert facts[0]["error"]


@pytest.mark.parametrize("change", ["bad_type", "wrong_quote", "wrong_method", "extra_key"])
def test_extraction_schema_rejects_invalid_records(change):
    f = fact()
    if change == "bad_type":
        f["fact_type"] = "made_up"
    elif change == "wrong_quote":
        f["citations"] = [citation("fabricated")]
    elif change == "wrong_method":
        f["method_id"] = "Z"
    else:
        f["winner"] = True
    with pytest.raises(ValueError):
        e.parse_facts(response([f]), bundle())


def test_unresolved_evidence_is_not_coerced_to_unreported():
    f = fact()
    f["fact_type"] = "unresolved_evidence"
    assert e.parse_facts(response([f]), bundle())[0][0]["fact_type"] == "unresolved_evidence"


@pytest.mark.parametrize("text", ['{"decision":"abstain","decision":"choose"}', '{"x":NaN}', '{"x":Infinity}'])
def test_model_json_rejects_duplicate_keys_and_nonfinite_constants(text):
    with pytest.raises(ValueError):
        e.parse_text({"text": text, "finish_reason": "stop"})


def test_incomplete_resigned_lock_rejected():
    value = {"version": "method-selection-v3", "evidence_grade": "independent_agent_authored_synthetic", "files": {}, "code": {}}
    with pytest.raises(ValueError, match="lock schema"):
        e.verify_lock({**value, "lock_hash": e.digest(value)})


def test_frozen_code_and_inputs_cannot_drift_and_gold_waits_until_scoring(monkeypatch):
    paths = [f"evals/method-selection-v3/{p}" for p in
             ("experiment.py", "run.py", "transport.py", "protocol.md", "tokenizer.json.meta",
              "DATASET-NOTES.md", "PREFLIGHT-REVIEW.md")]
    paths += ["sheaf_ai/passage_selection.py", "sheaf_ai/provenance_registry.py"]
    value = {"version": "method-selection-v3", "evidence_grade": "independent_agent_authored_synthetic",
             "files": {"inputs.json": "input", "gold.json": "gold"}, "code": dict.fromkeys(paths, "code")}
    lock = {**value, "lock_hash": e.digest(value)}
    monkeypatch.setattr(e, "file_hash", lambda p: "input" if p.name == "inputs.json" else "wrong-gold")
    monkeypatch.setattr(e, "code_hash", lambda _: "code")
    e.verify_lock(lock)
    with pytest.raises(ValueError, match="Fixture drift: gold"):
        e.verify_lock(lock, include_gold=True)
    monkeypatch.setattr(e, "code_hash", lambda _: "changed")
    with pytest.raises(ValueError, match="Code drift"):
        e.verify_lock(lock)
    monkeypatch.setattr(e, "code_hash", lambda _: "code")
    monkeypatch.setattr(e, "file_hash", lambda _: "changed")
    with pytest.raises(ValueError, match="Fixture drift: inputs"):
        e.verify_lock(lock)


def runner():
    # Avoid polluting other eval modules using generic import names.
    saved = {k: sys.modules.get(k) for k in ("experiment", "transport")}
    sys.modules["experiment"] = e
    sys.modules.pop("transport", None)
    try:
        return e.load_module("v3_runner_test", HERE / "run.py")
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def test_taskblind_extraction_and_distinct_repeat_requests():
    r = runner()
    b = bundle()
    b["tasks"][0]["question"] = "SECRET_TASK_QUESTION"
    assert "SECRET_TASK_QUESTION" not in json.dumps(r.extraction_payload(b))
    contexts, _ = e.prepare_contexts([b], {"b": response([fact()])}, len)
    plan = r.answer_plan(contexts)
    assert plan == r.answer_plan(contexts)
    assert len(plan) == len({p["request_id"] for p in plan}) == 6
    for arm in e.ARMS:
        pair = [p for p in plan if p["arm"] == arm]
        assert pair[0]["payload_hash"] == pair[1]["payload_hash"]
        assert pair[0]["request_id"] != pair[1]["request_id"]
        assert "task_id" not in json.dumps(pair[0]["payload"])


def test_preserve_refuses_overwrite(tmp_path):
    path = tmp_path / "artifact.json"
    e.preserve(path, {"v": 1})
    e.preserve(path, {"v": 1})
    with pytest.raises(ValueError, match="replace"):
        e.preserve(path, {"v": 2})


def test_pipeline_scores_after_all_response_identity_checks(tmp_path, monkeypatch):
    r = runner()
    monkeypatch.setattr(r, "HERE", tmp_path)
    monkeypatch.setattr(r, "CAMPAIGN", tmp_path / "campaign")
    monkeypatch.setattr(r, "RUN", tmp_path / "campaign/run")
    e.preserve(tmp_path / "lock.json", {})
    monkeypatch.setattr(r.e, "verify_lock", lambda *a, **kw: None)
    monkeypatch.setattr(r.e, "load_inputs", lambda: [bundle()])
    sent = []
    answer = {"decision": "choose", "method_id": "A", "evidence_state": "supported",
              "citations": [citation("A version 2 passed cold.")], "reason": "pass"}

    class FakeClient:
        def __init__(self, *args):
            assert args[3] == "offline"

        def call(self, rid, body):
            sent.append(rid)
            value = {"ok": True} if rid == "probe" else [fact()] if rid.startswith("extract-") else answer
            return {**response(value), "request_id": rid, "payload_hash": r.tr.payload_digest(body),
                    "model": r.MODEL, "usage": {"input_tokens": 100, "output_tokens": 50}, "latency_ms": 1}

    def gold_after_collection(*args):
        assert len(sent) == 8  # probe + construction + three arms times two draws
        return {"q": {"decision": "choose", "method_id": "A", "evidence_state": "supported",
                      "support_sets": [[citation("A version 2 passed cold.")]]}}

    monkeypatch.setattr(r.tr, "ExperimentClient", FakeClient)
    monkeypatch.setattr(r.e, "load_gold", gold_after_collection)
    monkeypatch.setattr(r.tr, "report_usage", lambda _: {"actual_requests": 8})
    result = r.run(len, offline=True)
    assert len(result["rows"]) == 6
    assert all(row["all_correct"] for row in result["rows"])
    assert result["cost"]["arms"]["all_facts"]["scenario_total_tokens"]["5"] == 900
    packet = e.read(r.RUN / "semantic-review-packet.json")
    assert all("arm" not in p and "all_correct" not in p for p in packet)


@pytest.mark.parametrize("key,value", [("model", "wrong"), ("request_id", "wrong"), ("payload_hash", "wrong")])
def test_response_identity_mismatch_fails_before_scoring(key, value):
    r = runner()
    p = r.payload("test", 32)
    record = {"request_id": "r", "payload_hash": r.tr.payload_digest(p), "model": r.MODEL,
              "text": "{}", "usage": {"input_tokens": 1, "output_tokens": 1}}
    record[key] = value
    with pytest.raises(ValueError, match="identity"):
        r.validate_response(record, "r", p)
