"""Mechanical diagnostics never silently correct or promote historical outputs."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("output_contract_audit", REPO / "evals/output-contract-regression/audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def bundle():
    return {"bundle_id": "b", "method_ids": ["A"], "sources": [
        {"source_id": "s", "text": "A was not tested in rain; dry performance passed."}]}


def fact():
    return {"method_id": "A", "fact_type": "unreported_dimension", "statement": "Rain untested",
            "applicability_conditions": [], "measurement_scope": [], "not_evaluated_scope": ["rain"],
            "citations": [{"source_id": "s", "quote": "A was not tested in rain;"}]}


def response(value):
    return {"text": json.dumps(value), "finish_reason": "stop"}


def answer():
    return {"decision": "choose", "method_id": "A", "evidence_state": "supported",
            "citations": [], "reason": "A meets the requested conditions."}


def test_overflow_does_not_hide_bad_quote_or_promote_partial_batch():
    values = [fact() for _ in range(41)]
    values[-1]["citations"][0]["quote"] = "A was not tested in rain."
    before = copy.deepcopy(values)
    row = audit.audit_extraction(response(values), bundle())
    assert row["batch_issues"] == ["fact_count_exceeded", "invalid_facts"]
    assert row["mechanically_valid_indices"] == list(range(40))
    assert row["rejected_facts"] == [{"index": 40, "issues": ["quote_not_verbatim"]}]
    assert values == before


@pytest.mark.parametrize("value, expected", [(None, "expected_array"), ([], "empty_batch")])
def test_empty_distinct_from_wrong_container(value, expected):
    assert audit.audit_extraction(response(value), bundle())["batch_issues"] == [expected]


@pytest.mark.parametrize("text", ['[{"a":1}', '[{"a":1,"a":2}]', '[NaN]'])
def test_malformed_or_ambiguous_json_is_not_salvaged(text):
    row = audit.audit_extraction({"text": text, "finish_reason": "stop"}, bundle())
    assert row["batch_issues"] == ["invalid_or_incomplete_json"]


def test_even_complete_json_with_length_finish_is_not_promoted():
    r = response([fact()])
    r["finish_reason"] = "length"
    assert audit.audit_extraction(r, bundle())["batch_issues"] == ["invalid_or_incomplete_json"]


@pytest.mark.parametrize("sid, quote, expected", [
    ([], "A", "unknown_source"), ("missing", "A", "unknown_source"),
    ("s", "changed", "quote_not_verbatim"), ("s", [], "citation_schema"),
    ("s", " ", "citation_schema"),
])
def test_citation_failure_taxonomy(sid, quote, expected):
    value = fact()
    value["citations"] = [{"source_id": sid, "quote": quote}]
    assert audit.fact_issues(value, bundle()) == [expected]


def test_ambiguous_quote_cannot_be_assigned_a_unique_location():
    b = bundle()
    b["sources"][0]["text"] *= 2
    assert audit.fact_issues(fact(), b) == ["quote_ambiguous"]


@pytest.mark.parametrize("patch, expected", [
    ({"decision": "abstain", "method_id": None}, ["abstain_with_supported_state"]),
    ({"evidence_state": "conflict"}, ["choose_without_supported_state"]),
    ({"method_id": "Z"}, ["invalid_chosen_method"]),
    ({"decision": "abstain", "evidence_state": "insufficient"}, ["abstain_with_method"]),
    ({"decision": []}, ["answer_schema"]),
    ({"evidence_state": {}}, ["answer_schema"]),
])
def test_inconsistent_answer_fields_require_review_not_repair(patch, expected):
    value = {**answer(), **patch}
    before = copy.deepcopy(value)
    assert audit.decision_issues(value, ["A"]) == expected
    assert value == before


def test_does_not_claim_to_detect_semantic_reason_conflict():
    value = {**answer(), "decision": "abstain", "method_id": None, "evidence_state": "insufficient"}
    # Prose contradicts decision, but free-text semantics are outside this check.
    assert audit.decision_issues(value, ["A"]) == []


def test_invalid_type_value_is_reported_without_unhashable_exception():
    value = fact()
    value["fact_type"] = []
    assert audit.fact_issues(value, bundle()) == ["fact_schema"]


def test_report_uses_bound_receipts_and_never_loads_gold(monkeypatch):
    original = audit.frozen.read

    def no_gold(path):
        assert Path(path).name != "gold.json"
        return original(path)

    monkeypatch.setattr(audit.frozen, "read", no_gold)
    report = audit.build_report()
    assert report["new_model_calls"] == 0 and report["gold_loaded"] is False
    assert report["automatic_repair"] is False
    assert report["reason_semantics"] == "not_assessed"
    assert report["summary"]["bundles"] == 8
    assert report["summary"]["original_contract_accepted"] == 3
    assert report["summary"]["emitted_facts"] == 310
    assert report["summary"]["answer_positions"] == 144
    assert report["summary"]["answer_statuses"]["preparation_failed"] == 60
    assert report["summary"]["mechanically_valid_facts"] == 304
    assert report["summary"]["rejected_facts"] == 6
    assert report["summary"]["bounded_isolation_candidate"]["bundles_with_remaining_facts"] == 4
    assert report["summary"]["bounded_isolation_candidate"]["remaining_facts"] == 135
    # All recorded answer fields are consistent: prose reasoning remains the hard part.
    assert report["summary"]["answer_issues"] == {}
    assert all(not p.endswith("gold.json") for p in report["source_files"])


@pytest.mark.parametrize("mutation", ["checksum", "wrong_request", "wrong_payload", "transport_error"])
def test_receipt_corruption_or_binding_failure_is_rejected(tmp_path, mutation):
    rid = "test-receipt"
    payload = {"messages": []}
    payload_hash = audit.frozen.digest(payload)
    intent = {"request_id": rid, "payload": payload, "payload_hash": payload_hash, "manifest_hash": "m"}
    intent["receipt_hash"] = audit.frozen.digest(intent)
    result = {"intent_hash": intent["receipt_hash"], "manifest_hash": "m", "payload_hash": payload_hash,
              "issues": [], "transport_error": False, "http_status": 200,
              "response": {"request_id": rid, "payload_hash": payload_hash}}
    if mutation == "wrong_request":
        result["response"]["request_id"] = "other"
    elif mutation == "wrong_payload":
        result["response"]["payload_hash"] = "other"
    elif mutation == "transport_error":
        result["transport_error"] = True
    result["receipt_hash"] = "bad" if mutation == "checksum" else audit.frozen.digest(result)
    calls = tmp_path / "calls"
    calls.mkdir()
    stem = calls / audit.frozen.digest(rid)
    stem.with_suffix(".intent.json").write_text(json.dumps(intent), encoding="utf-8")
    stem.with_suffix(".result.json").write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError):
        audit.checked_receipt(tmp_path, rid)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "hidden_failure", "wrong_draw"])
def test_plan_cannot_drop_or_replace_failures_with_repeated_success(monkeypatch, mutation):
    original = audit.read

    def changed(path):
        value = original(path)
        if path == audit.FINAL / "answer-plan.json":
            failed = next(i for i, item in enumerate(value) if item["payload"] is None)
            live = next(item for item in value if item["payload"] is not None)
            if mutation == "missing":
                value.pop(failed)
            elif mutation == "duplicate":
                value[failed] = copy.deepcopy(live)
            elif mutation == "hidden_failure":
                value[failed]["payload"] = live["payload"]
                value[failed]["payload_hash"] = live["payload_hash"]
            else:
                value[failed]["draw"] = 3
        return value

    monkeypatch.setattr(audit, "read", changed)
    with pytest.raises(ValueError):
        audit.build_report()


def test_self_consistent_extraction_receipt_still_must_match_source_payload(monkeypatch):
    original = audit.checked_receipt

    def substituted(run, rid):
        intent, result = original(run, rid)
        if rid == "extract-x01":
            intent["payload"]["messages"][-1]["content"] = "Another source bundle"
            payload_hash = audit.frozen.digest(intent["payload"])
            intent["payload_hash"] = result["payload_hash"] = result["response"]["payload_hash"] = payload_hash
            intent["receipt_hash"] = audit.frozen.digest({k: v for k, v in intent.items() if k != "receipt_hash"})
            result["intent_hash"] = intent["receipt_hash"]
            result["receipt_hash"] = audit.frozen.digest({k: v for k, v in result.items() if k != "receipt_hash"})
        return intent, result

    monkeypatch.setattr(audit, "checked_receipt", substituted)
    with pytest.raises(ValueError, match="current frozen sources"):
        audit.build_report()
