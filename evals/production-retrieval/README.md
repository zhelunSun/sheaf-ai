# E1: current production retrieval, offline cached replay

This is a new experiment directory. It does not replace the older frozen/LSA evaluations.
No real task, corpus, reference judgments, embedding model, or paid budget has been accepted yet.
The bundled fixture is **synthetic mechanism evidence only**; its metrics say nothing about retrieval quality.

The runner invokes production `search_hybrid` twice on the same full corpus, raw text and K:
`alpha=1.0` (BM25 only) and `alpha=0.6` (hybrid), both with `min_evidence_score=0.0`.
It uses the production Entry semantic index with an exact text/model cache. Network and legacy card
fallback are disabled. Missing cached documents or queries abort before either arm runs.
It never collects sources, generates embeddings, calls an LLM, or edits the user's library.

From the repository root, using the existing development Python:

```powershell
python evals/production-retrieval/run_eval.py freeze evals/production-retrieval/fixtures/synthetic local-e1-freeze.json
python evals/production-retrieval/run_eval.py run local-e1-freeze.json local-e1-run.json
python -m pytest tests/test_production_retrieval_eval.py -q
```

Choose new output names: freeze and run records are never overwritten. Freeze records input/gold/cache,
runner and every production Python file hash, package versions, alpha values, raw inclusion and gate setting.
Any drift rejects the run, including a second check after ranking/scoring. A rejected run remains an error
record and must not be cited as valid quality evidence. A freeze is a reproducibility guard, not a signature
proving that labels or externally generated vectors are authentic.

The default run selects **dev queries only** and retains the complete candidate corpus. Final queries require
an explicit `--split final` after the configuration is frozen, with a separate output filename. Never use final
queries for harness debugging; a new filename does not make a repeated final test independent.

The result contains every attempted query/arm, raw production outputs and diagnostics, local elapsed time,
failures, selected-split aggregates and denominators. Labels are opened only after both arms finish ranking.
Cached replay latency **excludes provider latency**; this run's API cost is zero. Historical embedding cost is
reported only from the optional cache receipt, otherwise `not supplied`.

See [protocol.md](protocol.md) for real experiment preparation and interpretation limits. A real run still
requires a selected task, frozen legal source snapshots, checked labels, and externally acquired exact cache.
Do not rename synthetic vectors to a model name and present them as model results.
