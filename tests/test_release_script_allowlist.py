"""Run the nightly hygiene gate against real, isolated Git indexes."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]
REVIEWED_SCRIPTS = (
    "scripts/smoke-pre-release.py",
    "scripts/llm_depth_test.py",
    "scripts/release/smoke_fresh_wheel.py",
)
FORBIDDEN_PATHS = (
    "scripts/unreviewed.py",
    "scripts/smoke-pre-release.py.bak",
    "scripts/llm_depth_test.py.bak",
    "scripts/release-extra/unreviewed.py",
    "internal/private.md",
    ".workbuddy/state.json",
    ".learnings/notes.md",
    "data/private.md",
    "dist/package.whl",
    "sheaf_ai.egg-info/PKG-INFO",
    ".env",
    "requirements.txt",
)


@pytest.fixture
def git_workspace(tmp_path):
    git = shutil.which("git")
    if git is None:
        pytest.skip("Git is required for the release hygiene regression")
    # Do not inherit a caller's index or worktree when constructing the fixture.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}

    def run_git(*args):
        return subprocess.run(
            [git, *args], cwd=tmp_path, env=env, capture_output=True,
            text=True, encoding="utf-8", check=True,
        )

    run_git("init", "--quiet")
    shutil.copyfile(ROOT / ".gitignore", tmp_path / ".gitignore")
    bash = shutil.which("bash")
    if os.name == "nt":
        # Git for Windows need not put bash on PATH; prefer its native shell to WSL.
        bundled_bash = Path(git).resolve().parents[1] / "bin" / "bash.exe"
        if bundled_bash.is_file():
            bash = str(bundled_bash)
    if bash is None:
        pytest.skip("Bash is required to execute the workflow's actual hygiene gate")
    def run_hygiene():
        return _run_hygiene(tmp_path, bash, env)

    return tmp_path, run_git, run_hygiene


def _stage(root, run_git, paths, *, force=False):
    for relative in paths:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")
    run_git("add", *(["--force"] if force else []), "--", *paths)


def _run_hygiene(root, bash, env):
    workflow = (ROOT / ".github/workflows/nightly-review.yml").read_text(encoding="utf-8")
    start = workflow.index('          tracked="')
    end = workflow.index("\n      - name:", start)
    # Execute the workflow commands themselves, not a Python copy of their regex.
    gate = textwrap.dedent(workflow[start:end])
    return subprocess.run(
        [bash, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", gate],
        cwd=root, env=env, capture_output=True, text=True, encoding="utf-8",
    )


def test_reviewed_scripts_are_trackable_and_pass_nightly(git_workspace):
    root, run_git, run_hygiene = git_workspace
    # Ordinary add must succeed: .gitignore must allow every reviewed script.
    _stage(root, run_git, REVIEWED_SCRIPTS)
    result = run_hygiene()
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("forbidden_path", FORBIDDEN_PATHS)
def test_nightly_rejects_unreviewed_or_private_tracked_paths(git_workspace, forbidden_path):
    root, run_git, run_hygiene = git_workspace
    # Force-add simulates accidental tracking despite the ignore policy.
    _stage(root, run_git, (forbidden_path,), force=True)
    if forbidden_path.startswith("scripts/"):
        assert run_git("check-ignore", "--no-index", forbidden_path).stdout.strip() == forbidden_path
    result = run_hygiene()
    assert result.returncode != 0, f"Nightly accepted {forbidden_path}"
    assert forbidden_path in result.stdout, result.stdout + result.stderr
