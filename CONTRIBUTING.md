# Contributing to Sheaf

Thanks for helping improve Sheaf. The project is early alpha, so small, focused changes are easiest to review.

## Development Setup

```bash
git clone https://github.com/zhelunSun/sheaf-ai.git
cd sheaf-ai
python -m pip install -e ".[dev]"
```

Optional extras:

```bash
python -m pip install -e ".[server]"   # HTTP API
python -m pip install -e ".[browser]"  # Playwright fetch fallback
```

## Checks

Run these before opening a PR:

```bash
python -m pytest tests -q
python -m ruff check sheaf_ai sheaf_cards tests
python -m build
```

On locked-down Windows environments, pytest may need an explicit workspace temp directory:

```bash
python -m pytest tests -q --basetemp .pytest-tmp
```

## Pull Requests

- Keep changes scoped to one behavior or subsystem.
- Add or update tests for user-visible behavior.
- Do not commit local data, API keys, private planning docs, or agent memory.
- Keep public docs consistent with actual commands, versions, and test counts.
- Follow the release and nightly merge rules in [docs/RELEASE-LIFECYCLE.md](docs/RELEASE-LIFECYCLE.md).

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) with an Issue reference:

```
feat: [#42] add YouTube video metadata extractor
fix: [#67] fallback to BM25 when embedding service unavailable
docs: update test badge count after nightly run
refactor: extract SPA fetcher into standalone module
chore: add .sandbox-test/ to .gitignore
```

**Rules:**

- One commit per Issue. Do not bundle multiple unrelated Issues into one commit.
- Always reference the Issue number (`#42` or `[Issue #42]`).
- Nightly/automated commits use the `nightly:` prefix with Issue reference.
- Scope is optional: `feat(extension): ...`, `fix(search): ...`.

## Issues

Well-structured Issues help contributors pick up work independently.

**Required fields:**

| Field | Description |
|-------|-------------|
| **Context** | Why this Issue exists (user pain point, feature gap, etc.) |
| **Task List** | `- [ ]` checklist of concrete steps |
| **Acceptance Criteria** | How to verify the Issue is done |

**Labels:** Assign at least one priority label (`P0` / `P1` / `P2`) and one type label (`bug` / `enhancement` / `refactor` / `documentation`).

**Milestones:** Every open Issue must have a milestone (`backlog` / `v0.5.0` / etc).

**Example:**

```markdown
## Context
Users sharing Chinese platform links (e.g., mp.weixin.qq.com) get empty content because the SPA fetcher doesn't detect these domains.

## Tasks
- [ ] Add WeChat MP URL pattern to `collectors/url_patterns.py`
- [ ] Add Playwright fallback for `.qq.com` domains
- [ ] Add test for WeChat article extraction

## Acceptance Criteria
- [ ] `sheaf collect "https://mp.weixin.qq.com/s/..."` returns non-empty content
- [ ] Test passes on CI
```

## Branches

- `main` — stable, always passing tests
- `nightly/YYYY-MM-DD` — automated nightly development branches, merged via fast-forward

## Security and Privacy

Sheaf is local-first. Do not add telemetry, remote sync, or external service calls without explicit user action and clear documentation.
