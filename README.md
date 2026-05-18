# Sheaf

> Your personal knowledge layer. Paste a link, AI does the rest.

**Sheaf** transforms scattered bookmarks into structured, agent-consumable knowledge assets. One sheaf at a time.

## What it does

You know the feeling — you bookmark an article, save a tweet, copy a link... and never look at it again. Sheaf fixes this:

1. **Paste a link** → Sheaf fetches, classifies, and summarizes it
2. **AI structures it** → tags, topics, deadlines, content type — all automatic
3. **Query it back** → full-text search, weekly reports, cross-topic insights
4. **Agent-ready** → MCP server for LLM agents to query your knowledge base

## Quick Start

```bash
# Install
pip install sheaf-ai

# Install Playwright browser (first time only)
playwright install chromium

# Configure API key
cp .env.example .env
# Edit .env with your LLM API key (OpenAI-compatible)

# Initialize
sheaf --init

# Collect your first sheaf
sheaf https://example.com/article
```

## Usage

```bash
sheaf <url>                # Collect an article / webpage / ChatGPT share link
sheaf --search <query>     # Full-text search across your collection
sheaf --tags               # View tag statistics
sheaf --trends             # Topic trends over time
sheaf --weekly             # Weekly summary report
sheaf --insights           # Cross-topic association discovery
sheaf --urgent             # Show entries with upcoming deadlines
sheaf --reclassify         # Re-run AI classification on existing entries
sheaf                      # Show collection stats
```

## MCP Server

Sheaf ships with a built-in [Model Context Protocol](https://modelcontextprotocol.io/) server, so any MCP-compatible agent can query your knowledge base:

```bash
# Start the MCP server (stdio transport)
sheaf --mcp
```

**Available MCP tools:**
| Tool | Description |
|------|-------------|
| `search` | Full-text search across all entries |
| `list` | List recent entries with filtering |
| `get` | Get full entry details by ID |
| `urgent` | Find time-sensitive entries |
| `collect` | Add a new URL to your collection |
| `correct` | Correct a classification error |

## Supported Content

| Source | Support |
|--------|---------|
| Web articles | Full extraction with 3-strategy fallback |
| ChatGPT share links | Structured conversation archiving |
| WeChat articles | Full content extraction |
| Any URL | Playwright-powered fallback |

## Architecture

```
URL → fetch → classify → summarize → store → query
         ↓          ↓          ↓         ↓
    3-strategy   LLM tags   summary   JSONL + MD
    fallback     + topics   + deadline  index
```

- **`uc/`** — Core package (pipeline, storage, search, MCP server)
- **`prompts/`** — LLM prompt templates
- **`data/`** — Local knowledge base (JSONL + Markdown, gitignored)

## Configuration

Sheaf uses environment variables for LLM API access. Copy `.env.example` to `.env`:

```bash
# Required: at least one LLM provider
SILICONFLOW_API_KEY=sk-...     # SiliconFlow (DeepSeek, Qwen, etc.)
OPENAI_API_KEY=sk-...          # OpenAI-compatible endpoint
DEFAULT_PROVIDER=siliconflow   # or "openai"
DEFAULT_MODEL=deepseek-ai/DeepSeek-V3.2
```

## Requirements

- Python 3.10+
- An LLM API key (OpenAI-compatible endpoint)
- Playwright Chromium (auto-installed via `playwright install chromium`)

## License

MIT

---

*The name "Sheaf" comes from mathematics — a [sheaf](https://en.wikipedia.org/wiki/Sheaf_(mathematics)) attaches local data to the open sets of a topological space and glues them together into a consistent global picture. That's exactly what this tool does: gather scattered fragments of knowledge into a coherent whole.*
