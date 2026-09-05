# Method selection v3 synthetic dataset

Status: authored and mechanically checked on 2026-09-05; final independent preflight review is recorded separately in PREFLIGHT-REVIEW.md. The experiment owner is responsible for freezing files before execution.

This is an independently authored synthetic evaluation set for this experiment. Its fictional documents are not external blind-test material, and its author-written reference answers are not a human gold standard. No previous evaluation data, previous answers, runner implementation, model responses, API endpoints, or credentials were consulted to construct it.

The completed scope is eight independent English document bundles, three questions per bundle, and three sources per bundle: 24 sources and 24 questions. Each bundle meets the 900–1400 English-word source-text target. The questions concern bounded software or device choices using only the supplied documents. All method names, organizations implied by the documents, measurements, incidents, and document histories are fictional.

Only inputs.json, gold.json, and this note are authored by the dataset author. Input records contain no answer labels or evaluation splits. The reference answers distinguish support, explicit violation by every candidate, missing evidence, and unresolved contradictory reports about the same configuration.

## Construction and limitations

The source packets and reference answers were written together for this bounded experiment. An independent agent read the questions and sources without seeing the reference answers first, then reviewed the answers and citation sets. This is an internal synthetic authoring and review procedure, not an external blind benchmark, an independent real-world measurement campaign, or a human-validated scientific gold standard. Agreement between author and reviewer establishes a checked intended interpretation, not empirical validity outside these fictional cases.

The packets cover archive transfer, event indexing, remote loggers, analytical planning, service deployment, firmware updating, passage retrieval, and dual-link bridges. They use distinct operational conditions and distractors such as performance measured at the wrong concurrency, recovery of a queue instead of progress within a file, partial installation sizes, environmental exposures that were never run, optional versus mandatory network dependencies, and unresolved same-configuration replays. Several choices require evidence from multiple sources. Nine questions restrict eligibility to a subset of the methods in their bundle.

No source text or question was adapted to experiment-model outputs. The author did not call a model API, inspect credentials, read the experiment runner, or inspect previous evaluation data or previous answers. The two source-condition repairs during preflight made the common metadata-write interruption apply to every logger and made the common key-rotation test explicitly use board revision B. Neither change depends on an experiment response.

The set contains 11 supported choices, 4 explicit-negative abstentions, 5 insufficient-evidence abstentions, and 4 conflict abstentions. All supported choices are unique under the stated candidate list and constraints. In conflict questions, every other candidate is explicitly excluded; no remaining candidate is merely untested. A conflict about a different operation does not disqualify a method when the question asks only about unaffected, supported properties.

## Reference evidence contract

For a supported choice, a sufficient citation set establishes every mandatory condition for the selected method. It does not require citation of every other candidate's disqualification. The rationale may explain uniqueness using those additional source facts, but that explanation is not an additional mandatory citation requirement.

For an explicit-negative abstention, the evidence covers a definite violation for every eligible candidate. For an insufficient-evidence abstention, the cited scope statement establishes the relevant missing measurement or untested condition for the eligible candidates. Missing evidence is not recoded as observed failure. For a conflict abstention, evidence covers the contradictory observations under the same configuration, their unresolved status, and the explicit exclusion of the other eligible candidates.

Each support_sets entry is one alternative sufficient set; citations within that set are jointly required semantic anchors. Alternatives are permitted when the same needed fact is documented in another source or when a shorter exact excerpt can omit an irrelevant member of a shared candidate list. required_sources is the intersection of source identifiers across all alternative sufficient sets, not their union. Thus b06q02 legitimately has an empty required_sources list because either x06s1 or x06s3 can independently establish the missing revision-C evidence.

Every quote is an exact, unique, continuous substring of its identified source text. Necessary sentences are separate anchors, so a response may quote them separately without needing to quote intervening sentence spacing. Some anchors are clause fragments that retain the decisive method, measurement, or common test condition; jointly they preserve the required semantics without forcing irrelevant candidate values into a quotation. A longer faithful quotation containing these anchors is valid evidence. These finite alternatives document known sufficient routes; they do not establish that an automatic exact-span metric recognizes every semantically correct explanation a reader might give.

## Mechanical checks

The author checked JSON parsing; exact permitted key sets; 8 bundle IDs, 24 source IDs, and 24 matching task and answer IDs; candidate membership; choose/abstain method values; the required_sources intersection; source word counts; and exact source occurrence counts for every quotation. The final authored gold contains 28 alternative sufficient sets and 72 citation anchors, all occurring exactly once in their identified source. Logical review additionally checked that each chosen method covers the question's actual conditions and that abstention categories do not collapse missing evidence into failure or unresolved conflict into a resolved outcome.

Word counts below include source text only, excluding titles, method lists, and questions. Whitespace counts split on whitespace. English counts use the case-insensitive letter-token pattern `\b[A-Za-z]+(?:[-'][A-Za-z]+)*\b`, so standalone numerical tokens are excluded and hyphenated English compounds count as one token. Both conventions place every bundle within the target interval.

| Bundle | Source theme | Whitespace words | English words |
|---|---|---:|---:|
| x01 | Archive transfer | 1069 | 1042 |
| x02 | Event indexing | 1068 | 1039 |
| x03 | Remote loggers | 1065 | 1032 |
| x04 | Analytical planning | 1046 | 1008 |
| x05 | Service deployment | 1042 | 1005 |
| x06 | Firmware updating | 1079 | 1055 |
| x07 | Passage retrieval | 1045 | 1010 |
| x08 | Dual-link bridges | 1030 | 1000 |

A structurally valid packet and reviewed reference interpretation provide an internal evaluation fixture. Any subsequent model result remains bounded by this small synthetic dataset and the separately frozen execution protocol; it does not by itself establish external validity, live-system fidelity, or a general method effect.
