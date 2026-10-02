<p align="center">
  <b>English</b> | <a href="README_CN.md">中文</a>
</p>

<p align="center">
  <img src="assets/logo.png" alt="Sheaf Logo" width="360">
</p>

<h1 align="center">Sheaf</h1>

<p align="center"><b>Your sources and judgments, ready for your agent. Help deciding what deserves your own reading.</b></p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0"></a>
  <a href="https://github.com/zhelunSun/sheaf-ai/actions/workflows/ci.yml"><img src="https://github.com/zhelunSun/sheaf-ai/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/sheaf-ai/"><img src="https://img.shields.io/pypi/v/sheaf-ai.svg" alt="PyPI"></a>
</p>

---

Sheaf is building **personal knowledge infrastructure for the agent era**. Today it organizes saved sources into a local, searchable, source-linked library that agents can access. Saving signals interest; it does not establish agreement, correctness, or a complete model of your judgment. Local-first and open-source.

> A **sheaf** is a bundle of harvested grain. Sheaf gathers deliberately chosen sources into knowledge that remains tied to its evidence.

> **Product direction:** Save naturally, let your existing agent reuse relevant material, and get help deciding what to read yourself. Value should not depend on questionnaires, mandatory tagging, or teaching a taste profile. Reading suggestions, preference reuse, and a smoother source-checking flow are [planned work](docs/PRODUCT-FEATURES.md); the complete experience is not yet validated. See the [current product direction](docs/PRODUCT-DESIGN-INDEX.md) and [development plan](docs/NEXT-PHASE-PLAN.md).


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
sheaf search-index --rebuild                     # optional: Entry embeddings (provider call)
sheaf search "transformer architecture"          # hybrid search; diagnostic keyword fallback
sheaf crystallize AI                             # optional: distill knowledge cards
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

The current alpha collects and searches sources, and can optionally turn them into source-linked cards. The next step is to show that this helps with real tasks, reduces repeated searching, and preserves the distinction between a source's claims and your own judgment. No minimum collection size or card generation is required to start using saved sources.

## Features

| | What it does |
|---|---|
| 🌾 **Save sources** | Paste a link or note. Sheaf fetches, cleans, classifies, and preserves its source. Existing quality/source checks are heuristic signals, not fact verification. |
| 🔎 **Find material again** | Keyword and optional semantic retrieval, with explicit diagnostics when indexes are stale or unavailable. |
| 🤖 **Use your agent** | Supported MCP clients can search the library and read saved sources. Whether an agent uses them correctly still needs task-level checking. |
| ✨ **Optional knowledge cards** | Distill related entries into source-linked cards; original entries remain usable on their own. |
| 🧭 **Experimental version governance** | Constrained knowledge transitions and immutable history. This is separate from ordinary card generation; evidence strength is a heuristic, not a probability. |
| 🔒 **Local-first** | Knowledge files stay local; no Sheaf account or telemetry. Model-backed steps use the provider you configure. |

### Crystallize — curated sources into reusable claims

`sheaf crystallize` organizes related sources into reusable, source-linked cards.
Generated claims still need checking for the intended task. Example output:

```
$ sheaf crystallize AI
✨ 5 knowledge cards crystallized:
  📌 RAG faces retrieval relevance challenges
     RAG systems heavily depend on retrieval quality; errors degrade output reliability.
  📌 CRAG framework improves RAG robustness
     CRAG introduces a retrieval evaluator, web search augmentation, and document decomposition.
```

Each batch card carries **evidence tracing** (which sources contributed), **topic provenance**, and **tags**. Semantic-search across all of them with `sheaf crystallize --semantic "query"`.

<details>
<summary>Technical guarantees and experimental evidence</summary>

The experimental evidence-governed path is deliberately stricter. Ledger
schema 3 verifies quote or character-span evidence identity and replays older
ledgers. `evidence-rule-v3` derives non-duplicate groups only from a shared
`source_key`, a trusted full SHA-256 evidence digest, or a persisted
`exact`/`near_duplicate` relation; ordinary self-declared provenance never
overrides deduplication. Those groups are not automatically treated as
independent corroboration: `independent_source_count` remains conservatively
`1` and the corroboration bonus is disabled. A local append-only provenance
registry now binds admin attestations to the exact Entry, origin, and full
evidence digest. Missing, conflicting, corrupt, or revoked records fail closed
to tier `U`; active records can grant source tier, primary/authority scope and
correction relations. Its SHA-256 chain is integrity evidence, not identity
authentication. Historical v1/v2 scores replay unchanged. This does not claim
that an LLM policy or confidence probability has already been calibrated:

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

SPLIT and NOOP have an auditable preview-first decision-trace protocol. The
production evidence-ledger adapter commits a SPLIT's UPDATE + CREATE, receipt,
and head compare-and-swap through one file replacement. Its execution-manifest
hash binds the exact operations, evidence, target head, policy versions, and
idempotency identity, so a retry cannot substitute a different plan. The
decision and evidence ledgers remain separate files: receipt-first
reconciliation makes that boundary recoverable, not a cross-file transaction.

The broader [architecture and evaluation contract](docs/ARCHITECTURE-AND-EVALUATION.md)
describes supporting algorithms, their maturity, and the experiments still
required for comparative claims. Product priorities follow the
[current plan](docs/NEXT-PHASE-PLAN.md).

### Retrieval evidence snapshot

The first frozen retrieval experiment contains 22 Entries and 36 queries. Its
manifest locks corpus, query, and evaluator-only qrels hashes, and rankings are
produced before qrels are loaded. The checked-in local-LSA run is a classical
TF-IDF/SVD baseline—not a neural embedding result. Development selection chose
`linear-0.25 @ 0.4`; held-out Recall@5 is `0.9375`, MRR `1.0`, nDCG@5 `0.9498`,
and no-answer FPR `1.0`. It did not outperform keyword retrieval and did not
solve abstention. A later query-support-v3 post-hoc regression on the already
inspected labels reached Recall@5 `1.0`, nDCG@5 `0.9698`, and FPR `0.0`; this is
not a blind effectiveness result. A live embedding run was not produced because
credentials were unavailable. See the [frozen retrieval report](evals/retrieval-frozen/README.md).

The current relevance gate is a backend/version-specific experimental signal,
not a probability or portable threshold. If semantic retrieval degrades,
production search returns to the keyword-coverage scale.

</details>

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
- Open local Markdown and JSON/JSONL files you can inspect directly; supported export and recovery are [planned separately](docs/PRODUCT-FEATURES.md#pf-06--export-and-restore-a-minimal-local-library).

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

Sheaf is early alpha. Collection, retrieval, and agent interfaces are implemented;
their engineering checks do not establish continued user adoption. The current
focus is a [low-effort, source-checkable product loop](docs/NEXT-PHASE-PLAN.md):
save material, reuse it in real tasks, and test lightweight reading suggestions.
Comparative quality, user value, and willingness to pay remain hypotheses.

A Chrome extension (`extension/`) adds one-click collect + search from any page: start the local API with `sheaf serve`, load `extension/` unpacked (Chrome → Manage Extensions → Developer mode), then `Alt+Shift+S` or right-click any page → "🌾 Collect with Sheaf".

**Try it:** choose a question you are already working on, save a few relevant sources, and ask your agent to use them for a comparison or explanation. Check whether the sources and conclusions help. Share friction or useful outcomes in an issue or discussion.

> ⭐ If Sheaf saves you time, a star on [GitHub](https://github.com/zhelunSun/sheaf-ai) helps others find it.

## License

[Apache 2.0](LICENSE)

---

*A **sheaf** is a bundle of harvested grain. In mathematics, a [sheaf](https://en.wikipedia.org/wiki/Sheaf_(mathematics)) attaches local data to open sets and glues them into a global picture. Sheaf the tool does both: gather selected sources into coherent bundles, ready for agents to retrieve, inspect, and reuse.*
