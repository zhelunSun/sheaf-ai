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

### Language Policy

- **Issue titles**: English, using Conventional Commit prefix (`fix:`, `feat:`, `refactor:`, `docs:`, etc.)
- **Issue body**: English as primary language. Chinese supplementary notes are allowed below the English content.
- **PR titles / changelog / release notes**: English
- **Commit messages**: English
- **Internal planning / personal notes**: Should NOT be filed as public issues. Use private Projects or internal docs instead.

### Labels

Every open issue must have **at least one type label** and optionally a priority label.

**Type labels (required):**

| Label | Color | Purpose |
|-------|-------|---------|
| `bug` | 🔴 | Real bugs that affect users |
| `enhancement` | 🔵 | New features or improvements |
| `release-blocker` | 🔴 | Blocks current release — must fix before shipping |
| `research` | 🟡 | Exploratory — no short-term delivery commitment |
| `internal` | ⚪ | Internal planning — not user-facing (business plans, personal workflow, thesis) |
| `needs-validation` | 🟡 | Code complete but awaiting real-data / manual verification |
| `documentation` | 🔵 | Doc improvements |
| `refactor` | 🟣 | Code structure improvements |
| `good first issue` | 🟢 | Suitable for new contributors |

**Priority labels:**

| Label | Meaning |
|-------|---------|
| `P0` | Must have — blocks release |
| `P1` | Important — should have soon |
| `P2` | Nice to have — backlog |

**Domain labels (optional):**

`ux`, `dev`, `uc` (Universal Collector), `extension`, `vision`, `crystallize`

### Milestones

Every open issue **must** have a milestone:

| Milestone | Purpose |
|-----------|---------|
| `v0.6.0` | Current release — error classification, OutputGuard, regression tests |
| `v0.7.0` | Next iteration — growth engine, knowledge bundle |
| `v1.0.0` | Long-term vision / roadmap |
| `backlog` | Unscheduled — grooming queue |

### Issue Template

**Required fields:**

| Field | Description |
|-------|-------------|
| **Context** | Why this Issue exists (user pain point, feature gap, etc.) |
| **Task List** | `- [ ]` checklist of concrete steps |
| **Acceptance Criteria** | How to verify the Issue is done |

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

### Automation Comment Style

When automated agents (nightly dev, bots) comment on issues, use a professional, neutral tone:

```markdown
Status: implemented in commit abc1234
Validation: 829 tests passed, manual verification pending
Next action: close after live data validation
```

**Do NOT use:**
- Personal address ("Sir", "老板")
- Informal claims ("已完成", "建议关闭") without evidence
- Internal-only context that external contributors can't understand

## Branches

- `main` — stable, always passing tests
- `nightly/YYYY-MM-DD` — automated nightly development branches, merged via fast-forward

## Security and Privacy

Sheaf is local-first. Do not add telemetry, remote sync, or external service calls without explicit user action and clear documentation.
