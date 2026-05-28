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

## Security and Privacy

Sheaf is local-first. Do not add telemetry, remote sync, or external service calls without explicit user action and clear documentation.
