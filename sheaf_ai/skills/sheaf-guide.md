---
name: sheaf-guide
description: Operate Sheaf — a local-first knowledge layer — to collect URLs into structured entries, search the knowledge base, and crystallize knowledge cards. Use this when the user wants to save/read/verify web content, search what they've collected, or distill cards from a topic. Covers the 4 MCP entry tools (sheaf_collect / sheaf_search / sheaf_crystallize / sheaf_get_card), the `sheaf` CLI for the rest (list, get, insights, cards, batch), and MCP `tools/call` for correct/crosscheck.
---

# Sheaf — Agent Operating Guide

Sheaf is a local-first knowledge layer: paste a URL and Sheaf fetches,
classifies, summarizes, and stores a **structured entry**. Agents then search,
cite, and reason over everything collected. Data lives in `~/.sheaf/data/`
(Markdown + JSON). No cloud, no accounts.

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
| Health check after install | `sheaf doctor` |

> Set env `SHEAF_MCP_TOOLS=all` to re-expose the full 11-tool MCP surface if a
> workflow needs direct MCP access to list/get/crosscheck/etc.

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

> **🧠 Proactive capture — judge by information density.** Capture as a note
> *without* waiting for an explicit "save" when the user states something **dense
> and reusable**: **decisions** ("we'll use Postgres") · **durable facts /
> constraints** (deadlines, budgets, requirements) · **preferences** ·
> **commitments** ("I'll send it Friday"). These survive the moment — that's the
> signal they're worth keeping. **Skip** status updates, small talk, and ephemeral
> chatter (low density). One self-contained sentence each (not a transcript dump);
> the AI titles + summarizes it. Light ack: `📝 Noted: <title>`.

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

## When to choose MCP vs CLI

- **MCP tool**: single, high-frequency action that needs a structured result
  handed back to you (collect one URL, search, crystallize).
- **CLI** (`--json`): browsing, batch, deep analysis (crosscheck / insights),
  corrections, or anything you'd script/chain. Always append `--json` so the
  output is machine-parseable.

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
