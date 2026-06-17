---
name: sheaf-guide
description: Operate Sheaf — a local-first knowledge layer — to collect URLs into structured entries, search the knowledge base, and crystallize knowledge cards. Use this when the user wants to save/read/verify web content, search what they've collected, or distill cards from a topic. Covers the 4 MCP entry tools (sheaf_collect / sheaf_search / sheaf_crystallize / sheaf_get_card) and when to use the `sheaf` CLI for everything else (list, get, correct, crosscheck, insights, cards, batch).
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
| **Save** a URL → knowledge | MCP `sheaf_collect(url)` — or `sheaf collect <url>` |
| **Search** the KB | MCP `sheaf_search(query)` — or `sheaf search "<q>" --json` |
| **Crystallize** cards from a topic | MCP `sheaf_crystallize(topic)` — or `sheaf crystallize <topic>` |
| **Read** one card by ID | MCP `sheaf_get_card(card_id)` — or `sheaf crystallize --show <id>` |
| List / browse entries | `sheaf list [--json]` (`--filter urgent\|untagged`, `--category`, `--limit`, `--offset`) |
| Get one entry's full detail | `sheaf get <id> --json` |
| Correct a mis-classification | `sheaf correct <id> --field topics\|tags ... ` |
| Cross-verify an entry's claims | `sheaf crosscheck <id> --json` |
| Discover cross-topic links | `sheaf insights --json` |
| List / show knowledge cards | `sheaf crystallize --list` / `sheaf crystallize --show <card_id>` |
| Batch collect | `sheaf collect <url1> <url2> <url3>` |
| Health check after install | `sheaf doctor` |

> Set env `SHEAF_MCP_TOOLS=all` to re-expose the full 11-tool MCP surface if a
> workflow needs direct MCP access to list/get/crosscheck/etc.

## MCP tool details

### `sheaf_collect(url, force=false)`
Save a URL into the KB. Returns the structured entry
(`id`, `title`, `one_liner` summary, `topics`, `tags`, `importance`).
Prefer this MCP tool for single saves — the result is handed back structured.
For >1 URL, use the CLI: `sheaf collect a b c`.
Supported: arXiv, GitHub, web articles, ChatGPT/Claude shared chats, WeChat/Zhihu.

### `sheaf_search(query, mode="hybrid", limit=10, ...)`
Hybrid (BM25 + semantic) search by default; also `"keyword"` and `"quick"`.
Advanced syntax: `#tag`, `after:YYYY-MM-DD` / `before:`, `source:arxiv`,
`is:fav`. Cross-lingual synonyms expand automatically (AI ↔ 人工智能,
deep learning ↔ 深度学习). Returns ranked results with scores, match
locations, and snippets.

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

## Typical workflows

**Save a new source and verify it:**
1. `sheaf_collect` the URL
2. `sheaf get <id> --json` for full detail
3. `sheaf crosscheck <id> --json` to fact-check claims against other entries

**Answer "what did I read about X?":**
1. `sheaf_search "X"` → scan ranked results
2. `sheaf get <top_id> --json` for depth
3. `sheaf crystallize <topic>` once you have enough material

**Distill a topic into citable cards:**
1. Confirm ≥3 entries: `sheaf list --category <topic> --json`
2. `sheaf crystallize <topic>` → cards with confidence + evidence
3. `sheaf crystallize --show <card_id>` to read one in full

## Setup & troubleshooting
- Install: `pip install sheaf-ai` → `sheaf init --auto`
- One-command agent wiring: `sheaf setup --target claude|codex|cursor|windsurf`
  (also deploys this skill / AGENTS note)
- Diagnose: `sheaf doctor` — checks data dir, API key, MCP config, skill deploy
- API key: `sheaf config setup`, or set `SILICONFLOW_API_KEY` /
  `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`
