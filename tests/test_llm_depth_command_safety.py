"""Offline safety tests for the optional, paid exploratory profile driver."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest


@pytest.fixture
def driver():
    path = Path(__file__).resolve().parents[1] / "scripts" / "llm_depth_test.py"
    name = "_sheaf_llm_depth_test_safety"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(name, None)


@pytest.fixture
def workspace(driver, tmp_path):
    root = tmp_path / "profile"
    root.mkdir()
    result = driver.ProfileWorkspace(root, root / "data", root / "cwd", root / "home")
    for path in (result.data, result.cwd, result.home):
        path.mkdir()
    return result


@pytest.mark.parametrize("command", [
    "sheaf stats", "tags", "weekly", "trends", "urgent", "insights --json",
    'search "多智能体 remote sensing" --json --limit 3',
    'list --recent --page 2 --limit 10 --topic "AI agents" --json',
    'crystallize "AI agents" --format json', "crystallize --list", "crystallize --stats",
    "collect https://arxiv.org/abs/2401.15884 --json",
    'collect ""', "collect just-plain-text-not-a-url",
])
def test_allowed_commands_round_trip_without_repair(driver, command):
    argv = driver.parse_command(command)
    assert driver.parse_command(driver.normalize_command(command)) == argv


@pytest.mark.parametrize("command", [
    "stats && whoami", "stats; whoami", "stats | whoami", "stats > /tmp/result",
    'search "$(whoami)"', 'search "`whoami`"', 'search "%USERPROFILE%"',
    "stats\nconfig list", "stats\rsetup", "stats\x00",
    "python -c pass", "powershell -Command whoami", "cmd /c whoami",
    "/bin/sh -c true", r"C:\Windows\System32\cmd.exe /c whoami",
    "sheaf setup --target codex", "init --auto", "config list", "memory snapshot",
    "serve", "mcp", "reclassify", "doctor --json", "search-index --rebuild",
    "collect --batch ../../private.txt", "collect --output ../../result.json x",
    "collect --text secret", "collect file:///etc/passwd", "collect http://127.0.0.1/",
    "collect https://unlisted.example/", "collect ../private.txt",
    "crystallize --delete card", "crystallize --rebuild-embeddings", "crystallize",
    "search", "sheaf", "stats --json", "list --data-dir ../../data",
    "list --lim 4", "search query --limit 100000", "search query --limit 0",
    'search "unterminated', "", " " * 20,
])
def test_rejected_commands_never_start_a_subprocess(driver, workspace, monkeypatch, command):
    run = Mock(side_effect=AssertionError("must not execute"))
    monkeypatch.setattr(driver.subprocess, "run", run)
    stdout, stderr, code, elapsed = driver.run_sheaf_command(command, workspace)
    assert stdout == "" and code == 2 and elapsed == 0
    assert stderr.startswith("COMMAND_REJECTED:")
    run.assert_not_called()


def test_fixed_argv_and_minimal_isolated_environment(driver, workspace, monkeypatch):
    monkeypatch.setenv("SHEAF_DATA_DIR", "real-user-library")
    monkeypatch.setenv("PYTHONPATH", "untrusted-import-path")
    monkeypatch.setenv("PYTHONHOME", "other-python")
    monkeypatch.setenv("HOME", "real-home")
    monkeypatch.setenv("OPENAI_API_KEY", "unapproved-key")
    monkeypatch.setenv("DEFAULT_PROVIDER", "unapproved-provider")
    monkeypatch.setenv("UNRELATED_SECRET", "do-not-forward")
    explicit = {
        "OPENAI_API_KEY": "fake-approved-key", "OPENAI_BASE_URL": "https://example.invalid/v1",
        "DEFAULT_MODEL": "test-model",
    }
    run = Mock(return_value=subprocess.CompletedProcess([], 7, "actual stdout", "actual stderr"))
    monkeypatch.setattr(driver.subprocess, "run", run)
    before = dict(os.environ)
    result = driver.run_sheaf_command('sheaf search "中文 AI" --json', workspace, provider_env=explicit)
    assert result[:3] == ("actual stdout", "actual stderr", 7)
    argv = run.call_args.args[0]
    kwargs = run.call_args.kwargs
    assert argv == [sys.executable, "-m", "sheaf_ai.cli", "search", "中文 AI", "--json"]
    assert kwargs["shell"] is False and kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["cwd"] == workspace.cwd
    env = kwargs["env"]
    assert env["HOME"] == env["USERPROFILE"] == str(workspace.home)
    assert env["SHEAF_DATA_DIR"] == str(workspace.data)
    assert env["SHEAF_LOAD_DOTENV"] == "0"
    assert env["DEFAULT_PROVIDER"] == "openai"
    assert env["OPENAI_API_KEY"] == "fake-approved-key"
    assert env["PYTHONPATH"] == str(driver.SOURCE_ROOT)
    assert "PYTHONHOME" not in env
    assert "UNRELATED_SECRET" not in env
    assert os.environ == before


def test_provider_environment_is_opt_in(driver, workspace, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")
    env = driver.isolated_environment(workspace, {})
    assert not driver.PROVIDER_ENV_NAMES.intersection(env)
    with pytest.raises(ValueError, match="Unexpected provider"):
        driver.isolated_environment(workspace, {"SHEAF_DATA_DIR": "../outside"})


def test_timeout_remains_failure(driver, workspace, monkeypatch):
    monkeypatch.setattr(driver.subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("x", 30)))
    assert driver.run_sheaf_command("stats", workspace)[:3] == ("", "TIMEOUT", -1)


@pytest.mark.parametrize("module_name", ["config", "providers"])
def test_disable_dotenv_blocks_cwd_and_source_fallback(module_name, tmp_path, monkeypatch):
    from sheaf_ai import config, providers
    module = {"config": config, "providers": providers}[module_name]
    cwd = tmp_path / "run"
    source = tmp_path / "source"
    cwd.mkdir()
    source.mkdir()
    (cwd / ".env").write_text("SHEAF_TEST_CWD_DOTENV=from-cwd\n", encoding="utf-8")
    (source / ".env").write_text("SHEAF_TEST_SOURCE_DOTENV=from-source\n", encoding="utf-8")
    monkeypatch.chdir(cwd)
    if module_name == "config":
        monkeypatch.setattr(module, "PROJECT_ROOT", source)
    else:
        monkeypatch.setattr(module, "__file__", str(source / "sheaf_ai" / "providers.py"))
    monkeypatch.setenv("SHEAF_LOAD_DOTENV", "0")
    for name in ("SHEAF_TEST_CWD_DOTENV", "SHEAF_TEST_SOURCE_DOTENV"):
        monkeypatch.delenv(name, raising=False)
    module._load_env_file()
    assert "SHEAF_TEST_CWD_DOTENV" not in os.environ
    (cwd / ".env").unlink()
    module._load_env_file()
    assert "SHEAF_TEST_SOURCE_DOTENV" not in os.environ
    # Default behavior remains compatible for ordinary production callers.
    monkeypatch.delenv("SHEAF_LOAD_DOTENV")
    module._load_env_file()
    assert os.environ.pop("SHEAF_TEST_SOURCE_DOTENV") == "from-source"


def test_driver_requires_explicit_configuration_before_constructing_client(driver, monkeypatch):
    import openai
    client = Mock()
    monkeypatch.setattr(openai, "OpenAI", client)
    with pytest.raises(ValueError, match="Explicit endpoint"):
        driver.get_llm()
    client.assert_not_called()
    driver.LIVE_PROVIDER_ENV.update({
        "OPENAI_API_KEY": "fake", "OPENAI_BASE_URL": "https://example.invalid/v1",
        "DEFAULT_MODEL": "fixed-model",
    })
    _, model = driver.get_llm()
    assert model == "fixed-model"
    assert client.call_args.kwargs["max_retries"] == 0


@pytest.mark.parametrize("arguments", [[], ["--dry-run"], ["--execute"], ["--execute", "--steps", "0"]])
def test_main_defaults_to_no_paid_calls(driver, monkeypatch, arguments):
    get_llm = Mock(side_effect=AssertionError("must not make calls"))
    monkeypatch.setattr(driver, "get_llm", get_llm)
    monkeypatch.setattr(sys, "argv", ["llm_depth_test.py", *arguments])
    with pytest.raises(SystemExit) as error:
        driver.main()
    assert error.value.code == 2
    get_llm.assert_not_called()


def test_rejected_intent_retains_raw_command_without_judging(driver, workspace, monkeypatch):
    monkeypatch.setattr(driver.ProfileWorkspace, "create", lambda _: workspace)
    raw = "sheaf setup --target codex"
    monkeypatch.setattr(driver, "llm_generate_intent", lambda *a, **kw: {"intent": "setup", "command": raw})
    execute = Mock(side_effect=AssertionError("must not execute"))
    judge = Mock(side_effect=AssertionError("must not judge"))
    monkeypatch.setattr(driver, "run_sheaf_command", execute)
    monkeypatch.setattr(driver, "llm_judge_result", judge)
    report = driver.run_profile_test("A", steps=1)
    assert report.steps[0].raw_command == raw
    assert report.steps[0].execution_status == "command_rejected"
    assert report.steps[0].exit_code == 2
    assert report.overall_score is None
    execute.assert_not_called()
    judge.assert_not_called()


def test_intent_failure_is_not_replaced_with_successful_stats(driver, workspace, monkeypatch):
    monkeypatch.setattr(driver.ProfileWorkspace, "create", lambda _: workspace)
    monkeypatch.setattr(driver, "llm_generate_intent", Mock(side_effect=ValueError("bad JSON")))
    execute = Mock(side_effect=AssertionError("must not execute"))
    monkeypatch.setattr(driver, "run_sheaf_command", execute)
    report = driver.run_profile_test("A", steps=1)
    assert report.steps[0].execution_status == "intent_failed"
    assert report.steps[0].quality_score is None
    execute.assert_not_called()


@pytest.mark.parametrize("response", [{"intent": "missing command"}, [], {"intent": "x", "command": None}])
def test_malformed_intent_never_defaults_to_stats(driver, workspace, monkeypatch, response):
    monkeypatch.setattr(driver.ProfileWorkspace, "create", lambda _: workspace)
    monkeypatch.setattr(driver, "llm_generate_intent", lambda *a, **kw: response)
    execute = Mock(side_effect=AssertionError("must not execute"))
    monkeypatch.setattr(driver, "run_sheaf_command", execute)
    report = driver.run_profile_test("A", steps=1)
    assert report.steps[0].execution_status == "intent_failed"
    execute.assert_not_called()


def test_judge_failure_is_unscored_and_does_not_reuse_previous_highlight(driver, workspace, monkeypatch):
    monkeypatch.setattr(driver.ProfileWorkspace, "create", lambda _: workspace)
    monkeypatch.setattr(driver, "llm_generate_intent", lambda *a, **kw: {"intent": "stats", "command": "stats"})
    monkeypatch.setattr(driver, "run_sheaf_command", lambda *a, **kw: ("{}", "", 0, 0.1))
    monkeypatch.setattr(driver, "llm_judge_result", Mock(side_effect=[
        {"overall": 8, "highlight": "first only"}, ValueError("bad score"),
    ]))
    report = driver.run_profile_test("A", steps=2)
    assert report.steps[1].quality_score is None
    assert report.steps[1].execution_status == "executed"
    assert report.steps[1].judgment_status == "failed"
    assert report.overall_score == 8
    assert report.highlights == ["Step 1: first only"]


def test_report_exposes_unscored_denominator(driver, tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "REPORTS_DIR", tmp_path)
    report = driver.ProfileReport("A", "fixture", steps=[driver.TestStep(
        step_num=1, intent="rejected", command="", raw_command="setup",
        execution_status="command_rejected", exit_code=2,
    )])
    output = tmp_path / "report.md"
    driver.generate_report([report], output, seed=0)
    text = output.read_text(encoding="utf-8")
    assert "| 1 | 0 | unscored |" in text
    assert "command_rejected" in text and "`setup`" in text
    assert "Seed**: 0" in text


def test_report_creates_only_requested_parent_and_never_overwrites(driver, tmp_path, monkeypatch):
    default = tmp_path / "unused-default" / "reports"
    monkeypatch.setattr(driver, "REPORTS_DIR", default)
    output = tmp_path / "custom" / "nested" / "report.md"
    driver.generate_report([], output)
    original = output.read_bytes()
    assert not default.exists()
    with pytest.raises(FileExistsError):
        driver.generate_report([], output)
    assert output.read_bytes() == original


def test_fixed_source_is_imported_in_actual_isolated_child(driver, workspace):
    """Read-only process check: no model, network, or actual user data is involved."""
    env = driver.isolated_environment(workspace, {})
    completed = subprocess.run(
        [sys.executable, "-c", "import sheaf_ai; print(sheaf_ai.__file__)"],
        shell=False, cwd=workspace.cwd, env=env, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert Path(completed.stdout.strip()).resolve() == driver.SOURCE_ROOT / "sheaf_ai" / "__init__.py"


@pytest.mark.parametrize("exit_code, stderr, status", [
    (-1, "TIMEOUT", "timeout"), (1, "some cards rejected", "partial"),
    (3, "quality validation failed", "command_failed"),
    (-1, "could not start child", "command_failed"),
])
def test_high_judge_score_never_turns_failed_execution_into_success(
    driver, workspace, monkeypatch, tmp_path, exit_code, stderr, status,
):
    monkeypatch.setattr(driver.ProfileWorkspace, "create", lambda _: workspace)
    monkeypatch.setattr(driver, "llm_generate_intent", lambda *a, **kw: {"intent": "stats", "command": "stats"})
    monkeypatch.setattr(driver, "run_sheaf_command", lambda *a, **kw: ("", stderr, exit_code, 30))
    monkeypatch.setattr(driver, "llm_judge_result", lambda *a, **kw: {"overall": 10, "highlight": "not a success"})
    report = driver.run_profile_test("A", steps=1)
    assert report.steps[0].execution_status == status
    assert report.steps[0].exit_code == exit_code
    assert report.steps[0].judgment_status == "scored"
    assert report.overall_score == 10  # Experience rating, explicitly NOT pass/fail.
    assert report.highlights == []
    output = tmp_path / "failure-report.md"
    driver.generate_report([report], output)
    text = output.read_text(encoding="utf-8")
    assert f"| {status} | {exit_code} | scored |" in text
    assert "| 0/1 |" in text
    assert stderr in text
    assert "10.0/10 ✅" not in text
    assert "not a success" not in text


def test_judge_failure_does_not_hide_timeout(driver, workspace, monkeypatch):
    monkeypatch.setattr(driver.ProfileWorkspace, "create", lambda _: workspace)
    monkeypatch.setattr(driver, "llm_generate_intent", lambda *a, **kw: {"intent": "stats", "command": "stats"})
    monkeypatch.setattr(driver, "run_sheaf_command", lambda *a, **kw: ("", "TIMEOUT", -1, 30))
    monkeypatch.setattr(driver, "llm_judge_result", Mock(side_effect=ValueError("invalid JSON")))
    report = driver.run_profile_test("A", steps=1)
    assert report.steps[0].execution_status == "timeout"
    assert report.steps[0].judgment_status == "failed"
    assert report.overall_score is None
