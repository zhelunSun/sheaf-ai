"""The explicit repair changes the output envelope, not the experimental question."""
import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "evals/method-selection-v3/revisions/output-cap-v1"
spec = importlib.util.spec_from_file_location("v3_cap_wrapper_test", HERE / "run.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


def test_amendment_preserves_prompt_model_context_and_budget(monkeypatch):
    monkeypatch.setattr(w, "verify_revision", lambda: {"revision_lock_hash": "unit-test"})
    r = w.configured_runner()
    b = {"method_ids": ["A"], "sources": [{"source_id": "s", "title": "t", "text": "A passed."}],
         "tasks": [{"question": "NOT_FOR_EXTRACTION"}]}
    body = r.extraction_payload(b)
    assert body["max_tokens"] == 12000
    assert body["reasoning_effort"] == "none" and body["temperature"] == .2
    assert "NOT_FOR_EXTRACTION" not in str(body)
    assert body["messages"][1]["content"].startswith(w.e.EXTRACT)
    m = r.manifest(w.e.read(w.BASE / "lock.json"))
    assert m["max_requests"] == 170 and m["max_tokens"] == 600000 and m["context_cap"] == 800
    assert m["answer_output_cap"] == 1200 and m["draws"] == 2
    assert m["recovery_from_receipts"] == w.RECOVERY
    assert m["reused_probe"]["receipt_hash"] == w.PROBE_RECEIPT
    assert m["manifest_hash"] == r.tr.digest({k: v for k, v in m.items() if k != "manifest_hash"})
    assert r.RUN.name == "run-v2-output-cap"


def test_revision_drift_stops_before_client_construction(monkeypatch):
    monkeypatch.setattr(w.e, "read", lambda _: {"revision_lock_hash": "saved"})
    monkeypatch.setattr(w, "make_lock", lambda: {"revision_lock_hash": "changed"})
    with pytest.raises(ValueError, match="identity changed"):
        w.configured_runner()
