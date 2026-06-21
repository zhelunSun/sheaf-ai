# Changelog

All notable changes to Sheaf.

## [0.7.0] — 2026-06-21

### MCP Resources — browse the knowledge base (Issue #89, design Principle F)
Agents can now **browse** the KB read-only via MCP Resources (`resources/list` / `resources/read`), complementing the 4 tools (write/act) with a read/browse surface:
- `sheaf://entries/recent` — 10 most recent entries
- `sheaf://entries/{id}` — one entry's full detail (template)
- `sheaf://entries/{id}/raw` — the **original fetched text**, so an agent can verify a summary or quote the source without re-fetching (works even if the source is gone)
- `sheaf://stats` / `sheaf://tags` — aggregate counts and tag frequency
- `initialize` advertises the `resources` capability. New module `sheaf_ai/mcp/resources.py` reuses existing data functions — zero new data code. Entry-id validation blocks path traversal.

### Install: MCP + skill unified
- Clarified that `sheaf setup` deploys the MCP server **and** the skill together (the skill drives proactive capture/recall — not optional). `sheaf init --auto` does it all (key + MCP + skill + health) in one command. Bare `uvx` wires MCP only.

### Stats
- 1024 tests passing (+14 since 0.6.3: 11 MCP-resource + 1 raw-resource + 2 contract), 19 skipped, 0 warnings, ruff clean.

## [0.6.3] — 2026-06-21

### Agent-doc contract test + drift repair (v0.7 Phase 1)
- **New `tests/test_skill_contract.py`** — parses the agent skill (`sheaf-guide.md` / `AGENTS.sheaf.md`) and asserts every referenced CLI command, MCP tool, and flag resolves against the real CLI parser + MCP registry. A CI guardrail so skill/CLI drift surfaces in tests, not at agent runtime. On first run it caught 6 live drifts, all repaired:
  - **Skill drift** — the skill told agents to run `sheaf correct` / `sheaf crosscheck`, which are not CLI commands → rerouted to MCP `tools/call` (Issue #91's demoted-tool design) / `sheaf matrix`; and `list --filter` / `--category` / `--offset` don't exist → real flags (`--topic` / `--tag` / `--type` / `--page`) + `sheaf urgent`.
  - **Code bug fixed** — `sheaf setup --target codex` was rejected by argparse (the `--target` choices omitted `codex` though the setup function supported it). Added `codex` to the choices; regression test `test_cli_setup_target_codex_parses` added.

### Stats
- 1010 tests passing (+7), 19 skipped, 0 warnings, ruff clean.

## [0.6.2] — 2026-06-20

### Agent-native collect (freeform text via MCP)
- **`sheaf_collect(text=…)`** — the MCP tool now accepts `text` as an alternative to `url`, so an agent can save a pasted insight/note without a URL (closes the "收藏这个观点" gap). url/text are mutually exclusive; validated in the handler.
- **Notes are a first-class type** — manual/pasted entries are tagged `content_type:"note"`, bypass the short-content quality gate (a note is intentionally short), and get an AI-generated title (the summarize step now generates a title when none is provided) with a deterministic first-sentence fallback.
- **Agent memory UX in the skill** — proactive capture (judge by information density), gated proactive recall (one search on knowledge-shaped questions), and light value-visibility footer (`📖 via Sheaf KB`) when memory materially contributed. Design + iteration plan in `internal/design/AGENT-MEMORY-UX.md`.

### Human CLI UX
- **`sheaf help`** — a curated, grouped command overview (Collect / Read / Crystallize / Agent). `sheaf help <cmd>` delegates to argparse. Distinct from the agent-facing skill.
- **`sheaf search` shows the entry ID** per result (so you can `sheaf get <id>` or open the file). MCP search already returned full entries.
- **`sheaf list --page N`** — 1-indexed pagination with page navigation hints.
- **CLI beautification** — new zero-dependency `sheaf_ai/term.py` ANSI helper (respects `NO_COLOR` / non-TTY); applied to recent / search / list for a cleaner, Claude-Code-style terminal feel. No new deps, no perf impact.

### Under the hood
- **`SCHEMA_VERSION` centralized** in `config.py` (was inconsistently stamped `1.1.0` in pipeline vs `1.2.0` in storage, and never read). Now single-source `1.2.0`; stamped but not yet used for migration — design in `internal/design/DATA-LIFECYCLE.md`.

### Stats
- 1003 tests passing, 0 warnings, ruff clean.

## [0.6.1] — 2026-06-19

### One-click agent install + MCP surface slim (closes #91)
- **One-line agent wiring (uvx, npm-equivalent)** — `claude mcp add sheaf -- uvx --from sheaf-ai sheaf-mcp`; no Python install needed for agent users. README Quick Start now leads with this; `pip install` kept for CLI/library users.
- **Codex CLI support** — `sheaf setup --target codex` writes `~/.codex/config.toml` (TOML, idempotent merge preserving user config) + deploys `AGENTS.sheaf.md`. Claude Code path deploys `~/.claude/skills/sheaf-guide.md`.
- **MCP surface slimmed to 4 core tools** — `sheaf_collect`, `sheaf_search`, `sheaf_crystallize`, `sheaf_get_card` (~1.5k vs ~5k tokens). The other 7 keep their handlers (callable via `tools/call`) and are guided to the `sheaf` CLI (`--json`); `SHEAF_MCP_TOOLS=all` re-exposes all 11.
- **Command hardening** — `sheaf setup` now writes `command=sheaf-mcp` (path-independent) instead of a fragile absolute venv python path.
- **Provider routing fix** — `build_mcp_config` now injects `DEFAULT_PROVIDER` + key + `OPENAI_BASE_URL` (was hardcoding `OPENAI_API_KEY`, which silently misrouted non-OpenAI users in the MCP subprocess).
- **`sheaf doctor` MCP+skill self-check** + warnings honesty (no longer prints "All checks passed" while listing ⚠️).
- New CLI: `sheaf get <id>` and `sheaf insights --json` (high-frequency demoted-tool fallbacks).

### Reliability (Codex prelaunch audit fixes)
- **Concurrency lock** — `update_tags_registry` / `append_index` are now serialized via `_STORAGE_LOCK`; fixes both a lost-update race and a Windows `os.replace` `WinError 5` crash under concurrent batch-collect. Regression tests added.
- **PyPDF2 deprecation** — PDF collector now prefers `pypdf` (maintained) over `PyPDF2` (fallback). Eliminates the last test warning.
- ruff clean (10 errors resolved), README/README_CN/STATUS fact drift corrected (test count, data-dir resolution, MCP tool count).

### Stats
- 986 tests passing, 0 warnings.

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
- **MCP v2 architecture plan** — `internal/design/MCP-V2-PLAN.md` (元工具 + 角色专属工具两层草案)

### Positioning
- Phase 5.5 in `PRODUCT-EVOLUTION.md` — "消息源信任基础设施"
- Bridges current collect pipeline to Phase 4 Matrix (v0.7.0) and Phase 5 Agent Memory Layer

### Known Gaps (blocking v0.6.1 release)
- ⚠️ **#67** SiliconFlow live rebuild verification (open 9d, blocked by Sir network window)
- ⚠️ Manual test checklist written but not yet executed end-to-end (`internal/test-reports/manual-test-checklist-2026-06-15.md`)

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
