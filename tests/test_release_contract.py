"""Release contract test — the docs and version stay consistent with code.

``test_skill_contract.py`` guards the agent-facing skill (skill <-> CLI/MCP).
This test guards the *human-facing release surface* that historically drifted
and needed manual re-sync (see commit history: "sync README test counts",
"fix README/README_CN test count drift"). Every check here is deterministic —
zero network, zero API, runs in CI.

Guarded contracts:
  1. CHANGELOG head version == pyproject.toml version.
  2. README's three test-count mentions agree (badge / dev section / alpha line).
  3. CLAUDE.md core MCP tools == sheaf_ai.mcp.server.CORE_TOOL_NAMES.
  4. CLAUDE.md demoted MCP tools == ALL_TOOLS - CORE_TOOL_NAMES.
  5. README "4 core tools" sentence == CORE_TOOL_NAMES.
  6. Every non-"custom" provider in providers.py is advertised in README
     (both its display name and its API-key env var).
"""
from __future__ import annotations

import re
from pathlib import Path

from sheaf_ai.mcp.server import ALL_TOOLS, CORE_TOOL_NAMES
from sheaf_ai.providers import PROVIDERS

REPO_ROOT = Path(__file__).resolve().parents[1]

README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
CHANGELOG = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
CLAUDE = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
PYPROJECT = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _changelog_head_version() -> str:
    """Return the version of the topmost CHANGELOG entry, e.g. "0.7.0"."""
    match = re.search(r"^##\s*\[(\d+\.\d+\.\d+)\]", CHANGELOG, flags=re.MULTILINE)
    assert match, "CHANGELOG.md has no `## [x.y.z]` entry"
    return match.group(1)


def _pyproject_version() -> str:
    """Return the ``[project] version`` field from pyproject.toml."""
    match = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT, flags=re.MULTILINE)
    assert match, "pyproject.toml has no `version = \"...\"` under [project]"
    return match.group(1)


def _backtick_sheaf_tokens(text: str) -> list[str]:
    """All backtick-quoted ``sheaf_*`` tool tokens in a region of text."""
    return re.findall(r"`(sheaf_[a-z_]+)`", text)


def _section(text: str, start_marker: str, end_marker: str | None) -> str:
    """Return the substring after ``start_marker`` up to ``end_marker``."""
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start) if end_marker else len(text)
    return text[start:end]


# ---------------------------------------------------------------------------
# 1. Version alignment.
# ---------------------------------------------------------------------------

def test_changelog_version_matches_pyproject():
    changelog_v = _changelog_head_version()
    pyproject_v = _pyproject_version()
    assert changelog_v == pyproject_v, (
        f"CHANGELOG head version {changelog_v!r} != pyproject.toml version "
        f"{pyproject_v!r} — update both before release."
    )


# ---------------------------------------------------------------------------
# 2. README test-count internal consistency.
# ---------------------------------------------------------------------------

def test_readme_test_counts_agree():
    badge = re.search(r"tests-(\d+)%20pass", README)
    dev_line = re.search(r"(\d+) passed, (\d+) skipped", README)
    alpha_line = re.search(r"(\d+) passing tests", README)

    assert badge, "README badge `tests-NNN%20pass` not found"
    assert dev_line, "README dev section `NNN passed, M skipped` not found"
    assert alpha_line, "README alpha line `NNN passing tests` not found"

    counts = {
        "badge": int(badge.group(1)),
        "dev section": int(dev_line.group(1)),
        "alpha line": int(alpha_line.group(1)),
    }
    distinct = set(counts.values())
    assert len(distinct) == 1, (
        f"README test counts disagree across locations: {counts} — they must be "
        f"updated in lockstep."
    )


# ---------------------------------------------------------------------------
# 3 & 4. CLAUDE.md MCP tool table == registry.
# ---------------------------------------------------------------------------

def test_claude_core_tools_match_registry():
    region = _section(CLAUDE, "**Core (4", "**Demoted (7")
    claude_core = set(_backtick_sheaf_tokens(region))
    assert claude_core == set(CORE_TOOL_NAMES), (
        f"CLAUDE.md core tools {sorted(claude_core)} != registry "
        f"{sorted(CORE_TOOL_NAMES)}."
    )


def test_claude_demoted_tools_match_registry():
    region = _section(CLAUDE, "**Demoted (7", "**Deprecated (3")
    claude_demoted = set(_backtick_sheaf_tokens(region))
    all_names = {t["name"] for t in ALL_TOOLS}
    expected = all_names - set(CORE_TOOL_NAMES)
    assert claude_demoted == expected, (
        f"CLAUDE.md demoted tools {sorted(claude_demoted)} != registry "
        f"{sorted(expected)}."
    )


# ---------------------------------------------------------------------------
# 5. README "4 core tools" sentence == registry.
# ---------------------------------------------------------------------------

def test_readme_core_tools_match_registry():
    region = _section(README, "exposes **4 core tools**", "covering ~90%")
    readme_core = set(_backtick_sheaf_tokens(region))
    assert readme_core == set(CORE_TOOL_NAMES), (
        f"README core-tools sentence {sorted(readme_core)} != registry "
        f"{sorted(CORE_TOOL_NAMES)}."
    )


# ---------------------------------------------------------------------------
# 6. Providers advertised in README.
# ---------------------------------------------------------------------------

def test_providers_advertised_in_readme():
    for key, prov in PROVIDERS.items():
        if key == "custom":
            # "Custom" is the escape hatch, intentionally not in the README table.
            continue
        assert prov["name"] in README, (
            f"Provider {prov['name']!r} (key {key!r}) is not mentioned in README.md"
        )
        assert prov["api_key_env"] in README, (
            f"Provider {prov['name']!r} env var {prov['api_key_env']!r} missing "
            f"from README.md Configuration table"
        )


# ---------------------------------------------------------------------------
# Sanity: the registry itself is the shape the rest of the pipeline assumes.
# ---------------------------------------------------------------------------

def test_registry_shape():
    assert len(ALL_TOOLS) == len({t["name"] for t in ALL_TOOLS}), "duplicate tool names"
    assert CORE_TOOL_NAMES <= {t["name"] for t in ALL_TOOLS}, (
        "every core tool must exist in ALL_TOOLS"
    )
