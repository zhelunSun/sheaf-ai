# Sheaf Architecture and Evaluation

> Status: working contract for the current alpha. It separates implemented
> guarantees from hypotheses that still need experiments.

## 1. Product position

Sheaf is a local knowledge layer for people who deliberately collect sources
they consider worth keeping, then let an agent retrieve, synthesize, and update
that collection. The user is not merely saving links: source selection carries
their judgment into the agent's working context.

This is deliberately narrower than a general-purpose memory service. Sheaf's
starting point is explicit, high-quality user selection rather than passive
capture of every conversation. Its product loop is:

```text
choose a source -> preserve it -> find it later -> derive a source-backed claim
                -> revise that claim when better evidence arrives -> reuse it in an agent
```

The product hypothesis is that this smaller, inspectable corpus can be more
trustworthy and more personal than an automatically accumulated memory stream.
That hypothesis still needs user validation; the architecture does not prove
willingness to pay.

## 2. The three core algorithm paths

"Three core paths" is a useful product and engineering description, provided
their maturity is not presented as equal.

Multi-source collection is the input capability, not a fourth core algorithm.
Adding a website handler is mainly integration and reliability work. Source
quality scoring, duplicate or event detection, cross-source disagreement, and
long-document structure can still contain meaningful algorithms; they belong
to the ingestion and source-quality capability stream and improve the inputs to
the three paths below.

| Path | Product job | Implemented now | Still unproven |
|---|---|---|---|
| Retrieval | Recover the right saved evidence for a question | BM25 plus a direct Entry vector index, atomic generations, stale diagnostics, keyword fallback, and a frozen 22-Entry/36-query classical-baseline ablation | Live embedding quality, no-answer/entity ambiguity, and long-document passage coverage |
| Crystallization | Turn several sources into reusable claims | Model-assisted extraction, strict schema validation, and resolvable source links | Claim entailment, contradiction handling, redundancy, stability across models, and usefulness to people |
| Incremental evolution | Change knowledge without erasing why it changed | Explicit create/update/merge/retire/contest transitions; schema-3 quote/span evidence identity; scoped correction authority; replayable old ledgers; auditable SPLIT/NOOP previews | A production atomic SPLIT adapter, automatic action selection, trusted provenance registry, and end-to-end quality under noisy inputs |

The third path is the deepest deterministic subsystem today. Its
`evidence-rule-v3` derives non-duplicate groups only through a shared
`source_key`, a trusted versioned full SHA-256 evidence digest, or persisted
`exact` / `near_duplicate` relations. Ordinary self-declared provenance is
retained for audit but never overrides those duplicate edges. The groups are
reported for inspection, not certified as independent corroboration: pending a
trusted provenance registry, `independent_source_count` is conservatively `1`
when evidence exists and the corroboration bonus is disabled. Historical v1/v2
scores replay under their original algorithms. Official correction also
requires a primary source whose declared authority scope covers the topic and
fact key and whose persisted `corrects` relation names the corrected Entry.

Retrieval is a working hybrid implementation, but the checked-in local-LSA
result did not beat keyword retrieval. Crystallization is central to the product
and still depends most heavily on model behavior.

Idempotency keys, request hashes, file locks, atomic writes, and replay checks
are not a fourth algorithm. They are reliability mechanisms that make all three
paths safe to retry and possible to audit.

## 3. System shape

Sheaf now has a coherent architecture that can be reviewed as a system rather
than as a collection of scripts:

```text
CLI / MCP / HTTP
        |
application services: collect, search, crystallize, preview/apply evidence transition
        |
domain records: Entry, KnowledgeCard, EvidenceEvent, CardVersion
        |
infrastructure: collectors, local JSONL/Markdown storage, model and embedding adapters
        |
quality control: contracts, profile journeys, offline evaluations, build and wheel smoke
```

The main flows are:

```text
source -> collector -> Entry -----------------------> retrieval -> agent
                       |                                  |
                       +-> source bundle -> crystallization -> KnowledgeCard
                       |
new evidence -> decision preview -> validated transition -> event ledger -> current card projection
```

This is enough to explain and defend the design in an interview: interfaces do
not own the domain rules, source-backed cards have a checked boundary, and
incremental changes preserve history. It is not yet equivalent to a mature
memory platform in scale, ecosystem, migrations, or published benchmark
evidence. Important remaining architecture work includes removing global path
configuration, long-document passage selection, trusted provenance
registration, cross-file transactions, and a production adapter that can commit
a SPLIT's UPDATE + CREATE atomically.

The SPLIT/NOOP decision trace is deliberately conditional. It records the input
snapshot and request hash, policy/algorithm versions, evidence IDs, target heads, reason,
status, and the shared `decision_id` of a planned UPDATE + CREATE. Before apply,
it checks that the target head has not changed. It will only call an external
`execute_atomic(...)` protocol and otherwise fails closed. The repository has
tests with an atomic fake, but no production evidence-memory batch executor;
the trace must not be described as an end-to-end atomic SPLIT implementation.

## 4. How the product should be managed

Managing only by feature encourages vertical demos with hidden gaps. Managing
only by code module loses sight of user outcomes. Use three views together:

1. **Product journeys** define why the work exists: collect and recover a paper,
   synthesize a defensible brief, update an obsolete fact, and give an agent the
   result.
2. **Capability streams** own durable behavior: ingestion and source quality,
   retrieval, crystallization, knowledge evolution, agent interfaces, and
   platform reliability/evaluation.
3. **Code modules** define implementation ownership and change boundaries.

Every capability should carry its own success measure, fixtures, failure modes,
and release gate. Cross-cutting work such as privacy, observability, packaging,
and migration belongs to the platform stream, not to a miscellaneous backlog.

## 5. Development stages and exit criteria

| Stage | Goal | Exit criterion |
|---|---|---|
| Foundation | A usable local collect-to-agent loop | Clean install, deterministic storage, CLI/MCP contracts, and release smoke pass |
| Evidence loop | Source-backed cards and inspectable updates | Unknown sources fail closed; quote/span evidence, scoped authority, conflict, and old-ledger replay are checked |
| Algorithm evidence (current) | Establish what each core path improves | Versioned datasets, baselines, metrics, ablations, and reproducible raw outputs |
| Integrated policy | Choose and atomically execute memory transitions from incoming evidence | A production SPLIT adapter plus policy accuracy and safety that beat simple rules on a held-out labelled set |
| Product validation | Learn whether deliberate source curation creates repeat use | Design partners repeatedly retrieve or reuse knowledge and explain the value |
| Scale and distribution | Broaden storage, integrations, and collaboration | Only after algorithm and product evidence reveal actual bottlenecks |

## 6. Fast feedback without real users

The test ladder deliberately separates deterministic engineering checks from
model experiments and later user research.

| Gate | Runs | Purpose |
|---|---|---|
| Unit and contract tests | Every change | Schema-3 span identity, source grouping, scoped authority, decision traces, edge cases, retries, storage, and interface compatibility |
| Synthetic profile journeys | Every CI run | Researcher, developer, and creator workflows over isolated local data |
| Offline core evaluation | Every CI run | Production retrieval plumbing with a fixture embedder, crystallization provenance, and the checked-in evidence-memory scenario |
| Fixed-dataset model experiment | Nightly or manual | Real embeddings and LLM outputs with pinned model settings and preserved raw responses |
| Exploratory live-site sampling | Manual | Collector drift, JavaScript sites, rate limits, and provider changes |
| Design-partner study | Later | Usefulness, trust, repeat behavior, and willingness to pay |

Run the first three locally with:

```bash
python -m pytest tests -q
python evals/core-algorithms/run_offline_eval.py --compact
```

The profile tests never touch the user's knowledge base, the network, or a paid
model. They create isolated synthetic entries and frozen model responses.

## 7. Experiments required for the core claims

An interview-worthy innovation needs negative results and ablations, not only a
demo. Each run must record the dataset revision, fixture hash, code commit,
model and embedding versions, sampling settings, raw output, and human labels.

### Retrieval

The first frozen set now contains 22 synthetic-but-realistic Entries and 36
queries. The manifest locks corpus, query, and qrels hashes, and the runner
creates rankings before it loads evaluator-only qrels. It compares keyword,
semantic, linear hybrid, and RRF variants through the production Entry index.

The checked-in `local-lsa-v1` run is a classical TF-IDF/SVD baseline, not a
neural embedding result. Development selection chose `linear-0.25` with a `0.4`
minimum evidence gate. On held-out queries it achieved Recall@5 `0.9375`, MRR
`1.0`, nDCG@5 `0.9498`, and no-answer FPR `1.0`; keyword achieved `0.9688`,
`1.0`, `0.9560`, and `1.0`. The selected method therefore did not outperform
keyword and did not solve abstention. A live embedding run was not produced
because credentials were unavailable.

The `coverage-semantic-v1` relevance gate is an experimental signal tied to the
backend and version that produced it, not a calibrated probability or portable
threshold. When semantic retrieval degrades, production search falls back to
the keyword-coverage scale. Next retrieval experiments target no-answer/entity
ambiguity, a real embedding provider, and long-document passage retrieval.

### Crystallization

Give multiple systems the same source bundles. Blindly label whether each claim
is supported, whether its citations resolve and entail the claim, whether it
misses a contradiction, and whether it duplicates another card. Compare a
single-source summary, unconstrained multi-source generation, and Sheaf's
source-constrained pipeline. Frozen outputs currently prove fail-closed
provenance behavior only—not synthesis quality.

### Incremental evolution

Create evidence sequences containing confirmation, conflict, correction,
version changes, and irrelevant noise. Measure transition-action accuracy,
conflict recall, invalid-resolution rate, audit completeness, replay
correctness, and cost. Compare the frozen G0-G3 variants in
`evals/evidence-governed-memory/PROTOCOL.md`.

The current deterministic layer verifies schema-3 quote/character-span
identity, v1/v2 replay and migration, `evidence-rule-v3` grouping, scoped
official correction, and decision-trace integrity. The SPLIT/NOOP trace only
enforces the precondition that a caller provide an atomic batch executor; it
does not supply that production executor or prove that a model chooses the
right transition.

## 8. Claim boundary

Current safe claim:

> Sheaf implements and automatically tests a local, source-backed knowledge
> loop with stable keyword retrieval, a direct and diagnostically degradable
> Entry-level hybrid path, provenance-constrained crystallization, and
> replayable evidence updates with verified quote/span identity.

The checked-in classical retrieval baseline is useful precisely because it is
a negative result: hybrid did not beat keyword and no-answer FPR remained 1.0.
Claims such as “retrieves better,” “solves abstention,” “creates more accurate
knowledge,” “atomically executes SPLIT in production,” or “updates memory more
intelligently than another project” remain unsupported.
