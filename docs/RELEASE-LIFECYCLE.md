# Sheaf Release Lifecycle

Sheaf is early alpha. The goal of this lifecycle is to keep `main` installable while allowing fast nightly development.

## Branches and Versions

| Surface | Meaning |
|---|---|
| `main` | Releasable trunk. It should pass tests, lint, build, and CLI smoke checks. |
| `nightly/YYYY-MM-DD` | Integration branch for automated or assisted development. It is not a release channel. |
| `0.x.yaN` | Alpha preview. Interfaces may still move. |
| `0.x.ybN` | Beta preview. Core workflows should work and public contracts should remain compatible. |
| `0.x.yrcN` | Release candidate. Bugfix-only unless a blocker appears. |
| `0.x.y` | Release. |

Sheaf uses SemVer-shaped versions with Python-compatible pre-release suffixes.

## Merge Gate

Before a nightly branch can merge to `main`, maintainers should run:

```bash
python -m pytest tests -q --basetemp .pytest-tmp
python -m ruff check sheaf_ai sheaf_cards tests
python -m build
python -m sheaf_ai.cli --help
python -m sheaf_ai.cli --version
git diff --check
git ls-files internal .workbuddy .learnings data dist sheaf_ai.egg-info .env scripts requirements.txt
```

The last command must print nothing. Local data, private planning docs, agent memory, build artifacts, and secrets must not be tracked.

For the full pre-release checklist, see [RELEASE-CHECKLIST.md](RELEASE-CHECKLIST.md).

## Public Contracts

Changes to these surfaces need tests and documentation:

- CLI command names and machine-readable output.
- MCP tool names, arguments, and result shapes.
- HTTP routes and JSON response shapes.
- Local storage paths and schemas.
- Knowledge card public JSON projection.

The browser extension is currently experimental and versioned independently from the Python package.

## Automation

The scheduled nightly review workflow may test and report on nightly branches, but it must not merge, tag, publish, or push `main`.
