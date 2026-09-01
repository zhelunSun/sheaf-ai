# Frozen Entry Retrieval Experiment

> Current frozen revision: `2026-09-01.2` — 22 Entries and 36 queries.

This experiment separates four concerns that were previously conflated:

1. Ranker-visible queries contain only `query_id` and `text`.
2. `category`, `split`, and `relevance` live in evaluator-only `qrels.jsonl`,
   which is loaded after rankings exist.
3. `manifest.json` locks the role and SHA-256 hash of all three fixture files;
   the runner fails if any file drifts.
4. `run_benchmark.py` records every top-ten ranking, dataset hash, backend, model,
   development-set selection result, evaluator split result, category slice,
   and negative case.

Revision `2026-09-01.1` remains in this directory for compatibility. It exposed
`category` in `queries.jsonl`, including the `no_answer` label, so its runner
contract was not label-isolated even though the ranking loop did not read that
field. Revision `2026-09-01.2` is under
[`revisions/2026-09-01.2`](revisions/2026-09-01.2) and is the default.

The locked hashes are:

| File | Role | SHA-256 |
|---|---|---|
| `corpus.jsonl` | ranker input | `1e6d271d17ff86486926145f52117b911a9255d18c8e1ac95a2163ae79a02fbe` |
| `queries.jsonl` | ranker input | `0824902a285db4759fa251db4716a01af457ce81faa01d3371a575145e15e304` |
| `qrels.jsonl` | evaluator only | `9cd809eaec70f15e92d70beec97259832a2f99ac9c6a8d3985f03b05bb65717b` |

Run the reproducible local classical baseline:

```bash
python evals/retrieval-frozen/run_benchmark.py --backend local-lsa
```

Re-run the legacy data contract explicitly with:

```bash
python evals/retrieval-frozen/run_benchmark.py \
  --backend local-lsa \
  --fixture-dir evals/retrieval-frozen
```

The local backend combines word/character TF-IDF with truncated SVD. It is
useful for testing the production Entry index and the ablation protocol, but it
is **not** a neural embedding model.

## Checked-in result

[`runs/local-lsa-v1.json`](runs/local-lsa-v1.json) is the checked-in classical
baseline. Development-set selection chose `linear-0.25` with a minimum
retrieval-evidence score of `0.4`. Its held-out test metrics are:

| Method | Recall@5 | MRR | nDCG@5 | No-answer FPR |
|---|---:|---:|---:|---:|
| Selected `linear-0.25 @ 0.4` | 0.9375 | 1.0000 | 0.9498 | 1.0000 |
| Keyword | 0.9688 | 1.0000 | 0.9560 | 1.0000 |

This is a negative result: the selected local-LSA hybrid did **not** outperform
keyword retrieval, and both no-answer test queries produced false positives.
The experiment therefore does not establish better retrieval and does not
solve abstention. It gives the next iteration concrete failure cases in
no-answer handling and entity ambiguity.

## Query-support v2 diagnostic

After inspecting the two no-answer failures, production search was changed to
separate candidate ordering from a query-level answerability decision. The
follow-up run is preserved as
[`runs/local-lsa-v1-query-support-v2-diagnostic.json`](runs/local-lsa-v1-query-support-v2-diagnostic.json).
It reuses the selected `linear-0.25` ordering and the numeric value `0.4`, but
the threshold now controls one query-level decision; it is not the baseline's
per-result cutoff. The run records an explainable reason for accepting or
rejecting the returned candidate set.

| Run | Recall@5 | MRR | nDCG@5 | No-answer FPR |
|---|---:|---:|---:|---:|
| Original selected baseline | 0.9375 | 1.0000 | 0.9498 | 1.0000 |
| Query-support v2 diagnostic | 1.0000 | 1.0000 | 0.9698 | 0.0000 |

These numbers are useful regression evidence, not a new blind effectiveness
claim: q-035 and q-036 were examined before the rule was implemented. The JSON
report therefore sets `eligible_for_blind_effectiveness_claim` to `false`.
A newly sealed test set is required before claiming general no-answer gains.
The original negative report remains unchanged.

## Query-support v3 post-hoc regression

The current Unicode identity, CJK bigram, mixed-language, filter-scope, and
multi-candidate rules are preserved in
[`runs/local-lsa-v1-query-support-v3-posthoc.json`](runs/local-lsa-v1-query-support-v3-posthoc.json).
On the same already-known labels they retain Recall@5 `1.0000`, MRR `1.0000`,
nDCG@5 `0.9698`, and no-answer FPR `0.0000`. The report deliberately calls the
slice `known_test_posthoc`, not `test`, and remains ineligible for a blind
effectiveness claim. These unchanged metrics are regression evidence only.

The 22-entry fixture fits inside the production candidate depth and has no
structured-filter queries. Limit independence and fail-closed filtering are
therefore pytest invariants, not conclusions from this frozen benchmark.

`retrieval_evidence_score` (`coverage-semantic-v1`) is an experimental,
backend/version-specific gate signal, not a probability or a portable global
threshold. Results expose `retrieval_evidence_mode`; when semantic retrieval is
degraded or unavailable, the mode is `keyword_coverage` rather than silently
treating a missing semantic score as healthy evidence.

Run a configured OpenAI-compatible embedding model without fallback:

```bash
python evals/retrieval-frozen/run_benchmark.py \
  --backend live \
  --model text-embedding-3-small \
  --output evals/retrieval-frozen/runs/openai-text-embedding-3-small.json
```

The live run fails closed if credentials or the provider are unavailable. A
report path is immutable by default: the runner refuses to overwrite it.
Hyperparameters are selected on the development split; the test split is only
used for the final comparison. No live embedding run was produced in this
snapshot because credentials were unavailable. This remains a
synthetic-but-realistic offline benchmark, not evidence of user value or
superiority over another product.
