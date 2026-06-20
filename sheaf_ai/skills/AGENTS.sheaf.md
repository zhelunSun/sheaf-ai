# Sheaf — Knowledge Layer (Codex integration note)

This file is deployed by `sheaf setup --target codex` into `~/.codex/`.
Sheaf is wired into Codex as an MCP server (`~/.codex/config.toml` →
`[mcp_servers.sheaf]`) and exposes **4 tools** by default. Use the `sheaf` CLI
(with `--json`) for everything else.

## The 4 MCP tools (default surface)

| Tool | Use for |
|------|---------|
| `sheaf_collect(url=\|text=)` | Save a **URL** (fetch+summarize) **or a pasted note** (`text`, no fetch, tagged `content_type:"note"`) → structured entry |
| `sheaf_search(query, ...)` | Hybrid BM25 + semantic search. `#tag`, `after:`, `source:`, `is:fav`. Cross-lingual synonyms (AI ↔ 人工智能). Returns the **full entry** per hit — usually no separate read needed |
| `sheaf_crystallize(topic)` | Distill 3+ entries into knowledge cards with confidence + evidence tracing |
| `sheaf_get_card(card_id)` | Read one card in full (claim, evidence, confidence, sources) |

> **"收藏/保存/记下 X"**: X is a URL → `sheaf_collect(url=X)`; X is text/idea → `sheaf_collect(text=X)`.
>
> **🧠 Proactive capture (judge by information density)**: when the user states something dense & reusable — a **decision**, durable **fact/constraint**, **preference**, or **commitment** — capture it as `sheaf_collect(text=…)` without waiting for "save". Skip status/small-talk (low density). One self-contained sentence; AI titles it. This is the most frequent agent use of Sheaf.
>
> **🧠 Proactive recall**: before answering a *knowledge-shaped* question (about a topic/project you may have notes on), do ONE focused `sheaf_search`. Skip trivial/operational turns.
>
> **Make memory visible — lightly**: when your answer materially used Sheaf, add a one-line footer `📖 via Sheaf KB (3 notes)`. Skip when it didn't. Never reflexive.

## Everything else — use the `sheaf` CLI (always with `--json`)

```bash
sheaf list [--topic T] [--tag T] [--type T] [--page N] [--json]  # browse entries
sheaf get <id> --json                                            # full entry detail
sheaf insights --json                                            # cross-topic associations
sheaf crystallize --list                                         # list knowledge cards
sheaf crystallize --show <card_id>                               # read one card
sheaf collect <url1> <url2> <url3>                               # batch save
sheaf matrix <url>                                               # cross-source matrix for a URL
sheaf urgent                                                     # entries with upcoming deadlines
sheaf doctor                                                     # health check
```

> `sheaf_correct` and `sheaf_crosscheck` are demoted MCP tools — call them via
> MCP `tools/call` (or set `SHEAF_MCP_TOOLS=all` to re-expose the full 11-tool surface).

## Rule of thumb
- **MCP tool** for a single high-frequency action that needs a structured result
  returned to you (collect / search / crystallize).
- **CLI `--json`** for browsing, batch, deep analysis, corrections, scripting.

## Setup
- Install: `pip install sheaf-ai` → `sheaf init --auto`
- Re-wire: `sheaf setup --target codex`
- API key: `sheaf config setup`, or set `SILICONFLOW_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`
- Data lives locally in `~/.sheaf/data/` — no cloud, no accounts.
