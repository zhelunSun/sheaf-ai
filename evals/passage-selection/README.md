# passage-selection-v1 frozen synthetic diagnostic

This directory contains a small, hand-authored offline ablation for
`passage-selection-v1`. It is a **synthetic diagnostic**, not evidence of LLM
answer quality, user benefit, or production performance.

## Frozen inputs and label isolation

- `ranker_inputs.jsonl` is the only case data visible while passages are selected.
  It contains source documents, topics, ranker-visible entry metadata, and budgets.
- `evaluator_gold.jsonl` contains evaluator-only exact spans and required facts. It
  is loaded only after every strategy has completed two ranking passes.
- `manifest.json` assigns the two files disjoint roles and locks their exact byte
  lengths and SHA-256 digests. The runner refuses drift before ranking.
- `runs/passage-selection-v1-synthetic-diagnostic.json` is the checked result for
  the frozen manifest. Its `manifest_hash` and `input_hashes` bind the report to the
  evaluated bytes.

The four cases exercise a relevant fact near the tail, a relevant fact in the
middle, two distributed facts, and a document with no ranker-visible lexical
signal. The set is deliberately small enough for manual inspection.

## Compared strategies

1. `head_truncation`: the legacy first-`prompt_budget` characters.
2. `stratified_fallback`: the production selector with lexical inputs suppressed,
   forcing deterministic document coverage.
3. `current_relevance_mmr`: the production `passage-selection-v1` call with the
   case topic and entry metadata. It may legitimately report
   `stratified_fallback` when there is no lexical signal.

## Metrics

- **Evidence hit:** fraction of cases where at least one complete gold span is
  covered by a selected passage.
- **Span recall:** complete covered gold spans divided by all gold spans (micro).
- **Required-fact recall:** exact evaluator-only facts present in selected text
  divided by all required facts (micro).
- **Budget compliance:** fraction of cases at or below `prompt_budget`, plus mean
  selected characters and mean utilisation.
- **Determinism:** fraction of cases with identical structured selection output on
  two consecutive calls.

## Frozen result

| Strategy | Evidence hit | Span recall | Fact recall | Budget compliant | Deterministic |
| --- | ---: | ---: | ---: | ---: | ---: |
| Head truncation | 0.50 | 0.429 | 0.429 | 1.00 | 1.00 |
| Stratified fallback | 0.25 | 0.143 | 0.143 | 1.00 | 1.00 |
| Current relevance + MMR | 1.00 | 0.571 | 0.571 | 1.00 | 1.00 |

On these fixtures, current relevance + MMR raises case-level evidence hit and
micro span recall relative to both baselines. It still recovers only four of seven
gold spans, and the fallback baseline performs worse than head truncation. Those
are diagnostic observations from four synthetic cases, not a general superiority
claim. In particular, this benchmark does not exercise paraphrase matching,
semantic entailment, factual synthesis, real LLM generation, user preferences, or
production document distributions.

Run from the repository root:

```bash
python evals/passage-selection/run_benchmark.py \
  --output evals/passage-selection/runs/passage-selection-v1-synthetic-diagnostic.json
```
