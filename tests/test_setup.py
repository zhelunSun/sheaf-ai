"""Tests for sheaf_ai.setup — MCP auto-configuration module."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from sheaf_ai.setup import (
    build_full_config,
    build_mcp_config,
    detect_python_path,
    detect_sheaf_entry,
    get_config_path,
    merge_config,
    print_setup_result,
    read_existing_config,
    setup_target,
    write_config,
)


# ============================================================
# Environment detection
# ============================================================

class TestDetectPythonPath:
    def test_returns_string(self):
        result = detect_python_path()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_sys_executable(self):
        assert detect_python_path() == sys.executable


class TestDetectSheafEntry:
    def test_with_sheaf_on_path(self):
        with patch("sheaf_ai.setup.shutil.which", return_value="/usr/bin/sheaf"):
            assert detect_sheaf_entry() == "sheaf"

    def test_without_sheaf_on_path(self):
        with patch("sheaf_ai.setup.shutil.which", return_value=None):
            result = detect_sheaf_entry()
            assert "python" in result or "sheaf_ai.cli" in result


# ============================================================
# Config path resolution
# ============================================================

class TestGetConfigPath:
    def test_cursor(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        path = get_config_path("cursor")
        assert path == tmp_path / ".cursor" / "mcp.json"

    def test_claude(self):
        path = get_config_path("claude")
        assert path.name == ".claude.json"
        assert path.parent == Path.home()

    def test_workbuddy(self):
        path = get_config_path("workbuddy")
        assert path == Path.home() / ".workbuddy" / "mcp.json"

    def test_windsurf(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        path = get_config_path("windsurf")
        assert path == tmp_path / ".windsurf" / "mcp.json"

    def test_unknown_target_raises(self):
        with pytest.raises(ValueError, match="Unknown target"):
            get_config_path("unknown_platform")


# ============================================================
# MCP config generation
# ============================================================

class TestBuildMcpConfig:
    def test_basic_structure(self):
        config = build_mcp_config()
        assert "command" in config
        assert "args" in config
        assert config["args"] == ["-m", "sheaf_ai.mcp_server"]

    def test_custom_data_dir(self):
        config = build_mcp_config(data_dir="/tmp/sheaf-data")
        assert "env" in config
        assert config["env"]["SHEAF_DATA_DIR"] == str(Path("/tmp/sheaf-data").resolve())

    def test_api_key_from_env(self):
        saved = os.environ.get("OPENAI_API_KEY")
        saved_ds = os.environ.get("DEEPSEEK_API_KEY")
        saved_sf = os.environ.get("SILICONFLOW_API_KEY")
        try:
            os.environ.pop("SILICONFLOW_API_KEY", None)
            os.environ["OPENAI_API_KEY"] = "sk-test-key-123"
            os.environ.pop("DEEPSEEK_API_KEY", None)
            config = build_mcp_config()
            assert "env" in config
            assert config["env"]["OPENAI_API_KEY"] == "sk-test-key-123"
        finally:
            if saved is not None:
                os.environ["OPENAI_API_KEY"] = saved
            else:
                os.environ.pop("OPENAI_API_KEY", None)
            if saved_ds is not None:
                os.environ["DEEPSEEK_API_KEY"] = saved_ds
            else:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            if saved_sf is not None:
                os.environ["SILICONFLOW_API_KEY"] = saved_sf
            else:
                os.environ.pop("SILICONFLOW_API_KEY", None)

    def test_deepseek_api_key_from_env(self):
        saved = os.environ.get("OPENAI_API_KEY")
        saved_ds = os.environ.get("DEEPSEEK_API_KEY")
        saved_sf = os.environ.get("SILICONFLOW_API_KEY")
        try:
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ["DEEPSEEK_API_KEY"] = "ds-test-key"
            os.environ.pop("SILICONFLOW_API_KEY", None)
            config = build_mcp_config()
            assert config.get("env", {}).get("OPENAI_API_KEY") == "ds-test-key"
        finally:
            if saved is not None:
                os.environ["OPENAI_API_KEY"] = saved
            else:
                os.environ.pop("OPENAI_API_KEY", None)
            if saved_ds is not None:
                os.environ["DEEPSEEK_API_KEY"] = saved_ds
            else:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            if saved_sf is not None:
                os.environ["SILICONFLOW_API_KEY"] = saved_sf
            else:
                os.environ.pop("SILICONFLOW_API_KEY", None)

    def test_no_api_key_no_env(self):
        saved = os.environ.get("OPENAI_API_KEY")
        saved_ds = os.environ.get("DEEPSEEK_API_KEY")
        saved_sf = os.environ.get("SILICONFLOW_API_KEY")
        try:
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("DEEPSEEK_API_KEY", None)
            os.environ.pop("SILICONFLOW_API_KEY", None)
            config = build_mcp_config()
            assert "env" not in config
        finally:
            if saved is not None:
                os.environ["OPENAI_API_KEY"] = saved
            else:
                os.environ.pop("OPENAI_API_KEY", None)
            if saved_ds is not None:
                os.environ["DEEPSEEK_API_KEY"] = saved_ds
            else:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            if saved_sf is not None:
                os.environ["SILICONFLOW_API_KEY"] = saved_sf
            else:
                os.environ.pop("SILICONFLOW_API_KEY", None)

    def test_no_data_dir_no_sheaf_data_dir_in_env(self):
        # When data_dir is None, SHEAF_DATA_DIR should not appear in env
        config = build_mcp_config(data_dir=None)
        if "env" in config:
            assert "SHEAF_DATA_DIR" not in config["env"]


class TestBuildFullConfig:
    def test_cursor_format(self):
        config = build_full_config("cursor")
        assert "mcpServers" in config
        assert "sheaf" in config["mcpServers"]
        assert config["mcpServers"]["sheaf"]["args"] == ["-m", "sheaf_ai.mcp_server"]

    def test_claude_format(self):
        config = build_full_config("claude")
        assert "mcpServers" in config
        assert "sheaf" in config["mcpServers"]

    def test_custom_data_dir_propagated(self):
        config = build_full_config("cursor", data_dir="/custom/data")
        sheaf = config["mcpServers"]["sheaf"]
        assert "env" in sheaf
        assert "SHEAF_DATA_DIR" in sheaf["env"]


# ============================================================
# Config file I/O
# ============================================================

class TestReadExistingConfig:
    def test_nonexistent_returns_empty(self, tmp_path):
        result = read_existing_config(tmp_path / "nope.json")
        assert result == {}

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("")
        assert read_existing_config(f) == {}

    def test_invalid_json_returns_empty(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json at all")
        assert read_existing_config(f) == {}

    def test_valid_json_returned(self, tmp_path):
        f = tmp_path / "good.json"
        data = {"mcpServers": {"other": {"command": "node"}}}
        f.write_text(json.dumps(data))
        assert read_existing_config(f) == data


class TestWriteConfig:
    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "config.json"
        write_config(target, {"key": "value"})
        assert target.exists()
        assert json.loads(target.read_text()) == {"key": "value"}

    def test_pretty_printed(self, tmp_path):
        target = tmp_path / "config.json"
        write_config(target, {"a": 1})
        content = target.read_text()
        assert "\n" in content  # ends with newline
        assert "  " in content  # indented


class TestMergeConfig:
    def test_merge_into_empty(self):
        result = merge_config({}, {"command": "python"})
        assert result == {"mcpServers": {"sheaf": {"command": "python"}}}

    def test_merge_preserves_existing(self):
        existing = {
            "mcpServers": {"other_tool": {"command": "node"}},
            "otherKey": "preserved",
        }
        result = merge_config(existing, {"command": "python"})
        assert result["mcpServers"]["other_tool"]["command"] == "node"
        assert result["mcpServers"]["sheaf"]["command"] == "python"
        assert result["otherKey"] == "preserved"

    def test_merge_overwrites_sheaf(self):
        existing = {"mcpServers": {"sheaf": {"command": "old-python"}}}
        result = merge_config(existing, {"command": "new-python"})
        assert result["mcpServers"]["sheaf"]["command"] == "new-python"

    def test_merge_creates_mcpservers_if_absent(self):
        result = merge_config({"unrelated": True}, {"command": "python"})
        assert "mcpServers" in result
        assert result["mcpServers"]["sheaf"]["command"] == "python"


# ============================================================
# Full setup_target flow
# ============================================================

class TestSetupTarget:
    def test_dry_run_does_not_write(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("sheaf_ai.setup.get_config_path", return_value=tmp_path / "cursor" / "mcp.json"):
            result = setup_target("cursor", dry_run=True)
        assert result["ok"] is True
        assert result["target"] == "cursor"
        assert not (tmp_path / "cursor" / "mcp.json").exists()

    def test_actual_write(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / "cursor" / "mcp.json"
        with patch("sheaf_ai.setup.get_config_path", return_value=config_path):
            result = setup_target("cursor")
        assert result["ok"] is True
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert "mcpServers" in data
        assert "sheaf" in data["mcpServers"]

    def test_merge_with_existing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / "mcp.json"
        existing = {"mcpServers": {"other": {"command": "node"}}}
        config_path.write_text(json.dumps(existing))

        with patch("sheaf_ai.setup.get_config_path", return_value=config_path):
            result = setup_target("cursor")
        data = json.loads(config_path.read_text())
        assert data["mcpServers"]["other"]["command"] == "node"
        assert "sheaf" in data["mcpServers"]
        assert result["created"] is False

    def test_next_steps_returned(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / "mcp.json"
        with patch("sheaf_ai.setup.get_config_path", return_value=config_path):
            result = setup_target("cursor")
        assert len(result["next_steps"]) > 0

    def test_created_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / "new.json"
        with patch("sheaf_ai.setup.get_config_path", return_value=config_path):
            result = setup_target("cursor")
        assert result["created"] is True

    def test_custom_data_dir_in_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / "mcp.json"
        with patch("sheaf_ai.setup.get_config_path", return_value=config_path):
            result = setup_target("cursor", data_dir="/custom/path")
        sheaf_entry = result["sheaf_entry"]
        assert "env" in sheaf_entry
        assert "SHEAF_DATA_DIR" in sheaf_entry["env"]


# ============================================================
# print_setup_result (smoke test)
# ============================================================

class TestPrintSetupResult:
    def test_no_error(self, capsys):
        result = {
            "ok": True,
            "target": "cursor",
            "config_path": "/tmp/mcp.json",
            "created": True,
            "sheaf_entry": {"command": "python", "args": ["-m", "sheaf_ai.mcp_server"]},
            "next_steps": ["1. Restart Cursor."],
        }
        print_setup_result(result)
        captured = capsys.readouterr()
        assert "Created" in captured.out
        assert "cursor" in captured.out
        assert "Restart Cursor" in captured.out

    def test_updated_not_created(self, capsys):
        result = {
            "ok": True,
            "target": "claude",
            "config_path": "/home/.claude.json",
            "created": False,
            "sheaf_entry": {"command": "python", "args": ["-m", "sheaf_ai.mcp_server"]},
            "next_steps": [],
        }
        print_setup_result(result)
        captured = capsys.readouterr()
        assert "Updated" in captured.out
        assert "claude" in captured.out

    def test_env_vars_shown(self, capsys):
        result = {
            "ok": True,
            "target": "cursor",
            "config_path": "/tmp/mcp.json",
            "created": True,
            "sheaf_entry": {
                "command": "python",
                "args": [],
                "env": {"OPENAI_API_KEY": "sk-xxx", "SHEAF_DATA_DIR": "/data"},
            },
            "next_steps": [],
        }
        print_setup_result(result)
        captured = capsys.readouterr()
        assert "Env vars" in captured.out
