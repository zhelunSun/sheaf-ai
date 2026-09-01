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
| Retrieval | Recover the right saved evidence for a question | Keyword scoring and card-mediated semantic score fusion | Direct Entry semantic coverage, embedding quality, representative queries, and credible baselines |
| Crystallization | Turn several sources into reusable claims | Model-assisted extraction, strict schema validation, and resolvable source links | Claim entailment, contradiction handling, redundancy, stability across models, and usefulness to people |
| Incremental evolution | Change knowledge without erasing why it changed | Explicit create, update, contest, and merge transitions; immutable history; replayable versions | Automatic action selection, calibrated evidence weighting, and end-to-end quality under noisy inputs |

The third path is the deepest deterministic subsystem today. Retrieval is a
working hybrid implementation. Crystallization is central to the product but
still depends most heavily on model behavior.

Idempotency keys, request hashes, file locks, atomic writes, and replay checks
are not a fourth algorithm. They are reliability mechanisms that make all three
paths safe to retry and possible to audit.

## 3. System shape

Sheaf now has a coherent architecture that can be reviewed as a system rather
than as a collection of scripts:

```text
CLI / MCP / HTTP
        |
application services: collect, search, crystallize, apply evidence transition
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
new evidence -> validated transition -> event ledger -> current card projection
```

This is enough to explain and defend the design in an interview: interfaces do
not own the domain rules, source-backed cards have a checked boundary, and
incremental changes preserve history. It is not yet equivalent to a mature
memory platform in scale, ecosystem, migrations, or published benchmark
evidence. Important remaining architecture work includes removing global path
configuration, planning storage beyond JSON files, automating the evidence
policy, and defining stable data migrations.

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
| Evidence loop | Source-backed cards and inspectable updates | Unknown sources fail closed; conflict and history are replayable |
| Algorithm evidence (current) | Establish what each core path improves | Versioned datasets, baselines, metrics, ablations, and reproducible raw outputs |
| Integrated policy | Choose memory transitions from incoming evidence | Policy accuracy and safety beat simple rules on a held-out labelled set |
| Product validation | Learn whether deliberate source curation creates repeat use | Design partners repeatedly retrieve or reuse knowledge and explain the value |
| Scale and distribution | Broaden storage, integrations, and collaboration | Only after algorithm and product evidence reveal actual bottlenecks |

## 6. Fast feedback without real users

The test ladder deliberately separates deterministic engineering checks from
model experiments and later user research.

| Gate | Runs | Purpose |
|---|---|---|
| Unit and contract tests | Every change | Schema, edge cases, retries, storage, and interface compatibility |
| Synthetic profile journeys | Every CI run | Researcher, developer, and creator workflows over isolated local data |
| Offline core evaluation | Every CI run | Retrieval fusion, crystallization provenance, and evidence-ledger invariants |
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

Build a small query-to-source relevance set from realistic personal knowledge
tasks. Compare keyword-only, semantic-only, and hybrid retrieval. Report
Recall@k, reciprocal rank, latency, and failure slices such as paraphrases,
versioned facts, and long documents. The current offline suite fixes semantic
scores, so it tests fusion logic only—not embedding quality.

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
`evals/evidence-governed-memory/PROTOCOL.md`. The current executor acceptance
proves state invariants only—not that a model can choose the right transition.

## 8. Claim boundary

Current safe claim:

> Sheaf implements and automatically tests a local, source-backed knowledge
> loop with stable keyword retrieval, an experimental card-mediated hybrid
> path, provenance-constrained crystallization, and replayable evidence-based
> updates.

Claims such as “retrieves better,” “creates more accurate knowledge,” or
“updates memory more intelligently than another project” remain hypotheses
until the experiments above produce checked-in results.
