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

Default MCP surface = **4 core entry tools** (Issue #91). The remaining 7 stay
callable via `tools/call` for backward compat, but agents are guided to the
`sheaf` CLI (`--json`) by the deployed skill. Set `SHEAF_MCP_TOOLS=all` to
re-expose the full 11.

**Core (4, default in `tools/list`):**

| Tool | Purpose |
|------|---------|
| `sheaf_collect` | Collect a URL **or a pasted note** (`url` or `text`) |
| `sheaf_search` | Full-text + semantic search |
| `sheaf_crystallize` | Synthesize knowledge cards |
| `sheaf_get_card` | Get card details |

**Demoted (7, via CLI `--json` or `tools/call` / `SHEAF_MCP_TOOLS=all`):**

| Tool | CLI equivalent |
|------|-------------|
| `sheaf_list` | `sheaf list [--topic T] [--json]` |
| `sheaf_get` | `sheaf get <id> --json` |
| `sheaf_insights` | `sheaf insights --json` |
| `sheaf_list_cards` | `sheaf crystallize --list` |
| `sheaf_collect_batch` | `sheaf collect URL1 URL2 ...` |
| `sheaf_correct` | MCP `tools/call` only (complex nested params) |
| `sheaf_crosscheck` | MCP `tools/call`; see also `sheaf matrix <url>` |

**Deprecated (3, retained as fallback):**

| Tool | Replacement |
|------|-------------|
| `sheaf_urgent` | `sheaf list --filter urgent` |
| `sheaf_healthcheck` | HTTP `GET /health` |
| `sheaf_stats` | `sheaf list` returns `total` + `topics_summary` |

**Agent wiring (writes MCP config + deploys skill/AGENTS note):**

```bash
sheaf setup --target claude   # ~/.claude.json + ~/.claude/skills/sheaf-guide.md
sheaf setup --target codex    # ~/.codex/config.toml + ~/.codex/AGENTS.sheaf.md
sheaf setup --target cursor|windsurf|workbuddy
```

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
