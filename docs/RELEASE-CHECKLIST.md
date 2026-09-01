# Release Checklist

Complete every item below before tagging a release. This list applies to all version bumps (alpha, beta, rc, final).

## 1. Version Alignment

- [ ] **`pyproject.toml`** — update `version` field
- [ ] **`sheaf_ai/__init__.py`** — no hard-coded version (reads from metadata ✓), but verify it resolves correctly after build
- [ ] **`CHANGELOG.md`** — add entry for the new version with all notable changes
- [ ] **`README.md`** — update three locations:
  - Badge: `tests-NNN%20pass`
  - Dev section: `# NNN passed, N skipped`
  - Alpha status paragraph: `tested with NNN passing tests`
- [ ] **`CONTRIBUTING.md`** — check if milestone table still reflects current targets

## 2. Code Health

- [ ] `python -m pytest tests -q --basetemp .pytest-tmp` — **0 failures, 0 warnings**
- [ ] `python -m ruff check sheaf_ai sheaf_cards tests scripts/release` — **0 errors**
- [ ] `python -m build` — produces `dist/sheaf_ai-<version>-py3-none-any.whl` without errors
- [ ] `python scripts/release/smoke_fresh_wheel.py --wheel dist/sheaf_ai-<version>-py3-none-any.whl --expected-version <version>` — creates a new venv, installs the wheel without editable mode, and passes installed metadata, `sheaf --version`, `sheaf --help`, and stdio `sheaf-mcp` JSON-RPC checks
- [ ] The smoke script runs outside the repository with an isolated data/home directory; a source-tree import cannot satisfy the gate

## 3. Hygiene

- [ ] `git diff --check` — no whitespace errors
- [ ] `git ls-files internal .workbuddy .learnings data dist sheaf_ai.egg-info .env requirements.txt` — **prints nothing** (no tracked private files)
- [ ] `git ls-files scripts` — only shows the existing reviewed `scripts/smoke-pre-release.py` helper and files under `scripts/release/`; other local scripts remain ignored
- [ ] Verify `sheaf_ai/synonyms.py` (user-customizable) is NOT in the sdist if it contains personal data
- [ ] `__pycache__` / `.pytest-tmp` / `test_debug_data` — not tracked

## 4. Documentation Consistency

- [ ] `CLAUDE.md` MCP tool table matches `mcp_server.py` tool definitions
- [ ] `README.md` "Core Commands" section matches `cli.py` subparsers
- [ ] `README.md` "Supported Providers" table matches `providers.py`
- [ ] `docs/RELEASE-LIFECYCLE.md` merge gate still matches this checklist

## 5. Publish

- [ ] Create exactly `git tag v<version>` on `main`; the workflow rejects a tag that differs from `project.version` in `pyproject.toml` or whose commit is not reachable from `origin/main`
- [ ] `git push origin main --tags`
- [ ] The tag-triggered workflow passes tests, lint, build, and the fresh-wheel smoke before the PyPI environment is entered
- [ ] PyPI publishes the exact distributions uploaded by the verification job, not a second rebuild
- [ ] Verify `pip install --upgrade sheaf-ai` installs the new version
- [ ] Verify `sheaf --version` from the public PyPI install

## 6. Post-Release

- [ ] Close the milestone on GitHub
- [ ] Create next milestone (if not already)
- [ ] Update `internal/` planning docs if they reference version-specific deadlines
