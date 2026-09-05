# Anonymous semantic review of the fixed first draw

Completed 2026-09-05 by one agent, not a human annotator. All 72 preselected first-draw records were reviewed; none was selected or excluded based on observed quality. The packet contains **41 non-null parsed answers and 31 null answers**, not 42 reviewable answers. A null entry means no evaluable answer is available in this packet, not necessarily that no provider completion was ever received.

The reviewer read only the frozen inputs, gold, and anonymous review packet as evaluation evidence. No arm names, mapping, results table, selected contexts, or raw run responses were inspected. The packet's error strings expose failure types; they were used to document unavailable answers, not to infer arm membership. Group aggregation must occur afterward without changing these annotations. Only `semantic-review.json` and this summary were created; frozen gold and existing results were not edited, and no API was called.

## Scoring interpretation

Decision and state are judged against the frozen task and source interpretation. Submitted structured fields govern the actionable output: a conflicting or self-correcting explanation does not silently repair them. Only actual `citations` excerpts supply evidence; uncited assertions in `reason` and uncited full-source material cannot fill missing conditions or candidate exclusions.

Citation sufficiency asks whether those excerpts support the submitted decision and its necessary conditions. It is separate from state accuracy: correct abstention can have sufficient citations but a mislabeled state. Citations that establish a supported choice do not support an incompatible submitted abstention. Supported choices need the selected method's complete positive case, not exclusions of every alternative. Abstentions must cover the eligible alternatives. Semantic sufficiency does not require every word of an exact reference anchor: for example, the complete-index figures and mandatory-file statements in `a022` and `a050` suffice without repeating the source's entire explanatory archive-boundary sentence.

All 31 null answers receive false for all three booleans and an explicit issue. Their provided errors comprise 24 fact-count errors, 6 source-span-identity errors, and 1 JSON parse error. All 92 citations in the 41 available answers independently matched unique contiguous source text. This identity check does not establish visibility in a selected context: contexts were deliberately not read.

## Aggregate findings before unmasking

| Criterion | Pass / all 72 | Pass / 41 available answers |
|---|---:|---:|
| Decision semantically correct | 27 / 72 | 27 / 41 |
| State semantically correct | 21 / 72 | 21 / 41 |
| Cited evidence sufficient for submitted decision | 22 / 72 | 22 / 41 |
| All three criteria | 17 / 72 | 17 / 41 |

The second denominator describes the available answers; it does not replace the complete 72-record denominator.

- `a021`, `a030`, and `a054` contain explicit corrections in their explanations that conflict with the submitted decision fields. They remain incorrect outputs.
- Among correct decisions, state errors comprise missing tests labeled as observed failure (`a016`, `a031`, `a040`, `a072`), measured violations labeled insufficient (`a012`), and unresolved conflict labeled insufficient (`a067`).
- Four answers have correct decision and state but incomplete citations: `a013` omits Aster's exclusion and the board-B condition; `a014` omits the common metadata-write interruption condition; `a018` omits the other bridges' exclusions and unresolved-report status; `a070` omits CedarPlan-6's exclusion. `a067` additionally lacks the contrary N9 report needed for its correct abstention.
- Other incorrect answers introduce unsupported extra requirements or evidence gaps, including requiring all qualifications in one source statement (`a053`), requiring exclusion of alternatives before making a supported choice (`a029`), and treating the task's stateless-appliance setting as a manager property to prove (`a041`). `a069` fails to combine two requirements that its own explanation says Dune-15 satisfies.

These are observations about the fixed synthetic tasks and submitted answers. Without selected contexts, this review cannot assign omissions to extraction, retrieval, or answer use, or decide whether an abstention was locally reasonable given a particular truncated context. The coordinator may join the frozen annotations to the mapping and context diagnostics afterward while preserving both this review and the original automatic scores. This agent review supplies neither human validation nor external-validity evidence. Second-draw answers remain outside this predeclared semantic review and retain their automatic scoring.

## Provenance and output checks

- `inputs.json` SHA-256: `084c2bee916a5fc02eb4bf3814ccf663ebc1618904b0c97037c4fa395a539e2b`
- `gold.json` SHA-256: `8f971056cc9598d4e74be0f968ae0bf637fc99bd5134912d9abe1afa4f12a4b9`
- `semantic-review-packet.json` SHA-256: `ceb8c12930f4777acc44c4c9b39239f1411de06f1bda2b5b4e6d7a2012f13d31`
- `semantic-review.json` SHA-256: `53fe0dc1991bb867cd1a9b6c7fc30440f154bf1d6c02cc1608fd23d64ec372bc`

The output parses as an array of exactly 72 unique, matching anonymous IDs, with the requested five fields and boolean types. Every unavailable answer retains its denominator entry and issue. Input, gold, and packet hashes were unchanged at verification.
