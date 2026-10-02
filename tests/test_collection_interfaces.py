"""Public boundaries must distinguish saved sources from complete enrichment."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from sheaf_ai.batch import batch_collect
from sheaf_ai.collection_projection import collection_diagnostics


@pytest.fixture
def partial():
    return {
        "success": True, "stored": True, "status": "partial", "entry_id": "test-entry",
        "url": "https://example.com", "one_liner": "",
        "processing": {
            "classify": {"status": "success", "method": "llm"},
            "summarize": {"status": "error", "method": "llm"},
        },
        "warnings": ["Summary unavailable; source saved."],
        "quality": {"quality_tier": "B", "score": 3, "private": "secret"},
        "source": {"tier": "B", "score": 0.6, "private": "secret"},
    }


def test_cli_partial_keeps_json_and_nonzero_exit(partial, capsys):
    from sheaf_ai.cli import _print_collect_result, _exit_on_collect_failure
    _print_collect_result(partial, json_output=True)
    assert json.loads(capsys.readouterr().out)["stored"] is True
    _print_collect_result(partial)
    assert "部分完成" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        _exit_on_collect_failure(partial)
    assert exc.value.code != 0


def test_mcp_partial_has_tool_error_and_saved_receipt(monkeypatch, partial):
    from sheaf_ai.mcp import collect
    monkeypatch.setattr(collect, "process_url", lambda *a, **kw: dict(partial))
    response = json.loads(collect._handle_collect(1, {"url": "https://example.com"}))["result"]
    payload = json.loads(response["content"][0]["text"])
    assert response["isError"] is True
    assert payload["stored"] is True
    assert payload["processing"]["summarize"]["status"] == "error"


def test_http_partial_projects_safe_diagnostics(monkeypatch, partial):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from sheaf_ai import api
    monkeypatch.setattr(api, "process_url", lambda **kw: partial)
    with TestClient(api.create_app(), base_url="http://localhost") as client:
        response = client.post("/collect", json={"url": "https://example.com"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True and data["stored"] is True
    assert data["status"] == "partial"
    assert data["warnings"] == partial["warnings"]
    assert data["source"] == {"tier": "B", "score": 0.6}
    assert "private" not in data["quality"]


def test_http_detail_preserves_legacy_unknown_and_persisted_partial(monkeypatch, tmp_path, partial):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from sheaf_ai import api
    monkeypatch.setattr(api, "ENTRIES_DIR", tmp_path)
    path = tmp_path / "test-en" / "test-entry.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"id": "test-entry", "title": "Legacy", "status": "active"}), encoding="utf-8")
    with TestClient(api.create_app(), base_url="http://localhost") as client:
        legacy = client.get("/entries/test-entry").json()
        assert legacy["stored"] is True and legacy["collection_status"] == "unknown"
        assert legacy["status"] == "active"
        assert legacy["processing"]["summarize"]["status"] == "unknown"
        path.write_text(json.dumps({"id": "test-entry", "status": "active", "metadata": {"collection": partial}}), encoding="utf-8")
        current = client.get("/entries/test-entry").json()
        assert current["collection_status"] == "partial" and current["warnings"] == partial["warnings"]
        assert current["status"] == "active"


@pytest.mark.parametrize("workers", [1, 2])
def test_batch_saved_partial_counts_and_jsonl(monkeypatch, tmp_path, partial, workers):
    monkeypatch.setattr("sheaf_ai.pipeline.process_url", lambda *a, **kw: dict(partial))
    path = tmp_path / "receipts.jsonl"
    result = batch_collect(["https://a", "https://b"], concurrency=workers, quiet=True, jsonl_output=path)
    payload = result.to_dict()
    assert payload["succeeded"] == 2 and payload["partial"] == 2
    assert payload["complete"] == 0 and payload["ok"] is False
    assert payload["status"] == "partial"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_batch_stop_writes_failure_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr("sheaf_ai.pipeline.process_url", lambda *a, **kw: {"success": False, "status": "error"})
    path = tmp_path / "receipts.jsonl"
    result = batch_collect(["https://a", "https://b"], on_error="stop", quiet=True, jsonl_output=path)
    assert result.failed == 1 and result.to_dict()["not_completed"] == 1
    assert len(path.read_text().splitlines()) == 1


def test_concurrent_stop_accounts_for_already_running_saves(monkeypatch, tmp_path):
    barrier = Barrier(2)
    def process(url, **kw):
        barrier.wait(timeout=5)
        return {"success": url.endswith("b"), "status": "success" if url.endswith("b") else "error"}
    monkeypatch.setattr("sheaf_ai.pipeline.process_url", process)
    path = tmp_path / "receipts.jsonl"
    with ThreadPoolExecutor(max_workers=1) as guard:
        result = guard.submit(batch_collect, ["https://a", "https://b"], concurrency=2,
                              on_error="stop", quiet=True, jsonl_output=path).result(timeout=10)
    assert result.succeeded == 1 and result.failed == 1
    assert len(path.read_text().splitlines()) == 2


def test_batch_cli_json_remains_parseable_and_exits_partial(monkeypatch, partial, capsys):
    from sheaf_ai.cli import _batch_collect_cli
    monkeypatch.setattr("sheaf_ai.pipeline.process_url", lambda *a, **kw: dict(partial))
    with pytest.raises(SystemExit):
        _batch_collect_cli(["https://a"], json_output=True)
    assert json.loads(capsys.readouterr().out)["partial"] == 1


def test_unexpected_failure_does_not_claim_no_save_or_expose_exception(monkeypatch):
    from sheaf_ai.mcp import collect
    def fail(*a, **kw):
        raise RuntimeError("token=SECRET private/path provider.example")
    monkeypatch.setattr(collect, "process_url", fail)
    response = json.loads(collect._handle_collect(1, {"url": "https://example.com"}))["result"]
    text = response["content"][0]["text"]
    assert "SECRET" not in text and "private/path" not in text
    assert json.loads(text)["stored"] is None
    assert response["isError"] is True


def test_projection_does_not_fabricate_legacy_success():
    assert collection_diagnostics({"success": True})["status"] == "unknown"


def test_legacy_batch_processing_is_unknown(monkeypatch):
    monkeypatch.setattr("sheaf_ai.pipeline.process_url", lambda *a, **kw: {"success": True})
    result = batch_collect(["https://a"], quiet=True).to_dict()
    assert result["ok"] is True  # legacy compatibility: no operational failures
    assert result["status"] == "unknown" and result["processing_complete"] is False
    assert result["unassessed"] == 1 and result["complete"] == 0


def test_cli_unexpected_error_is_safe_json_receipt(monkeypatch, capsys):
    from sheaf_ai.cli import _run_collect, _print_collect_result, _exit_on_collect_failure
    def fail(*a, **kw):
        raise RuntimeError("SECRET provider/private/path")
    monkeypatch.setattr("sheaf_ai.pipeline.process_url", fail)
    result = _run_collect("https://a")
    _print_collect_result(result, json_output=True)
    output = capsys.readouterr().out
    assert json.loads(output)["stored"] is None and "SECRET" not in output
    with pytest.raises(SystemExit):
        _exit_on_collect_failure(result)


def test_http_pipeline_persistence_detail_and_agent_raw_roundtrip(monkeypatch, isolated_data_dir):
    """Real adapters/storage with only the model unavailable, no mocked result."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from sheaf_ai import api, llm_client, retrieval_service, storage
    from sheaf_ai.mcp.resources import read_resource
    monkeypatch.setattr(api, "ENTRIES_DIR", isolated_data_dir / "entries")
    monkeypatch.setattr(storage, "_extract_entities_for_index", lambda *_: [])
    monkeypatch.setattr(retrieval_service, "update_entry_index_if_initialized", lambda *a, **kw: None)
    def fail(**kw):
        raise RuntimeError("SECRET model endpoint")
    monkeypatch.setattr(llm_client, "chat", fail)
    raw = "Version two requires explicit consent, including offline indexing. " * 5
    with TestClient(api.create_app(), base_url="http://localhost") as client:
        response = client.post("/collect", json={"url": "manual://integration", "manual_text": raw})
        assert response.status_code == 200
        collected = response.json()
        assert collected["status"] == "partial" and collected["stored"] is True
        entry_id = collected["entry_id"]
        detail = client.get(f"/entries/{entry_id}").json()
        assert detail["status"] == "active" and detail["collection_status"] == "partial"
        assert detail["derived"]["summary"]["status"] == "current"
        assert detail["processing"] == collected["processing"]
        assert detail["summary"] == "" and "SECRET" not in json.dumps(detail)
    resource = json.loads(read_resource(1, f"sheaf://entries/{entry_id}/raw"))
    assert resource["result"]["contents"][0]["text"] == raw
    persisted = json.loads((isolated_data_dir / "entries" / entry_id[:7] / f"{entry_id}.json").read_text("utf-8"))
    assert "author" in detail["source"] and detail["source"] == persisted["source"]
