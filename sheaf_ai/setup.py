"""
Sheaf Setup — auto-configure MCP server for Agent platforms.

Generates MCP configuration entries and merges them into the target
platform's config file, reducing the deploy process to a single command:

    sheaf setup --target cursor
    sheaf setup --target workbuddy
    sheaf setup --target claude

Supports: cursor, claude, workbuddy, windsurf.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional


# ============================================================
# Platform config locations
# ============================================================

def _home() -> Path:
    """Return the user home directory."""
    return Path.home()


def get_config_path(target: str) -> Path:
    """Return the expected MCP config file path for *target* platform.

    Supported targets: cursor, claude, workbuddy, windsurf.
    """
    home = _home()
    cwd = Path.cwd()

    if target == "cursor":
        return cwd / ".cursor" / "mcp.json"
    elif target == "claude":
        # Claude Code stores MCP config in ~/.claude.json (top-level key "mcpServers")
        return home / ".claude.json"
    elif target == "workbuddy":
        return home / ".workbuddy" / "mcp.json"
    elif target == "windsurf":
        return cwd / ".windsurf" / "mcp.json"
    else:
        raise ValueError(f"Unknown target: {target!r}. Supported: cursor, claude, workbuddy, windsurf")


# ============================================================
# Environment detection
# ============================================================

def detect_python_path() -> str:
    """Detect the absolute path of the current Python interpreter."""
    return sys.executable


def detect_sheaf_entry() -> str:
    """Return the CLI entry point command.

    If sheaf is installed as a console script, return "sheaf".
    Otherwise fall back to ``python -m sheaf_ai.cli``.
    """
    if shutil.which("sheaf"):
        return "sheaf"
    return f"{detect_python_path()} -m sheaf_ai.cli"


def detect_all_platforms() -> list[str]:
    """Detect all Agent platforms present on this machine.

    Returns a list of platform IDs: cursor, claude, workbuddy, windsurf.
    Checks both CWD project markers and global config files.
    """
    found = []
    cwd = Path.cwd()
    home = _home()

    # Cursor: .cursor/ dir or .cursorrules in CWD
    if (cwd / ".cursor").exists() or (cwd / ".cursorrules").exists():
        found.append("cursor")

    # Claude Code: ~/.claude.json exists
    if (home / ".claude.json").exists():
        found.append("claude")

    # WorkBuddy: ~/.workbuddy/ dir
    if (home / ".workbuddy").exists():
        found.append("workbuddy")

    # Windsurf: .windsurf/ dir or .windsurfrules in CWD
    if (cwd / ".windsurf").exists() or (cwd / ".windsurfrules").exists():
        found.append("windsurf")

    return found


# ============================================================
# MCP config templates
# ============================================================

def build_mcp_config(data_dir: Optional[str] = None) -> dict:
    """Build a Sheaf MCP server config block.

    Returns a dict suitable for nesting under ``mcpServers.sheaf``.
    """
    python_path = detect_python_path()

    config: dict = {
        "command": python_path,
        "args": ["-m", "sheaf_ai.mcp_server"],
    }

    # Pass data dir via env if custom
    env: dict = {}
    if data_dir:
        env["SHEAF_DATA_DIR"] = str(Path(data_dir).resolve())

    # Preserve API key if available — check all common providers
    api_key = (
        os.environ.get("SILICONFLOW_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    if api_key:
        env["OPENAI_API_KEY"] = api_key

    if env:
        config["env"] = env

    return config


def build_full_config(target: str, data_dir: Optional[str] = None) -> dict:
    """Build a complete config dict with the sheaf MCP entry.

    For *claude*, the config is the top-level ``.claude.json`` where
    ``mcpServers`` is a nested key.  For other targets the file is
    an MCP-only JSON (``{ "mcpServers": { ... } }``).
    """
    sheaf_block = build_mcp_config(data_dir=data_dir)

    if target == "claude":
        return {"mcpServers": {"sheaf": sheaf_block}}
    else:
        return {"mcpServers": {"sheaf": sheaf_block}}


# ============================================================
# Config file operations
# ============================================================

def read_existing_config(path: Path) -> dict:
    """Read and parse an existing config file. Returns {} on any failure."""
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        return json.loads(text)
    except (json.JSONDecodeError, OSError):
        return {}


def write_config(path: Path, config: dict) -> None:
    """Write *config* as pretty-printed JSON to *path*, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def merge_config(existing: dict, sheaf_entry: dict) -> dict:
    """Merge the sheaf MCP entry into an existing config dict.

    - Creates ``mcpServers`` key if absent.
    - Overwrites the ``sheaf`` entry if present.
    - Preserves all other keys and MCP servers.
    """
    merged = dict(existing)
    servers = dict(merged.get("mcpServers", {}))
    servers["sheaf"] = sheaf_entry
    merged["mcpServers"] = servers
    return merged


# ============================================================
# Public API
# ============================================================

def setup_target(
    target: str,
    data_dir: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Run the setup for a specific target platform.

    Returns a result dict with keys:
        ok, target, config_path, created, sheaf_entry, next_steps

    The function is side-effect-free when *dry_run* is True.
    """
    config_path = get_config_path(target)
    sheaf_entry = build_mcp_config(data_dir=data_dir)

    existing = read_existing_config(config_path)
    merged = merge_config(existing, sheaf_entry)

    if not dry_run:
        write_config(config_path, merged)

    return {
        "ok": True,
        "target": target,
        "config_path": str(config_path),
        "created": not existing,
        "sheaf_entry": sheaf_entry,
        "merged_config": merged,
        "next_steps": _next_steps(target, config_path),
    }


def _next_steps(target: str, config_path: Path) -> list[str]:
    """Return human-readable next-step instructions for *target*."""
    if target == "cursor":
        return [
            "1. Restart Cursor (or reload the window).",
            "2. Open any chat → the Sheaf MCP tools should auto-appear.",
            f"3. Config written to: {config_path}",
        ]
    elif target == "claude":
        return [
            "1. Restart Claude Code.",
            "2. Run: claude mcp list  (should show 'sheaf').",
            f"3. Config written to: {config_path}",
        ]
    elif target == "workbuddy":
        return [
            "1. Open WorkBuddy → Settings → Custom Connectors.",
            "2. Click 'Trust' on the new 'sheaf' MCP server.",
            "3. Start a new conversation — Sheaf tools will be available.",
            f"4. Config written to: {config_path}",
        ]
    elif target == "windsurf":
        return [
            "1. Restart Windsurf.",
            "2. The Sheaf MCP tools should appear in the agent panel.",
            f"3. Config written to: {config_path}",
        ]
    return []


# ============================================================
# CLI helpers
# ============================================================

def print_setup_result(result: dict) -> None:
    """Pretty-print the setup result for CLI output."""
    target = result["target"]
    path = result["config_path"]
    created = result["created"]

    if created:
        print(f"✓ Created new MCP config for {target}: {path}")
    else:
        print(f"✓ Updated existing MCP config for {target}: {path}")

    entry = result["sheaf_entry"]
    print(f"  Command: {entry.get('command')} {' '.join(entry.get('args', []))}")
    if entry.get("env"):
        print(f"  Env vars: {', '.join(entry['env'].keys())}")

    print()
    steps = result.get("next_steps", [])
    if steps:
        print("Next steps:")
        for step in steps:
            print(f"  {step}")
