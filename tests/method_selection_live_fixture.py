"""Fresh unit-test locks, never amended historical experiment artifacts.

Copy the current test subject byte-for-byte into a temporary checkout so every
default argument and __file__-relative hash resolves there. All admission and
receipt checks remain the original executor's checks. These locks describe
synthetic MockTransport tests, not the September model campaign.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_FILES = (
    "run_experiment.py", "run_live.py", "run_live_repair.py",
    "inputs.json", "gold.json", "protocol.md", "live_protocol.md", "repair_protocol.md",
)
DEPENDENCY_FILES = (
    "sheaf_ai/renderer.py", "sheaf_ai/card_trace.py", "sheaf_ai/card_governance.py",
    "sheaf_cards/base.py", "sheaf_ai/provenance_registry.py",
)


def load_current_live_fixture(tmp_path, monkeypatch, *, repaired=False):
    """Return an unmodified executor with a separate, honestly current test lock."""
    root = tmp_path / "current-code-unit-fixture"
    directory = root / "evals" / "method-selection"
    paths = [*(f"evals/method-selection/{name}" for name in EXPERIMENT_FILES), *DEPENDENCY_FILES]
    for relative in paths:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    # Executor imports prepend their temporary ROOT; undo that after each test.
    monkeypatch.setattr(sys, "path", sys.path[:])
    name = "run_live_repair.py" if repaired else "run_live.py"
    spec = importlib.util.spec_from_file_location("current_code_unit_live", directory / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    live = module.live if repaired else module
    lock = live.experiment.make_lock(directory)
    live.experiment.write_new(directory / "lock.json", lock)
    live.experiment.verify_lock(lock, include_gold=True)
    return module
