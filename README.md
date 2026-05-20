# Sheaf

> **Paste links. Ask your agent later.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-68%20pass-brightgreen)](tests/)
<!-- PyPI badges — uncomment after publishing to PyPI -->
<!-- [![PyPI](https://img.shields.io/pypi/v/sheaf-ai.svg)](https://pypi.org/project/sheaf-ai/) -->
<!-- [![PyPI - Python Version](https://img.shields.io/pypi/pyversions/sheaf-ai.svg)](https://pypi.org/project/sheaf-ai/) -->

Sheaf is a local-first tool that turns saved links into structured context your AI agents can search and use. Paste a link — Sheaf fetches, classifies, summarizes, and stores it locally. Your MCP-compatible agent (Claude Desktop, Cursor, etc.) can then query your collection.

## Quick Start

```bash
# Install (from source — PyPI coming soon)
git clone https://github.com/zhelunSun/sheaf-ai.git
cd sheaf-ai
pip install -e .

# Set your LLM API key (any OpenAI-compatible endpoint)
export OPENAI_API_KEY=sk-...

# Collect your first link
sheaf https://arxiv.org/abs/2401.00000

# Search your collection
sheaf --search "transformer architecture"

# Check what's in your collection
sheaf
```

That's it. No accounts. No cloud. Your data lives in `./data/` as Markdown + JSON.

## The Problem

You save links every day — articles, repos, papers, tutorials. **95% never get opened again.**

Not because you're lazy. Because bookmarks serve *human reading*, not *agent workflows*. When you ask your coding agent "what did I read about MCP last week?", it has no idea.

Sheaf fixes this. Every link you save becomes a **structured entry** that any MCP-compatible agent can search, reference, and reason about.

## What It Does

1. **Paste a link** → Sheaf fetches, classifies, and summarizes it
2. **AI structures it** → tags, topics, content type, deadlines — all automatic
3. **Query it back** → full-text search across your entire collection
4. **Agent-ready** → built-in MCP server lets any LLM agent query your knowledge base

## Core Commands

```bash
sheaf <url>                # Collect an article, paper, or webpage
sheaf --search <query>     # Full-text search across your collection
sheaf --mcp                # Start MCP server (stdio transport)
sheaf                      # Show collection stats
sheaf --init               # First-time onboarding with demo
sheaf --weekly             # Weekly summary report
sheaf --insights           # Cross-topic association discovery
sheaf --urgent             # Show entries with upcoming deadlines
sheaf --version            # Show version
```

## MCP Server

Sheaf ships with a built-in [Model Context Protocol](https://modelcontextprotocol.io/) server. Any MCP-compatible agent can query your knowledge base:

```bash
sheaf --mcp
```

**Available tools:**

| Tool | Description |
|------|-------------|
| `sheaf_search` | Full-text search across all entries |
| `sheaf_list` | List recent entries with filtering |
| `sheaf_get` | Get full entry details by ID |
| `sheaf_urgent` | Find time-sensitive entries (deadlines, CFPs) |
| `sheaf_collect` | Add a new URL to your collection |
| `sheaf_correct` | Correct a classification error |

### Example: Your Agent Remembers What You Read

```bash
sheaf https://arxiv.org/abs/2312.06648
sheaf https://modelcontextprotocol.io/introduction
```

Then ask your MCP-connected agent:

> "What have I saved about MCP? Summarize the key points."

Your agent searches your Sheaf knowledge base, finds the relevant entries, and answers with source attribution.

## Architecture

```
URL → fetch → classify → summarize → store → query
         ↓          ↓          ↓         ↓
    3-strategy   LLM tags   summary   JSONL + MD
    fallback     + topics   + deadline  index
```

| Module | Purpose |
|--------|---------|
| `sheaf_ai/` | Core — pipeline, storage, search, CLI, MCP server |
| `sheaf_cards/` | Knowledge card engine — embedding + generation |
| `prompts/` | LLM prompt templates |
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
pip install -e ".[dev]"
pytest tests/ -v
```

## Alpha Status

Sheaf is in early alpha. The core collect → search → query → MCP pipeline works and is tested with 68 tests. We're validating with real users before beta.

**Try it:** save 20+ links, then ask your agent to find them. If it works for you, open an issue or discussion to tell us what you'd change.

## License

[MIT](LICENSE)

---

*The name "Sheaf" comes from mathematics — a [sheaf](https://en.wikipedia.org/wiki/Sheaf_(mathematics)) attaches local data to open sets and glues them into a consistent global picture. That's what this tool does: gather scattered fragments of knowledge into a coherent whole your agents can use.*
