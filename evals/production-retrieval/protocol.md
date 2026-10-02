# Bounded E1 protocol — draft until the real task is selected

Question: under one sustained user task, does current hybrid retrieval recover useful evidence better than
the same production lexical path? This evaluates ranking, not answer correctness, hallucination, adoption,
or long-term product value. Explicit contradictory/negative evidence can be relevant; absence of evidence
means no source in the fixed corpus supports an answer and is labeled separately.

## Revision files

Create a new revision directory containing three JSON files. The small synthetic revision is a format example.

1. `inputs.json`: `schema:1`, `evidence_kind:real-corpus`, a positive integer `k`, `corpus` and `queries`.
   Sources have `id,title,summary,tags,raw_text,source_group,split`, optional `topics,entities,collected_at`, and for real sources
   required `url,provenance`. Use opaque source IDs. URL is the original source URL or a clear `manual://`
   URI for author-supplied material; provenance records acquisition date, source/version and reuse basis.
   Keep title/summary/tags/topics, stored entities (`text,label`) and collection timestamp as the frozen
   production inputs available before labeling. Queries have only `id,text,group,split`.
   Entities preserve the production lexical boost and collection time preserves production tie-breaking;
   do not recompute or remove these fields when replaying an existing snapshot.
   Every split is `dev` or `final`; near duplicates, versions and paraphrases share one group and split.
   Ranker records reject additional label fields. Both arms search the same complete corpus.
2. `gold.json`: query IDs map to `evidence:present|absent`, graded `relevance:{source_id:0..3}` and optional
   `wrong_entity_ids`, `wrong_version_ids`, `required_conditions:{condition:[supporting_source_ids]}`.
   Positive relevance must stay within the query's split. Absent evidence requires `checked_entire_corpus:true`.
   Include human `audit_notes` in each gold label: quoted evidence span/location, version/entity and key-condition
   rationale, original source provenance and reviewer identity/date. For true absence, record the full-corpus
   check rationale. These notes are hashed with gold but excluded from ranking and numeric scoring. The runner
   cannot establish that judgments are independent or correct. No source grouping or labels should change
   after final results are seen.
3. `embedding-cache.json`: `kind:real-embedding-cache`, exact `model`, acquisition `provenance`, optional
   `cost_receipt`, and `vectors:[{text,text_sha256,vector}]`. The hash is SHA-256 of exact UTF-8 text.
   Document text must be production `entry_embedding_text` for the frozen fields/raw source and 12,000-character
   default limit; query text is the exact stripped query. All vectors have one dimension and finite numbers.
   The runner has no cache generation command or provider fallback. Obtain vectors separately only after
   the user confirms provider, model, maximum spend and source handling, then freeze the cache and receipts.

## Freeze and order

Suggested real size remains 30–40 sources / 24 queries, approximately 12 dev and 12 final. This is not a sample
already collected. Pick K and groups before results. Check source identity, version/date, negation and key
conditions; count invalid extraction and model construction failures in the source preparation report.
Freeze inputs, cache, labels and code before the final run. Use independent small dev cases to check the harness.
The CLI defaults to `--split dev`; `--split final` must be explicit. Only the selected queries and their gold
reach ranking/scoring; the full candidate corpus stays identical in both arms.
Final data is intended for one planned test after configuration is frozen; the runner refuses output overwrite
but does not prevent a person making another output file. Any later run or changed labels must be disclosed as
replication or a new/exploratory revision, never silently substituted for the original final run.

## Metrics and failure accounting

Recall@K uses all labeled relevant documents as denominator. nDCG@K uses gain `2^grade-1`, log2 discount,
and an ideal ordering from the full relevance set. Failed answerable query/arm attempts get zero in these means;
they remain in `attempted` and `failed`. Missing cache, input drift or invalid gold invalidates the whole run
with the error preserved; partial valid trials do not disappear from the output.

True no-evidence queries have null Recall/nDCG and a separate denominator, number of failed attempts and rate
of attempts returning candidates. Because the ranker gate is deliberately off, returning candidates is not
an assertion that an answer is supported. An errored no-evidence attempt is not a successful abstention;
read the failure count alongside the candidate rate. Entity/version and condition hits are exact source-label
diagnostics, not semantic judgments or final answer scores. No post-hoc threshold search, reranker, alternative
embedding model, or synthetic-vs-real substitution belongs in this fixed two-arm run.

## Interpretation and stopping

This runner can establish that current code executes the intended controlled comparison and preserves its
record. The bundled synthetic fixture only exercises that mechanism. Real embedding quality, external
provider latency/cost, current user benefit and generalization remain untested. Report adverse/neutral results.
If the real task or reference labels are not ready, stop at the runnable harness; do not invent a real corpus.
