# Changelog

All notable changes to Sheaf.

## [Unreleased] — Wave 2.5: Gamification Lite + Quality Gate

### Added
- `sheaf_ai/gamification.py` — gamification engine v2.5:
  - Collection progress bars (dual-dimension: sheaves + cards)
  - Progress thresholds at 10/30/50/100
  - 12 milestone definitions (6 core + 6 extended)
  - Streak tracking with CLI startup display
  - ASCII progress bars with threshold markers
- `sheaf_ai/quality.py` — content quality gate:
  - `QualityReport` dataclass — structured quality assessment
  - `assess_quality()` — core quality gate (pass/warn/reject)
  - Image density detection + alt text extraction
  - Force mode for `--force` flag
  - Pipeline integration at Step 1.1 (before classify/summarize)
- `sheaf_ai/api.py` — MCP Streamable HTTP transport (`/mcp` endpoint):
  - POST for JSON-RPC requests
  - GET with SSE for streamable responses
  - CORS + health check support
- `sheaf_ai/display.py` — streak line display on CLI startup
- Chrome Extension MVP scaffold (popup, background, options, icons)
- CONTRIBUTING.md — public contribution guide

### Changed
- Pipeline now runs quality gate before classify/summarize
- Image-heavy articles auto-append alt text supplement
- CLI shows quality hints on failure (with `--force` suggestion)
- `sheaf stats` shows dual-dimension progress bars + milestone badges
- Gamification update after both glean and crystallize

### Tests
- 273 tests (100% pass) — 62 new gamification + 35 quality gate tests
- Ruff lint: 0 issues

---

## [Unreleased] — Wave 2: Crystallize

### Release Hardening
- Ran a pre-release hard-gate audit covering tracked private files, first-run config, build artifacts, local API/MCP boundaries, and docs consistency.
- Aligned default model configuration with `.env.example`: provider defaults now come from `llm_client`, with optional `DEFAULT_MODEL` / task-specific overrides.
- Unified MCP protocol version reporting across stdio and HTTP transport.
- Tightened default CORS behavior for the local HTTP API and added a warning for non-localhost binds.
- Fixed Windows subprocess decoding in CLI smoke tests.
- Updated public docs to reflect 273 tests and pyproject extras as the dependency source of truth.

### Added
- `sheaf_ai/crystallize.py` — knowledge crystallization engine:
  - `find_entries_by_topic()`: cross title/topics/tags/summary matching
  - `crystallize_topic()`: LLM multi-source synthesis → KnowledgeCards with evidence tracing
  - `crystallize_and_save(auto_embed=True)`: crystallize + dedup + persist
  - `list_crystallized/get_card/delete_card/get_topic_stats`: card CRUD + stats
  - `semantic_search()`: vector similarity search across cards
  - `rebuild_embeddings()`: full index rebuild from stored cards
  - `_embed_cards()`: best-effort embedding (fails gracefully, doesn't block core)
- `prompts/crystallize.md` — LLM prompt template for knowledge synthesis
- CLI `sheaf crystallize` subcommand (topic, --list, --show, --delete, --stats, --semantic, --rebuild-embeddings)
- MCP tools: `sheaf_crystallize`, `sheaf_list_cards`, `sheaf_get_card` (9 tools total)
- MCP `ping` method for health checks
- E2E test environment: `D:/Agent/WorkBuddy/sheaf-e2e-test/` with `run-e2e.sh` automated suite
- `--help` epilog with quick start examples
- Nightly Dev Pipeline v2 with fault-tolerance and tool fallback chains
- Agent profile: `.workbuddy/agents/nightly-dev.md`
- Developer experience log: `internal/dev-log/` (6 entries, Sheaf-indexable)

### Fixed
- `ensure_data_dirs()` was defined but never called → `sheaf init` crashed on storage. Fixed by adding call at start of `process_url()` (BLG-K04)
- `sheaf_ai/query.py`: restored `TAGS_REGISTRY_FILE` import for test conftest compatibility
- `EmbeddingBridge` now uses canonical `data/cards/knowledge_cards.json` and read-only migrates legacy `data/cards/cards.json`.

### Changed
- `process_url()` now calls `ensure_data_dirs()` before any writes
- CLI argument parser: added epilog with quick start guide
- Commands now use proper subcommand syntax (no `--` prefix required)
- MCP tools set expanded from 6 to 9
- Ruff linting: 108 issues fixed, per-file-ignores for intentional CLI compact syntax

### Developer Experience
- `internal/dev-log/`: 6 entries covering pipeline fault-tolerance, test isolation, UX audit, project conventions, mock lazy import, and E2E testing
- `.learnings/`: ERRORS.md (ERR-20260522-001) + LEARNINGS.md (LRN-001, LRN-002)
- Ruff per-file-ignores: `sheaf_ai/cli.py` (E701/E702), `sheaf_ai/config.py` (E402)

---

## [0.4.0-alpha] — 2026-05-19

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

---

## [0.3.x] — 2026-05-13 ~ 2026-05-17

### 0.3.1a (2026-05-17)
- Legacy migration + full reclassification
- Dynamic tag support

### 0.3.0 (2026-05-16)
- Fetch v2 with 3-strategy fallback (requests → Playwright → manual)
- Dynamic topic classification

### 0.1.0 (2026-05-13)
- MVP: fetch → classify → summarize → store
- Basic CLI
