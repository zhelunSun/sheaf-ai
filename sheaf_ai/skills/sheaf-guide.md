---
name: sheaf-guide
description: Operate Sheaf — a local-first knowledge layer for deliberately curated sources — to collect URLs or approved notes, search the knowledge base, crystallize cards, and inspect evidence-governed memory. Covers the 4 default MCP entry tools, CLI operations, and the experimental evidence-memory executor.
---

# Sheaf — Agent Operating Guide

Sheaf is a local-first knowledge layer: paste a URL and Sheaf fetches,
classifies, summarizes, and stores a **structured entry**. Agents then search,
cite, and reason over everything collected. The stored corpus lives locally in
`~/.sheaf/data/` (Markdown + JSON). Collection and synthesis may send content to
the user's configured model provider; local storage does not imply local inference.

## Tool surface — 4 MCP entry points + CLI for the rest

To keep the tool list lean, only **4 MCP tools** are exposed by default.
Everything else is done via the `sheaf` CLI with `--json` for structured output.

| Goal | How |
|------|-----|
| **Save** a URL **or a pasted note** | MCP `sheaf_collect(url=…)` (fetch a link) or `sheaf_collect(text=…)` (store a note) — CLI: `sheaf collect <url>` / `sheaf collect --text "…"` |
| **Search** the KB | MCP `sheaf_search(query)` — or `sheaf search "<q>" --json` |
| **Crystallize** cards from a topic | MCP `sheaf_crystallize(topic)` — or `sheaf crystallize <topic>` |
| **Read** one card by ID | MCP `sheaf_get_card(card_id)` — or `sheaf crystallize --show <id>` |
| List / browse entries | `sheaf list [--topic T] [--tag T] [--type T] [--page N] [--json]` (deadline view: `sheaf urgent`) |
| Get one entry's full detail | `sheaf get <id> --json` |
| Correct a mis-classification | MCP `tools/call sheaf_correct` (demoted tool) |
| Cross-verify an entry's claims | MCP `tools/call sheaf_crosscheck`, or `sheaf matrix <url>` |
| Discover cross-topic links | `sheaf insights --json` |
| List / show knowledge cards | `sheaf crystallize --list` / `sheaf crystallize --show <card_id>` |
| Batch collect | `sheaf collect <url1> <url2> <url3>` |
| Apply a reviewed evidence transition | `sheaf memory apply --request FILE` |
| Inspect current or historical memory | `sheaf memory snapshot --topic T` / `sheaf memory history --topic T` |
| Health check after install | `sheaf doctor` |

> Set env `SHEAF_MCP_TOOLS=all` to re-expose the full 14-tool MCP surface if a
> workflow needs direct MCP access to list/get/crosscheck/evidence-memory/etc.

## MCP tool details

### `sheaf_collect(url=… | text=…, force=false)`
The agent's main **write** to the knowledge base. For most agents, **capturing
notes from conversation (`text`) is the most frequent and most valuable use** —
users express decisions, facts, and insights in chat far more often than they
paste URLs into a terminal. Give **exactly one** of:
- **`text`** *(the common agent case)* — store a conversational insight / decision /
  quote / takeaway directly (no fetch). Tagged `content_type:"note"`, gets an AI
  title + summary, bypasses the short-content gate. **Default to this** when the
  user shares content with no URL.
- **`url`** — fetch + classify + summarize a link (arXiv, GitHub, web articles,
  ChatGPT/Claude shared chats, WeChat/Zhihu, PDFs). Use when the user shares a link.

Returns the structured entry (`id`, `title`, `one_liner`, `topics`, `tags`,
`content_type`, `importance`). For >1 URL, use CLI: `sheaf collect a b c`.

> **🧠 Conversational capture defaults to suggest.** When the user states a dense,
> reusable decision, fact, constraint, preference, or commitment, propose one
> self-contained note and wait for approval before calling `sheaf_collect(text=…)`.
> Write immediately only when the user explicitly says save/collect/remember.
> Skip status updates, small talk, and transcript dumps.

> **"收藏/保存/记下 X"** decision:
> - X is a URL (`http…`) → `sheaf_collect(url=X)`
> - X is text/an idea → `sheaf_collect(text=X)`
> - Ambiguous (could be either) → if it parses as a URL, `url`; else `text`.

### `sheaf_search(query, mode="hybrid", limit=10, ...)`
Hybrid (BM25 + semantic) search by default; also `"keyword"` and `"quick"`.
Advanced syntax: `#tag`, `after:YYYY-MM-DD` / `before:`, `source:arxiv`,
`is:fav`. Cross-lingual synonyms expand automatically (AI ↔ 人工智能,
deep learning ↔ 深度学习). Returns ranked results with scores, match
locations, snippets, **and the full entry** (`id`, `title`, `summary`, …) —
so you usually have the content in-hand and don't need a separate read. For the
raw file path or to re-fetch later, note the `id` (human CLI also prints it:
`sheaf search "<q>"`).

> **🧠 Proactive recall** — the complement of capture. Before answering a
> **knowledge-shaped** question (about a topic / project / entity you may have
> notes on), do **one** focused `sheaf_search` — prior context often changes the
> answer. Skip for trivial or purely operational tasks; don't search every turn.

### `sheaf_crystallize(topic)`
Distills 3+ related entries into falsifiable **knowledge cards** — each with a
confidence score and evidence tracing to source entries. This is Sheaf's
differentiator. Call it once a topic has ≥3 collected entries.

### `sheaf_get_card(card_id)`
Read one crystallized knowledge card in full — claim, evidence, confidence,
tags, and links to the source entries that contributed. Use this to inspect or
cite a card surfaced by search or crystallize.

## Experimental evidence-governed memory

`sheaf memory apply` accepts only a closed transition request and resolves
`source_ids` against Entries already stored by Sheaf. Never invent a source ID,
never treat “the user saved it” as proof that it is true, and do not bypass a
contested state with an ordinary update. Use snapshot/history to show both sides
and the resolution basis. The projected evidence strength is an ordinal,
recomputable heuristic (`is_probability=false`), not calibrated confidence.

## When to choose MCP vs CLI

- **MCP tool**: single, high-frequency action that needs a structured result
  handed back to you (collect one URL, search, crystallize).
- **CLI** (`--json`): browsing, batch, deep analysis (crosscheck / insights),
  corrections, or anything you'd script/chain. Always append `--json` so the
  output is machine-parseable.

## Browse the knowledge base (MCP Resources)

Besides tools, Sheaf exposes **read-only resources** — browse the KB structure
without a tool side-effect. `resources/list` enumerates them; `resources/read`
with a `uri` fetches one.

| URI | What |
|------|------|
| `sheaf://entries/recent` | 10 most recent entries (id, title, topics, tags) |
| `sheaf://entries/{id}` | one entry's full detail (template — find ids via recent) |
| `sheaf://entries/{id}/raw` | the original fetched text — read to verify a summary or quote the source (no re-fetch) |
| `sheaf://stats` | total / topic / type / tag counts |
| `sheaf://tags` | tags ranked by frequency |

Good first move on a knowledge-shaped question: read `sheaf://entries/recent`
to see what's there before deciding to search.

## Make the memory visible — lightly

When your answer **materially drew on Sheaf memory**, add a one-line footer so
the user sees the value (not noise). Skip it entirely when Sheaf wasn't used.

- Recalled notes/cards: `📖 via Sheaf KB (3 notes, 1 card)`
- Just crystallized: `✨ synthesized 5 notes → 2 cards`

Rules: **conditional, never reflexive** — one short line, only when Sheaf truly
contributed. This is *operational transparency* (the "labor illusion"), not a
badge to slap on every reply.

## Typical workflows

**Save a new source and verify it:**
1. `sheaf_collect` the URL
2. `sheaf get <id> --json` for full detail
3. MCP `tools/call sheaf_crosscheck` to fact-check claims against other entries

**Answer "what did I read about X?":**
1. `sheaf_search "X"` → scan ranked results
2. `sheaf get <top_id> --json` for depth
3. `sheaf crystallize <topic>` once you have enough material

**Distill a topic into citable cards:**
1. Confirm ≥3 entries: `sheaf list --topic <topic> --json`
2. `sheaf crystallize <topic>` → cards with confidence + evidence
3. `sheaf crystallize --show <card_id>` to read one in full

## Setup & troubleshooting
- Install: `pip install sheaf-ai` → `sheaf init --auto`
- One-command agent wiring: `sheaf setup --target claude|codex|cursor|windsurf`
  (also deploys this skill / AGENTS note)
- Diagnose: `sheaf doctor` — checks data dir, API key, MCP config, skill deploy
- API key: `sheaf config setup`, or set `SILICONFLOW_API_KEY` /
  `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`
