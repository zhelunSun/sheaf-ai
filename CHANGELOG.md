# Changelog

All notable changes to Sheaf.

## [0.6.1-beta.1] — 2026-06-12 (feat/mcp-v2, pending merge to main)

### Added (Beta)
- **Source Credibility Score** — hybrid rule+LLM scoring, every entry now carries `source.score` (0-100) and `tier` (A/B/C/D)
  - Rule base (0-40): domain authority table + primary/secondary detection + author + citations
  - LLM bonus (0-30): `is_primary_source`, `has_verifiable_claims`, `domain_expertise` (no extra API cost — runs inside classify call)
  - Freshness (0-10): news decay bonus
  - User override: persisted to `source_registry.json` for domain-level caching
- **`sheaf_crosscheck` MCP tool** — cross-verify claims against other entries in the knowledge base
  - Returns a fact comparison matrix with status per claim: ✅ confirmed / ⚠️ divergent / ❌ lone source / ❓ not covered
  - Overall confidence: high / medium / low
- **Source Intelligence design** — `docs/SOURCE-INTELLIGENCE-DESIGN.md` (draft v0.1)
- **MCP v2 architecture plan** — `internal/MCP-V2-PLAN.md` (元工具 + 角色专属工具两层草案)

### Positioning
- Phase 5.5 in `PRODUCT-EVOLUTION.md` — "消息源信任基础设施"
- Bridges current collect pipeline to Phase 4 Matrix (v0.7.0) and Phase 5 Agent Memory Layer

### Known Gaps (blocking v0.6.1 release)
- ⚠️ **#67** SiliconFlow live rebuild verification (open 9d, blocked by Sir network window)
- ⚠️ Manual test checklist written but not yet executed end-to-end (`docs/manual-test-checklist-2026-06-15.md`)

## [0.6.0] — 2026-06-08

### Added
- **User-customizable synonym config** — `sheaf_ai/synonyms.py` module for cross-lingual search expansion
- **Semantic exit codes for failed collects** — `invalid_url→5 (CONFIG)`, `network_error→4 (NETWORK)`, `js_rendering→1 (PARTIAL)`, `quality→3 (QUALITY)`, dedup exits cleanly with 0
- **OutputGuard v2** — three new quality signals: `EXIT_MISMATCH`, `UNSTRUCTURED_ERROR`, `NO_SUGGESTION`
- **LLM depth test framework** — migrated from `tests/` to `scripts/` with `--seed`, `--output` CLI, raw-vs-normalized command tracking, model/provider/version metadata in reports
- **12 deterministic regression tests** — SPA misclassification, empty search suggestions, invalid URL friendly errors, exit code semantics

### Fixed
- **Error classification triage in fetch_article.py** — Strategy 3 no longer defaults all failures to `js_rendering_required`; now distinguishes `invalid_url`, `network_error`, and genuine SPA
- **Doctor command refactored** — split into `_build_doctor_report()` (pure) + `_doctor()` (print-only) + `_doctor_cli()` (exit wrapper); human-readable labels restored
- **ERROR_LEAKED vulnerability** — failed collects no longer output error text with exit code 0
- **pytest collection warnings** — root `conftest.py` excludes `scripts/` and `internal/` from collection; 0 warnings
- **MCP subprocess tests** — use `python -m sheaf_ai.cli` for cross-platform compatibility
- **Doctor env patch overflow** — fixed Windows test environment variable explosion

### Changed
- Version bump: `0.5.0` → `0.6.0`
- Test suite: 846 → 885 tests collected (867 passed + 19 skipped)

### Tests
- 885 collected, 867 passed, 19 skipped, 0 failures, 0 warnings

### Added
- **CLI `sheaf search --json`** — structured JSON output for Agent consumption (#78)
  - `--limit` / `-n` flag for result count control
  - JSON includes query, total, results with scores, snippets, and expanded_terms
- **MCP tools consolidated 13→10** — cleaner Agent interface
  - `sheaf_list` enhanced: `filter` param (`urgent`/`untagged`/`recent`), returns `total` + `topics_summary`
  - `sheaf_urgent` → deprecated (use `sheaf_list filter="urgent"`)
  - `sheaf_healthcheck` → deprecated (use HTTP `/health`)
  - `sheaf_stats` → deprecated (use `sheaf_list` for total + topics)
  - Deprecated tools retain backward-compatible fallback (return data + deprecation notice)
- **Doctor multi-provider key scan** — detects all provider API keys (#79)
  - Checks OPENAI, DEEPSEEK, SILICONFLOW, TOGETHER, GROQ, SHEAF_API_KEY
  - Also checks user config file (~/.sheaf/config.json)
- **Chrome Extension v2** — from MVP skeleton to usable product
  - Search: search input in popup, calls `/search` API, renders results with topics + date
  - Connection wizard: guided setup when API offline (`sheaf serve` command + retry button)
  - Enhanced collect feedback: one_liner display, contextual error hints (duplicate, quality, fetch, timeout)
  - Settings page: connection info panel, keyboard shortcuts, About section with repo link
  - Offline handling: `fetchWithTimeout()` for all API calls with configurable timeouts
  - Version: 0.1.0 → 0.4.0 (independent companion versioning)
  - Added `127.0.0.1` host permission alongside `localhost`

### Changed
- `show_search()` now accepts `limit` parameter (was hardcoded to 10)
- `sheaf_list` MCP response changed from plain `list` to `{total, topics, entries}` dict
- MCP server docstring updated to reflect 10 active + 3 deprecated tools

### Tests
- 846 passed (+8 new), 13 skipped, 0 failures
- New: `TestSearchJSON` (6 tests), `TestSheafDoctor` multi-provider (2 tests), MCP consolidation (7 tests)

## [0.4.0a1] — 2026-06-06

### Fixed
- Atomic writes to storage, feedback, pipeline, and gamification modules
- Retry with exponential backoff and timeout to LLM client
- Default data directory changed to `~/.sheaf/data` when not in project context
- Unused import lint errors in card_service and test_tag_tracking
- CI workflow added for test/ruff/build on push and PR

## [0.4.0a0] — 2026-05-19

### Added
- Alpha public release
- Full test suite: 68 tests, 100% pass
- Brand rename: uc → sheaf_ai
- `sheaf_ai/` 15-module architecture
- `sheaf_cards/` knowledge card engine (4 modules)
- SiliconFlow API embeddings + numpy cosine similarity
- MCP server with 6 tools (JSON-RPC over stdio)
- DeepSeek-V3.2 via openai-compatible API
- GitHub public repo
