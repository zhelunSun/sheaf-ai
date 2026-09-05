# Extraction Review: `run-v2-output-cap`

## Scope and conclusion

This is a bounded, read-only review of `inputs.json`, `extracted-facts.json`, and the eight complete `extract-x01` through `extract-x08` intent/result receipt pairs. It did not read gold, answer responses, answer results, or scoring outputs. All eight package parse/validation outcomes were checked; the semantic review below uses named examples and deterministic citation checks, but is not a claim that every fact received full human semantic review.

Raising only the extraction output cap to 12,000 removed the prior `finish_reason=length` failure: all eight extraction calls returned HTTP 200, `finish_reason=stop`, provider model `DeepSeek-V4-Flash`, and provider-reported `reasoning_tokens=0`. It did not make the extraction stage healthy. Only 3 of 8 bundles were admitted by `extracted-facts.json`; four exceeded the frozen 40-fact contract and one failed verbatim citation validation.

## Complete package status

Counts below are from the normalized JSON arrays in the complete extraction receipts, including arrays rejected by the importer. `Global` means `method_id=null`.

| Bundle | Receipt facts | Global | Global share | Extraction artifact status | Output tokens |
|---|---:|---:|---:|---|---:|
| x01 | 31 | 15 | 48.4% | accepted | 4,967 |
| x02 | 47 | 19 | 40.4% | failed: `Expected 1-40 facts` | 8,681 |
| x03 | 31 | 17 | 54.8% | accepted | 4,850 |
| x04 | 39 | 14 | 35.9% | failed: `Citation not a unique original span` | 5,443 |
| x05 | 41 | 19 | 46.3% | failed: `Expected 1-40 facts` | 7,960 |
| x06 | 41 | 22 | 53.7% | failed: `Expected 1-40 facts` | 6,957 |
| x07 | 39 | 14 | 35.9% | accepted | 6,533 |
| x08 | 41 | 25 | 61.0% | failed: `Expected 1-40 facts` | 9,267 |

Across the eight complete receipts, the model emitted 310 facts, including 145 global facts (46.8%), 325 citations, and 54,658 output tokens. The fail-closed artifact retains 101 facts from x01, x03, and x07; it does not silently truncate an over-limit array to 40.

The x02 and x04 raw messages used a whole-message JSON fence. Removing only that wrapper produced valid arrays; their reported failures are respectively the 47-fact limit and citation identity, not incomplete JSON. The other six responses were bare JSON.

## Citation and condition findings

The seven-field schema is present (`method_id`, `fact_type`, `statement`, three scope/condition arrays, and `citations`), but several facts put critical identity or applicability information only in the paraphrased fields rather than in the cited span.

- A deterministic literal check found 24 of 165 method-specific facts whose combined citation quotes do not name their `method_id`. This is a self-containment warning, not a complete entailment metric. Examples include x01 fact 9 (`Its in-memory checksum buffer...` assigned to Tide-4), x02 facts 4-6 (`All three returned correct record identifiers...` split into Oak, Silt-22, and N9), x06 facts 7-9 (`all three packages` split into three method-specific wrong-board rejection facts), and x08 fact 15 (`The replay observed...` assigned to Kestrel).
- x01 facts 1-3 attach the one-worker, 8,000-file, 512 MiB, retained-process setup and four not-evaluated dimensions to each method, while their cited result sentences do not contain those setup details. Those qualifiers are available elsewhere in x01s1, but not in the fact's citation.
- x02 latency facts add release identities such as Oak release 3 and N9 release 9.2 although the long latency quote begins with the workload and uses only the short method names. The release mapping is in preceding source context. The facts are source-traceable, but the citations do not satisfy the prompt's stronger request to keep method version and complete conditions in the cited spans.
- x04 has five mechanically invalid quotes. In each case the source ends a clause with a semicolon, while the model changed it to a period. Named cases include `Q2x used a smaller buffer and spilled repeatedly.` and the two split facts citing `Vela and CedarPlan-6 can export the loaded rule-pack checksum without contacting another service.`
- x06 also contains a non-verbatim quote in raw fact 28, hidden behind the earlier 41-fact rejection. The fact claims no lower-than-gate test was reported, but cites a modified sentence about ordinary success at a stated charge not establishing lower-charge startup.

These findings do not show that every affected statement is false. They show that downstream evidence cannot rely on citation-substring validity alone to recover all method/version/test conditions.

## Fact-type boundary findings

The type labels are not used consistently at the important absence/conflict/denial boundary.

- Untested or unreported scope is sometimes labeled `explicit_denial`: x01 fact 16 says the clients were not tested for repairing an incorrectly owned directory; x03 fact 26 says no salt-mist exposure test was performed; x06 facts 10-15 say board-C and surrounding functions were not evaluated; x08 fact 16 says no 256-bit latency test was performed. Nearby facts describing equivalent missing evidence use `unreported_dimension`, including x08 fact 17 for the same missing 256-bit p95 evidence.
- Inferential cautions are also labeled `explicit_denial`, for example x01 fact 22 (an inventory is not proof of safe resume), x03 fact 29 (dry cold or room-temperature vibration cannot establish salt-mist performance), and x07 fact 21 (literal-code results do not imply semantic-match quality). These are useful limitations but are not necessarily explicit negative method capabilities.
- `unresolved_evidence` is sometimes used without contradictory active evidence. x01 fact 30 is an unexecuted proposed memory exercise. In x05, facts 37-41 include a hypothetical stateless workload, a warning about log-line evidence, a failure-counting convention, a workflow interpretation, and a removed experimental symbolic link. These are scenario, provenance, or missing-evidence facts rather than unresolved disagreements.
- `requirement` is overextended to descriptive protocol/context. x02 facts 37-47 restate workload, query, disk, cut-schedule, and replay setup; x08 facts 31-41 similarly restate measurement configuration and instrumentation. Preserving this context is valuable, but treating every setup sentence as a separate requirement drives both global-fact volume and downstream context pressure.

## Inflation diagnosis and boundary

The new cap resolves truncation but not extraction inflation. Output size ranged from 2.84 to 5.68 times source-text characters. x02 produced 47 facts and unusually long citations (average 234 characters; maximum 608). x08 produced 41 facts, 25 global facts, and 56 citations. High global-fact shares, repeated seven-field envelopes, duplicated shared setup across method-specific facts, and long self-contained citations account for the expansion; provider reasoning does not.

This review supports an engineering conclusion only: the 12,000-token revision made complete responses observable and exposed contract/citation/type failures that the 6,000-token run could not fully reveal. It does not assess answer accuracy, compare algorithmic effectiveness, or infer the correctness of every extracted fact.
