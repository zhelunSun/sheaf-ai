<p align="center">
  <b>English</b> | <a href="README_CN.md">中文</a>
</p>

<p align="center">
  <img src="assets/logo.png" alt="Sheaf Logo" width="360">
</p>

<h1 align="center">Sheaf</h1>

<p align="center"><b>Choose good sources. Turn them into knowledge your agents can verify.</b></p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0"></a>
  <a href="https://github.com/zhelunSun/sheaf-ai/actions/workflows/ci.yml"><img src="https://github.com/zhelunSun/sheaf-ai/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/sheaf-ai/"><img src="https://img.shields.io/pypi/v/sheaf-ai.svg" alt="PyPI"></a>
</p>

---

Sheaf turns the technical sources you deliberately choose into a **searchable, inspectable knowledge base your AI agents can actually use**. Your selections carry your information taste into the agent's working context; source provenance keeps that taste from being mistaken for truth. Local-first and open-source.

> A **sheaf** is a bundle of harvested grain. Sheaf gathers deliberately chosen sources into knowledge that remains tied to its evidence.

> **Design note:** Sheaf is not meant to be another generic conversation-memory service. Deliberately curated sources are the input; the goal is a local, source-backed knowledge layer that coding and research agents can search, quote, challenge, and check.
> Read the v0.7.0 discussion: [Sheaf v0.7.0: a local-first knowledge layer for coding agents](https://github.com/zhelunSun/sheaf-ai/discussions/94)


## Quick Start

**1 · Install (works everywhere):**

```bash
pip install sheaf-ai
sheaf config setup     # one-time: pick a provider, paste an OpenAI-compatible API key
```

**2 · Connect your agent:**

```bash
sheaf setup            # auto-detects Claude Code / Codex / Cursor / Windsurf / WorkBuddy,
                       # writes the MCP config + deploys the bundled skill
```

**3 · Use it:**

```bash
sheaf collect https://arxiv.org/abs/2401.00000   # save a link
sheaf search-index --rebuild                     # opt in to Entry embeddings (provider call)
sheaf search "transformer architecture"          # hybrid search; diagnostic keyword fallback
sheaf crystallize AI                             # distill knowledge cards
```

No Sheaf account or hosted storage is required. Your corpus lives locally — `./data/` inside a project, else `~/.sheaf/data` — as Markdown + JSON. Model inference is sent to the provider you configure. Override the data path with `SHEAF_DATA_DIR`.

> **Even faster on Claude Code — no install at all:**
> ```bash
> claude mcp add sheaf -- uvx --from sheaf-ai sheaf-mcp
> ```
> `uvx` is the npm-style runner (`brew install uv` / `winget install astral-sh.uv`). Then set a key via `uvx --from sheaf-ai sheaf config setup`.

## Why

Saved articles, papers, repositories, and tutorials are difficult to reuse in an
agent workflow. A bookmark can tell you where a page was; it cannot tell an
agent which source supports a claim or how that claim changed.

Sheaf fixes this. Every link becomes a **structured entry**. Crystallize enough of them and you get **knowledge cards** — portable, searchable, agent-ready.

## Features

| | What it does |
|---|---|
| 🌾 **Collect — foundation** | Paste a link or note. Sheaf fetches, cleans, classifies, and preserves its source. |
| 🔎 **Retrieve — core path** | Hybrid retrieval combines BM25 with a direct Entry vector index, exposes stale/unavailable diagnostics, and falls back to keyword search without hiding the degradation. |
| ✨ **Crystallize — core path** | Distill multiple entries into knowledge cards with resolvable source links. |
| 🧭 **Evolve — core path** | Apply schema-constrained create, update, merge, contest, resolve, and retire transitions with immutable history. Evidence strength is an explainable ordinal heuristic, not a probability. |
| 🤖 **Agent-ready** | Built-in MCP server — any agent searches, cites, and reasons over your knowledge base. |
| 🔒 **Local-first** | Knowledge files stay local; no Sheaf account or telemetry. Model-backed steps use the provider you configure. |

### Crystallize — curated sources into reusable claims

Crystallization is one of Sheaf's three core algorithm paths. Instead of leaving
sources as disconnected bookmarks, `sheaf crystallize` produces reusable,
source-linked claims:

```
$ sheaf crystallize AI
✨ 5 knowledge cards crystallized:
  📌 RAG faces retrieval relevance challenges (90%)
     RAG systems heavily depend on retrieval quality; errors degrade output reliability.
  📌 CRAG framework improves RAG robustness (95%)
     CRAG introduces a retrieval evaluator, web search augmentation, and document decomposition.
```

Each batch card carries **evidence tracing** (which sources contributed), **topic provenance**, and **tags**. Semantic-search across all of them with `sheaf crystallize --semantic "query"`.

The experimental evidence-governed path is deliberately stricter. Ledger
schema 3 verifies quote or character-span evidence identity and replays older
ledgers. `evidence-rule-v3` derives non-duplicate groups only from a shared
`source_key`, a trusted full SHA-256 evidence digest, or a persisted
`exact`/`near_duplicate` relation; ordinary self-declared provenance never
overrides deduplication. Those groups are not yet treated as verified independent
corroboration: while a trusted provenance registry is absent,
`independent_source_count` remains conservatively `1` when evidence exists and
the corroboration bonus is disabled. Historical v1/v2 scores replay unchanged.
Official correction requires primary status, explicit
topic/fact-key authority scope, and a persisted `corrects` relation. It does not
claim that an LLM policy or confidence probability has already been calibrated:

```bash
sheaf memory apply --request transition.json
sheaf memory snapshot --topic "Agent memory"
sheaf memory history --topic "Agent memory"
```

See [the product and evaluation proposal](docs/EVIDENCE-GOVERNED-MEMORY-PROPOSAL.md) and the frozen [G0-G3 protocol](evals/evidence-governed-memory/PROTOCOL.md) for the implemented/proposed boundary.
The deterministic executor scenario is independently replayable with
`python evals/evidence-governed-memory/run_executor_acceptance.py`; it checks
provenance, idempotency, contest preservation, official correction, and audit
history without pretending to be an LLM-quality benchmark.

SPLIT and NOOP have an auditable preview-first decision-trace protocol. A SPLIT
is planned as UPDATE + CREATE with one `decision_id`, checks that its target head
has not moved, and refuses to run without an external atomic batch executor.
There is no production atomic SPLIT adapter in this repository yet; tests use an
atomic fake, so this is a fail-closed integration contract rather than a shipped
end-to-end executor.

The broader [architecture and evaluation contract](docs/ARCHITECTURE-AND-EVALUATION.md)
defines the three core algorithm paths, their current maturity, the no-user
test ladder, and the experiments still required for comparative claims.

### Retrieval evidence snapshot

The first frozen retrieval experiment contains 22 Entries and 36 queries. Its
manifest locks corpus, query, and evaluator-only qrels hashes, and rankings are
produced before qrels are loaded. The checked-in local-LSA run is a classical
TF-IDF/SVD baseline—not a neural embedding result. Development selection chose
`linear-0.25 @ 0.4`; held-out Recall@5 is `0.9375`, MRR `1.0`, nDCG@5 `0.9498`,
and no-answer FPR `1.0`. It did not outperform keyword retrieval and did not
solve abstention. A live embedding run was not produced because credentials
were unavailable. See the [frozen retrieval report](evals/retrieval-frozen/README.md).

The current relevance gate is a backend/version-specific experimental signal,
not a probability or portable threshold. If semantic retrieval degrades,
production search returns to the keyword-coverage scale.

## Connect Your Agent

`sheaf setup` writes the right MCP config for each tool and deploys a bundled skill / agents-note so the agent knows how to use Sheaf:

```bash
sheaf setup --target claude          # ~/.claude.json + ~/.claude/skills/sheaf-guide.md
sheaf setup --target codex           # ~/.codex/config.toml + ~/.codex/AGENTS.sheaf.md
sheaf setup --target cursor          # .cursor/mcp.json   (also: windsurf, workbuddy)
sheaf setup                          # auto-detect from CWD + installed agents
sheaf setup --target codex --dry-run # preview without writing
```

> **MCP + skill are one install.** `sheaf setup` deploys the MCP server **and** the skill together — the skill is what tells your agent *when* to proactively capture a note or recall from the KB, so it's not optional decoration. Prefer it over the bare `uvx` one-liner (which wires MCP only). Do it all at once — key + MCP + skill + health check — with `sheaf init --auto`.

The MCP server exposes **4 core tools** — `sheaf_collect`, `sheaf_search`, `sheaf_crystallize`, `sheaf_get_card` — and keeps the default prompt surface lean. 10 more, including the three evidence-memory tools, remain reachable via the CLI or explicit MCP `tools/call`; re-expose all 14 with `SHEAF_MCP_TOOLS=all`. Full tool matrix + rationale: [Issue #91](https://github.com/zhelunSun/sheaf-ai/issues/91). Setup details: [docs/mcp-setup.md](docs/mcp-setup.md).

Agents can also **browse** the knowledge base read-only via MCP Resources — `sheaf://entries/recent`, `sheaf://entries/{id}`, `sheaf://stats`, `sheaf://tags` (`resources/list` / `resources/read`). Spec: [docs/agent-query-spec.md](docs/agent-query-spec.md).

## Commands

```bash
sheaf help                       # grouped command overview
sheaf collect <url> | --text "…" # save a link, or a pasted note (tagged 'note')
sheaf search <query>             # hybrid Entry search (results show id + diagnostics)
sheaf search-index --rebuild     # explicitly build/rebuild Entry embeddings
sheaf list [--page N]            # browse entries, paginated
sheaf get <id>                   # full detail of one entry
sheaf crystallize <topic>        # crystallize knowledge cards from a topic
sheaf memory apply --request FILE # apply a validated evidence transition
sheaf memory snapshot            # read active and contested memory state
sheaf memory history             # inspect immutable transition history
sheaf stats | tags | weekly | insights | urgent
sheaf mcp                        # start the MCP server (stdio)
```

Run `sheaf <cmd> --help` for per-command options.

<details>
<summary><b>Agent-native: semantic exit codes</b></summary>

Sheaf returns typed exit codes so agents can branch on error type instead of parsing stderr:

| Code | Name | Meaning |
|------|------|---------|
| 0 | `SUCCESS` | completed successfully |
| 1 | `PARTIAL` | partial success (e.g. batch with skips) |
| 2 | `DUPLICATE` | entry already exists (dedup skip) |
| 3 | `QUALITY` | quality gate rejected the input |
| 4 | `NETWORK` | network / API connectivity failure |
| 5 | `CONFIG` | missing key, invalid URL, bad config |
| 6 | `LLM` | LLM API failure (rate limit, bad response) |
| 7 | `STORAGE` | file I/O / storage failure |

In `--json` mode, error payloads carry `exit_code`, `exit_code_name`, `error_type`, and `hint` for programmatic introspection.
</details>

## Privacy & Local-First

**Your stored corpus stays on your machine; inference follows your provider choice.**

- All content stored locally — `./data/` inside a project, otherwise `~/.sheaf/data` (override: `SHEAF_DATA_DIR`)
- LLM calls go to **your** chosen API provider — nothing routed through Sheaf
- No telemetry, no analytics, no accounts
- Markdown + JSONL format — fully portable, zero lock-in

## Configuration

`sheaf config setup` is the recommended path — interactive, OS-agnostic, stores keys in `~/.sheaf/config.json` with restricted permissions. Any OpenAI-compatible endpoint works:

| Provider | Key env var | Default model |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `gpt-4o` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| SiliconFlow | `SILICONFLOW_API_KEY` | `deepseek-ai/DeepSeek-V3.2` |
| Together AI | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |

```bash
sheaf config use deepseek        # switch default provider
sheaf config list                # show configured providers
```

<details>
<summary><b>Advanced: env vars / <code>.env</code> (CI or temporary use)</b></summary>

Sheaf auto-reads a `.env` file in your working directory (see [.env.example](.env.example)). Or set per-shell — the only OS difference is the syntax:

```bash
# macOS / Linux
export OPENAI_API_KEY=sk-...
# Windows PowerShell:   $env:OPENAI_API_KEY="sk-..."
# Windows CMD:          set OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1   # optional — for non-OpenAI endpoints
```
</details>

## Architecture

```
source → collect and normalize → Entry → retrieve → agent
                                  ↓
                     source bundle → crystallize → KnowledgeCard
                                  ↓
new evidence → validated transition → event ledger → current card version
```

| Module | Purpose |
|---|---|
| `sheaf_ai/` | Core — pipeline, storage, search, CLI, MCP server, crystallize engine |
| `sheaf_cards/` | Knowledge card engine — base types, embeddings, generation |
| `prompts/` | LLM prompt templates (classify, summarize, crystallize) |
| `data/` | Local knowledge base (JSONL + Markdown, gitignored) |

See [Architecture and Evaluation](docs/ARCHITECTURE-AND-EVALUATION.md) for the
application/domain/infrastructure boundaries and staged development plan.

## Requirements

- **Python 3.10+**
- An OpenAI-compatible API key
- Playwright Chromium *(optional, JS-heavy sites)*: `pip install -e ".[browser]" && playwright install chromium`

## Development

```bash
git clone https://github.com/zhelunSun/sheaf-ai.git && cd sheaf-ai
python -m pip install -e ".[dev]"
python -m pytest tests/ -q
python evals/core-algorithms/run_offline_eval.py --compact
python -m ruff check sheaf_ai/ tests/ sheaf_cards/
```

Extras: `.[dev]` for local dev, `.[server]` for the HTTP API, `.[browser]` for Playwright fetching.

## Status & Chrome Extension

Sheaf is early alpha. The local collect-to-agent loop works and is covered by
CI. The current development stage is [**core algorithm evidence**](docs/NEXT-PHASE-PLAN.md).
The production retrieval path and first frozen classical baseline are now in
place; its negative result redirects the next iteration toward no-answer/entity
ambiguity, a real embedding run, and long-document passages. The other priority
gaps are a trusted provenance registry, a real atomic SPLIT adapter, and
cross-file transactions. Comparative quality claims remain hypotheses.

A Chrome extension (`extension/`) adds one-click collect + search from any page: start the local API with `sheaf serve`, load `extension/` unpacked (Chrome → Manage Extensions → Developer mode), then `Alt+Shift+S` or right-click any page → "🌾 Collect with Sheaf".

**Try it:** save 20+ links, run `sheaf crystallize <topic>`, then ask your agent to find them. If it clicks for you, open an issue or discussion and tell us what you'd change.

> ⭐ If Sheaf saves you time, a star on [GitHub](https://github.com/zhelunSun/sheaf-ai) helps others find it.

## License

[Apache 2.0](LICENSE)

---

*A **sheaf** is a bundle of harvested grain. In mathematics, a [sheaf](https://en.wikipedia.org/wiki/Sheaf_(mathematics)) attaches local data to open sets and glues them into a global picture. Sheaf the tool does both: gather selected sources into coherent bundles, ready for agents to retrieve, inspect, and reuse.*
