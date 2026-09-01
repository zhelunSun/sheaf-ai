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
> **🧠 Conversational capture defaults to suggest**: when the user states a dense, reusable decision/fact/constraint/preference/commitment, propose one self-contained note and wait for approval. Write immediately only after an explicit save/collect/remember request. Skip status and transcript dumps.
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
sheaf memory apply --request FILE                               # reviewed evidence transition
sheaf memory snapshot --topic T                                 # active / contested state
sheaf memory history --topic T                                  # immutable audit history
sheaf urgent                                                     # entries with upcoming deadlines
sheaf doctor                                                     # health check
```

> `sheaf_correct` and `sheaf_crosscheck` are demoted MCP tools — call them via
> MCP `tools/call` (or set `SHEAF_MCP_TOOLS=all` to re-expose the full 14-tool surface).

## Browse the KB (MCP Resources, read-only)

`resources/list` → `sheaf://entries/recent` · `sheaf://entries/{id}` · `sheaf://stats` · `sheaf://tags`. Read one with `resources/read {uri}`. Peek `sheaf://entries/recent` before searching a knowledge-shaped question.

## Rule of thumb
- **MCP tool** for a single high-frequency action that needs a structured result
  returned to you (collect / search / crystallize).
- **CLI `--json`** for browsing, batch, deep analysis, corrections, scripting.

## Setup
- Install: `pip install sheaf-ai` → `sheaf init --auto`
- Re-wire: `sheaf setup --target codex`
- API key: `sheaf config setup`, or set `SILICONFLOW_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`
- Stored data lives locally in `~/.sheaf/data/`; configured model inference may be remote.
