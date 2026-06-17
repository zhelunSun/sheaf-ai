"""
Sheaf Setup — auto-configure MCP server for Agent platforms.

Generates MCP configuration entries and merges them into the target
platform's config file, reducing the deploy process to a single command:

    sheaf setup --target cursor
    sheaf setup --target workbuddy
    sheaf setup --target claude
    sheaf setup --target codex

For claude & codex it also deploys a bundled skill / AGENTS note so the agent
is guided to use the `sheaf` CLI for the non-core operations.

Supports: cursor, claude, codex, workbuddy, windsurf.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

# TOML support — Codex MCP config lives in ~/.codex/config.toml. tomllib is
# stdlib in 3.11+; tomli is the 3.10 backport. tomli_w writes TOML for merges.
try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - exercised only on 3.10
    import tomli as tomllib  # type: ignore[no-redef]
import tomli_w


# ============================================================
# Platform config locations
# ============================================================

def _home() -> Path:
    """Return the user home directory."""
    return Path.home()


def get_config_path(target: str) -> Path:
    """Return the expected MCP config file path for *target* platform.

    Supported targets: cursor, claude, codex, workbuddy, windsurf.
    """
    home = _home()
    cwd = Path.cwd()

    if target == "cursor":
        return cwd / ".cursor" / "mcp.json"
    elif target == "claude":
        # Claude Code stores MCP config in ~/.claude.json (top-level key "mcpServers")
        return home / ".claude.json"
    elif target == "codex":
        # OpenAI Codex CLI stores MCP config in ~/.codex/config.toml ([mcp_servers.*])
        return home / ".codex" / "config.toml"
    elif target == "workbuddy":
        return home / ".workbuddy" / "mcp.json"
    elif target == "windsurf":
        return cwd / ".windsurf" / "mcp.json"
    else:
        raise ValueError(
            f"Unknown target: {target!r}. Supported: cursor, claude, codex, workbuddy, windsurf"
        )


def get_skill_path(target: str) -> Optional[Path]:
    """Return the destination path for the bundled skill / AGENTS note, or None.

    claude → ~/.claude/skills/sheaf-guide.md  (Claude Code native Skills)
    codex  → ~/.codex/AGENTS.sheaf.md         (Codex AGENTS.md convention)
    others → None (no first-class skill mechanism)
    """
    home = _home()
    if target == "claude":
        return home / ".claude" / "skills" / "sheaf-guide.md"
    elif target == "codex":
        return home / ".codex" / "AGENTS.sheaf.md"
    return None


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


def _resolve_mcp_command() -> tuple[str, list[str]]:
    """Resolve the MCP server launch command.

    Prefer the ``sheaf-mcp`` console script — it is path-independent: it keeps
    working after the venv used at install time is removed, as long as
    sheaf-ai is installed somewhere on PATH. Fall back to
    ``<python> -m sheaf_ai.mcp_server`` when the script is not on PATH.
    """
    if shutil.which("sheaf-mcp"):
        return ("sheaf-mcp", [])
    return (detect_python_path(), ["-m", "sheaf_ai.mcp_server"])


def _resolve_active_provider() -> tuple[str, str, str]:
    """Resolve ``(provider_id, api_key, base_url)`` for the MCP env block.

    The MCP server is a *subprocess*, so it inherits only what we inject — it
    does not see the user's shell config. Previously build_mcp_config injected
    whatever key it found under the hardcoded name ``OPENAI_API_KEY`` without a
    ``DEFAULT_PROVIDER``, so a DeepSeek/SiliconFlow user's MCP calls silently
    routed to OpenAI and failed (audit P0).

    Resolution order:
      1. ``settings.resolve_provider(None)`` — honors ``DEFAULT_PROVIDER`` env
         and ``~/.sheaf/config.json`` (the ``sheaf config setup`` path).
      2. Reverse-lookup: whichever provider's ``api_key_env`` is set in the
         environment (e.g. ``DEEPSEEK_API_KEY`` → ``deepseek``), so a bare env
         key without ``DEFAULT_PROVIDER`` still routes correctly.
      3. ``("", "", "")`` — nothing resolvable; setup writes no key env and
         ``sheaf doctor`` flags the gap. Strictly better than the old behavior
         of injecting a DeepSeek key under the ``OPENAI_API_KEY`` name.
    """
    try:
        from sheaf_ai.settings import resolve_provider
        return resolve_provider(None)
    except (ValueError, Exception):
        pass
    # Reverse-lookup from provider env vars (bare key, no DEFAULT_PROVIDER).
    try:
        from sheaf_ai.providers import PROVIDERS
        for pid, cfg in PROVIDERS.items():
            if pid == "custom":
                continue
            key = os.environ.get(cfg.get("api_key_env", ""), "").strip()
            if key:
                return pid, key, cfg.get("base_url", "")
    except Exception:  # pragma: no cover - defensive
        pass
    return "", "", ""


def detect_all_platforms() -> list[str]:
    """Detect all Agent platforms present on this machine.

    Returns a list of platform IDs: cursor, claude, codex, workbuddy, windsurf.
    Checks both CWD project markers and global config files.
    """
    found = []
    cwd = Path.cwd()
    home = _home()

    # Cursor: .cursor/ dir or .cursorrules in CWD
    if (cwd / ".cursor").exists() or (cwd / ".cursorrules").exists():
        found.append("cursor")

    # Claude Code: ~/.claude.json exists or `claude` on PATH
    if (home / ".claude.json").exists() or shutil.which("claude"):
        found.append("claude")

    # Codex CLI: ~/.codex/ dir or `codex` on PATH
    if (home / ".codex").exists() or shutil.which("codex"):
        found.append("codex")

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

    Returns a dict suitable for nesting under ``mcpServers.sheaf`` (JSON
    targets) or ``mcp_servers.sheaf`` (Codex TOML).
    """
    command, args = _resolve_mcp_command()

    config: dict = {
        "command": command,
        "args": args,
    }

    # Pass data dir via env if custom
    env: dict = {}
    if data_dir:
        env["SHEAF_DATA_DIR"] = str(Path(data_dir).resolve())

    # Inject a self-describing provider env block so the MCP subprocess uses the
    # SAME provider/key/base_url as the CLI — not a hardcoded OPENAI_API_KEY that
    # misroutes non-OpenAI users (audit P0). DEFAULT_PROVIDER + SHEAF_API_KEY is
    # the universal set; OPENAI_API_KEY is kept for backward compat with older
    # code paths that read it directly.
    provider_id, api_key, base_url = _resolve_active_provider()
    if api_key:
        env["DEFAULT_PROVIDER"] = provider_id
        env["SHEAF_API_KEY"] = api_key
        env["OPENAI_API_KEY"] = api_key
        if base_url:
            env["OPENAI_BASE_URL"] = base_url

    if env:
        config["env"] = env

    return config


def build_full_config(target: str, data_dir: Optional[str] = None) -> dict:
    """Build a complete config dict with the sheaf MCP entry.

    For *claude*, the config is the top-level ``.claude.json`` where
    ``mcpServers`` is a nested key.  For other targets the file is
    an MCP-only JSON (``{ "mcpServers": { ... } }``).  Codex is TOML and is
    not handled here — see ``setup_target``.
    """
    sheaf_block = build_mcp_config(data_dir=data_dir)

    if target == "codex":
        raise ValueError("Codex uses TOML — use setup_target(), not build_full_config()")

    return {"mcpServers": {"sheaf": sheaf_block}}


# ============================================================
# JSON config file operations
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
# TOML config file operations (Codex)
# ============================================================

def read_existing_config_toml(path: Path) -> dict:
    """Read and parse an existing TOML config file. Returns {} on any failure."""
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        return tomllib.loads(text)
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def merge_toml_mcp(parsed: dict, sheaf_entry: dict) -> dict:
    """Merge the sheaf MCP entry into a parsed Codex config dict.

    - Creates the ``mcp_servers`` table if absent.
    - Overwrites the ``sheaf`` entry if present.
    - Preserves all other keys ([model], [profiles], other mcp_servers.*, …).
    """
    merged = dict(parsed)
    servers = dict(merged.get("mcp_servers", {}))
    servers["sheaf"] = sheaf_entry
    merged["mcp_servers"] = servers
    return merged


def write_config_toml(path: Path, parsed: dict) -> None:
    """Write *parsed* as TOML to *path*, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(parsed), encoding="utf-8")


# ============================================================
# Skill / AGENTS note deployment
# ============================================================

def _skills_dir() -> Path:
    """Return the directory bundled skill markdown files live in."""
    return Path(__file__).resolve().parent / "skills"


def deploy_skill(target: str) -> Optional[dict]:
    """Deploy the bundled skill / AGENTS note for *target*.

    claude → copies sheaf-guide.md to ~/.claude/skills/sheaf-guide.md
    codex  → copies AGENTS.sheaf.md to ~/.codex/AGENTS.sheaf.md
    others → returns None (no first-class skill mechanism).

    Idempotent — overwrites with the bundled version. Returns a result dict on
    deployment (or attempted), None when there is nothing to deploy.
    """
    dest = get_skill_path(target)
    if dest is None:
        return None

    src_name = "sheaf-guide.md" if target == "claude" else "AGENTS.sheaf.md"
    src = _skills_dir() / src_name
    if not src.exists():
        return {"ok": False, "target": target, "dest": str(dest), "error": f"bundled skill missing: {src}"}

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return {"ok": True, "target": target, "dest": str(dest)}


# ============================================================
# Backup
# ============================================================

def _backup_if_exists(path: Path) -> Optional[Path]:
    """Copy *path* to ``<path>.sheaf-bak`` if it exists. Defense against bad merges."""
    if path.exists():
        bak = path.with_name(path.name + ".sheaf-bak")
        shutil.copy2(path, bak)
        return bak
    return None


# ============================================================
# Public API
# ============================================================

def setup_target(
    target: str,
    data_dir: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Run the setup for a specific target platform.

    JSON targets (cursor/claude/workbuddy/windsurf): merge into the platform's
    ``mcpServers`` JSON. Codex: merge into ``~/.codex/config.toml`` (TOML,
    key ``mcp_servers``). For claude & codex it also deploys the bundled skill
    / AGENTS note. A ``<file>.sheaf-bak`` backup is written before overwriting
    an existing config.

    Returns a result dict with keys:
        ok, target, config_path, created, sheaf_entry, merged_config, skill, next_steps

    The function is side-effect-free when *dry_run* is True.
    """
    config_path = get_config_path(target)
    sheaf_entry = build_mcp_config(data_dir=data_dir)

    if target == "codex":
        existing = read_existing_config_toml(config_path)
        merged = merge_toml_mcp(existing, sheaf_entry)
        if not dry_run:
            _backup_if_exists(config_path)
            write_config_toml(config_path, merged)
    else:
        existing = read_existing_config(config_path)
        merged = merge_config(existing, sheaf_entry)
        if not dry_run:
            _backup_if_exists(config_path)
            write_config(config_path, merged)

    # Deploy skill / AGENTS note (claude & codex only). Skipped on dry_run.
    skill_result = None if dry_run else deploy_skill(target)

    return {
        "ok": True,
        "target": target,
        "config_path": str(config_path),
        "created": not existing,
        "sheaf_entry": sheaf_entry,
        "merged_config": merged,
        "skill": skill_result,
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
        skill = get_skill_path("claude")
        return [
            "1. Restart Claude Code.",
            "2. Run: claude mcp list  (should show 'sheaf').",
            f"3. Agent skill deployed to: {skill}",
            f"4. Config written to: {config_path}",
        ]
    elif target == "codex":
        skill = get_skill_path("codex")
        return [
            "1. Restart Codex CLI (or start a new session).",
            "2. The Sheaf MCP tools should auto-load.",
            f"3. Agent guide deployed to: {skill}",
            f"4. MCP config written to: {config_path}",
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

    skill = result.get("skill")
    if skill:
        if skill.get("ok"):
            print(f"  Skill:   deployed → {skill['dest']}")
        else:
            print(f"  Skill:   {skill.get('error', 'deploy failed')}")

    print()
    steps = result.get("next_steps", [])
    if steps:
        print("Next steps:")
        for step in steps:
            print(f"  {step}")
