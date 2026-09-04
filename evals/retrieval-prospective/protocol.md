# Prospective synthetic retrieval diagnostic / holdout — protocol v1

Registered on 2026-09-04T06:53:29.6983129Z, before creating this revision's corpus,
queries, or qrels and before generating any rankings. The paired code lock records
commit `4b2326a7323f1a978f59e7dc2edfb207743e53a6` and SHA-256 hashes of all tracked
production Python files, the unchanged frozen benchmark runner, and pyproject.toml.

## Claim boundary and author access

This is a **prospective synthetic diagnostic/holdout**, not an externally independent
blind test, real-user study, or estimate of deployment generalization. The model
author knows the retrieval task type and the fixed policy name/parameters. During
this task it inspected only the old runner interface, not `sheaf_ai/search.py`'s
implementation, old corpus/queries, or old gold. Hashing source bytes is allowed;
hashing is not semantic inspection. Synthetic documents contain invented facts,
reserved `.example` URLs, and no real-user data. No network or hosted embedding
provider is permitted.

## Frozen design, decided before sample construction

- One new revision: `2026-09-04.1`, with 28 corpus entries and 24 queries.
- 16 answerable queries and 8 no-answer queries; all qrels are `split=holdout`.
- Include Chinese and English, entity-name collisions, condition/version/location
  differences, compositional requests, paraphrase, and cross-language requests.
- Use opaque document and query identifiers. Every ranker query has exactly
  `query_id` and `text`; category, split, and relevance remain evaluator-only.
- Qrels use grade 3 for a direct full match, 2 for a useful but incomplete match,
  and 1 for weak contextual relevance. Only explicit, defensible answers count;
  sharing an entity name without requested conditions is not relevance. Empty
  relevance denotes no answer in this synthetic corpus, not global nonexistence.
- Author all samples and gold once. Lock corpus, queries, qrels, this protocol, and
  code-lock with SHA-256 in the manifest before the first real ranking run.
- After observing rankings, do not edit queries, documents, gold, policy parameters,
  or candidate arms. Preserve all failures, including rejected answerable queries.
  Implementation-only bug fixes must be disclosed; do not reinterpret gold.

## Fixed policy and comparison arms

Backend: unchanged `local-lsa-v1` from the frozen runner, a corpus-fitted classical
TF-IDF/SVD baseline, **not** a neural embedding result. No new backend tuning.

The four reported arms are keyword, semantic, fixed linear `alpha=0.25`, and
deployed `query-support-v3` gate over that linear policy with numeric
`min_evidence_score=0.4`. No alpha/threshold sweep, optimization, dev set, selected
candidate, release pass/fail criterion, or policy change is allowed. The gate is
invoked through the existing production search path, not reimplemented by the
evaluator. Rank depth is 10 and evaluation cutoff is 5.

The old runner's loader requires at least 30 queries and dev/test splits, and its
top-level evaluator performs dev selection. Those two helpers are not appropriate
to this fixed 24-query holdout. A new strict loader and fixed-arm evaluator will
therefore be added only here. The old `generate_rankings` function is reused via
importlib with its `ALPHAS` restricted to the already-fixed `(0.25,)`; incidental
RRF generation is discarded. The old files are not edited. This restriction does
not select a parameter from new samples.

## Ordering, isolation, and audit

1. Read manifest and ranker inputs; verify only their hashes.
2. Validate fixed code hashes and policy constants. Record current commit, dirty
   status, runtime/dependency versions, adapter hash, and fixed code hashes.
3. Generate and finish **all** four rankings using only corpus and query text.
4. Only then open, hash, parse, and validate qrels.
5. Score all queries and store complete rankings, diagnostics, per-query metrics,
   every defined failure, and aggregate results.

A test will prohibit even reading/hashing qrels until ranking completion. Further
tests cover label-bearing query rejection, fixture/hash drift, unchanged fixed
parameters, analytical metrics, no parameter selection, and no-overwrite output.
Manifest metadata is evaluator metadata and is never passed to the ranker. No
result is allowed outside this new experiment directory; result files use
exclusive creation and cannot overwrite any prior result.

## Preregistered metrics and interpretation

Report Recall@5, MRR@10, and nDCG@5 averaged over the 16 answerable queries (including
zero for false rejections). Recall uses all positive relevance grades; nDCG uses
`2^grade-1` gain. Empty-gold queries are excluded from relevance means.

For each arm also report:
- overall refusal rate: empty ranking / 24;
- no-answer refusal rate: empty ranking among the 8 no-answer queries;
- no-answer false-positive rate: nonempty ranking among those 8;
- false-rejection count/rate: empty ranking among the 16 answerable queries.

Keep per-query classifications for no-answer false positives, answerable false
rejections, missing relevant entries at 5, and relevant top-1 misses. Include
category counts and metrics only descriptively. No inferential significance,
causal claim, external-blind claim, or model superiority claim is planned. The
small synthetic set and LSA backend limit interpretation even if metrics improve.

## Reproduction

Run the new `run_benchmark.py` using the installed local Python, with a fresh output
filename. The runner has no tuning or network-backend flags. After first scoring,
record the compact findings and exact command without changing this protocol.
