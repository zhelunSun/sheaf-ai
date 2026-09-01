# Frozen Entry Retrieval Experiment

> Frozen revision: `2026-09-01.1` — 22 Entries and 36 queries.

This experiment separates four concerns that were previously conflated:

1. `corpus.jsonl` and `queries.jsonl` are ranker-visible inputs.
2. `qrels.jsonl` is evaluator-only gold and is loaded after rankings exist.
3. `manifest.json` locks the role and SHA-256 hash of all three fixture files;
   the runner fails if any file drifts.
4. `run_benchmark.py` records every top-ten ranking, dataset hash, backend, model,
   development-set selection result, held-out test result, category slice, and
   negative case.

The locked hashes are:

| File | Role | SHA-256 |
|---|---|---|
| `corpus.jsonl` | ranker input | `1e6d271d17ff86486926145f52117b911a9255d18c8e1ac95a2163ae79a02fbe` |
| `queries.jsonl` | ranker input | `a10f78de9cd2a8b86a956309f089f6e43aadab21acbc9207f6b84567d03678e1` |
| `qrels.jsonl` | evaluator only | `8b4bd5dc5c3bef1d07387f96217252dcfb92cc00a296fad5f1098c19bb81787d` |

Run the reproducible local classical baseline:

```bash
python evals/retrieval-frozen/run_benchmark.py --backend local-lsa
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

`retrieval_evidence_score` (`coverage-semantic-v1`) is an experimental,
backend/version-specific gate signal, not a probability or a portable global
threshold. When semantic retrieval is degraded or unavailable, production
search computes it on the keyword-coverage scale rather than treating a missing
semantic score as healthy evidence.

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
