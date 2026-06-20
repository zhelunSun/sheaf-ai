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
  <a href="tests/"><img src="https://img.shields.io/badge/tests-1010%20pass-brightgreen" alt="Tests"></a>
  <a href="https://pypi.org/project/sheaf-ai/"><img src="https://img.shields.io/pypi/v/sheaf-ai.svg" alt="PyPI"></a>
</p>

---

Sheaf turns the links you save every day into a **searchable knowledge base your AI agents can actually use**. Paste a link — it fetches, classifies, summarizes. Crystallize many into portable knowledge cards. Local-first, open-source, no cloud.

> A **sheaf** is a bundle of grain a farmer brings to market. Sheaf does the same for knowledge — gather, bundle, trade.

## Quick Start

**1 · Install (works everywhere):**

```bash
pip install sheaf-ai
sheaf config setup     # one-time: pick a provider, paste an OpenAI-compatible API key
```

**2 · Connect your agent:**

```bash
sheaf setup            # auto-detects Claude Code / Codex / Cursor / Windsurf / WorkBuddy,
                       # writes the MCP config + deploys the bundled skill
```

**3 · Use it:**

```bash
sheaf collect https://arxiv.org/abs/2401.00000   # save a link
sheaf search "transformer architecture"          # search your collection
sheaf crystallize AI                             # distill knowledge cards
```

No accounts, no cloud. Your data lives locally — `./data/` inside a project, else `~/.sheaf/data` — as Markdown + JSON. Override with `SHEAF_DATA_DIR`.

> **Even faster on Claude Code — no install at all:**
> ```bash
> claude mcp add sheaf -- uvx --from sheaf-ai sheaf-mcp
> ```
> `uvx` is the npm-style runner (`brew install uv` / `winget install astral-sh.uv`). Then set a key via `uvx --from sheaf-ai sheaf config setup`.

## Why

You save links every day — articles, papers, repos, tutorials. **90% never get opened again.**

Not because you're lazy. Bookmarks serve *human reading*, not *agent workflows*. Ask your coding agent "what did I read about MCP last week?" — it has no idea.

Sheaf fixes this. Every link becomes a **structured entry**. Crystallize enough of them and you get **knowledge cards** — portable, searchable, agent-ready.

## Features

| | What it does |
|---|---|
| 🌾 **Harvest** | Paste a link (or `--text` for a note). Sheaf fetches + classifies + summarizes — web articles, arXiv papers, WeChat / Zhihu, ChatGPT shares, pasted insights. |
| ✨ **Crystallize** | Distill 3+ entries into knowledge cards with confidence scores and evidence tracing. |
| 🤖 **Agent-ready** | Built-in MCP server — any agent searches, cites, and reasons over your knowledge base. |
| 🔒 **Local-first** | No cloud, no telemetry, no accounts. Your data stays on your machine. |

### Crystallize — your second brain

Sheaf's killer feature. Instead of letting bookmarks rot, `sheaf crystallize` synthesizes insights across entries:

```
$ sheaf crystallize AI
✨ 5 knowledge cards crystallized:
  📌 RAG faces retrieval relevance challenges (90%)
     RAG systems heavily depend on retrieval quality; errors degrade output reliability.
  📌 CRAG framework improves RAG robustness (95%)
     CRAG introduces a retrieval evaluator, web search augmentation, and document decomposition.
```

Each card carries a **confidence score**, **evidence tracing** (which sources contributed), **topic provenance**, and **tags**. Semantic-search across all of them with `sheaf crystallize --semantic "query"`.

## Connect Your Agent

`sheaf setup` writes the right MCP config for each tool and deploys a bundled skill / agents-note so the agent knows how to use Sheaf:

```bash
sheaf setup --target claude          # ~/.claude.json + ~/.claude/skills/sheaf-guide.md
sheaf setup --target codex           # ~/.codex/config.toml + ~/.codex/AGENTS.sheaf.md
sheaf setup --target cursor          # .cursor/mcp.json   (also: windsurf, workbuddy)
sheaf setup                          # auto-detect from CWD + installed agents
sheaf setup --target codex --dry-run # preview without writing
```

The MCP server exposes **4 core tools** — `sheaf_collect`, `sheaf_search`, `sheaf_crystallize`, `sheaf_get_card` — covering ~90% of automated agent workflows and kept lean by design (~1.5k vs ~5k tokens). 7 more stay reachable via the `sheaf` CLI (`--json`) or MCP `tools/call`; re-expose all with `SHEAF_MCP_TOOLS=all`. Full tool matrix + rationale: [Issue #91](https://github.com/zhelunSun/sheaf-ai/issues/91). Setup details: [docs/mcp-setup.md](docs/mcp-setup.md).

## Commands

```bash
sheaf help                       # grouped command overview
sheaf collect <url> | --text "…" # save a link, or a pasted note (tagged 'note')
sheaf search <query>             # full-text search (results show the entry id)
sheaf list [--page N]            # browse entries, paginated
sheaf get <id>                   # full detail of one entry
sheaf crystallize <topic>        # crystallize knowledge cards from a topic
sheaf stats | tags | weekly | insights | urgent
sheaf mcp                        # start the MCP server (stdio)
```

Run `sheaf <cmd> --help` for per-command options.

<details>
<summary><b>Agent-native: semantic exit codes</b></summary>

Sheaf returns typed exit codes so agents can branch on error type instead of parsing stderr:

| Code | Name | Meaning |
|------|------|---------|
| 0 | `SUCCESS` | completed successfully |
| 1 | `PARTIAL` | partial success (e.g. batch with skips) |
| 2 | `DUPLICATE` | entry already exists (dedup skip) |
| 3 | `QUALITY` | quality gate rejected the input |
| 4 | `NETWORK` | network / API connectivity failure |
| 5 | `CONFIG` | missing key, invalid URL, bad config |
| 6 | `LLM` | LLM API failure (rate limit, bad response) |
| 7 | `STORAGE` | file I/O / storage failure |

In `--json` mode, error payloads carry `exit_code`, `exit_code_name`, `error_type`, and `hint` for programmatic introspection.
</details>

## Privacy & Local-First

**Your data never leaves your machine unless you choose to.**

- All content stored locally — `./data/` inside a project, otherwise `~/.sheaf/data` (override: `SHEAF_DATA_DIR`)
- LLM calls go to **your** chosen API provider — nothing routed through Sheaf
- No telemetry, no analytics, no accounts
- Markdown + JSONL format — fully portable, zero lock-in

## Configuration

`sheaf config setup` is the recommended path — interactive, OS-agnostic, stores keys in `~/.sheaf/config.json` with restricted permissions. Any OpenAI-compatible endpoint works:

| Provider | Key env var | Default model |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `gpt-4o` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| SiliconFlow | `SILICONFLOW_API_KEY` | `deepseek-ai/DeepSeek-V3.2` |
| Together AI | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |

```bash
sheaf config use deepseek        # switch default provider
sheaf config list                # show configured providers
```

<details>
<summary><b>Advanced: env vars / <code>.env</code> (CI or temporary use)</b></summary>

Sheaf auto-reads a `.env` file in your working directory (see [.env.example](.env.example)). Or set per-shell — the only OS difference is the syntax:

```bash
# macOS / Linux
export OPENAI_API_KEY=sk-...
# Windows PowerShell:   $env:OPENAI_API_KEY="sk-..."
# Windows CMD:          set OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1   # optional — for non-OpenAI endpoints
```
</details>

## Architecture

```
URL → fetch → classify → summarize → store → query
       (3-strategy   (LLM tags   (summary    (JSONL + MD
        fallback)     + topics)   + deadline)  index)
                     ↓
              crystallize → KnowledgeCard → EmbeddingEngine → semantic search
```

| Module | Purpose |
|---|---|
| `sheaf_ai/` | Core — pipeline, storage, search, CLI, MCP server, crystallize engine |
| `sheaf_cards/` | Knowledge card engine — base types, embeddings, generation |
| `prompts/` | LLM prompt templates (classify, summarize, crystallize) |
| `data/` | Local knowledge base (JSONL + Markdown, gitignored) |

## Requirements

- **Python 3.10+**
- An OpenAI-compatible API key
- Playwright Chromium *(optional, JS-heavy sites)*: `pip install -e ".[browser]" && playwright install chromium`

## Development

```bash
git clone https://github.com/zhelunSun/sheaf-ai.git && cd sheaf-ai
python -m pip install -e ".[dev]"
python -m pytest tests/ -q          # 1003 passed, 19 skipped
python -m ruff check sheaf_ai/ tests/ sheaf_cards/
```

Extras: `.[dev]` for local dev, `.[server]` for the HTTP API, `.[browser]` for Playwright fetching.

## Status & Chrome Extension

Sheaf is early alpha. The collect → search → crystallize → MCP pipeline works and is covered by **1003 passing tests**. We're validating with real users before beta.

A Chrome extension (`extension/`) adds one-click collect + search from any page: start the local API with `sheaf serve`, load `extension/` unpacked (Chrome → Manage Extensions → Developer mode), then `Alt+Shift+S` or right-click any page → "🌾 Collect with Sheaf".

**Try it:** save 20+ links, run `sheaf crystallize <topic>`, then ask your agent to find them. If it clicks for you, open an issue or discussion and tell us what you'd change.

> ⭐ If Sheaf saves you time, a star on [GitHub](https://github.com/zhelunSun/sheaf-ai) helps others find it.

## License

[Apache 2.0](LICENSE)

---

*A **sheaf** is a bundle of harvested grain — the unit a farmer brings to market. In mathematics, a [sheaf](https://en.wikipedia.org/wiki/Sheaf_(mathematics)) attaches local data to open sets and glues them into a global picture. Sheaf the tool does both: gather scattered knowledge into coherent bundles, ready for your agents to consume or for you to share.*
