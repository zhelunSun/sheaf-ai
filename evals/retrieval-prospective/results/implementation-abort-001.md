# Implementation-only abort before gold scoring

On 2026-09-04, the first real full-ranking attempt ran:

```
python evals/retrieval-prospective/run_benchmark.py --output evals/retrieval-prospective/results/local-lsa-2026-09-04.1-first.json
```

The unchanged frozen generator completed its rankings. The new adapter then
raised `ValueError: Unexpected deployed evidence version` before returning to
`run_benchmark`, hence before that run opened, hashed, parsed, or scored qrels.
No report was created. The unscored in-memory rankings were not persisted.

Cause: the adapter incorrectly required each candidate's numeric
`retrieval_evidence_version` to equal `query-support-v3`. A one-query interface
probe on q-001, without gold access or metrics, showed the existing public
contracts are:

- candidate numeric evidence version: `coverage-semantic-v1`;
- query diagnostic `retrieval_gate_version`: `query-support-v3`.

The adapter now checks the query-level version and complete gate diagnostics;
it separately records numeric signal versions. The probe inspected only returned
diagnostics, not the production search implementation or old gold. No corpus,
query, qrel, manifest, protocol, production code, old evaluation code, alpha,
threshold, backend, ranking depth, or scoring rule changed. This is an evaluation
interface correction, not parameter selection. The first completed scored run
retains its originally planned `...-first.json` filename because it did not exist.
