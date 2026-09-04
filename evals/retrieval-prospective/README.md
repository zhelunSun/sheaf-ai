# Prospective synthetic retrieval diagnostic / holdout

One completed scored run on revision `2026-09-04.1`: 28 invented documents,
24 queries, 16 answerable and 8 no-answer. This is model-authored synthetic data
created after freezing production commit `4b2326a7323f1a978f59e7dc2edfb207743e53a6`;
it is **not externally independent blind evaluation or real-user generalization**.
The author knew the task type and fixed gate policy, but did not inspect the
production search implementation or old corpus, queries, or gold during this task.

## Fixed-arm results

Backend is `local-lsa-v1` (classical corpus-fitted TF-IDF/SVD, not neural embeddings).
Linear alpha remained 0.25; the deployed query-level `query-support-v3` gate used
numeric `min_evidence_score=0.4`. No new-data parameter search or policy change.

| Arm | Recall@5 | MRR@10 | nDCG@5 | All-query refusal | No-answer refusal | False rejection |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Keyword | 1.000000 | 0.968750 | 0.976933 | 0/24 | 0/8 | 0/16 |
| Semantic / local LSA | 1.000000 | 0.906250 | 0.930799 | 0/24 | 0/8 | 0/16 |
| Fixed linear | 1.000000 | 1.000000 | 1.000000 | 0/24 | 0/8 | 0/16 |
| Fixed gate | 0.812500 | 0.812500 | 0.812500 | 8/24 (33.33%) | 5/8 (62.50%) | 3/16 (18.75%) |

Relevance metrics average only answerable queries, including zero for false
rejections. No-answer false-positive rates are 100% for the three ungated arms and
37.5% (3/8) for the fixed gate. The gate rejects five otherwise-returned no-answer
queries, but also rejects three answerable queries; this is a measured trade-off
on this particular synthetic set, not a superiority or release-readiness claim.

All three false rejections had the relevant entry ranked first by fixed linear:

- `q-008`: Sable Archive monthly offline integrity audit, English paraphrase.
- `q-011`: Tinfin transparent PNG export, Chinese query / English document.
- `q-018`: Brindle seminar volunteer check-in, multi-part English request.

Their returned gate reason is `unsupported_modifiers`. Gate false positives are
`q-009` (five-metre wind-sensor procedure), `q-013` (frost-triggered sprinkler
threshold), and `q-019` (2030 tax-report export). No failures were removed from the
report. Full top-10 rankings, scores, gate diagnostics, per-query metrics, category
summaries, and all defined failure types for all four arms are retained in
`results/local-lsa-2026-09-04.1-first.json`.

## Integrity and limitations

`protocol.md` and `code-lock.json` were written before sample construction. The
manifest freezes the corpus, queries, gold, protocol, and code lock. The runner
checks 67 fixed source/configuration files and records current commit, dirty
status, adapter SHA-256, and dependency versions both before and after scoring.
The initial code freeze was clean; the scored run was dirty because the new
experimental files and concurrent experimental work were untracked. All fixed
file hashes still matched and the production entry index was healthy.

Ranker queries have only `query_id` and `text`. All four rankings finish and pass
coverage validation before qrels is opened or hashed. Qrels alone carries
category, split, and relevance. Everything is holdout; the old dev-tuning evaluator
is not called. The unchanged old generator is reused only for its ranking path,
with its unused alpha arms disabled. Socket connections are blocked during the
ranking call, and no real-user data or external services are used.

The initial full-ranking attempt aborted before gold access because the new
adapter confused the numeric evidence version with the query-level gate version.
`results/implementation-abort-001.md` preserves the failure and one-query interface
probe. Only the version assertion was corrected; samples, gold, protocol,
manifest, fixed policy, and production/old evaluation code were unchanged. The
completed report separately records `coverage-semantic-v1` numeric evidence and
`query-support-v3` gate diagnostics.

Small, model-written, deliberately contrastive documents and explicit unsupported
conditions do not represent a sampled deployment distribution. Some documents
explicitly deny a requested capability; a returned denial could support a useful
negative answer, but this preregistered retrieval task counts the requested
procedure/capability as unavailable. Consequently no-answer false positives are
retrieval-policy diagnostics, not a measurement of generated hallucination.
The LSA model, easy entity cues, and synthetic same-name distinctions further
limit interpretation. Gold was not reinterpreted after observing failures.

## Reproduce and verify

From the repository root, using the installed local environment:

```powershell
python -m pytest tests/test_retrieval_prospective.py -q
python -m ruff check evals/retrieval-prospective/run_benchmark.py tests/test_retrieval_prospective.py
python evals/retrieval-prospective/run_benchmark.py --output evals/retrieval-prospective/results/local-lsa-2026-09-04.1-reproduction.json
```

Use a fresh output filename on each invocation. Existing reports are rejected
before ranking, and exclusive file creation prevents overwrite races. Reproducing
the frozen run is not another independent holdout. The first completed run used
the same command with output `.../local-lsa-2026-09-04.1-first.json`.

The ordinary code-snapshot unit test simulates the historical file hashes and
file set, then injects drift. It does not require future production code to remain
unchanged. The real runner/CLI still strictly rejects code drift. New algorithms
belong in a separately preregistered revision with their own code lock; never edit
this historical lock to make new code pass. Reusing these already-scored samples
is regression evaluation, not a new prospective holdout. This test-maintenance
clarification did not change frozen assets or rescore the experiment.

After the first scored run, replay compatibility was added for Git checkout line
endings: `core.autocrlf=true` can change the raw bytes of a historically mixed-EOL
file. A raw hash mismatch is accepted only when the lock records a clean initial
checkout and the current bytes, with CRLF replaced by LF, exactly equal the same
path's Git blob at `code-lock.commit`. No other whitespace/content normalization
is allowed, and current HEAD is never used as the comparison authority. Replays
record `line_ending_only_drift_files`, observed raw hashes, and frozen raw hashes.
Missing historical blobs or any non-newline content drift still fail closed.
This is a post-first-run replay compatibility correction, not a new experiment,
parameter change, or rescore. Historical code-lock, manifest, and report bytes
remain unchanged; the first report naturally predates these new audit fields.

Validation performed: 18 focused tests passed and both new Python files passed
Ruff. Tests cover gold access order (including hashing), incomplete rankings,
strict ranker schemas, fixed policy, data/code drift, analytical metrics, refusal
denominators, complete failure retention, scoped no-overwrite output, and
fixed-commit Git-blob checks accepting only newline drift.
Runtime: NumPy 1.26.4, SciPy 1.13.1, scikit-learn 1.5.1, pytest 9.0.3.
