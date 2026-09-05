# Anonymous semantic review: encoded-budget revision

This is an agent review, not human annotation or external validation. It covers all **72 fixed first-draw records** in the new anonymous packet: **42 non-null parsed answers and 30 null answers**. The complete denominator is retained.

Full decoded records, including `id`, `task_id`, `answer`, and `error`, were compared with the previous anonymous packet. **54 records were exactly identical** and their five-field annotations were copied unchanged. **18 changed records were rereviewed in full**, including changed explanations or citation order even when their decision fields were unchanged. Identical-record reuse is not a new model sample or a new independent observation.

The freshly reviewed IDs are `a016`, `a017`, `a019`, `a022`, `a028`, `a029`, `a031`, `a033`, `a034`, `a037`, `a042`, `a050`, `a056`, `a059`, `a061`, `a063`, `a066`, and `a071`. Every other ID preserves the prior annotation exactly.

The reviewer used only the frozen inputs/gold, the two permitted anonymous packets, and the previous annotations. No mapping, selected contexts, results table, arm names, or raw response files were inspected. No API was called, and no pre-existing file, label, or algorithm was changed. This review does not independently verify the underlying context-budget correction. Only the two new review files in this directory were written; judgments are final before group aggregation.

## Same scoring contract

Decision and state refer to the submitted structured output against the frozen source-task interpretation. A reason that announces a different answer does not repair contradictory decision fields. Evidence sufficiency uses actual citation excerpts, not uncited claims in the explanation or uncited source text. It asks whether those excerpts support the submitted decision and its necessary conditions, separately from state-label correctness.

A supported choice requires its own complete positive case, not mandatory exclusion of every other method. An abstention must cover the eligible alternatives. Correct abstention can therefore have sufficient citations while using the wrong state. Complete-index measurements in `a022` and `a050` are semantically sufficient for the tested index-size requirement; the review does not require repeating an entire explanatory reference sentence solely to achieve literal-anchor coverage.

All 30 null entries receive three false values and an issue, preserving the denominator. Their packet errors are 24 fact-count errors and 6 source-span-identity errors. A null entry denotes unavailable reviewable output, not necessarily the absence of a raw provider completion. All **90 citations** in the available answers independently matched unique contiguous original-source text. This establishes source identity, not visibility within a selected context.

## Results before unmasking

| Criterion | Pass / all 72 | Pass / 42 available answers |
|---|---:|---:|
| Decision semantically correct | 30 / 72 | 30 / 42 |
| State semantically correct | 23 / 72 | 23 / 42 |
| Cited evidence sufficient for submitted decision | 25 / 72 | 25 / 42 |
| All three criteria | 19 / 72 | 19 / 42 |

The available-answer denominator is descriptive and does not replace 72. Within the 18 rereviewed records, 13 decisions, 10 states, and 13 citation sets pass; 10 pass all three criteria.

The revised responses at `a028`, `a029`, and `a037` now select the supported method with sufficient citations. `a059` still correctly abstains and cites both excessive required footprints but newly mislabels the observed violations as insufficient evidence. `a017` is now a parsed answer, yet its submitted choice of MicaX contradicts the 25 MiB limit and the explanation's repeated announced abstention; it fails all three checks. These comparisons describe changed records, not a causal effect of the budget repair.

The other changed records retain their prior pass/fail pattern after fresh review. `a016` and `a031` still misclassify unperformed salt-mist testing as explicit failure. `a019` and `a061` do not cite a basis for the asserted cold-performance evidence gaps; `a033` and `a034` do not cite a basis for rejecting Larch's local-operation support. The unchanged records retain their previously recorded issues without reinterpretation.

Without selected contexts, missing evidence cannot be attributed here to extraction, selection, or answer use. The coordinator may join these fixed judgments to the mapping and context diagnostics afterward, preserving both prior and new annotations and the original automatic tables. The second draw remains outside this semantic-review sample. The result is bounded to the synthetic fixture and one agent's stated interpretation.

## Provenance and validation

- Previous packet SHA-256: `ceb8c12930f4777acc44c4c9b39239f1411de06f1bda2b5b4e6d7a2012f13d31`
- Previous annotation SHA-256, unchanged: `53fe0dc1991bb867cd1a9b6c7fc30440f154bf1d6c02cc1608fd23d64ec372bc`
- New packet SHA-256: `51633c0b05a5c3f03cd9c9a4e7208b2f1098ec7fac51a5b494cfb84ce8e46fa5`
- New `semantic-review.json` SHA-256: `de5d089fdaf0809ccd01328034eecf9d92ddf0b706b009ec25e6f280cabb1f2a`
- Frozen input SHA-256, unchanged: `084c2bee916a5fc02eb4bf3814ccf663ebc1618904b0c97037c4fa395a539e2b`
- Frozen gold SHA-256, unchanged: `8f971056cc9598d4e74be0f968ae0bf637fc99bd5134912d9abe1afa4f12a4b9`

Validation confirmed 72 unique IDs matching the new packet, exactly the requested five fields and boolean types, unchanged annotations for all 54 identical records, and explicit failure treatment for all 30 null entries. Previous packet/annotation and frozen input/gold hashes were unchanged after writing the new output.
