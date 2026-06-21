"""Contract test: the agent-facing skill docs only reference real commands/tools.

The skill (sheaf-guide.md / AGENTS.sheaf.md) is the agent's primary instruction
set. If it tells an agent to run ``sheaf correct ...`` and no such command
exists, the agent fails at runtime. This test parses both skill files and
asserts every referenced CLI command, MCP tool, and flag resolves against the
real CLI parser and MCP tool registry — the deterministic guardrail for the
scenario-layer (agent-behavior) tests that come later.

Zero network, zero API, runs in CI. See the v0.7 plan for the drift this caught.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from sheaf_ai.cli import build_parser
from sheaf_ai.setup import _skills_dir
from sheaf_ai.mcp.server import ALL_TOOLS, CORE_TOOL_NAMES

SKILL_FILES = ("sheaf-guide.md", "AGENTS.sheaf.md")


# ---------------------------------------------------------------------------
# Introspection helpers.
#
# We check existence via the subparsers action's registered options rather than
# by parsing, so required positionals (e.g. ``get <id>``) don't make the flag
# check spuriously fail. ``_actions`` / ``option_strings`` are stable argparse
# internals used widely in test suites.
# ---------------------------------------------------------------------------

def _subparser_choices() -> dict:
    """Return ``{command: sub-ArgumentParser}`` from the sheaf CLI parser."""
    parser = build_parser()
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if (isinstance(choices, dict) and choices
                and all(hasattr(v, "_actions") for v in choices.values())):
            return choices
    return {}


_SUBPARSERS = _subparser_choices()


def _cmd_exists(cmd: str) -> bool:
    return cmd in _SUBPARSERS


def _flag_accepted(cmd: str, flag: str) -> bool:
    """True iff the subcommand for *cmd* registers *flag* (e.g. ``--json``)."""
    sub = _SUBPARSERS.get(cmd)
    if sub is None:
        return False
    return any(flag in getattr(act, "option_strings", ()) for act in sub._actions)


def _flag_value_accepted(cmd: str, flag: str, value: str) -> bool:
    """True iff ``sheaf <cmd> <flag> <value>`` parses (choice regressions)."""
    try:
        build_parser().parse_args([cmd, flag, value])
        return True
    except SystemExit:
        return False


# ---------------------------------------------------------------------------
# Token extraction.
# ---------------------------------------------------------------------------

_CMD_RE = re.compile(r"\bsheaf (\w+)")        # sheaf collect
_TOOL_RE = re.compile(r"\bsheaf_(\w+)\b")     # sheaf_collect
_FLAG_RE = re.compile(r"(?<![\w-])(--\w[\w-]*)")  # --json / --target


def _code_text(path: Path) -> str:
    """Concatenate fenced blocks + inline code spans from a markdown file.

    Commands/tools in the skill are always backtick-delimited, so scanning only
    code-bearing text avoids prose false positives ("the sheaf CLI").
    """
    text = path.read_text(encoding="utf-8")
    parts: list[str] = []
    parts.extend(re.findall(r"```[^\n]*\n(.*?)```", text, flags=re.DOTALL))
    no_fences = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    parts.extend(re.findall(r"`([^`\n]*)`", no_fences))
    return "\n".join(parts)


def _code_spans_from_line(line: str) -> list[str]:
    """Inline code spans within a single markdown line."""
    return re.findall(r"`([^`\n]*)`", line)


@pytest.fixture(scope="module")
def skill_paths():
    d = _skills_dir()
    return [d / name for name in SKILL_FILES]


@pytest.fixture(scope="module")
def code(skill_paths):
    """name -> concatenated code-span text (for command/tool existence checks)."""
    return {p.name: _code_text(p) for p in skill_paths}


@pytest.fixture(scope="module")
def raw_text(skill_paths):
    """name -> raw markdown (for per-line flag association)."""
    return {p.name: p.read_text(encoding="utf-8") for p in skill_paths}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_skill_files_exist(skill_paths):
    """Both skill files ship and are non-empty (deploy-regression guard)."""
    for p in skill_paths:
        assert p.exists(), f"bundled skill missing: {p}"
        assert p.stat().st_size > 0, f"empty skill file: {p}"


def test_cli_commands_referenced_are_real(code):
    """A: every `sheaf <cmd>` in the skill resolves to a real CLI command."""
    missing: dict[str, list[str]] = {}
    for name, text in code.items():
        for cmd in sorted(set(_CMD_RE.findall(text))):
            if not _cmd_exists(cmd):
                missing.setdefault(name, []).append(cmd)
    assert not missing, f"skill references unknown CLI commands: {missing}"


def test_mcp_tools_referenced_are_real(code):
    """B: every `sheaf_<tool>` in the skill is a registered MCP tool."""
    real = {t["name"] for t in ALL_TOOLS}
    missing: dict[str, list[str]] = {}
    for name, text in code.items():
        for suffix in sorted(set(_TOOL_RE.findall(text))):
            tool = "sheaf_" + suffix
            if tool not in real:
                missing.setdefault(name, []).append(tool)
    assert not missing, f"skill references unknown MCP tools: {missing}"


def test_flags_referenced_are_accepted(raw_text):
    """C: every `--flag` shown on the same line as a `sheaf <cmd>` is accepted.

    Flags may sit in separate code spans from the command (e.g. a table row
    ``| list | `sheaf list` (`--filter`, `--category`) |``), so we associate at
    the markdown-line level: the command comes from code spans on the line, the
    flags from anywhere on the line.
    """
    bad: set[str] = set()
    for name, text in raw_text.items():
        for line in text.splitlines():
            spans = _code_spans_from_line(line)
            cmds: list[str] = []
            for span in spans:
                cmds.extend(_CMD_RE.findall(span))
            flags = _FLAG_RE.findall(line)
            if not cmds or not flags:
                continue
            cmd = cmds[0]  # skill documents one command per row
            if not _cmd_exists(cmd):
                continue  # already reported by the command-existence test
            for flag in flags:
                if not _flag_accepted(cmd, flag):
                    bad.add(f"{name}: `sheaf {cmd} -> {flag}` not accepted")
    assert not bad, "skill documents flags the CLI rejects:\n  " + "\n  ".join(sorted(bad))


def test_core_mcp_surface_documented(code):
    """D: the skill teaches all 4 default-surface tools."""
    blob = "\n".join(code.values())
    missing = [t for t in CORE_TOOL_NAMES if t not in blob]
    assert not missing, f"skill omits core MCP tools: {missing}"


def test_setup_targets_parse(code):
    """E: every `--target` value the skill advertises is a valid setup choice."""
    targets: set[str] = set()
    for text in code.values():
        for m in re.finditer(r"--target\s+([A-Za-z|]+)", text):
            for t in m.group(1).split("|"):
                t = t.strip()
                if t:
                    targets.add(t)
    assert targets, "no --target values found in skill to test"
    bad = [t for t in sorted(targets) if not _flag_value_accepted("setup", "--target", t)]
    assert not bad, f"skill advertises invalid `setup --target` values: {bad}"


def test_skill_resource_uris_resolve(code):
    """F: every `sheaf://` URI in the skill is a real resource or the {id} template."""
    from sheaf_ai.mcp.resources import RESOURCES, RESOURCE_TEMPLATES
    static_uris = {r["uri"] for r in RESOURCES}
    template_literals = {t["uriTemplate"] for t in RESOURCE_TEMPLATES}
    entry_id_pat = re.compile(r"^sheaf://entries/[A-Za-z0-9_-]+(/raw)?$")
    uri_re = re.compile(r"sheaf://[A-Za-z0-9_{}/.-]+")

    bad: list[str] = []
    seen = False
    for name, text in code.items():
        for uri in uri_re.findall(text):
            seen = True
            if uri in static_uris or uri in template_literals:
                continue
            if entry_id_pat.match(uri):  # concrete id example → valid template instance
                continue
            bad.append(f"{name}: {uri}")
    assert seen, "skill documents no sheaf:// resource URIs (browse capability missing)"
    assert not bad, f"skill references unknown resource URIs: {bad}"
