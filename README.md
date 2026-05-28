# Sheaf

> **Harvest your knowledge. Bundle it. Share it.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-288%20pass-brightgreen)](tests/)
[![PyPI](https://img.shields.io/pypi/v/sheaf-ai.svg)](https://pypi.org/project/sheaf-ai/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/sheaf-ai.svg)](https://pypi.org/project/sheaf-ai/)

A **sheaf** is a bundle of grain — the basic unit a farmer brings to market. Sheaf does the same for knowledge: gather what you read, crystallize it into structured bundles, and make it tradable. Your AI agents can search, cite, and reason over everything you've collected.

## Quick Start

```bash
# Install from PyPI
pip install sheaf-ai

# Or install from source
git clone https://github.com/zhelunSun/sheaf-ai.git
cd sheaf-ai
pip install -e .

# Set your LLM API key (any OpenAI-compatible endpoint)
export OPENAI_API_KEY=sk-...

# First-time onboarding (collects 3 sample articles)
sheaf init

# Collect a link
sheaf collect https://arxiv.org/abs/2401.00000

# Search your collection
sheaf search "transformer architecture"

# Crystallize knowledge cards from collected articles
sheaf crystallize AI
```

No accounts. No cloud. Your data lives in `./data/` as Markdown + JSON.

## The Problem

You save links every day — articles, repos, papers, tutorials. **95% never get opened again.**

Not because you're lazy. Because bookmarks serve *human reading*, not *agent workflows*. When you ask your coding agent "what did I read about MCP last week?", it has no idea.

Sheaf fixes this. Every link you save becomes a **structured entry** — a single stalk of grain. Crystallize enough of them, and you get a **bundle**: a portable, searchable knowledge pack any agent can consume.

## What It Does

1. **Harvest** — paste a link, Sheaf fetches, classifies, and summarizes it
2. **Crystallize** — distill 3+ related entries into structured knowledge cards with evidence tracing
3. **Bundle** — package cards into a portable `.sheaf` unit (coming soon)
4. **Agent-ready** — built-in MCP server lets any LLM agent query your knowledge base

## Core Commands

```bash
sheaf collect <url>         # Collect an article, paper, or webpage
sheaf search <query>        # Full-text search across your collection
sheaf stats                 # Collection statistics with topic trends
sheaf crystallize <topic>   # Crystallize knowledge cards from a topic
sheaf crystallize --list    # List all crystallized cards
sheaf crystallize --semantic <q>  # Semantic vector search across cards
sheaf tags                  # Tag statistics
sheaf weekly                # Weekly summary report
sheaf insights              # Cross-topic association discovery
sheaf urgent                # Show entries with upcoming deadlines
sheaf mcp                   # Start MCP server (stdio transport)
sheaf init                  # First-time onboarding with demo
```

## Crystallize: Your Second Brain

This is Sheaf's killer feature. Instead of leaving your bookmarks to rot, `sheaf crystallize` synthesizes insights across multiple entries:

```bash
$ sheaf crystallize AI
Crystallizing 'AI'...
✨ 5 knowledge cards crystallized:
  📌 RAG faces retrieval relevance challenges (90%)
     RAG systems heavily depend on retrieval quality; errors degrade LLM output reliability.
  📌 CRAG framework improves RAG robustness (95%)
     CRAG introduces a retrieval evaluator, web search augmentation, and document decomposition.
  📌 Retrieval granularity significantly impacts performance (90%)
     Finer-grained units like propositions outperform traditional passage-level retrieval.
```

Each card includes:
- **Confidence score** (0-100%)
- **Evidence tracing** — which source entries contributed
- **Topic provenance** — what topic this card belongs to
- **Tags** — for filtering and cross-referencing

Use `sheaf crystallize --semantic "query"` for vector-based semantic search across all your cards.

## MCP Server

Sheaf ships with a built-in [Model Context Protocol](https://modelcontextprotocol.io/) server. Any MCP-compatible agent can query your knowledge base:

```bash
sheaf mcp
```

**Available tools (9 total):**

| Tool | Description |
|------|-------------|
| `sheaf_search` | Full-text search across all entries |
| `sheaf_list` | List recent entries with filtering |
| `sheaf_get` | Get full entry details by ID |
| `sheaf_urgent` | Find time-sensitive entries (deadlines, CFPs) |
| `sheaf_collect` | Add a new URL to your collection |
| `sheaf_correct` | Correct a classification error |
| `sheaf_crystallize` | Crystallize knowledge cards from a topic |
| `sheaf_list_cards` | List crystallized cards (optional topic filter) |
| `sheaf_get_card` | Get full card details by ID |

## What You Can Collect

Sheaf handles more than just web articles:

| Input | Example | What Sheaf does |
|-------|---------|-----------------|
| **Web articles** | `sheaf collect https://arxiv.org/abs/2401.00000` | Fetches full text, extracts title/author/abstract, classifies topic |
| **AI chat shares** | `sheaf collect https://chatgpt.com/share/...` | Extracts the Q&A conversation, structures it as reusable knowledge |
| **WeChat / Zhihu posts** | `sheaf collect https://mp.weixin.qq.com/s/...` | Handles paywalls and dynamic rendering via Playwright fallback |
| **Pasted text** | `sheaf collect --text "Key insight..."` | Wraps freeform text into a structured entry with auto-classification |

Under the hood, every input goes through the same pipeline: **fetch → classify → summarize → store**. The output is always a structured entry your agents can search and cite.

## Architecture

```
URL → fetch → classify → summarize → store → query
         ↓          ↓          ↓         ↓
    3-strategy   LLM tags   summary   JSONL + MD
    fallback     + topics   + deadline  index

              ↓
         crystallize → KnowledgeCard → EmbeddingEngine
              ↓              ↓
          CLI/MCP       semantic search
```

| Module | Purpose |
|--------|---------|
| `sheaf_ai/` | Core — pipeline, storage, search, CLI, MCP server, crystallize engine |
| `sheaf_cards/` | Knowledge card engine — base types, embeddings, generation |
| `prompts/` | LLM prompt templates (classify, summarize, crystallize) |
| `data/` | Local knowledge base (JSONL + Markdown, gitignored) |

## Privacy & Local-First

**Your data never leaves your machine unless you choose to.**

- All content stored locally in `./data/` (configurable via `SHEAF_DATA_DIR`)
- LLM calls go to **your** chosen API provider
- No telemetry, no analytics, no accounts
- Markdown + JSONL format — fully portable, zero lock-in

## Configuration

Sheaf works with any OpenAI-compatible API:

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# Or any compatible endpoint (Together, Groq, DeepSeek, etc.)
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.together.xyz/v1
```

Optional: create a `.env` file in your working directory. See [.env.example](.env.example) for all options.

## Requirements

- **Python 3.10+**
- **An LLM API key** — any OpenAI-compatible endpoint
- **Playwright Chromium** (optional, for JS-heavy sites): `pip install -e ".[browser]" && playwright install chromium`

## Development

```bash
git clone https://github.com/zhelunSun/sheaf-ai.git
cd sheaf-ai
python -m pip install -e ".[dev]"
python -m pytest tests/ -q     # 288 passed, 13 opt-in E2E skipped
python -m ruff check sheaf_ai/ tests/ sheaf_cards/
```

Dependencies are managed through `pyproject.toml` extras. Use `.[dev]` for local development, `.[server]` for the HTTP API, and `.[browser]` for Playwright-based fetching.

## Alpha Status

Sheaf is in early alpha. The core collect → search → crystallize → MCP pipeline works and is tested with 288 passing tests. We're validating with real users before beta.

The browser extension under `extension/` is an experimental local companion for the HTTP API. Its manifest version is independent from the Python package version until the extension has its own release channel.

**Try it:** save 20+ links, run `sheaf crystallize <topic>`, then ask your agent to find them. If it works for you, open an issue or discussion to tell us what you'd change.

## License

[MIT](LICENSE)

---

*A **sheaf** is a bundle of harvested grain — the unit a farmer brings to market. In mathematics, a [sheaf](https://en.wikipedia.org/wiki/Sheaf_(mathematics)) attaches local data to open sets and glues them into a global picture. Sheaf the tool does both: gather scattered knowledge into coherent bundles, ready for your agents to consume or for you to share.*
