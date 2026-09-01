# Evidence-Governed Memory: Product and Evaluation Proposal

> **Status:** Product proposal plus an implemented experimental executor. It is
> not a claim about the currently released PyPI product or about measured model
> quality.
>
> **Implemented on this branch:** user-initiated URL or note collection, local
> structured storage, search, batch crystallization into source-linked knowledge
> cards, agent access through MCP, and an explicitly invoked deterministic
> evidence-transition executor with immutable versions, contested state, and
> replay validation.
>
> **Still proposed or unmeasured:** consent modes for conversational capture, an
> automatic model policy that proposes transitions, calibrated probability,
> product analytics, and the G0-G3 evaluation described in
> [`../evals/evidence-governed-memory/PROTOCOL.md`](../evals/evidence-governed-memory/PROTOCOL.md).
> No benchmark result should be inferred from this document.

## 中文摘要

Sheaf 的核心不应再表述为泛化的“跨 Agent 记忆”。更准确的产品命题是：
**用户主动选择自己认为重要的高质量来源，Sheaf 保留这种信息品味，并把它转成 Agent
可检索、可核验、可随新证据演化的长期知识。** 用户的选择代表相关性与信任先验，
但不等于事实正确；因此每条知识仍需保留来源、冲突、版本和置信依据。

本文明确区分已实现的确定性执行器与尚未评测的模型策略。所有 G0-G3 指标都是验收
协议，不是已有结果；当前 evidence strength 是可重算的序数启发式分数，不是概率。

## 1. Product thesis

People already teach agents what matters through the sources they choose to
read, save, quote, and revisit. That selection is a high-signal expression of
their working taste: which authors they trust, what level of technical depth is
useful, and which evidence belongs in a decision.

Most memory products begin with conversation exhaust or broad connector
ingestion. Sheaf's intended wedge is narrower:

> **Turn a user's deliberately curated sources into evidence-backed memory that
> an agent can reuse without hiding where a claim came from or why it changed.**

Selection is not truth. A saved source may be wrong, outdated, promotional, or
contradicted later. Sheaf should therefore treat selection as a **relevance
prior**, not a correctness label. The product earns trust by preserving the
path from source to claim and from an old claim state to a new one.

## 2. Primary ICP and exclusions

### Primary ICP

An **agent-heavy technical knowledge worker**, initially an individual
developer or researcher, who:

- uses a coding or research agent several times per week;
- deliberately saves at least five sourced items per week, such as papers,
  technical posts, repositories, release notes, or standards;
- repeatedly makes decisions or writes artifacts that should cite those
  sources;
- values local files, inspectability, and provider choice enough to accept a
  developer-oriented setup; and
- has experienced “I know I read this, but I cannot recover or verify it now.”

The first design-partner cohort should be 5-10 people matching this profile.
That is a recruitment target, not a statement that such validation has already
happened.

### Not the initial ICP

- General consumers seeking a polished read-later application.
- Teams seeking a complete enterprise knowledge platform, SSO, or governance.
- Applications that need an SDK for arbitrary conversational personalization.
- Users who expect unattended ingestion of every chat, email, or drive file.
- Buyers of a knowledge marketplace.

These may become adjacent markets, but designing for them now would obscure the
initial job and create unsupported product claims.

## 3. Job to be done

### Core job

> When I make a technical decision or produce a research artifact with an
> agent, help the agent recover the best material I deliberately saved, show
> the evidence behind its claims, and reveal when newer evidence changed what
> the system believes, so I can move quickly without trusting an opaque memory.

### Functional outcomes

1. Capture a chosen source with minimal interruption.
2. Recover it by meaning rather than exact title or location.
3. Distill repeated evidence into claims without losing source identity.
4. Preserve disagreement instead of silently flattening it.
5. Update or retire claims with a reviewable reason and history.
6. Let an agent cite the memory in a real task, then let the user inspect it.

### Emotional and trust outcomes

- “My past reading is useful rather than buried.”
- “The agent reflects my information diet without impersonating my judgment.”
- “I can see and undo what was remembered.”
- “A confidence number has an inspectable basis.”

## 4. Competitive inheritance and claim boundaries

This positioning is **misaligned competition**, not a claim that Sheaf invented
agent memory. As of 2026-09-01, official product material shows overlapping
capabilities:

- [Mem0 MCP](https://docs.mem0.ai/platform/mem0-mcp) exposes save, search, list,
  update, and delete operations to MCP clients.
- [OpenMemory MCP](https://mem0.ai/blog/introducing-openmemory-mcp) describes a
  private, local-first memory layer shared across MCP clients.
- [Supermemory](https://supermemory.ai/) offers personal cross-agent memory,
  connectors, a Chrome extension, structured retrieval, and evolving facts.
- [Pieces Long-Term Memory MCP](https://pieces.app/blog/inside-mcp-server-implementation)
  exposes developer memories to MCP clients for downstream work.

### What Sheaf inherits

- Persistent memory accessed through agent tools.
- Semantic or hybrid retrieval.
- Cross-client access through MCP.
- Finite memory operations such as create, update, merge, and retire.
- The need for lifecycle management rather than append-only storage.

### What Sheaf must not claim

- “The first personal memory layer for agents.”
- “The first local-first MCP memory.”
- “The inventor of memory state transitions or memory operations.”
- “State-of-the-art retrieval” without a named benchmark and reproducible run.
- “Better than Mem0, Supermemory, or Pieces” without a matched evaluation.
- “Trustworthy” merely because data is local or a source URL is stored.

### The proposed right to win

Sheaf can instead compete on a narrower contract:

| Dimension | Generic agent memory | Proposed Sheaf emphasis |
|---|---|---|
| Primary input | Conversation history and broad connectors | Sources deliberately selected by the user |
| Selection meaning | Material available to remember | A relevance and taste signal, not a truth label |
| Knowledge unit | Memory text, chunks, or profile facts | Falsifiable claim with source-level provenance |
| Contradiction | Update, merge, or forget | Preserve both evidence and the reason for transition |
| Confidence | Model score or ranking signal | Recomputable evidence features with visible limits |
| User control | Product-specific | Local/open artifacts plus explicit capture controls |
| Best initial task | Personalization and context continuity | Evidence-backed technical or research decisions |

This difference is only real when demonstrated in stored artifacts and
evaluation. It cannot remain a prompt-only instruction.

## 5. Consent and control contract

User-selected sources are explicit capture actions. Conversational memory is
more sensitive and should have separate controls.

### Proposed modes

| Mode | Behavior | Recommended default |
|---|---|---|
| `off` | Never propose or perform conversational capture | Available at all times |
| `suggest` | Agent proposes one self-contained memory; user approves before write | **Default** |
| `auto` | Agent may write high-density memories under declared rules | Explicit opt-in only |

These modes are proposed and are not documented here as implemented settings.

### Non-negotiable controls

1. **Visible write:** every capture returns what was stored and its source type.
2. **Undo:** the latest write can be reverted without locating a file manually.
3. **Inspectable log:** users can review capture, update, merge, and retirement
   events with timestamps and reasons.
4. **No truth laundering:** “user selected” and “source tier” remain separate
   from factual correctness.
5. **Least capture:** status chatter and transient instructions are not durable
   memories by default.
6. **Provider disclosure:** local storage does not imply local inference. The UI
   must state when content is sent to the user's configured model provider.
7. **No silent destructive transition:** update, merge, and retire preserve a
   before/after trace and source references.

## 6. Five-minute demonstration loop

Two demos should be kept separate so interviews do not present proposed work as
released behavior.

### A. Current-product demo (available after a clean install)

**0:00-1:00 — Curate.** The user collects three sources on one technical topic.
Explain that the corpus is intentionally selected, not a background scrape.

**1:00-2:00 — Inspect.** Show the structured entries and their original source
identity. State that source presence supports traceability but does not prove a
claim true.

**2:00-3:00 — Crystallize.** Generate cross-source cards and open one card with
its supporting source IDs.

**3:00-4:00 — Reuse.** Ask an MCP-connected agent a decision-shaped question
about the topic and have it search Sheaf before answering.

**4:00-5:00 — Verify.** Open the cited card and one raw source. End on the user
outcome: selected reading changed a real agent answer and remained inspectable.

This demo proves capture, retrieval, batch synthesis, and agent reuse. It does
**not** prove incremental evolution, calibrated confidence, or conflict audit.

### B. Experimental executor demo (implemented; not a G0-G3 result)

**0:00-1:00 — Establish state.** Feed the first batch from one evaluation case
and show the initial claim with provenance.

**1:00-2:00 — Add tension.** Add a lower-quality conflicting source. The system
must preserve the conflict rather than silently overwrite the claim.

**2:00-3:00 — Add stronger/newer evidence.** Add the next source and run the
incremental transition.

**3:00-4:00 — Audit.** Show the prior state, new state, operation, reason,
timestamp, and all supporting or contradicting source IDs.

**4:00-5:00 — Reuse and challenge.** Ask the agent for the current answer and
“why did this change?” The answer must cite the current evidence and expose the
history.

This state-machine path can be replayed now through `sheaf memory` or the
checked-in executor acceptance runner. It demonstrates transition invariants,
not automatic policy quality. The broader vNext demo passes only if its fixture
case also passes the recorded G3 protocol. A polished screen recording is not
evaluation evidence by itself.

## 7. Product loop and instrumentation

```text
select source -> capture -> structure -> retrieve/crystallize
      ^                                      |
      |                                      v
correct or refine <- inspect evidence <- agent reuse in a task
```

Instrumentation should be local by default. Aggregated product analytics are
shared only with explicit opt-in.

### North-star metric

**Weekly Evidence-Backed Reuses (WEBR):** the number of unique weekly agent
answers or artifacts that materially use at least one Sheaf memory and retain a
resolvable trace to its supporting source.

“Materially use” means removing the recalled item would change a conclusion,
decision, citation, or produced artifact. Merely calling search does not count.
The first implementation may use a user confirmation or local review queue;
it must not pretend to infer materiality perfectly.

Why WEBR instead of cards created:

- it measures activation of saved knowledge, not accumulation;
- it connects capture to downstream work;
- the evidence requirement protects against ungrounded recall; and
- it discourages duplicate card generation.

### Diagnostic metrics

| Stage | Metric | Failure it reveals |
|---|---|---|
| Capture | selection-to-first-reuse time | Collection that never creates value |
| Recall | useful recall rate after user review | Search calls that return noise |
| Evidence | citation resolvability and claim grounding | Broken or decorative provenance |
| Evolution | correct conflict preservation and transition accuracy | Silent knowledge corruption |
| Control | suggestion acceptance, undo, and false-capture rates | Agent overreach |
| Efficiency | latency, model calls, and tokens per WEBR | A useful loop that is too costly |

### Design-partner success gate

For a two-week, 5-10 person design-partner study, define the gate before data is
collected. A reasonable proposal is:

- at least half of activated participants record two or more WEBRs in week two;
- median time to first WEBR is under three days;
- every counted WEBR retains resolvable source provenance; and
- false or unwanted conversational captures remain below 5% in `suggest` mode.

These are proposed thresholds, not observed results. Report participant count,
dropout, and raw denominators alongside any percentage.

## 8. Interview narrative contract

### Defensible 30-second version

> “Sheaf starts from a signal most memory systems underuse: the sources a user
> deliberately chooses. I turn that curated corpus into source-backed memory for
> coding and research agents. I am not claiming to have invented MCP memory or
> update operations. The technical question I am testing is narrower: when new
> evidence arrives, can claims evolve without losing provenance, unresolved
> conflicts, or the reason a prior state was retired? I evaluate that with a
> four-group incremental protocol, not with a polished anecdote.”

### Claims allowed before G0-G3 is run

- “I implemented and attack-tested the deterministic state executor and designed
  the evaluation contract.”
- “The current product supports curated capture, search, batch crystallization,
  source-linked cards, and MCP reuse.”
- “The incremental evidence-governed executor is an explicitly invoked
  prototype; the automatic transition policy and comparative quality claims are
  still unvalidated.”

### Claims allowed only after evidence exists

- “G3 improved grounding/conflict handling over G1 or G2,” followed by the
  exact fixture version, model, run ID, score, and limitations.
- “Confidence is calibrated,” only with a labeled set and reported calibration
  error or Brier score.
- “The audit chain is complete,” only if every destructive transition in the
  fixture passes the trace-completeness gate.

### Never claim from this proposal alone

- superior benchmark performance;
- user retention or willingness to pay;
- production-ready trustworthy memory;
- novelty of the finite operation set; or
- broad competitive superiority.

## 9. Decision sequence

1. Freeze the ICP and consent contract before expanding ingestion channels.
2. Keep the executor acceptance scenario and attack-oriented tests green.
3. Implement the smallest automatic G2/G3 policy path against the checked-in
   fixture, then run G0-G3 with frozen inputs and publish raw outputs plus the
   score sheet.
4. Record the five-minute acceptance demo from a passing G3 run.
5. Recruit design partners and measure WEBR locally.
6. Revisit hosted sync, team features, or monetization only after reuse is
   demonstrated.
