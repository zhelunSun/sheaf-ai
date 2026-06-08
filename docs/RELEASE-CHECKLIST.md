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
- [ ] `python -m ruff check sheaf_ai sheaf_cards tests` — **0 errors**
- [ ] `python -m build` — produces `dist/sheaf_ai-<version>-py3-none-any.whl` without errors
- [ ] `python -m sheaf_ai.cli --version` — prints `Sheaf v<version>`
- [ ] `python -m sheaf_ai.cli --help` — no tracebacks

## 3. Hygiene

- [ ] `git diff --check` — no whitespace errors
- [ ] `git ls-files internal .workbuddy .learnings data dist sheaf_ai.egg-info .env scripts requirements.txt` — **prints nothing** (no tracked private files)
- [ ] Verify `sheaf_ai/synonyms.py` (user-customizable) is NOT in the sdist if it contains personal data
- [ ] `__pycache__` / `.pytest-tmp` / `test_debug_data` — not tracked

## 4. Documentation Consistency

- [ ] `CLAUDE.md` MCP tool table matches `mcp_server.py` tool definitions
- [ ] `README.md` "Core Commands" section matches `cli.py` subparsers
- [ ] `README.md` "Supported Providers" table matches `providers.py`
- [ ] `docs/RELEASE-LIFECYCLE.md` merge gate still matches this checklist

## 5. Publish

- [ ] `git tag v<version>` on `main` (or release branch)
- [ ] `git push origin main --tags`
- [ ] `twine upload dist/sheaf_ai-<version>*` (or CI auto-publish)
- [ ] Verify `pip install --upgrade sheaf-ai` installs the new version
- [ ] Verify `sheaf --version` on a clean install

## 6. Post-Release

- [ ] Close the milestone on GitHub
- [ ] Create next milestone (if not already)
- [ ] Update `internal/` planning docs if they reference version-specific deadlines
