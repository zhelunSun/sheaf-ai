# Changelog

All notable changes to Sheaf.

## [0.5.0] — 2026-06-07

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
