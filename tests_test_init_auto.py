"""Tests for sheaf init --auto — Agent-Native one-line deploy (Issue #62)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ============================================================
# setup.detect_all_platforms
# ============================================================

class TestDetectAllPlatforms:
    def test_detects_workbuddy(self, tmp_path, monkeypatch):
        from sheaf_ai.setup import detect_all_platforms
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".workbuddy").mkdir()
        result = detect_all_platforms()
        assert "workbuddy" in result

    def test_detects_claude(self, tmp_path, monkeypatch):
        from sheaf_ai.setup import detect_all_platforms
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude.json").write_text("{}")
        result = detect_all_platforms()
        assert "claude" in result

    def test_detects_cursor(self, tmp_path, monkeypatch):
        from sheaf_ai.setup import detect_all_platforms
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".cursor").mkdir()
        result = detect_all_platforms()
        assert "cursor" in result

    def test_detects_windsurf(self, tmp_path, monkeypatch):
        from sheaf_ai.setup import detect_all_platforms
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".windsurfrules").write_text("")
        result = detect_all_platforms()
        assert "windsurf" in result

    def test_detects_multiple(self, tmp_path, monkeypatch):
        from sheaf_ai.setup import detect_all_platforms
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".workbuddy").mkdir()
        (tmp_path / ".claude.json").write_text("{}")
        result = detect_all_platforms()
        assert "workbuddy" in result
        assert "claude" in result

    def test_detects_none(self, tmp_path, monkeypatch):
        from sheaf_ai.setup import detect_all_platforms
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)
        monkeypatch.chdir(tmp_path)
        result = detect_all_platforms()
        assert result == []


# ============================================================
# setup.build_mcp_config — SILICONFLOW_API_KEY priority
# ============================================================

class TestBuildMcpConfigSiliconFlow:
    def test_siliconflow_key_priority(self):
        from sheaf_ai.setup import build_mcp_config
        saved_sf = os.environ.get("SILICONFLOW_API_KEY")
        saved_ds = os.environ.get("DEEPSEEK_API_KEY")
        saved_oa = os.environ.get("OPENAI_API_KEY")
        try:
            os.environ["SILICONFLOW_API_KEY"] = "sf-test-key"
            os.environ.pop("DEEPSEEK_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            config = build_mcp_config()
            assert config.get("env", {}).get("OPENAI_API_KEY") == "sf-test-key"
        finally:
            if saved_sf is not None:
                os.environ["SILICONFLOW_API_KEY"] = saved_sf
            else:
                os.environ.pop("SILICONFLOW_API_KEY", None)
            if saved_ds is not None:
                os.environ["DEEPSEEK_API_KEY"] = saved_ds
            else:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            if saved_oa is not None:
                os.environ["OPENAI_API_KEY"] = saved_oa
            else:
                os.environ.pop("OPENAI_API_KEY", None)

    def test_deepseek_fallback_when_no_siliconflow(self):
        from sheaf_ai.setup import build_mcp_config
        saved_sf = os.environ.get("SILICONFLOW_API_KEY")
        saved_ds = os.environ.get("DEEPSEEK_API_KEY")
        saved_oa = os.environ.get("OPENAI_API_KEY")
        try:
            os.environ.pop("SILICONFLOW_API_KEY", None)
            os.environ["DEEPSEEK_API_KEY"] = "ds-test-key"
            os.environ.pop("OPENAI_API_KEY", None)
            config = build_mcp_config()
            assert config.get("env", {}).get("OPENAI_API_KEY") == "ds-test-key"
        finally:
            if saved_sf is not None:
                os.environ["SILICONFLOW_API_KEY"] = saved_sf
            else:
                os.environ.pop("SILICONFLOW_API_KEY", None)
            if saved_ds is not None:
                os.environ["DEEPSEEK_API_KEY"] = saved_ds
            else:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            if saved_oa is not None:
                os.environ["OPENAI_API_KEY"] = saved_oa
            else:
                os.environ.pop("OPENAI_API_KEY", None)


# ============================================================
# _init_auto integration tests (via CLI dispatch)
# ============================================================

class TestInitAutoCLI:
    def test_init_auto_creates_data_dir(self, tmp_path, monkeypatch, capsys):
        """sheaf init --auto creates data directory structure."""
        data_dir = tmp_path / "sheaf-data"
        monkeypatch.setenv("SHEAF_DATA_DIR", str(data_dir))
        # Patch home to avoid touching real config
        monkeypatch.setattr("sheaf_ai.cli.Path.home", lambda: tmp_path)
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)
        monkeypatch.setattr("sheaf_ai.setup.get_config_path", lambda t: tmp_path / f"{t}_mcp.json")

        # Remove API keys to avoid real LLM calls
        for k in ["SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SHEAF_API_KEY"]:
            monkeypatch.delenv(k, raising=False)

        # Patch get_provider_config (imported inside _init_auto from sheaf_ai.settings)
        monkeypatch.setattr("sheaf_ai.settings.get_provider_config", lambda: None)

        # Run
        monkeypatch.setattr(sys, "argv", ["sheaf", "init", "--auto"])
        from sheaf_ai.cli import _run
        _run()

        assert data_dir.exists()
        assert (data_dir / "entries").exists()
        assert (data_dir / "summaries").exists()
        assert (data_dir / "raw").exists()
        assert (data_dir / "index.jsonl").exists()

    def test_init_auto_detects_platform(self, tmp_path, monkeypatch, capsys):
        """sheaf init --auto auto-detects workbuddy platform."""
        data_dir = tmp_path / "sheaf-data"
        monkeypatch.setenv("SHEAF_DATA_DIR", str(data_dir))
        monkeypatch.setattr("sheaf_ai.cli.Path.home", lambda: tmp_path)
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)

        # Create workbuddy marker
        (tmp_path / ".workbuddy").mkdir()

        # Remove API keys
        for k in ["SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SHEAF_API_KEY"]:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr("sheaf_ai.settings.get_provider_config", lambda: None)

        monkeypatch.setattr(sys, "argv", ["sheaf", "init", "--auto"])
        from sheaf_ai.cli import _run
        _run()

        captured = capsys.readouterr()
        assert "workbuddy" in captured.out

    def test_init_auto_with_target(self, tmp_path, monkeypatch, capsys):
        """sheaf init --auto --target cursor sets up cursor even without detection."""
        data_dir = tmp_path / "sheaf-data"
        monkeypatch.setenv("SHEAF_DATA_DIR", str(data_dir))
        monkeypatch.setattr("sheaf_ai.cli.Path.home", lambda: tmp_path)
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)

        # Override get_config_path to write to tmp
        cursor_config = tmp_path / ".cursor" / "mcp.json"
        monkeypatch.setattr("sheaf_ai.setup.get_config_path", lambda t: cursor_config)

        # Remove API keys
        for k in ["SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SHEAF_API_KEY"]:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr("sheaf_ai.settings.get_provider_config", lambda: None)

        monkeypatch.setattr(sys, "argv", ["sheaf", "init", "--auto", "--target", "cursor"])
        from sheaf_ai.cli import _run
        _run()

        captured = capsys.readouterr()
        assert "cursor" in captured.out
        # Verify config was written
        assert cursor_config.exists()
        data = json.loads(cursor_config.read_text())
        assert "mcpServers" in data
        assert "sheaf" in data["mcpServers"]

    def test_init_auto_idempotent(self, tmp_path, monkeypatch, capsys):
        """Running init --auto twice is safe."""
        data_dir = tmp_path / "sheaf-data"
        monkeypatch.setenv("SHEAF_DATA_DIR", str(data_dir))
        monkeypatch.setattr("sheaf_ai.cli.Path.home", lambda: tmp_path)
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)

        for k in ["SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SHEAF_API_KEY"]:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr("sheaf_ai.settings.get_provider_config", lambda: None)

        monkeypatch.setattr(sys, "argv", ["sheaf", "init", "--auto"])
        from sheaf_ai.cli import _run

        # First run
        _run()
        # Second run
        _run()

        captured = capsys.readouterr()
        assert "Sheaf" in captured.out
        # Data dir still exists, no error
        assert data_dir.exists()

    def test_init_auto_json_output(self, tmp_path, monkeypatch, capsys):
        """sheaf init --auto --json produces machine-readable JSON."""
        data_dir = tmp_path / "sheaf-data"
        monkeypatch.setenv("SHEAF_DATA_DIR", str(data_dir))
        monkeypatch.setattr("sheaf_ai.cli.Path.home", lambda: tmp_path)
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)

        for k in ["SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SHEAF_API_KEY"]:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr("sheaf_ai.settings.get_provider_config", lambda: None)

        monkeypatch.setattr(sys, "argv", ["sheaf", "init", "--auto", "--json"])
        from sheaf_ai.cli import _run
        _run()

        captured = capsys.readouterr()
        # Should contain JSON at the end
        lines = captured.out.strip().splitlines()
        # Find the JSON block (last lines starting with {)
        json_start = None
        for i, line in enumerate(lines):
            if line.strip().startswith("{"):
                json_start = i
                break
        assert json_start is not None, "No JSON output found"
        json_str = "\n".join(lines[json_start:])
        data = json.loads(json_str)
        assert "version" in data
        assert "data_dir" in data
        assert "api_key_detected" in data
        assert "status" in data


# ============================================================
# One-line agent experience
# ============================================================

class TestAgentOneLineExperience:
    """Verify the Agent one-line deployment flow end-to-end."""

    def test_fresh_install_no_api_key(self, tmp_path, monkeypatch, capsys):
        """Simulate a fresh agent install: no API key, no data, detects platform."""
        data_dir = tmp_path / "fresh-sheaf"
        monkeypatch.setenv("SHEAF_DATA_DIR", str(data_dir))
        monkeypatch.setattr("sheaf_ai.cli.Path.home", lambda: tmp_path)
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)

        # Agent has workbuddy installed
        (tmp_path / ".workbuddy").mkdir()

        # No API keys
        for k in ["SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SHEAF_API_KEY"]:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr("sheaf_ai.settings.get_provider_config", lambda: None)

        monkeypatch.setattr(sys, "argv", ["sheaf", "init", "--auto"])
        from sheaf_ai.cli import _run
        _run()

        captured = capsys.readouterr()

        # Verify all steps reported
        assert "Data dir" in captured.out
        assert "Config dir" in captured.out
        assert "API key" in captured.out
        assert "workbuddy" in captured.out
        assert "warning" in captured.out.lower()  # API key missing = warning
        assert "sheaf <url>" in captured.out  # next steps shown

    def test_full_install_with_api_key(self, tmp_path, monkeypatch, capsys):
        """Full install with API key: should report all green."""
        data_dir = tmp_path / "full-sheaf"
        monkeypatch.setenv("SHEAF_DATA_DIR", str(data_dir))
        monkeypatch.setattr("sheaf_ai.cli.Path.home", lambda: tmp_path)
        monkeypatch.setattr("sheaf_ai.setup._home", lambda: tmp_path)

        # Has API key
        monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test-key")

        # Has workbuddy
        (tmp_path / ".workbuddy").mkdir()

        # Mock LLM client
        mock_client = MagicMock()
        mock_client.__class__.__name__ = "OpenAI"
        monkeypatch.setattr("sheaf_ai.settings.get_provider_config", lambda: None)

        monkeypatch.setattr(sys, "argv", ["sheaf", "init", "--auto"])
        from sheaf_ai.cli import _run

        # Patch get_client to avoid real API call
        with patch("sheaf_ai.llm_client.get_client", return_value=mock_client):
            _run()

        captured = capsys.readouterr()
        assert "SILICONFLOW_API_KEY detected" in captured.out
        assert "ready" in captured.out.lower() or "passed" in captured.out.lower()
