# Method selection v3 independent preflight review

Review date: 2026-09-05. Outcome: **PASS for freezing the reviewed synthetic fixtures.** No unresolved decision-label or necessary-evidence blocker remains. This is an agent review of an internally authored synthetic diagnostic, not human annotation, external validation, or evidence of a method effect.

The reviewer read all source texts and questions and recorded decisions before opening `gold.json`. All 24 initial decisions agreed with the author's labels. The reviewer did not inspect v3 experiment responses, invoke a model API, access credentials, or use experiment outcomes to revise labels. The author made the fixture edits; the reviewer wrote only this review file.

Reviewed SHA-256 identities:

- `inputs.json`: `084c2bee916a5fc02eb4bf3814ccf663ebc1618904b0c97037c4fa395a539e2b`
- `gold.json`: `8f971056cc9598d4e74be0f968ae0bf637fc99bd5134912d9abe1afa4f12a4b9`

These identities, rather than this review's date alone, identify the approved fixtures. Any subsequent fixture revision requires a new review before generation. The execution owner separately freezes prompts, selection code, tokenizer, transport controls, and protocol.

## Confirmed checks

The final fixtures contain 8 bundles, 24 source texts, and 24 matching tasks and reference answers. Source-only whitespace counts range from 1030 to 1079 words per bundle, within the requested 900-1400 interval. Labels comprise 11 supported choices, 4 explicit-negative abstentions, 5 insufficient-evidence abstentions, and 4 conflict abstentions.

Independent mechanical checks confirmed that all 72 anchors in 28 alternative sufficient sets occur exactly once as contiguous substrings of their identified source. Every anchor belongs to its task's bundle. The `required_sources` fields equal the intersection of source sets across sufficient alternatives; they are not a substitute for span coverage.

For supported choices, required anchors establish the selected method's complete positive case. Other candidates' exclusions may explain uniqueness but are not mandatory citations. For abstentions, the reviewed evidence covers all eligible candidates: definite violations, explicit lack of the requested observations, or an unresolved same-configuration contradiction plus definite exclusion of the remaining candidates. No conflict task leaves an additional merely untested candidate whose status would make the task ambiguous.

## Revisions resolved before freeze

- `b03q01` / `x03s2`: the common recovery exercise now explicitly interrupts a metadata write on each board. The question separates cold-chamber acquisition from this documented recovery exercise; it does not infer recovery tested at the cold temperature.
- `b06q03` / `x06s2`: the common key-rotation exercise now explicitly uses board revision B, binding the Aster failure as well as the M4L observations to the required hardware.
- All 11 supported tasks: removed mandatory citations of other candidates' failures while retaining every condition for the selected method.
- `b01q02`, `b02q02`, `b03q03`, `b04q02`: shortened or added alternatives to avoid forcing irrelevant candidate values into subset-task citations. `b04q02` no longer requires the explanatory S80 sentence in addition to the direct absence statement.
- `b05q02`: retained both legitimate routes for read-only-root evidence: the rollback record alone, or the filesystem audit combined with rollback timing and controller conditions.
- Necessary sentences in longer evidence blocks are separate AND anchors. Separate sentence quotations therefore do not have to cover the whitespace between sentences. Common conditions and per-method values can be separate jointly required anchors.

## Per-task review

`abstain` means no method is selected. All rows below are confirmed against the final reviewed fixture identities.

| Task | Decision | State |
|---|---|---|
| b01q01 | Tide-4 | supported |
| b01q02 | abstain | explicit_negative |
| b01q03 | abstain | insufficient |
| b02q01 | Silt-22 | supported |
| b02q02 | abstain | conflict |
| b02q03 | Oak | supported |
| b03q01 | F3 | supported |
| b03q02 | abstain | explicit_negative |
| b03q03 | abstain | insufficient |
| b04q01 | Vela | supported |
| b04q02 | abstain | insufficient |
| b04q03 | abstain | conflict |
| b05q01 | JettyS | supported |
| b05q02 | Umbra-2 | supported |
| b05q03 | abstain | explicit_negative |
| b06q01 | Quill-9 | supported |
| b06q02 | abstain | insufficient |
| b06q03 | abstain | conflict |
| b07q01 | Dune-15 | supported |
| b07q02 | abstain | explicit_negative |
| b07q03 | Larch | supported |
| b08q01 | Kestrel | supported |
| b08q02 | abstain | insufficient |
| b08q03 | abstain | conflict |

## Interpretation and stop boundaries

The nine tasks where candidate filtering can change eligibility are `b01q02`, `b02q02`, `b02q03`, `b03q03`, `b04q02`, `b04q03`, `b05q02`, `b06q03`, and `b07q03`. The other 15 include every bundle method. Report the full 24-task denominator, the predeclared nine-task subset, and actual identical/different fact contexts. Differences for identical answer inputs are sampling variation, not realized filtering effects. Task IDs are retained for provenance and omitted from the answer payload; all first-numbered questions happen to be supported.

The pre-freeze change from a 1200-token proposal to an 800-token context cap is acceptable as a single calibration based on aggregate source lengths, with no experiment outputs. It sets a diagnostic compression pressure, not an optimal or production threshold. The protocol requires an evaluator-only whole-unit feasibility check; no gold spans may enter extraction, eligibility, or ranking. Extracted omissions and their downstream failures remain measured outcomes rather than reasons to retune the cap.

Raw versus facts changes extraction, unit granularity, and token occupancy together. Only the all-facts versus scoped-facts contrast holds the extracted representation fixed. The eight bundles share several constraint patterns and explicit missing-evidence language; their diversity does not establish real-document representativeness. Two answer samples share both task and extraction, so aggregation must preserve bundle dependence and must not treat 48 answers as independent tasks.

Exact-anchor coverage is conservative and does not enumerate every semantically sufficient quotation. Continuous source identity, current-context visibility, and sufficient-set coverage remain separate checks. Before generation, the follow-up semantic review is fixed to all 72 first-draw answers, anonymized without arm names or scores; all second-draw answers receive automatic scoring. This review has not yet been performed. Responses will not be selected for review based on observed quality, and frozen labels will not be rewritten afterward.

Freeze only the reviewed snapshots and execute the already bounded protocol. Preserve all 24 tasks in each arm/draw denominator, including invalid output or unavailable contexts. Stop new sends on the protocol's identity, transport, unresolved-dispatch, repeated-output, or budget conditions; low quality alone is not a stopping rule. If a fixture defect is discovered after generation, preserve the original full-denominator result and report an explicit sensitivity analysis without editing gold.
