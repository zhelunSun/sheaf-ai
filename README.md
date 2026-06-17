<p align="center">
  <b>English</b> | <a href="README_CN.md">中文</a>
</p>

<p align="center">
  <img src="assets/logo.png" alt="Sheaf Logo" width="360">
</p>

<h1 align="center">Sheaf</h1>

<p align="center"><b>Harvest your knowledge. Bundle it. Share it.</b></p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0"></a>
  <a href="tests/"><img src="https://img.shields.io/badge/tests-983%20pass-brightgreen" alt="Tests"></a>
  <a href="https://pypi.org/project/sheaf-ai/"><img src="https://img.shields.io/pypi/v/sheaf-ai.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/sheaf-ai/"><img src="https://img.shields.io/pypi/pyversions/sheaf-ai.svg" alt="Python Version"></a>
</p>

---

A **sheaf** is a bundle of grain — the basic unit a farmer brings to market. Sheaf does the same for knowledge: gather what you read, crystallize it into structured bundles, and make it tradable. Your AI agents can search, cite, and reason over everything you've collected.

**One-liner:** A global bookmark manager + agent memory layer. Local-first, open-source.

## Quick Start

```bash
# Install from PyPI (all platforms)
pip install sheaf-ai

# Or install from source
git clone https://github.com/zhelunSun/sheaf-ai.git
cd sheaf-ai
pip install -e .

# Configure your LLM API key (interactive wizard — recommended for all platforms)
sheaf config setup
```

> **Already have a key?** Set it via [environment variable](#option-2-environment-variables) instead.

<details>
<summary><b>macOS / Linux</b></summary>

```bash
export OPENAI_API_KEY=sk-...
```

</details>
<details>
<summary><b>Windows PowerShell</b></summary>

```powershell
$env:OPENAI_API_KEY="sk-..."
```

</details>
<details>
<summary><b>Windows CMD</b></summary>

```cmd
set OPENAI_API_KEY=sk-...
```

</details>

```bash
# First-time onboarding (collects 3 sample articles)
sheaf init

# Collect a link
sheaf collect https://arxiv.org/abs/2401.00000

# Search your collection
sheaf search "transformer architecture"

# Crystallize knowledge cards from collected articles
sheaf crystallize AI
```

No accounts. No cloud. Your data lives locally — `./data/` when run inside a project dir, otherwise `~/.sheaf/data` — as Markdown + JSON. Override with `SHEAF_DATA_DIR`.

## The Problem

You save links every day — articles, repos, papers, tutorials. **90% never get opened again.**

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
sheaf setup --target <platform>  # One-command MCP config (cursor/claude/workbuddy/windsurf)
sheaf init                  # First-time onboarding with demo

# API Key & Provider management
sheaf config setup          # Interactive setup wizard (recommended)
sheaf config list           # Show configured providers
sheaf config set-key --provider <id>   # Add/update a provider key
sheaf config use <provider> # Switch default provider
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

**Available tools (4 core + 7 CLI-only, see [Issue #91](https://github.com/zhelunSun/sheaf-ai/issues/91)):**

| Tool | Type | Description |
|------|------|-------------|
| `sheaf_collect` | Core MCP | Add a new URL to your collection |
| `sheaf_search` | Core MCP | Full-text + semantic search (keyword/hybrid/quick) |
| `sheaf_crystallize` | Core MCP | Crystallize knowledge cards from a topic |
| `sheaf_get_card` | Core MCP | Get full card details by ID |
| `sheaf_collect_batch` | CLI / on-demand | Batch-collect via `sheaf collect URL1 URL2 ...` |
| `sheaf_list` | CLI / on-demand | `sheaf list [--topic T] [--tag T] [--json]` |
| `sheaf_get` | CLI / on-demand | Full entry detail (MCP `tools/call` fallback) |
| `sheaf_correct` | CLI / on-demand | Correct classification (MCP `tools/call` fallback) |
| `sheaf_insights` | CLI / on-demand | `sheaf insights` — cross-topic associations |
| `sheaf_crosscheck` | CLI / on-demand | Fact matrix (MCP `tools/call`; see also `sheaf matrix`) |
| `sheaf_list_cards` | CLI / on-demand | `sheaf crystallize --list` |

The 4 core tools cover ~90% of automated agent workflows and keep the MCP schema
lean (~1.5k tokens vs ~5k before). The 7 demoted tools keep their handlers
registered for backward compat — call them via `tools/call`, or re-expose the
full set with `SHEAF_MCP_TOOLS=all sheaf mcp` (power users / migration). For
Claude Code & Codex, `sheaf setup` also deploys a bundled skill / AGENTS note
(`sheaf-guide.md` / `AGENTS.sheaf.md`) so the agent knows when to use the
`sheaf` CLI for the demoted tools.

## Agent Integration (One Command)

Connect Sheaf to your AI coding agent in a single step — this writes the MCP
config **and** deploys the bundled skill / agents note (Claude Code & Codex):

```bash
# Cursor / Windsurf / WorkBuddy
sheaf setup --target cursor      # writes .cursor/mcp.json
sheaf setup --target windsurf    # writes .windsurf/mcp.json
sheaf setup --target workbuddy   # writes ~/.workbuddy/mcp.json

# Claude Code — writes ~/.claude.json + deploys ~/.claude/skills/sheaf-guide.md
sheaf setup --target claude

# OpenAI Codex — writes ~/.codex/config.toml + deploys ~/.codex/AGENTS.sheaf.md
sheaf setup --target codex

# Auto-detect from CWD + installed agents
sheaf setup                      # detects claude/codex/cursor/windsurf/workbuddy
```

**Zero-install alternative (no `pip install` needed):**

```bash
# Claude Code
claude mcp add sheaf -- uvx --from sheaf-ai sheaf-mcp
# Codex — add to ~/.codex/config.toml:
#   [mcp_servers.sheaf]
#   command = "uvx"
#   args = ["--from", "sheaf-ai", "sheaf-mcp"]
```

**Preview without writing:**
```bash
sheaf setup --target codex --dry-run
```

See [docs/mcp-setup.md](docs/mcp-setup.md) for detailed platform guides and troubleshooting.

## What You Can Collect

Sheaf handles more than just web articles:

| Input | Example | What Sheaf does |
|-------|---------|-----------------|
| **Web articles** | `sheaf collect https://arxiv.org/abs/2401.00000` | Fetches full text, extracts title/author/abstract, classifies topic |
| **AI chat shares** | `sheaf collect https://chatgpt.com/share/...` | Extracts the Q&A conversation, structures it as reusable knowledge |
| **WeChat / Zhihu posts** | `sheaf collect https://mp.weixin.qq.com/s/...` | Handles paywalls and dynamic rendering via Playwright fallback |
| **Pasted text** | `sheaf collect --text "Key insight..."` | Wraps freeform text into a structured entry with auto-classification |

Under the hood, every input goes through the same pipeline: **fetch → classify → summarize → store**. The output is always a structured entry your agents can search and cite.

## Exit Codes (Agent-Native)

Sheaf returns **semantic exit codes** so agents can programmatically branch on error type instead of parsing stderr:

| Code | Name         | Meaning                                      |
|------|--------------|----------------------------------------------|
| 0    | `SUCCESS`    | Operation completed successfully             |
| 1    | `PARTIAL`    | Partial success (e.g. batch ops with skips) |
| 2    | `DUPLICATE`  | Entry already exists (dedup skip)            |
| 3    | `QUALITY`    | Content quality gate rejected the input      |
| 4    | `NETWORK`    | Network connectivity or API call failure     |
| 5    | `CONFIG`     | Missing API key, invalid URL, or bad config  |
| 6    | `LLM`        | LLM API failure (rate limit, bad response)   |
| 7    | `STORAGE`    | File I/O or data storage failure             |

In `--json` mode, error payloads include `exit_code`, `exit_code_name`, and `error_type` fields for programmatic introspection:

```json
{"success": false, "error": "Config error: missing API key", "exit_code": 5, "exit_code_name": "CONFIG", "error_type": "ConfigError", "hint": "Set SHEAF_API_KEY"}
```

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

- All content stored locally — `./data/` inside a project dir, otherwise `~/.sheaf/data` (override via `SHEAF_DATA_DIR`)
- LLM calls go to **your** chosen API provider
- No telemetry, no analytics, no accounts
- Markdown + JSONL format — fully portable, zero lock-in

## Configuration

Sheaf supports **any OpenAI-compatible API** and offers three ways to configure your keys:

### Option 1: Interactive Wizard (Recommended)

```bash
sheaf config setup
```

Guides you through selecting a provider, entering your API key (hidden input), and setting defaults. Keys are stored securely in `~/.sheaf/config.json` with restricted file permissions.

### Option 2: Environment Variables

Best for CI/CD or temporary use. Sheaf reads standard `.env` files automatically.

<details open>
<summary><b>macOS / Linux</b></summary>

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1   # optional
```
</details>
<details>
<summary><b>Windows PowerShell</b></summary>

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_BASE_URL="https://api.openai.com/v1"   # optional
```
</details>
<details>
<summary><b>Windows CMD</b></summary>

```cmd
set OPENAI_API_KEY=sk-...
set OPENAI_BASE_URL=https://api.openai.com/v1       # optional
```
</details>

Or create a `.env` file in your working directory:
```
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
```

### Option 3: CLI Config Commands

```bash
# Add/update a provider
sheaf config set-key --provider deepseek
sheaf config set-key --provider siliconflow

# Switch default provider
sheaf config use deepseek

# List configured providers
sheaf config list

# Remove a provider
sheaf config remove groq
```

### Supported Providers

| Provider | Key Env Var | Default Model |
|----------|-------------|---------------|
| OpenAI | `OPENAI_API_KEY` | `gpt-4o` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| SiliconFlow | `SILICONFLOW_API_KEY` | `deepseek-ai/DeepSeek-V3.2` |
| Together AI | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |

Set the default provider via `sheaf config use <id>` or the `DEFAULT_PROVIDER` environment variable.

## Requirements

- **Python 3.10+**
- **An LLM API key** — any OpenAI-compatible endpoint
- **Playwright Chromium** (optional, for JS-heavy sites): `pip install -e ".[browser]" && playwright install chromium`

## Development

```bash
git clone https://github.com/zhelunSun/sheaf-ai.git
cd sheaf-ai
python -m pip install -e ".[dev]"
python -m pytest tests/ -q     # 986 passed, 19 skipped
python -m ruff check sheaf_ai/ tests/ sheaf_cards/
```

Dependencies are managed through `pyproject.toml` extras. Use `.[dev]` for local development, `.[server]` for the HTTP API, and `.[browser]` for Playwright-based fetching.

## Alpha Status

Sheaf is in early alpha. The core collect → search → crystallize → MCP pipeline works and is tested with 986 passing tests. We're validating with real users before beta.

### Chrome Extension

The browser extension provides one-click collection and search from any webpage:

1. Start the local API: `sheaf serve`
2. Load the extension from `extension/` (Chrome → Manage Extensions → Developer mode → Load unpacked)
3. Click the Sheaf icon to collect the current page or search your knowledge base
4. Right-click any page or link → "🌾 Collect with Sheaf"
5. Keyboard shortcut: `Alt+Shift+S`

The extension connects to your local `sheaf serve` instance. Its manifest version is independent from the Python package.

**Try it:** save 20+ links, run `sheaf crystallize <topic>`, then ask your agent to find them. If it works for you, open an issue or discussion to tell us what you'd change.
## License

[Apache 2.0](LICENSE)

---

*A **sheaf** is a bundle of harvested grain — the unit a farmer brings to market. In mathematics, a [sheaf](https://en.wikipedia.org/wiki/Sheaf_(mathematics)) attaches local data to open sets and glues them into a global picture. Sheaf the tool does both: gather scattered knowledge into coherent bundles, ready for your agents to consume or for you to share.*
