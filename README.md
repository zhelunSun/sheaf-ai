# Sheaf

> **Turn saved links into structured context for your AI agents.**

For AI-native researchers and builders who save too many links, Sheaf is a local-first knowledge layer that transforms scattered bookmarks into agent-consumable structured context. Paste a link. Sheaf fetches, classifies, summarizes, and makes it queryable — so your coding agent, research agent, or writing agent can find and use what you saved.

## Why Sheaf?

You save links every day — articles, repos, product launches, tutorials. But **95% never get opened again**.

Not because you're lazy. Because traditional bookmarking tools serve *human reading*, not *Agent workflows*. When you ask your coding agent "what did I read about MCP last week?", it has no idea.

Sheaf closes that gap. Every link you save becomes a **structured knowledge card** that any MCP-compatible agent can search, reference, and reason about.

## Quick Start

```bash
# Install
pip install sheaf-ai

# Set your LLM API key (OpenAI-compatible, e.g., SiliconFlow)
export SILICONFLOW_API_KEY=sk-...

# Collect your first link
sheaf https://example.com/article

# Search your collection
sheaf --search "MCP protocol"

# Check what's in your basket
sheaf
```

That's it. No accounts. No cloud. Your data lives in `~/.sheaf/` as Markdown + JSON.

## What It Does

1. **Paste a link** → Sheaf fetches, classifies, and summarizes it
2. **AI structures it** → tags, topics, content type — all automatic
3. **Query it back** → full-text search across your entire collection
4. **Agent-ready** → MCP server lets any LLM agent query your knowledge base

## Core Commands

```bash
sheaf <url>                # Collect an article / webpage / ChatGPT share link
sheaf --search <query>     # Full-text search across your collection
sheaf --mcp                # Start MCP server (stdio transport)
sheaf                      # Show collection stats
sheaf --init               # First-time onboarding with demo
```

## MCP Server

Sheaf ships with a built-in [Model Context Protocol](https://modelcontextprotocol.io/) server. Any MCP-compatible agent (Claude Desktop, Cursor, OpenClaw, etc.) can query your knowledge base:

```bash
sheaf --mcp
```

**Available MCP tools:**
| Tool | Description |
|------|-------------|
| `sheaf_search` | Full-text search across all entries |
| `sheaf_list` | List recent entries with filtering |
| `sheaf_get` | Get full entry details by ID |
| `sheaf_urgent` | Find time-sensitive entries |
| `sheaf_collect` | Add a new URL to your collection |
| `sheaf_correct` | Correct a classification error |

## Demo: Your Agent Remembers What You Read

Save 5 articles about AI agents:

```bash
sheaf https://mp.weixin.qq.com/s/-aI2DldsCRSt5AoRXr4XdQ
sheaf https://modelcontextprotocol.io/introduction
sheaf https://supermemory.ai/
# ... more links
```

Then ask your MCP-connected agent:

> "What have I saved about MCP security risks? Summarize the key points and tell me which ones are worth blogging about."

Your agent searches your Sheaf knowledge base, finds the relevant articles, and answers with source attribution.

## Architecture

```
URL → fetch → classify → summarize → store → query
         ↓          ↓          ↓         ↓
    3-strategy   LLM tags   summary   JSONL + MD
    fallback     + topics   + deadline  index
```

- **`sheaf_ai/`** — Core package (pipeline, storage, search, MCP server)
- **`sheaf_cards/`** — Knowledge card engine (embedding + generation)
- **`prompts/`** — LLM prompt templates
- **`data/`** — Local knowledge base (JSONL + Markdown, gitignored)

## Privacy & Local-First

**Your data never leaves your machine unless you choose to.**

- All content stored locally in `~/.sheaf/`
- LLM calls go to your chosen API provider (SiliconFlow, OpenAI, etc.)
- No telemetry, no analytics, no accounts
- Markdown + JSONL format — fully portable, zero lock-in

See [PRIVACY.md](PRIVACY.md) and [SECURITY.md](SECURITY.md) for details.

## Configuration

Set one environment variable and you're ready:

```bash
# Recommended: SiliconFlow (DeepSeek, Qwen, etc.)
export SILICONFLOW_API_KEY=sk-...

# Or any OpenAI-compatible endpoint
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1
```

Optional: create `~/.sheaf/.env` to persist settings.

## Requirements

- Python 3.10+
- An LLM API key (SiliconFlow, OpenAI, or any OpenAI-compatible endpoint)
- Playwright Chromium (auto-installed on first use, or run `playwright install chromium`)

## Alpha Status

Sheaf is in early alpha. Core collect/search/query/MCP pipeline is stable. We're validating with real users before beta.

**We'd love your feedback.** If you save 20+ links and your agent actually finds them useful, we've succeeded.

## License

MIT

---

*The name "Sheaf" comes from mathematics — a [sheaf](https://en.wikipedia.org/wiki/Sheaf_(mathematics)) attaches local data to the open sets of a topological space and glues them together into a consistent global picture. That's exactly what this tool does: gather scattered fragments of knowledge into a coherent whole.*
