# Sheaf Agent Handoff

## Current Branch

- Branch: `nightly/2026-06-06`
- Current full gate: `python -m pytest tests -q --tb=short --basetemp .pytest-tmp-codex`
- Latest observed result: 796 passed, 13 skipped, 2 warnings
- Full lint gate: `python -m ruff check sheaf_ai/ sheaf_cards/ tests/`

## Active Working State

- Provider definitions are centralized in `sheaf_ai/providers.py`.
- `sheaf_ai/llm_client.py` and `sheaf_ai/settings.py` should consume provider data from that registry, not duplicate provider metadata.
- PDF collector should gracefully return `pdf-extract` results for malformed/empty bytes; router fallback should not be used for parser-only failures.
- `test_debug_data/` is local debug data and should stay untracked unless the human explicitly says otherwise.

## Product Boundary

- Open core now: CLI, local storage, collectors, search, crystallize, MCP, HTTP adapter, public card JSON contract.
- Future commercial layer is documented in `internal/commercialization/sheaf-unit-spec.md` and `internal/TECH-ROADMAP.md`.
- Do not implement paid/proprietary bundle registry runtime until `.sheaf` bundle format and import/export contract exist.
- Near-term registry work should stay open-core and concrete: provider registry, handler registry, schema registries, and later public `.sheaf` JSON index design.

## Hygiene Rules

- Do not commit `.env`, `data/`, `dist/`, `sheaf_ai.egg-info/`, `internal/`, `.workbuddy/`, or local debug folders.
- Keep public README/CHANGELOG/AGENTS test counts aligned after full gate runs.
- Run tests with isolated basetemp, then remove the temp dir after confirming it is under repo root.
