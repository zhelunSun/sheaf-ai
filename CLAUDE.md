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

**Active (10):**

| Tool | Purpose |
|------|---------|
| `sheaf_search` | Full-text + semantic search |
| `sheaf_list` | Browse entries, with pagination + filters |
| `sheaf_get` | Get full entry by ID |
| `sheaf_collect` | Collect a URL |
| `sheaf_collect_batch` | Bulk collect URLs |
| `sheaf_correct` | Correct entry classification |
| `sheaf_crystallize` | Synthesize knowledge cards |
| `sheaf_list_cards` | List knowledge cards |
| `sheaf_get_card` | Get card details |
| `sheaf_insights` | Cross-topic associations |

**Deprecated (3, retained as fallback):**

| Tool | Replacement |
|------|-------------|
| `sheaf_urgent` | `sheaf_list` with `filter="urgent"` |
| `sheaf_healthcheck` | HTTP `GET /health` |
| `sheaf_stats` | `sheaf_list` returns `total` + `topics_summary` |

## Issue Governance (Agent Quick Reference)

When creating or managing issues, follow these rules:

1. **Title**: English, Conventional Commit prefix (`fix:`, `feat:`, `refactor:`, `docs:`)
2. **Labels**: At least one type label (`bug`/`enhancement`/`release-blocker`/`internal`) + optional priority (`P0`/`P1`/`P2`)
3. **Milestone**: Every open issue must have a milestone
4. **Internal items** (business plans, thesis, personal workflow): Do NOT file as public issues — use `internal` label if already exists, or move to private docs
5. **Comment style**: Professional, neutral. No personal address. Use `Status:` / `Validation:` / `Next action:` format.
6. **Language**: Public-facing content (titles, bodies, comments) in English. Chinese supplementary notes OK below English.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

## Release Checklist

Before any version bump, follow [docs/RELEASE-CHECKLIST.md](docs/RELEASE-CHECKLIST.md).

## Requirements

- Any OpenAI-compatible API key: `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or `SHEAF_API_KEY`
- Data stored locally at `~/.sheaf/data`
