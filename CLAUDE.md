# Sheaf — Quick Agent Setup

## Install & Configure

```bash
pip install sheaf-ai
sheaf init --auto
```

## MCP Server (for Claude Code, Cursor, etc.)

```bash
claude mcp add sheaf -- python -m sheaf_ai.mcp_server
```

Or with uvx (no install needed):
```bash
claude mcp add sheaf -- uvx --from sheaf-ai sheaf-mcp
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `sheaf_search` | Full-text + semantic search |
| `sheaf_list` | Browse entries, with pagination |
| `sheaf_get` | Get full entry by ID |
| `sheaf_collect` | Collect a URL |
| `sheaf_collect_batch` | Bulk collect URLs |
| `sheaf_correct` | Correct entry classification |
| `sheaf_crystallize` | Synthesize knowledge cards |
| `sheaf_list_cards` | List knowledge cards |
| `sheaf_get_card` | Get card details |
| `sheaf_urgent` | Time-sensitive entries |
| `sheaf_healthcheck` | Server health probe |
| `sheaf_stats` | Collection statistics |
| `sheaf_insights` | Cross-topic associations |

## Requirements

- Any OpenAI-compatible API key: `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or `SHEAF_API_KEY`
- Data stored locally at `~/.sheaf/data`
