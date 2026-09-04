# Sheaf Architecture and Evaluation

> Status: working contract for the current alpha. It separates implemented
> guarantees from hypotheses that still need experiments.

### 2026-09-04 consumption contract update

Full-card rendering now preserves the whole claim and exposes original source-alias
bindings. The parser records these in `provenance.source_citations`; old cards with
missing maps are explicitly unresolved. `cited_input_trace` records input selection,
not entailment or source authority. API/MCP card projections add `citation_trace`.

`query-support-v4` keeps strict selection unchanged and adds an opt-in `review`
policy. CLI/HTTP/MCP propagate the gate state even on empty results, including to
text-only MCP clients. `candidates` and `review_required` are retrieval states,
never answer verification. The legacy core `retrieval_gate_answerable` is now null;
consumers checking the strict heuristic should use `retrieval_gate_passed`.

The follow-up stage completes built-in governed-state/strength notices, including
compact and field-filtered views. Historical projections distinguish the recorded
state from whether a version has since been superseded; ledger events are unchanged.
CLI/MCP and the explicit HTTP `GET /memory/snapshot` share the public projection.
Ordinary cards are still not automatically merged with governed versions.

Method-selection experiment preparation now compares raw sources, complete plain
text cards and structured cards sharing one extraction. The offline importer and
scorer are ready, but no real model effects or equal-token-budget result exists.
See the [phase record](METHOD-SELECTION-PHASE-2026-09-04.md) and the earlier
[repair/investment assessment](FIX-ROUND-2026-09-04.md).

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
| Retrieval | Recover the right saved evidence for a question | BM25 plus a direct Entry vector index, query-level support gate, fail-closed scoped filters, Unicode/CJK entity handling, and a frozen classical-baseline ablation | Live embedding quality and a newly sealed no-answer/entity-ambiguity evaluation |
| Crystallization | Turn several sources into reusable claims | Model-assisted extraction, strict schema validation, resolvable source links, and deterministic long-document passage selection with exact offsets | Claim entailment, contradiction handling, redundancy, stability across models, and usefulness to people |
| Incremental evolution | Change knowledge without erasing why it changed | Explicit lifecycle transitions; schema-4 ledger and atomic SPLIT batches; content-bound provenance registry; replayable old ledgers; preview, receipt, CAS and execution-plan checks | Automatic action selection, calibrated independence rewards, cross-file recovery, and end-to-end quality under noisy inputs |

The third path is the deepest deterministic subsystem today. Its
`evidence-rule-v3` derives non-duplicate groups only through a shared
`source_key`, a trusted versioned full SHA-256 evidence digest, or persisted
`exact` / `near_duplicate` relations. Ordinary self-declared provenance is
retained for audit but never overrides those duplicate edges. The groups are
reported for inspection, not automatically certified as independent
corroboration: `independent_source_count` is conservatively `1` and the bonus is
disabled until a separately versioned scoring rule is evaluated. The new local
registry does solve authorization and audit identity: active attestations bind
the exact Entry, origin, and full digest; conflicting, revoked or missing grants
fail closed. Its hash chain provides integrity checks, not authentication.
Historical scores replay under their original algorithms.

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
configuration, cross-file transactions, filtered ANN for large collections,
and policy/LLM evaluations that measure decisions rather than mechanisms.

The SPLIT/NOOP decision trace records the input snapshot and request hash,
policy/algorithm versions, evidence IDs, target heads, reason, status, and the
shared `decision_id` of a planned UPDATE + CREATE. The production evidence
adapter stages both events and its durable receipt under one evidence-ledger
lock and file replacement. An execution-manifest hash prevents operation or
evidence substitution. The separate decision ledger is reconciled from the
domain receipt after failures, so the exact claim is “atomic inside the evidence
ledger and recoverable across the two ledgers,” not “one cross-file transaction.”

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
| Integrated policy | Choose and atomically execute memory transitions from incoming evidence | The SPLIT adapter is implemented; the remaining gate is policy accuracy and safety that beat simple rules on a held-out labelled set |
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

An interview-worthy technical contribution needs negative results and ablations,
not only a demo. Experiments test utility; they do not establish originality.
The three core paths are responsibilities, not three novel algorithms.
Each run must record the dataset revision, fixture hash, code commit,
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

The `coverage-semantic-v1` relevance signal and `query-support-v3` gate are tied
to the backend and version that produced them, not calibrated probabilities or
portable thresholds. When semantic retrieval degrades, production search falls
back to keyword coverage. On already inspected labels, the v3 post-hoc
regression reached Recall@5 `1.0`, nDCG@5 `0.9698`, and FPR `0.0`; that is a
mechanism regression, not blind evidence. The next experiment needs a newly
sealed set and a real embedding provider.

On 2026-09-04, a new fixed-code synthetic diagnostic was completed on 28 documents
and 24 queries. Fixed linear retrieval reached Recall@5 1.0 on 16 answerable
queries; the deployed gate configuration reduced this to 0.8125 through three
false rejections. It refused 5/8 protocol-defined no-answer queries, leaving 3/8
nonempty responses. These labels describe unavailable requested procedures/facts:
a retrieved explicit denial may still support a useful negative answer, so this
FPR is not a hallucination rate. This remains classical LSA and internally
authored synthetic evidence, not an independent external test or a live-model
result. See [the run record](EXPERIMENT-ROUND-2026-09-04.md).

### Crystallization

Give multiple systems the same source bundles. Blindly label whether each claim
is supported, whether its citations resolve and entail the claim, whether it
misses a contradiction, and whether it duplicates another card. Compare a
single-source summary, unconstrained multi-source generation, and Sheaf's
source-constrained pipeline. Frozen outputs currently prove fail-closed
provenance behavior only—not synthesis quality.

The deterministic passage selector has its own four-case synthetic diagnostic.
Under the same character budget, relevance+MMR hit at least one labelled span in
all four cases and recovered 4/7 spans; head truncation hit 2/4 cases and 3/7
spans. This verifies long-document evidence recovery mechanics only. It does
not show that an LLM will form a correct claim from the selected passages.

### Incremental evolution

Create evidence sequences containing confirmation, conflict, correction,
version changes, and irrelevant noise. Measure transition-action accuracy,
conflict recall, invalid-resolution rate, audit completeness, replay
correctness, and cost. Compare the frozen G0-G3 variants in
`evals/evidence-governed-memory/PROTOCOL.md`.

The current deterministic layer verifies quote/character-span identity,
historical replay and migration, `evidence-rule-v3` grouping, content-bound
registry grants, scoped official correction, decision-trace integrity, and one
atomic UPDATE+CREATE evidence-ledger commit. It still does not prove that a
model chooses the right transition.

## 8. Claim boundary

The 2026-09-04 representation audit also distinguishes capacity from use:
`CardVersion` and evidence locators exist, and can be projected to ordinary cards,
but ordinary crystallization does not automatically enter that ledger. Default
card text rendering truncates the claim and hides provenance/source IDs; card
embedding text excludes provenance and extra fields. A condition stored somewhere
is not necessarily visible to an Agent. These are distinct from semantic
extraction errors. See [the research agenda](REPRESENTATION-AND-RESEARCH-AGENDA.md)
and the [controlled transport diagnostic](../evals/representation-boundary/README.md).

Current safe claim:

> Sheaf implements and automatically tests a local, source-backed knowledge
> loop with stable keyword retrieval, a direct and diagnostically degradable
> Entry-level hybrid path, provenance-constrained crystallization, and
> replayable evidence updates with verified quote/span identity.

The checked-in classical retrieval baseline is useful precisely because it is
a negative result: hybrid did not beat keyword and no-answer FPR remained 1.0.
The later FPR `0.0` result is explicitly post-hoc. Claims such as “retrieves
better,” “solves abstention in general,” “creates more accurate knowledge,” or
“updates memory more intelligently than another project” remain unsupported.
