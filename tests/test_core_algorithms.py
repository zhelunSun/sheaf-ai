"""The fast offline gate must use its own corpus and never a user's library."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

from sheaf_ai import _entry_storage, config


RUNNER = Path(__file__).resolve().parents[1] / "evals/core-algorithms/run_offline_eval.py"


def test_retrieval_harness_isolates_authoritative_paths_and_restores_config(tmp_path, monkeypatch):
    unrelated = tmp_path / "unrelated-library"
    unrelated.mkdir()
    sentinel = unrelated / "sentinel.txt"
    sentinel.write_text("Must stay untouched", encoding="utf-8")
    for name, relative in (
        ("DATA_DIR", "."), ("ENTRIES_DIR", "entries"), ("RAW_DIR", "raw"),
        ("SUMMARIES_DIR", "summaries"), ("INDEX_FILE", "index.jsonl"),
        ("TAGS_REGISTRY_FILE", "tags_registry.json"),
    ):
        monkeypatch.setattr(config, name, unrelated / relative)
    lock = _entry_storage.writer_lock
    checked_roots = []

    @contextmanager
    def confined_lock(root, **kwargs):
        assert not Path(root).resolve().is_relative_to(unrelated.resolve())
        checked_roots.append(Path(root))
        with lock(root, **kwargs) as held:
            yield held

    monkeypatch.setattr(_entry_storage, "writer_lock", confined_lock)
    runner = runpy.run_path(str(RUNNER))
    result = runner["evaluate_retrieval"]()
    assert result["semantic_only_cases_recovered"]
    assert result["production_entry_index_exercised"]
    assert result["hybrid_not_worse"]
    assert checked_roots
    assert config.DATA_DIR == unrelated
    assert list(unrelated.iterdir()) == [sentinel]
    assert sentinel.read_text(encoding="utf-8") == "Must stay untouched"


def test_standalone_offline_gate_does_not_create_configured_library(tmp_path):
    configured_root = tmp_path / "must-not-be-created"
    environment = {
        **os.environ, "SHEAF_DATA_DIR": str(configured_root),
        "SHEAF_LOAD_DOTENV": "0", "PYTHONUTF8": "1",
    }
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--compact"],
        cwd=RUNNER.parents[2], env=environment, capture_output=True, text=True,
        encoding="utf-8", timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["passed"] is True
    assert report["retrieval"]["semantic_only_cases_recovered"] is True
    assert not configured_root.exists()
