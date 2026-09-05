# Long-source method selection v3

Evidence grade: independently authored, agent-reviewed synthetic evaluation.
The author has a fresh context and does not see earlier fixtures, implementation,
or model responses. A second agent audits labels before any paid run. Neither is
a human annotator or an external data source. No scientific-gold claim is made.

## Question and comparisons

Under a fixed content-token allowance, can reusable method facts preserve the
evidence needed to select an applicable option? Does filtering facts to candidate
methods improve the result over selecting from the same unfiltered facts?

Eight bundles, three tasks each. Each bundle has 900-1400 English words across
3-4 sources. Labels and alternative sufficient support spans live only in gold.
Candidate IDs are normal task input, visible to every arm.
Task IDs remain in local manifests only, since their numeric ordering can correlate
with question types; model answer payloads contain only question and options.

- raw_passages: select complete source paragraphs/sentence groups.
- all_facts: select compact, source-quoted facts from one task-blind extraction.
- scoped_facts: remove facts about methods outside task.options before applying
  the same selection function. Bundle-wide facts remain eligible.

Extraction is shared by both fact arms and runs once per bundle. Every deployed
fact arm bears its full construction cost. Raw versus facts compares the complete
pipeline, including extraction, granularity and token occupancy. The all-versus-
scoped contrast isolates candidate filtering within the fixed extracted facts.
Both fact arms use exactly the same compact rendering and ranking parameters.

The experiment imports production passage tokenization and Jaccard primitives;
the unit selection adapter is an experimental candidate, not the full production
crystallization path. It never looks up evaluator spans for selection.

## Fixed execution

Paratera DeepSeek-V4-Flash, reasoning_effort=none, temperature=0.2, stream=false.
Extraction output cap 6000; answer output cap 1200; probe output cap 32.
Use the official tokenizer asset pinned by tokenizer.json.meta, tokenizers=0.22.2,
add_special_tokens=false. Each arm receives at most 800 locally counted context
tokens, including source IDs and fact syntax. Shared system, task and instruction
tokens are additional; all actual provider usage is reported. Provider-side chat
serialization and alias version are unverified, so equal local context caps do
not imply exactly equal billed input tokens.

Pre-freeze calibration, 2026-09-05: the initial 1200-token proposal was tightened
once to 800 after aggregate source lengths measured 1290-1330 tokens per bundle.
No model outputs existed. The original allowance nearly admitted the full source;
800 is a diagnostic pressure point, not an optimized or production-recommended
threshold. Only this one allowance is tested. An evaluator-only preflight verifies
that at least one sufficient gold set can fit as complete raw units for every task;
that oracle check is never passed to construction or selection. No change will be
made in response to fact expansion, extraction omissions, or answer quality.

Whole units only; no mid-quote truncation. Long raw paragraphs are split into
complete sentence groups at a 350-token soft target; one oversized sentence
remains a unit and can be rejected for budget. Facts are indivisible. Selection:
query term coverage weighted by log((unit_count+1)/(df+1))+1, plus density capped
at .2, minus .35 maximum Jaccard redundancy against prior selected units.
Weights use all units before scope filtering so the scoped contrast changes only
eligibility. Stable tie break is original unit order. Each proposed rendered
context is retokenized; units that cannot fit are skipped, not shortened.
Save candidate, selected and omitted IDs, source spans, token occupancy and slack.

Make two actual answer calls for each task and arm. Request IDs distinguish draws
even when payloads are equal. Randomize task and arm execution with fixed seed
20260905; draw two is a new model sample. No answer is reused as a second draw.
One extraction shared across draws means this does not measure extraction variance.

The full intended count is 1 probe + 8 construction + 144 answers = 153 calls.
Campaign-wide ceiling: 170 generation attempts and 600000 provider input+output
tokens, shared across revisions. Serial execution, no automatic retry, timeout
120s. All dispatches persist the complete effective payload (without credentials),
its hash, and the manifest hash before sending. Persist raw responses and usage.
Any unresolved intent stops new sends. HTTP/identity/usage errors stop after
preservation; two consecutive empty/truncated outputs stop the next send. A model
quality failure alone never ends the comparison early. Prices remain unknown.

## Labels and scoring

States: supported requires every task condition; explicit_negative requires an
explicit violation for every candidate; insufficient denotes missing or untested
relevant capability; conflict denotes blocking contradictory claims about the
same candidate, version and scope. Unresolved adjudication is distinct from a
dimension that was never measured. Mixed ambiguous states must be resolved in
task wording before freeze, not guessed after seeing outputs.

Gold support_sets is OR-of-AND: any one complete set of evidence spans suffices.
Quotes must be unique contiguous source spans and retain decisive identity,
conditions, versions, values and negatives. Multiple citations may jointly cover
a gold span without a gap. Equivalent smaller quotations can still be semantically
valid, so this exact-span metric is conservative and is not an entailment judge.

Report separately: schema/finish failures, decision accuracy, state accuracy,
source-quote identity, quote visibility in the actual selected context, sufficient
span coverage, and all criteria together. Gold span coverage asks whether cited
original intervals cover a sufficient set, not whether source IDs merely appear.
Also report whether selected context contained a sufficient set, so retrieval /
extraction omissions can be distinguished from answer-use errors. No hidden full
source may validate an invisible quote as a successful agent citation.

All 24 tasks remain in each arm and draw denominator, including failed extraction
or context preparation. Load gold for scoring only after response collection and
identity validation. Preflight label validation is a separate evaluator action;
extractor and selector only receive inputs.json, never labels or reviewed spans.

Main results average the two draws within task and then aggregate within eight
bundles. Paired resampling intervals, if reported, resample bundles rather than
treating 48 answers as independent. With eight synthetic bundles they remain
descriptive uncertainty, not evidence of broad statistical significance.
Also report the pre-specified subset whose task.options is a strict subset of
bundle.method_ids (nine of the 24 tasks), alongside the full denominator. Record
actual identical/different fact-arm contexts. The fifteen full-option tasks have
identical filtering eligibility; differences on identical inputs are sampling
variation, not a filtering benefit.
After completion, a reviewer audits anonymized responses and original sources,
without arm names or run score, to record semantic defects. The reviewer is an
agent, so this complements exact metrics rather than providing human validation.
The semantic review covers the pre-specified first draw of every task and arm
(72 answers), not a result-selected subset. It separately checks the decision,
state, and whether cited text supports the decisive conditions. The second draw
retains the same automatic metrics but does not count as semantically reviewed.

## Costs, stop rule and provenance

Report construction tokens, answer tokens and full standalone arm cost. Model
amortization for 1/5/20 queries as construction + n * mean query tokens, per bundle
and arm; this is an accounting scenario, not 20 newly executed queries. Track
cached input separately when the provider reports it; token savings do not imply
equal currency savings. Future queries use this bundle's three-task mean usage;
the second answer draw estimates that mean, not an extra future query.

Freeze fixtures, labels, prompts, selection code, tokenizer identity and protocol
before first generation. Correct ambiguity before freeze. If an invalid item is
discovered after results, preserve the original all-item table and report a
separate sensitivity table; never edit gold or silently remove a hard question.

This phase ends with the completed comparison, reproducible artifacts, failure
analysis and one investment decision. If fact arms do not show a useful quality /
cost tradeoff, stop expanding this schema and prioritize incremental action-policy
evaluation next. Product expansion, graph features and default-model migration
are outside this phase.
