# Sheaf — Knowledge Layer (Codex integration note)

This file is deployed by `sheaf setup --target codex` into `~/.codex/`.
Sheaf is wired into Codex as an MCP server (`~/.codex/config.toml` →
`[mcp_servers.sheaf]`) and exposes **3 tools** by default. Use the `sheaf` CLI
(with `--json`) for everything else.

## The 3 MCP tools (default surface)

| Tool | Use for |
|------|---------|
| `sheaf_collect(url)` | Save a URL → structured entry (id, title, summary, topics, tags) |
| `sheaf_search(query, ...)` | Hybrid BM25 + semantic search. `#tag`, `after:`, `source:`, `is:fav`. Cross-lingual synonyms (AI ↔ 人工智能) |
| `sheaf_crystallize(topic)` | Distill 3+ entries into knowledge cards with confidence + evidence tracing |

## Everything else — use the `sheaf` CLI (always with `--json`)

```bash
sheaf list [--json] [--filter urgent|untagged] [--category T]   # browse entries
sheaf get <id> --json                                            # full entry detail
sheaf correct <id> --field topics ...                            # fix classification
sheaf crosscheck <id> --json                                     # fact-verify claims (✅/⚠️/❌)
sheaf insights --json                                            # cross-topic associations
sheaf crystallize --list                                         # list knowledge cards
sheaf crystallize --show <card_id>                               # read one card
sheaf collect <url1> <url2> <url3>                               # batch save
sheaf doctor                                                     # health check
```

> Set `SHEAF_MCP_TOOLS=all` to re-expose the full 11-tool MCP surface.

## Rule of thumb
- **MCP tool** for a single high-frequency action that needs a structured result
  returned to you (collect / search / crystallize).
- **CLI `--json`** for browsing, batch, deep analysis, corrections, scripting.

## Setup
- Install: `pip install sheaf-ai` → `sheaf init --auto`
- Re-wire: `sheaf setup --target codex`
- API key: `sheaf config setup`, or set `SILICONFLOW_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`
- Data lives locally in `~/.sheaf/data/` — no cloud, no accounts.
