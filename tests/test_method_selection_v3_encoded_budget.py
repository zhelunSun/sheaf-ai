"""Offline mechanical budget tests; no live answers, gold, or result tables are read."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "evals/method-selection-v3"
WRAPPER = BASE / "revisions/encoded-budget-v1/run.py"


def load_wrapper():
    saved = sys.modules.get("experiment")
    spec = importlib.util.spec_from_file_location("encoded_budget_experiment_test", BASE / "experiment.py")
    experiment = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(experiment)
    sys.modules["experiment"] = experiment
    try:
        return experiment.load_module("encoded_budget_wrapper_test", WRAPPER)
    finally:
        if saved is None:
            sys.modules.pop("experiment", None)
        else:
            sys.modules["experiment"] = saved


@pytest.fixture
def wrapper():
    return load_wrapper()


def synthetic_units():
    return [{"unit_id": f"u{i}", "method_id": "A" if i % 3 else None,
             "text": json.dumps({"statement": "cold alpha beta gamma delta epsilon " * (i % 4 + 1),
                                 "condition": 'He said "cold".\nVersion 2\\only'}, ensure_ascii=False),
             "spans": [{"source_id": "s", "start": i * 10, "end": i * 10 + 5}]}
            for i in range(12)]


def test_final_budget_counts_json_literal_and_preserves_complete_units(wrapper):
    units = synthetic_units()
    task = {"question": "alpha cold version 2", "options": ["A"]}
    selected = wrapper.stable_select(units, task, len, cap=800)
    assert selected["context_tokens"] == len(json.dumps(selected["context"], ensure_ascii=False)) <= 800
    assert selected["slack_tokens"] == 800 - selected["context_tokens"]
    expected = "\n\n".join(next(u["text"] for u in units if u["unit_id"] == uid)
                             for uid in selected["selected_ids"])
    assert selected["context"] == expected
    assert selected["candidate_units"] == units


def test_pinned_tokenizer_exposes_old_overflow_and_enforces_delivered_cap(wrapper):
    asset = ROOT / ".pytest-tmp/v3-assets/tokenizer.json"
    if not asset.exists():
        pytest.skip("Pinned local tokenizer asset is not provisioned")
    runtime = pytest.importorskip("tokenizers")
    if runtime.__version__ != wrapper.e.read(BASE / "tokenizer.json.meta")["tokenizers_version"]:
        pytest.skip("Run with the pinned v3 Python environment")
    counter = wrapper.e.Counter(asset)
    dense = '{"condition":"cold","scope":"version2"}\n' * 80
    units = [{"unit_id": "quoted", "method_id": "A", "text": dense, "spans": []},
             {"unit_id": "short", "method_id": "A", "text": "cold test", "spans": []}]
    task = {"question": "condition cold scope version2", "options": ["A"]}
    old = wrapper.e.select(units, task, counter, cap=800)
    assert counter(old["context"]) == 800
    assert counter(json.dumps(old["context"], ensure_ascii=False)) == 1282
    corrected = wrapper.stable_select(units, task, counter, cap=800)
    assert corrected["selected_ids"] == ["short"]
    assert corrected["context_tokens"] == counter(json.dumps(corrected["context"], ensure_ascii=False)) <= 800


def test_raw_chunking_uses_original_counter_and_facts_keep_response_field_order(wrapper, monkeypatch):
    e = wrapper.e
    source = "A version 2 passed cold."
    bundle = {"bundle_id": "b", "method_ids": ["A"],
              "sources": [{"source_id": "s", "title": "Trial", "text": source}],
              "tasks": [{"task_id": "q", "question": "cold version 2", "options": ["A"]}]}
    # Deliberately differs from alphabetic artifact-key order.
    fact = {"statement": "cold pass", "method_id": "A", "fact_type": "measurement",
            "measurement_scope": ["version 2"], "applicability_conditions": [],
            "not_evaluated_scope": [], "citations": [{"source_id": "s", "quote": source}]}
    extraction = {"b": {"text": json.dumps([fact]), "finish_reason": "stop"}}
    original_raw = e.raw_units
    counters = []

    def raw(bundle, count):
        counters.append(count)
        return original_raw(bundle, count)

    monkeypatch.setattr(e, "raw_units", raw)
    monkeypatch.setattr(e, "select", wrapper.stable_select)
    cases, _ = e.prepare_contexts([bundle], extraction, len)
    assert counters == [len]
    fact_case = next(c for c in cases if c["arm"] == "all_facts")
    assert fact_case["candidate_units"][0]["text"] == json.dumps(fact, ensure_ascii=False, separators=(",", ":"))
    assert fact_case["candidate_units"][0]["text"] != json.dumps(fact, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    for case in cases:
        assert case["context_tokens"] == len(json.dumps(case["context"], ensure_ascii=False)) <= 800


def test_final_contexts_and_full_payloads_repeat_across_hash_seeds():
    script = r'''
import importlib.util,json,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("hashseed_budget_wrapper",Path(sys.argv[1]))
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
data=json.loads(sys.stdin.read());rows=[]
for scope in (False,True):
    selected=w.stable_select(data["units"],data["task"],len,cap=800,scope=scope)
    prompt=w.e.ANSWER+json.dumps({"task":data["task"],"context":selected["context"]},ensure_ascii=False)
    payload={"model":"test-model","messages":[{"role":"system","content":w.e.SYSTEM},{"role":"user","content":prompt}],"max_tokens":1200,"temperature":0.2,"stream":False,"reasoning_effort":"none"}
    rows.append({"context":selected["context"],"context_tokens":selected["context_tokens"],"selected_ids":selected["selected_ids"],"payload":payload,"payload_hash":w.e.digest(payload)})
print(json.dumps(rows,ensure_ascii=False,sort_keys=True))
'''
    data = {"units": synthetic_units(), "task": {"question": "alpha beta gamma cold version 2", "options": ["A"]}}
    outputs = []
    for seed in ("1", "99991"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run([sys.executable, "-B", "-c", script, str(WRAPPER)],
                                input=json.dumps(data), text=True, capture_output=True,
                                env=env, cwd=ROOT, timeout=30, check=True)
        outputs.append(json.loads(result.stdout))
    assert outputs[0] == outputs[1]
    assert all(row["context_tokens"] <= 800 for row in outputs[0])


def configured_fake(wrapper, monkeypatch, tmp_path):
    e = wrapper.e
    parent_run = tmp_path / "campaign/parent"
    payload = {"model": "test-model", "messages": [{"role": "system", "content": "system"},
               {"role": "user", "content": "original context"}], "max_tokens": 1200,
               "temperature": 0.2, "stream": False, "reasoning_effort": "none"}
    parent_manifest = {"model": "test-model", "revision_lock": {}, "manifest_hash": "parent",
                       "recovery_from_receipts": ["first", "second"]}
    planned = [{"request_id": "answer-q1-raw_passages-r1", "payload": payload,
                "payload_hash": e.digest(payload)}]
    calls = []

    class ParentClient:
        def __init__(self, run_dir, manifest, client, key, campaign_dir):
            self.run_dir, self.manifest = run_dir, manifest
            self.client, self.key, self.campaign_dir = client, key, campaign_dir

        def call(self, rid, body):
            calls.append(("reused" if self.key == "offline" else "new", rid, deepcopy(body)))
            if self.key == "offline" and body != payload:
                raise ValueError("Cached full payload differs")
            return {"request_id": rid, "payload_hash": e.digest(body)}

    transport = SimpleNamespace(ExperimentClient=ParentClient, digest=e.digest)
    runner = SimpleNamespace(RUN=parent_run, CAMPAIGN=parent_run.parent, tr=transport,
                             manifest=lambda _: deepcopy(parent_manifest))

    def read(path):
        path = Path(path)
        if path.name == "manifest.json":
            return deepcopy(parent_manifest)
        if path.name == "answer-plan.json":
            return deepcopy(planned)
        if path.name == "lock.json":
            return {}
        if path.name.endswith(".result.json"):
            return {"receipt_hash": "synthetic-receipt"}
        raise AssertionError("Unexpected artifact read")

    monkeypatch.setattr(wrapper, "verify_revision", lambda: {"revision_lock_hash": "synthetic-lock"})
    monkeypatch.setattr(wrapper.previous, "configured_runner", lambda: runner)
    monkeypatch.setattr(e, "read", read)
    monkeypatch.setattr(e, "select", e.select)  # Restore configure's module assignment after the test.
    configured, reused = wrapper.configure()
    client = configured.tr.ExperimentClient(configured.RUN, configured.manifest({}), None,
                                             "fake-never-used-on-network", configured.CAMPAIGN)
    return client, payload, calls, reused


@pytest.mark.parametrize("change", [None, "context", "temperature", "max_tokens"])
def test_reuse_requires_complete_payload_identity(wrapper, monkeypatch, tmp_path, change):
    client, payload, calls, reused = configured_fake(wrapper, monkeypatch, tmp_path)
    changed = deepcopy(payload)
    if change == "context":
        changed["messages"][1]["content"] = "new encoded-budget context"
    elif change == "temperature":
        changed["temperature"] = 0.3
    elif change == "max_tokens":
        changed["max_tokens"] = 1100
    rid = "answer-q1-raw_passages-r1"
    client.call(rid, changed)
    assert calls[0][0] == ("reused" if change is None else "new")
    assert (rid in reused) is (change is None)


def test_budget_amendment_cannot_dispatch_changed_extraction(wrapper, monkeypatch, tmp_path):
    client, payload, calls, _ = configured_fake(wrapper, monkeypatch, tmp_path)
    changed = deepcopy(payload)
    changed["max_tokens"] = 12000
    with pytest.raises(ValueError, match="Cached full payload"):
        client.call("extract-x01", changed)
    assert calls[0][0] == "reused"
    assert not any(kind == "new" for kind, _, _ in calls)
