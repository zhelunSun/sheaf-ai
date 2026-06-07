# Sheaf — Agent-Native Personal Knowledge Layer

> Harvest your knowledge. Bundle it. Share it.

## Quick Setup

```bash
# Install
pip install sheaf-ai

# Interactive setup (API key, data directory)
sheaf init --auto

# Or configure MCP directly for Claude Code:
claude mcp add sheaf -- python -m sheaf_ai.mcp_server
```

## Key Commands

```bash
sheaf collect <url>          # Collect article into knowledge base
sheaf search <query>         # Full-text + semantic search
sheaf crystallize <topic>    # Synthesize knowledge cards from 3+ articles
sheaf list                   # Browse recent entries
sheaf stats                  # Collection progress and milestones
sheaf doctor                 # Health check
sheaf serve                  # Start HTTP API server (port 8321)
```

## MCP Tools (for agents)

| Tool | Purpose |
|------|---------|
| `sheaf_search` | Search by keyword, hybrid (BM25+semantic), or quick mode |
| `sheaf_list` | Browse recent entries, filter by category |
| `sheaf_get` | Get full entry details by ID |
| `sheaf_collect` | Collect a URL into knowledge base |
| `sheaf_collect_batch` | Bulk collect multiple URLs |
| `sheaf_correct` | Submit corrections to entry classification |
| `sheaf_crystallize` | Synthesize knowledge cards on a topic |
| `sheaf_list_cards` | List crystallized knowledge cards |
| `sheaf_get_card` | Get knowledge card details by ID |
| `sheaf_urgent` | Get time-sensitive entries with deadlines |

## Architecture

```
sheaf_ai/              Core package (30 modules)
  collectors/          URL routing + content handlers (arxiv, github, pdf, spa)
  pipeline.py          Collect → classify → summarize → store
  mcp_server.py        MCP stdio server (10 tools)
  api.py               FastAPI HTTP transport
  search.py            BM25 + semantic hybrid search
  providers.py         LLM provider registry (single source of truth)
  storage.py           JSONL index + JSON entry storage
sheaf_cards/           Knowledge card engine (4 modules)
prompts/               LLM prompt templates (classify, summarize, crystallize)
tests/                 800+ tests with isolated data directories
extension/             Chrome Extension (Manifest V3)
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests -q           # Run tests
python -m ruff check sheaf_ai/      # Lint
python -m build                     # Build package
```

## Configuration

- **API keys**: Set `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or use `sheaf config setup`
- **Unified key**: Set `SHEAF_API_KEY` (auto-detects provider from key prefix)
- **Data directory**: Defaults to `~/.sheaf/data` (or `./data` in project dirs)
- **Models**: Override via `DEFAULT_MODEL`, `CLASSIFY_MODEL`, `SUMMARIZE_MODEL`

## Commit Conventions

- `feat:` new features, `fix:` bug fixes, `refactor:` restructuring
- `docs:` documentation, `chore:` maintenance, `ci:` CI/CD
- Reference issues: `feat: [#42] add feature`

## License

Apache 2.0 — see [LICENSE](LICENSE)
