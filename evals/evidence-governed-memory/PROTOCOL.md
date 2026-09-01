# Evidence-Governed Memory G0-G3 Protocol

> **Status:** Evaluation specification. No run has been executed and this file
> contains no results.

The adjacent `run_executor_acceptance.py` is a deterministic invariant smoke
test for the implemented state executor. It is intentionally not labeled a G3
run: it does not evaluate an LLM transition policy, claim extraction, grounding
quality, or calibration.

## 1. Question

When sources arrive sequentially, does evidence governance improve the quality
and auditability of a knowledge state beyond one-shot synthesis or incremental
editing without evidence rules?

This protocol evaluates the proposed mechanism on a small controlled fixture.
It is suitable for engineering acceptance and an interview demonstration. It
is **not** large enough to establish state-of-the-art performance or general
scientific superiority.

## 2. Frozen groups

Use the same source text, arrival order, model family, model version,
temperature, and token budget wherever the group permits.

| Group | System behavior | Purpose |
|---|---|---|
| **G0** | Summarize each source independently, then concatenate the summaries | Minimal non-synthesis baseline |
| **G1** | Run the current one-shot cross-source crystallization over all sources available at the final step | Tests batch synthesis without temporal state |
| **G2** | Incrementally choose create/update/merge/retire using semantic context, but hide source kind, source tier, conflict labels, and audit requirements from the policy | Isolates incremental operations from evidence governance |
| **G3** | Incremental operations with source IDs, evidence features, conflict preservation, ordinal evidence strength, and an append-only transition trace | Proposed system |

G2 and G3 must share the same operation executor. Only the policy inputs and
evidence-governance checks may differ. Otherwise an implementation difference
could be mistaken for a mechanism effect.

## 3. Fixture

`inputs.jsonl` contains four synthetic, copyright-free cases. Synthetic content
avoids using a model's world knowledge as the answer key. Evaluator-only answers
live separately in `gold.jsonl`; a policy runner must load model inputs through
`load_group_inputs()` in `validate_fixtures.py`, never by joining the two files.

Each input line contains:

- `case_id` and `topic`;
- a decision-shaped `user_question`;
- ordered `observations` with source ID, source kind, publication time, and text.

Each matching gold line contains `gold_by_step` with `allowed_operations`,
`required_behaviors`,
`forbidden_behaviors`, and `relevance_note`. Gold may be loaded only by the
scorer after the model output is immutable. The required loader removes source
kind and source tier from G0-G2 payloads; G3 receives both governance features
but never the gold fields. Case IDs are intentionally opaque so they do not
tell the policy whether a fixture expects correction, splitting, or no-op.

Source tier is an evaluation feature, not a truth oracle. Recency only matters
when the source explicitly describes a version or policy change.

## 4. Run record

Every run must write an immutable result directory outside this spec, for
example:

```text
evals/evidence-governed-memory/runs/<UTC timestamp>/
  manifest.json
  G0/<case_id>.json
  G1/<case_id>.json
  G2/<case_id>.json
  G3/<case_id>.json
  human_labels.jsonl
  metrics.json
  REPORT.md
```

`manifest.json` must include:

```json
{
  "run_id": "UTC timestamp or UUID",
  "git_commit": "full commit hash",
  "dirty_worktree": false,
  "input_fixture_sha256": "...",
  "gold_fixture_sha256": "...",
  "model_provider": "...",
  "model": "exact model identifier",
  "temperature": 0,
  "max_tokens": 4096,
  "prompt_or_policy_version": "...",
  "started_at": "ISO-8601",
  "completed_at": "ISO-8601",
  "executed": true
}
```

If the worktree is dirty, record the diff hash or refuse the official run. Do
not copy proposed thresholds into `metrics.json` as if they were observations.

## 5. Normalized output schema

Convert every group to the same scoring representation:

```json
{
  "case_id": "...",
  "group": "G3",
  "final_claims": [
    {
      "claim_id": "...",
      "text": "...",
      "status": "active|contested|retired",
      "supporting_source_ids": ["..."],
      "contradicting_source_ids": ["..."],
      "evidence_strength_ordinal": 0.0,
      "claim_correctness_probability": null
    }
  ],
  "transitions": [
    {
      "step": 1,
      "operation": "create|update|merge|split|retire|contest|noop",
      "before_claim_ids": [],
      "after_claim_ids": ["..."],
      "reason": "...",
      "source_ids": ["..."]
    }
  ],
  "latency_ms": 0,
  "input_tokens": 0,
  "output_tokens": 0,
  "raw_output_path": "..."
}
```

Groups without state transitions use an empty `transitions` array. `split` and
`noop` are policy-level operations: the current executor still needs the
versioned UPDATE+CREATE decision transaction and non-version-producing decision
trace described in the implementation roadmap. Missing fields remain missing
or null; do not synthesize provenance after generation.

## 6. Human labeling

Two passes are required:

1. **Blind content pass:** the reviewer sees claims and fixture sources but not
   the group name. Label atomic claim entailment, contradiction handling, and
   duplicates.
2. **Audit pass:** the reviewer sees transitions and provenance. Label trace
   completeness and operation acceptability against `gold_by_step`. This is the
   first point at which the gold fixture may be joined to a run.

One reviewer is enough for an engineering smoke run. A report used to make a
comparative quality claim requires two independent reviewers, disagreements
listed explicitly, and Cohen's kappa or raw agreement. An LLM judge may assist
but may not replace the human gold labels for the acceptance gate.

## 7. Metrics

Calculate raw numerator and denominator for every metric.

### 7.1 Claim grounding precision

`entailed atomic claims / all atomic claims`

A claim is entailed only when its cited source text supports it without relying
on outside knowledge. Claims with absent or invented source IDs are failures.

### 7.2 Citation completeness

`atomic claims with at least one resolvable supporting source / all atomic claims`

This is necessary but weaker than grounding precision.

### 7.3 Conflict preservation recall

`injected conflicts represented as contested or explicitly resolved with both sides retained / injected conflicts`

Silently choosing one side fails even if the final claim happens to match gold.

### 7.4 Transition accuracy

`steps whose operation and resulting claim state match an allowed gold transition / scored incremental steps`

The fixture may allow more than one operation sequence when the resulting
state and audit trace are equivalent.

### 7.5 Audit-trace completeness

For each update, merge, split, or retire, require:

- before and after identity;
- triggering source IDs;
- a non-empty reason;
- timestamp or sequence step; and
- access to the prior state.

Report `complete destructive transitions / all destructive transitions`.

### 7.6 Redundancy ratio

`duplicate active claim pairs / all active claim pairs`

Two claims are duplicates when they make the same assertion under the same
conditions, not merely when they share a topic.

### 7.7 Calibration

Only a separately defined claim-correctness probability may be scored with
Brier score. The executor's deterministic evidence strength is ordinal and
must never be substituted for that probability. When an aligned probability is
emitted, label atomic claims correct/incorrect, report Brier score, and print a
coarse reliability table. With this small fixture, do not claim that ECE is
stable or generalizable.

Compare structured G3 confidence with the G1 model-reported baseline only when
both are defined over the same labeled claims.

### 7.8 Efficiency

Report median and per-case latency, input tokens, output tokens, and model calls.
Do not hide failed or retried calls.

## 8. Acceptance gates

These gates are deliberately strict on provenance because the product promise
is trust, not merely fluent output.

### Critical gates for G3

- **0 invented or unresolvable source IDs.**
- **100% audit-trace completeness** for destructive transitions.
- **100% preservation of prior state** after update, merge, split, or retire.
- **0 silently discarded injected conflicts.**
- **0 invalid state transitions or broken history links.**

Any critical failure blocks the vNext acceptance demo.

### Quality gates for this fixture version

- Claim grounding precision >= 0.90.
- Citation completeness = 1.00.
- Conflict preservation recall = 1.00.
- Transition accuracy >= 0.85.
- Redundancy ratio <= G2 and <= G1.
- G3 Brier score <= G1 model-reported-confidence Brier score only when both
  groups emit aligned claim-correctness probabilities for at least 10 labeled
  claims. Mark the gate `not_applicable` while G3 exposes only ordinal evidence
  strength, and `insufficient_n` when probabilities exist but the sample is too
  small.
- G3 median model calls <= 2.5x G1 median model calls.

The fixture passes only if all critical gates and at least four of the first
five applicable quality gates pass. Efficiency is reported as a product
trade-off and does not excuse a critical provenance failure.

Thresholds are design choices for this small fixture, not previously observed
performance. Change them only in a versioned protocol revision before a run.

## 9. Reporting rules

`REPORT.md` must contain:

1. exact run manifest and both fixture hashes;
2. a G0-G3 table with raw counts and scores;
3. one worked transition trace per case;
4. every critical failure, retry, parse fallback, and reviewer disagreement;
5. limitations of synthetic data and sample size;
6. a conclusion limited to the tested fixture; and
7. a claim ledger with `supported`, `not supported`, or `not tested` status.

Forbidden reporting patterns:

- writing “G3 improves trust” without a named metric;
- presenting a protocol threshold as a measured score;
- dropping failed cases from the denominator;
- comparing different models or source sets without labeling the confound;
- using “calibrated” when only monotonicity was tested; or
- calling this small fixture a benchmark of the broader memory market.

## 10. Interview use

The interview artifact is the combination of:

- this frozen protocol;
- the versioned fixture;
- raw G0-G3 outputs;
- human labels;
- the generated score sheet; and
- a five-minute demo replaying one passing G3 case.

Before a run exists, describe this as an evaluation design. After a run exists,
quote the exact run ID and only the metrics that passed their gates.
