# Sheaf — Technical Architecture Audit & Roadmap

> **Status**: v0.4.0a0 architecture audit
> **Updated**: 2026-05-28

Sheaf is an early-alpha, local-first knowledge layer. The current product surface is CLI + MCP + local HTTP API, with an experimental browser extension and a structured KnowledgeCard layer.

This document describes the current public architecture and the near-term path toward a cleaner plugin/App-ready structure.

---

## 1. Current Architecture

```text
                   ┌──────────────────────────────┐
                   │ Interfaces / Adapters         │
                   │ CLI · MCP · HTTP · Extension  │
                   └──────────────┬───────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────┐
│ Core collection workflow                                  │
│ fetch → classify → summarize → quality → store → search   │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Local data layer                                          │
│ entries · raw text · summaries · index · tags · feedback  │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Knowledge card layer                                      │
│ crystallize → KnowledgeCard → CardStore → EmbeddingEngine │
└──────────────────────────────────────────────────────────┘
```

The codebase is currently organized by function modules rather than strict layers. That is acceptable for alpha, but the next maintainability step is to introduce light application/service boundaries before adding more public adapters.

| Area | Current modules | Notes |
|---|---|---|
| Interfaces | `cli.py`, `mcp_server.py`, `api.py`, `extension/` | Public entry points call core functions directly |
| Collection workflow | `pipeline.py`, `fetch_article.py`, `quality.py` | `process_url()` is the main collect use case |
| Local storage/search | `storage.py`, `query.py`, `search.py`, `feedback.py` | JSON/JSONL/Markdown files under `data/` |
| Cards/knowledge assets | `crystallize.py`, `card_service.py`, `renderer.py`, `sheaf_cards/` | Cards are structured, traceable units with shared public projection |
| Providers/config | `config.py`, `llm_client.py`, embedding/card provider helpers | OpenAI-compatible by default |

---

## 2. Public Interface Matrix

| Surface | Status | Contract | Notes |
|---|---|---|---|
| CLI `sheaf collect/search/crystallize/mcp/serve` | Alpha stable | Command names should remain compatible | Output text may evolve; JSON output should stay machine-readable |
| MCP stdio | Alpha stable | 9 tools: search, list, get, urgent, correct, collect, crystallize, list_cards, get_card | Tool names and argument shapes should be treated as public |
| HTTP API | Early alpha | `/health`, `/stats`, `/collect`, `/search`, `/entries`, `/crystallize`, `/cards`, `/feedback`, `/mcp` | Card JSON is projected through `card_service`; security model is localhost-first |
| Browser extension | Experimental | Calls local HTTP API at `http://localhost:8321` by default | Versioning is independent from the Python package |
| Python internals | Internal | No stable SDK yet | Future SDK should wrap services rather than expose raw modules |

Rule of thumb: adding or changing a public command, MCP tool, HTTP endpoint, or extension contract should update this matrix and the changelog.

---

## 3. Local Data Contracts

Sheaf stores user data locally. The default root is `./data/`, configurable via `SHEAF_DATA_DIR`.

| Data | Path | Purpose |
|---|---|---|
| Entry JSON | `data/entries/YYYY-MM/{id}.json` | Full structured metadata for a collected item |
| Raw text | `data/raw/{id}.txt` | Original extracted article/text content |
| Summary Markdown | `data/summaries/{id}.md` | Human-readable summary |
| Index | `data/index.jsonl` | Lightweight searchable index |
| Tags registry | `data/tags_registry.json` | Tag/topic usage history |
| Feedback | `data/feedback.jsonl` | User corrections and notes |
| Progress | `data/gamification.json` | Local progress/streak state |
| Knowledge cards | `data/cards/knowledge_cards.json` | Structured cards created by crystallization |
| Card embeddings | `data/cards/embeddings/` | Optional semantic-search vectors |

Architecture audit note: `knowledge_cards.json` should be the canonical card store. Any legacy or alternate card path must migrate or gracefully fall back before being treated as public.

---

## 4. Architecture Findings

### Strengths

- Local-first storage is simple, inspectable, and portable.
- CLI, MCP, and HTTP surfaces all exercise the same core product loop.
- `KnowledgeCard` provides a clearer domain model than plain vectors or opaque summaries.
- Optional Playwright and HTTP server dependencies are already separated through extras.
- Test coverage is broad enough to support careful structure cleanup.

### Gaps To Address

| Gap | Impact | Recommended action |
|---|---|---|
| No explicit application/use-case layer | CLI/MCP/HTTP adapters can drift in behavior | Add a light service facade for collect/search/crystallize/feedback |
| Import-time path constants | Tests and future apps must patch many modules | Introduce a path/storage context or repository boundary |
| Provider logic split across LLM/cards/embedding | Harder to add local models or provider-specific behavior | Centralize provider/env resolution |
| Public contracts live mostly in code | New adapters may accidentally change behavior | Keep a public interface matrix and route/tool tests |
| Large modules mix natural sub-responsibilities | Harder for humans and agents to safely edit | Split only around proven seams with tests |
| Embedding dependency footprint | Minimal install includes `numpy` | Revisit whether embeddings belong in an optional extra |

---

## 5. Recommended Roadmap

### Phase 1 — Contract Cleanup

- Treat `data/cards/knowledge_cards.json` as the canonical card store.
- Keep public card JSON generated through `card_service.card_to_public_dict()`.
- Keep CLI command names, MCP tool names, HTTP route names, and data file names compatible.
- Add tests for any public contract touched by a change.
- Keep extension documented as experimental until its local API contract is versioned.

### Phase 2 — Balanced Refactor

- Add a small application/service layer used by CLI, MCP, and HTTP.
- Add a storage/path context to reduce global path constants and broad monkeypatching.
- Move provider/env handling behind a shared boundary.
- Keep domain models small: Entry can remain dict-backed until schema pressure justifies dataclasses.

### Phase 3 — Plugin/App Readiness

- Define a stable local HTTP contract for extensions and desktop/mobile apps.
- Add Knowledge Pack manifest/export/import contracts.
- Consider a Python SDK only after services are stable.
- Add architecture decision records for storage schema, provider registry, and public API changes.

---

## 6. Design Principles

| Principle | Meaning |
|---|---|
| Local-first | Data stays on the user's machine unless explicitly exported or shared |
| Inspectable files | Prefer JSON/JSONL/Markdown over opaque local databases for core data |
| Stable adapters | CLI/MCP/HTTP contracts should evolve deliberately |
| Small boundaries before big moves | Add service/context seams before directory-wide restructuring |
| Cards over black-box vectors | KnowledgeCards should stay traceable, editable, and composable |
| Optional complexity | Playwright, HTTP server, embeddings, and future app features should stay optional where possible |

---

## 7. Verification Baseline

Before releasing architecture-affecting changes, run:

```bash
python -m pytest tests -q --basetemp .pytest-tmp
python -m ruff check sheaf_ai sheaf_cards tests
python -m build
python -m sheaf_ai.cli --help
python -m sheaf_ai.cli --version
```

Architecture changes should preserve existing CLI command names, MCP tool names, HTTP route names, and local data compatibility unless a migration is explicitly documented.
