# Long-source method-selection experiment

This is a bounded **agent-reviewed synthetic** experiment, not external or human
gold. It compares source passages, reusable quoted facts, and candidate-filtered
facts under a common 800-token content allowance. It is an experimental adapter,
not an end-to-end claim about the production crystallization service.

The [protocol](protocol.md) defines the controls, failure denominators, two answer
draws, nine-task scope-eligible subset and cost scenarios. Authoring and independent
preflight review are in `DATASET-NOTES.md` and `PREFLIGHT-REVIEW.md`. Frozen input,
label, code and tokenizer identities are in `lock.json`.

## Reproduction

Use a repository checkout with its development dependencies and Python 3.10+.
Install `tokenizers==0.22.2` in a task-local environment. Download only the tokenizer
asset from the exact revision URL in `tokenizer.json.meta`; no model weights are
needed. Its expected SHA-256 is checked by the runner. Default asset location is
`.pytest-tmp/v3-assets/tokenizer.json`; alternatively pass `--tokenizer PATH`.

```powershell
python evals/method-selection-v3/run.py preflight --tokenizer PATH
python evals/method-selection-v3/revisions/encoded-budget-v1/run.py replay --tokenizer PATH
python evals/method-selection-v3/analyze.py
python -m pytest tests/test_method_selection_v3.py tests/test_method_selection_v3_transport.py tests/test_method_selection_v3_recovery.py tests/test_method_selection_v3_amendment.py tests/test_method_selection_v3_encoded_budget.py -q
```

Replay uses a network-denying transport and dummy key, reconstructs every request,
verifies receipts, recomputes context selection and scoring, and requires existing
outputs to match. It is evidence replay, not a claim that fresh stochastic model
outputs will be identical. Ordinary unit tests use no tokenizer asset or API.

The original execution used `run --execute` after a separate `freeze`/`preflight`.
It stopped after four calls because two extraction JSON outputs exhausted the
6000-token allowance. The [explicit amendment](revisions/output-cap-v1/protocol.md)
raises only extraction output allowance to 12000, preserves the original freeze,
reuses the original probe explicitly, and writes `run-v2-output-cap`. Use its
wrapper for full replay and its transport for campaign-wide accounting. The
original four-call partial run is retained, not relabeled as a completed comparison.

A second, explicitly post-run [budget correction](revisions/encoded-budget-v1/protocol.md)
counts the actual JSON context literal, including escapes, instead of the plain
context before serialization. Its `run-v3-encoded-budget` is the final corrected
table: 800 delivered-context tokens, unchanged extraction/labels/prompts, 48
identical raw-answer payloads reused and 36 changed fact-answer payloads sampled
again. Earlier result tables remain intact. This is not an untouched preregistration.
The opt-in live runner selects only the Paratera `DeepSeek-V4-Pro` credential
profile at the exact Paratera endpoint from local `.workbuddy/models.json`, but
requests `DeepSeek-V4-Flash`; it never changes that profile or production defaults.
No credentials are stored in this tree. Do not use live mode just to inspect results.

## Evidence and recovery

The single active campaign is `campaigns/paratera-flash-20260905`; it holds all
revision registrations, generation admissions, complete request bodies and raw
responses. Its total ceiling is 170 attempts / 600000 provider tokens. A revision
does not reset this budget. One unresolved send, provider identity/usage error or
two consecutive empty/truncated outputs stop new sends. Inspect evidence; do not
delete intents or retry automatically. Copying a completed campaign is supported
for offline review, not simultaneous live execution in independent directories.

`contexts.json` records all candidate units, selected/omitted identities, actual
quoted source spans and unused token allowance. `answer-plan.json` freezes the
shuffled requests. `results.json` contains all answers, conservative quote-span
scores, paired bundle-level descriptive intervals, known cache use and cost
accounting scenarios. Original provider envelopes remain in `calls/`.

`semantic-review-packet.json` hides arm names and automatic scores; its mapping is
separate. It covers all 72 first-draw positions, chosen before execution,
including 30 positions without an answer because construction failed. An
independent agent's post-run semantic review complements, but does
not replace, the frozen automatic table. No result licenses rewriting old labels.

Token counts are not a Paratera currency-price estimate. Full construction cost is
charged to each hypothetical standalone fact deployment; 1/5/20 future-query
scenarios extrapolate this sample's per-bundle mean rather than new live calls.
The final full-denominator fact-arm cost scenarios are unavailable because five
construction bundles failed. `analysis.json` separately labels a post-hoc,
survivor-biased three-bundle accounting scenario; it never replaces the primary
table. The final correction's `provider_cache_usage` covers only its new local
receipts; reused-call lineage identifies the original records for other usage.
