#!/usr/bin/env python3
"""Sheaf v0.7.0 Pre-Release Gate — full pipeline smoke test + risk scan.

Part A — Functional Smoke (9 steps):
  1. Version check
  2. sheaf init --auto
  3. setup idempotency
  4. sheaf doctor
  5. MCP tools/list (4 core default)
  6. collect + search pipeline
  7. sheaf crystallize
  8. MCP Resources browse (resources/list, resources/read)
  9. SHEAF_MCP_TOOLS=all full surface

Part B — Pre-Release Risk Scan (4 steps):
  10. README consistency (test counts, version refs, links)
  11. Version management (pyproject.toml vs git tag)
  12. Issue history (open count, recently closed, milestone)
  13. Git hygiene (uncommitted changes, branch, tracked leaks)

Exit code 0 = ready to launch. Non-zero = gate criterion failed.

Usage:
    python scripts/smoke-pre-release.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Force UTF-8 stdout — Windows consoles default to GBK.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], env: dict = None, cwd=None,
         timeout: int | None = None) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           env=env or os.environ, encoding="utf-8",
                           cwd=cwd or str(REPO_ROOT), timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"TIMEOUT after {timeout}s: {' '.join(cmd[:4])}..."


def _extract_trailing_json(text: str) -> dict | None:
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    candidate = text[start:]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        lines = candidate.splitlines()
        for end in range(len(lines), 0, -1):
            try:
                return json.loads("\n".join(lines[:end]))
            except json.JSONDecodeError:
                continue
    return None


def _command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# ---------------------------------------------------------------------------
# Part A — Functional Smoke (steps 1–9)
# ---------------------------------------------------------------------------

def run_functional_smoke(py: str, env: dict, failures: list, api_key: str) -> None:
    REQ_KEY_SKIPPED = not api_key

    def check(label: str, cond: bool, detail: str = "") -> None:
        mark = "\u2705" if cond else "\u274c"
        print(f"  {mark} {label}{(' — ' + detail) if detail and cond else ''}")
        if not cond:
            failures.append(f"{label}{(' — ' + detail) if detail else ''}")

    def check_warn(label: str, cond: bool, detail: str = "") -> None:
        """Non-blocking warning — prints but doesn't add to failures."""
        mark = "\u26a0\ufe0f" if not cond else "\u2705"
        print(f"  {mark} {label}{(' — ' + detail) if not cond and detail else ''}")

    def check_skipped(label: str, reason: str) -> None:
        print(f"  \u23ed\ufe0f  {label} — SKIPPED ({reason})")

    # --- 1. Version check --------------------------------------------------
    print("\n[1/9] Version check")
    rc, out, err = _run([py, "-m", "sheaf_ai.cli", "--version"], env)
    check("sheaf --version exits 0", rc == 0)
    check("version is v0.7.0", "0.7.0" in out, out.strip()[:80])

    # --- 2. init --auto ----------------------------------------------------
    print("\n[2/9] sheaf init --auto --json")
    rc, out, err = _run([py, "-m", "sheaf_ai.cli", "init", "--auto", "--json"], env)
    check("init --auto exits 0", rc == 0, f"rc={rc}")
    deploy = None
    if rc == 0:
        deploy = _extract_trailing_json(out)
        if deploy:
            check("init reports data_dir", bool(deploy.get("data_dir")))
            check("init status ready", deploy.get("status") == "ready")
        else:
            check("init emits deploy JSON", False, "no JSON found")

    # --- 3. setup idempotency ----------------------------------------------
    print("\n[3/9] sheaf setup idempotency")
    from sheaf_ai.setup import detect_all_platforms, setup_target, get_skill_path
    os.environ["HOME"] = env["HOME"]
    os.environ["USERPROFILE"] = env["USERPROFILE"]
    platforms = detect_all_platforms() or ["claude", "codex"]
    for plat in platforms:
        try:
            r1 = setup_target(plat, dry_run=False)
            r2 = setup_target(plat, dry_run=False)
            check(f"setup {plat} idempotent", r2.get("created") is False)
            if get_skill_path(plat) is not None:
                skill_ok = (r2.get("skill") or {}).get("ok") is True
                check(f"setup {plat} deploys skill", skill_ok)
        except Exception as e:
            check(f"setup {plat}", False, str(e))

    # --- 4. doctor -------------------------------------------------------
    print("\n[4/9] sheaf doctor --json")
    rc, out, err = _run([py, "-m", "sheaf_ai.cli", "doctor", "--json"], env)
    check("doctor exits 0", rc == 0, f"rc={rc}")
    if rc == 0:
        doc = _extract_trailing_json(out)
        if doc:
            check("doctor reports checks", isinstance(doc.get("checks"), list))
        else:
            check("doctor emits JSON", False)

    # --- 5. MCP tools/list default = 4 core -------------------------------
    print("\n[5/9] MCP tools/list — default 4 core tools")
    from sheaf_ai.mcp.server import handle_request
    resp = json.loads(handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    names = {t["name"] for t in resp["result"]["tools"]}
    expected_core = {"sheaf_collect", "sheaf_search", "sheaf_crystallize", "sheaf_get_card"}
    check("default tools/list = 4 core", names == expected_core,
          f"got {sorted(names)}")

    # --- 6. collect + search pipeline --------------------------------------
    print("\n[6/9] collect + search pipeline")
    if REQ_KEY_SKIPPED:
        rc, out, err = _run([py, "-m", "sheaf_ai.cli", "collect",
                             "https://github.com/zhelunSun/sheaf-ai",
                             "--json"], env, timeout=120)
        if rc == 0:
            entry = _extract_trailing_json(out)
            if entry:
                check("collect repo returns entry", bool(entry.get("id")),
                      entry.get("title", "")[:60])
            else:
                check("collect emits JSON", False)
        else:
            check_skipped("collect pipeline", f"no API key; rc={rc}")
    else:
        rc, out, err = _run([py, "-m", "sheaf_ai.cli", "collect",
                             "https://github.com/zhelunSun/sheaf-ai",
                             "--json"], env, timeout=120)
        check("collect repo exits 0", rc == 0, f"rc={rc}")
        if rc == 0:
            entry = _extract_trailing_json(out)
            if entry:
                check("collect returns entry ID", bool(entry.get("id")))
            else:
                check("collect emits JSON", False)

        rc2, out2, _ = _run([py, "-m", "sheaf_ai.cli", "collect",
                             "--text", "Sheaf uses numpy cosine similarity for embeddings",
                             "--json"], env)
        check("collect --text exits 0", rc2 == 0, f"rc={rc2}")

        rc3, out3, _ = _run([py, "-m", "sheaf_ai.cli", "search", "embeddings", "--json"], env, timeout=60)
        check("search exits 0", rc3 == 0, f"rc={rc3}")
        if rc3 == 0:
            result = _extract_trailing_json(out3)
            if result and isinstance(result, list):
                check("search returns results", len(result) > 0,
                      f"{len(result)} results")

    # --- 7. crystallize ----------------------------------------------------
    print("\n[7/9] sheaf crystallize")
    if REQ_KEY_SKIPPED:
        check_skipped("crystallize", "no API key available")
    else:
        rc, out, err = _run([py, "-m", "sheaf_ai.cli", "crystallize", "knowledge management",
                             "--format", "json"], env, timeout=120)
        check("crystallize exits 0", rc == 0, f"rc={rc}")
        if rc == 0:
            cards = _extract_trailing_json(out)
            if cards:
                check("crystallize returns cards", isinstance(cards, list))
                if isinstance(cards, list) and len(cards) > 0:
                    card = cards[0]
                    check("card has title", bool(card.get("title")))
                    check("card has confidence", card.get("confidence") is not None)
            else:
                check("crystallize emits JSON", False)

    # --- 8. MCP Resources browse -------------------------------------------
    print("\n[8/9] MCP Resources browse")
    resp = json.loads(handle_request({"jsonrpc": "2.0", "id": 2, "method": "resources/list"}))
    resources = resp.get("result", {}).get("resources", [])
    uris = [r["uri"] for r in resources]
    check("resources/list returns URIs", len(uris) > 0, f"{len(uris)} resources")
    check("resources has sheaf://entries/recent",
          "sheaf://entries/recent" in uris, f"got {uris[:5]}")
    check("resources has sheaf://stats", "sheaf://stats" in uris)

    resp2 = json.loads(handle_request({
        "jsonrpc": "2.0", "id": 3, "method": "resources/read",
        "params": {"uri": "sheaf://entries/recent"}
    }))
    recent_content = resp2.get("result", {}).get("contents", [])
    check("resources/read recent succeeds", len(recent_content) > 0,
          f"{len(recent_content)} contents")

    # --- 9. SHEAF_MCP_TOOLS=all --------------------------------------------
    print("\n[9/9] MCP tools/list — SHEAF_MCP_TOOLS=all (full surface)")
    os.environ["SHEAF_MCP_TOOLS"] = "all"
    from sheaf_ai.mcp.server import _select_tools
    all_names = {t["name"] for t in _select_tools()}
    check("SHEAF_MCP_TOOLS=all exposes >=11", len(all_names) >= 11,
          f"got {len(all_names)}")
    check("full set includes demoted tools",
          {"sheaf_list", "sheaf_correct", "sheaf_crosscheck"} <= all_names)
    os.environ.pop("SHEAF_MCP_TOOLS", None)


# ---------------------------------------------------------------------------
# Part B — Pre-Release Risk Scan (steps 10–13)
# ---------------------------------------------------------------------------

def run_risk_scan(failures: list) -> None:
    def check(label: str, cond: bool, detail: str = "") -> None:
        mark = "\u2705" if cond else "\u274c"
        print(f"  {mark} {label}{(' — ' + detail) if detail and cond else ''}")
        if not cond:
            failures.append(f"{label}{(' — ' + detail) if detail else ''}")

    def check_warn(label: str, cond: bool, detail: str = "") -> None:
        mark = "\u26a0\ufe0f" if not cond else "\u2705"
        print(f"  {mark} {label}{(' — ' + detail) if not cond and detail else ''}")

    # --- 10. README consistency --------------------------------------------
    print("\n[10/13] README consistency")
    readme_path = REPO_ROOT / "README.md"
    try:
        readme = readme_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        check("README.md exists", False, "not found — critical for GitHub landing page")
        readme = ""

    if readme:
        # Check test count consistency (both badge and body)
        test_badge = re.search(r"tests-(\d+)(%20|%%)pass", readme)
        test_body = re.search(r"(\d{2,4})\s+(?:tests\b|passed)", readme, re.IGNORECASE)

        # Run pytest --collect-only to get actual count
        rc, out, _ = _run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                          "--basetemp", ".pytest-tmp-release-check"])
        actual_count = 0
        if rc == 0:
            count_match = re.search(r"(\d+)\s+tests?\s+collected", out)
            if count_match:
                actual_count = int(count_match.group(1))
        if actual_count:
            check(f"README test count matches (reported {actual_count})",
                  str(actual_count) in readme,
                  "README badge/body may be stale")
        else:
            check_warn("pytest --collect-only ran, but count not parseable",
                       False, "could not determine live test count")

        # Check that README mentions pip install correctly
        check("README has pip install sheaf-ai", "pip install sheaf-ai" in readme)
        check("README has GitHub URL",
              "github.com/zhelunSun/sheaf-ai" in readme.lower())

        # Check for broken relative links (quick heuristic)
        broken_links = []
        for m in re.finditer(r'\]\(([^)]+\.md)\)', readme):
            ref = m.group(1).split("#")[0]  # strip anchor
            if ref and not (REPO_ROOT / ref).exists():
                broken_links.append(ref)
        check("README has no broken .md links", len(broken_links) == 0,
              str(broken_links)[:120] if broken_links else "")

    # --- 11. Version management alignment ----------------------------------
    print("\n[11/13] Version management alignment")
    # pyproject.toml
    pyp = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pyp_ver = re.search(r'version\s*=\s*"([^"]+)"', pyp)
    pyp_version = pyp_ver.group(1) if pyp_ver else None
    check("pyproject.toml version found", pyp_version is not None)
    if pyp_version:
        check(f"pyproject.toml version = 0.7.0 (got {pyp_version})",
              pyp_version == "0.7.0")

    # git tag
    if _command_exists("git"):
        rc, out, _ = _run(["git", "describe", "--tags", "--abbrev=0"])
        latest_tag = out.strip() if rc == 0 else None
        if latest_tag:
            check(f"latest git tag = v0.7.0 (got {latest_tag})",
                  latest_tag == "v0.7.0")
        else:
            check_warn("git describe --tags returned no tag", False,
                       "repository may not have any release tags")

        # Verify tag is on current commit
        rc2, out2, _ = _run(["git", "rev-parse", "HEAD"])
        head_sha = out2.strip()[:8] if rc2 == 0 else ""
        rc3, out3, _ = _run(["git", "rev-list", "-n", "1", "v0.7.0"])
        tag_sha = out3.strip()[:8] if rc3 == 0 else ""
        if head_sha and tag_sha:
            check(f"git tag v0.7.0 is on HEAD ({tag_sha} == {head_sha})",
                  tag_sha == head_sha,
                  f"tag points to {tag_sha} but HEAD is {head_sha} — may need re-tag")

    # __init__.py version resolution
    rc, out, _ = _run([sys.executable, "-c",
                       "from sheaf_ai import __version__; print(__version__)"])
    init_version = out.strip() if rc == 0 else "ERROR"
    check(f"__init__.py resolves to 0.7.0 (got {init_version})",
          init_version == "0.7.0")

    # --- 12. Issue & milestone health --------------------------------------
    print("\n[12/13] Issue & milestone health")
    if _command_exists("gh"):
        # Open issues count
        rc, out, _ = _run(["gh", "issue", "list", "-s", "open", "-L", "50", "--json", "number,title,labels"])
        if rc == 0:
            issues = json.loads(out)
            open_count = len(issues)
            # Only flag if there are critical bugs open
            bug_labels = {"bug", "P0", "critical", "blocker"}
            critical_open = [i for i in issues
                           if any(l["name"].lower() in bug_labels for l in i.get("labels", []))]
            if critical_open:
                check("no critical/P0 open issues",
                      len(critical_open) == 0,
                      f"{len(critical_open)} open: {[i['number'] for i in critical_open]}")
            else:
                check(f"open issues ({open_count} total) — no criticals", True)
        else:
            check_warn("gh issue list failed", False, "may need gh auth")

        # Check if a v0.7.0 milestone is closed
        rc, out, _ = _run(["gh", "api", "repos/zhelunSun/sheaf-ai/milestones", "--jq",
                           ".[] | select(.title | test(\"0.7\")) | {title,state,open_issues,closed_issues}"])
        if rc == 0 and out.strip():
            ms = json.loads(out) if out.strip().startswith("{") else None
            if ms:
                check_warn(f"milestone {ms.get('title')} closed: {ms.get('state')}",
                           ms.get("state") == "closed",
                           f"{ms.get('open_issues')} open issues remaining")

        # Recently closed — regression check
        rc, out, _ = _run(["gh", "issue", "list", "-s", "closed", "-L", "5", "--json", "number,title,closedAt"])
        if rc == 0:
            recent = json.loads(out)
            check("recently closed issues queryable (regression check)", len(recent) > 0)
    else:
        check_warn("gh CLI not available — install gh for issue checks", False)

    # --- 13. Git hygiene ---------------------------------------------------
    print("\n[13/13] Git hygiene & private file leak check")
    if _command_exists("git"):
        # Uncommitted changes
        rc, out, _ = _run(["git", "status", "--porcelain"])
        dirty = out.strip()
        check("no uncommitted changes in repo",
              not dirty,
              f"{len(dirty.splitlines())} files dirty: {dirty[:200]}" if dirty else "")

        # Branch
        rc, out, _ = _run(["git", "branch", "--show-current"])
        branch = out.strip() if rc == 0 else ""
        check_warn(f"on main branch (current: {branch})",
                   branch == "main" or branch == "master",
                   f"releasing from '{branch}' — make sure this is intentional")

        # Private file leak: check git ls-files for internal/, .workbuddy/, data/, .env
        sensitive_patterns = ["internal/", ".workbuddy/", ".env", "__pycache__", ".pytest-tmp"]
        for pat in sensitive_patterns:
            rc, files, _ = _run(["git", "ls-files", pat])
            tracked = files.strip()
            check(f"no '{pat}' tracked in git", not tracked,
                  f"LEAK: {tracked[:120]}" if tracked else "")

        # Verify gitignore covers .pytest-tmp and internal
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8") if (REPO_ROOT / ".gitignore").exists() else ""
        for entry in ["internal/", ".pytest-tmp", "__pycache__"]:
            check(f".gitignore covers '{entry}'", entry in gitignore)
    else:
        check_warn("git not available — skip hygiene checks", False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    failures: list[str] = []

    # --- Setup isolated env ----------------------------------------------------
    tmp = Path(tempfile.mkdtemp(prefix="sheaf-prerelease-"))
    data_dir = tmp / "data"
    fake_home = tmp / "home"
    fake_home.mkdir()

    env = dict(os.environ)
    env["SHEAF_DATA_DIR"] = str(data_dir)
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)

    api_key = (os.environ.get("SILICONFLOW_API_KEY") or
               os.environ.get("DEEPSEEK_API_KEY") or
               os.environ.get("OPENAI_API_KEY") or
               os.environ.get("SHEAF_API_KEY"))

    py = sys.executable

    # Ensure sheaf_ai is importable (for step 3 direct imports and step 4+)
    sys.path.insert(0, str(REPO_ROOT))

    print("=" * 68)
    print("  Sheaf v0.7.0 Pre-Release Gate")
    print("  Part A — Functional Smoke (9 steps) + Part B — Risk Scan (4 steps)")
    print("=" * 68)
    print(f"  REPO_ROOT: {REPO_ROOT}")
    print(f"  temp dir:  {tmp}")
    print(f"  API key:   {'AVAILABLE' if api_key else 'MISSING — collect/crystallize skipped'}")

    # ---- Part A: Functional Smoke ---------------------------------------------
    print("\n" + "─" * 68)
    print("  PART A: Functional Smoke")
    print("─" * 68)
    run_functional_smoke(py, env, failures, api_key)

    # ---- Part B: Risk Scan ----------------------------------------------------
    print("\n" + "─" * 68)
    print("  PART B: Pre-Release Risk Scan")
    print("─" * 68)
    run_risk_scan(failures)

    # --- cleanup ---------------------------------------------------------------
    shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 68)
    if failures:
        print(f"  \u274c {len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"     - {f}")
        print("=" * 68)
        return 1
    print("  \u2705 All checks passed — Sheaf v0.7.0 is ready to launch.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
