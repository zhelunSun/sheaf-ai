# Representation-boundary v1: controlled transport diagnostic

This is a **six-case, seven-card, hand-authored transport diagnostic**, not an
evaluation of model extraction quality. Every source and response is synthetic.
The responses deliberately contain the information whose transport is inspected.
They are not sampled LLM outputs, a natural corpus, or an idealized competing
representation. No users, model calls, embedding calls, or network requests are
needed.

## Question and actual production path

When information is already present in an input response, what survives the real
parser and each current consumer representation, and how much character space
does the representation occupy?

The runner calls `parse_card_extraction_response(..., citation_mode="strict")`
with actual `CardSource` objects and a `UUIDMapper`, then uses these existing
implementations unchanged:

| Representation | Actual implementation |
| --- | --- |
| `stored_json` | `KnowledgeCard.to_json()`: the same record shape `CardStore` serializes with `to_dict()` |
| `default_text` | `CardRenderer().render(card, format="text")` |
| `default_json` | `CardRenderer().render(card, format="json")` |
| `detailed_text` | `CardRenderer(CardOutputConfig.detailed()).render(card, format="detailed")` |
| `embedding_text` | `EmbeddingEngine._text_for_card(card)`, with no engine instantiation or embedding call |

`stored_json` is an in-memory serialization of the actual stored card record, not
a CardStore transaction, disk-integrity, or replay test. Card IDs, association
targets and generated timestamps are normalized consistently for byte-reproducible
output. No title, claim, evidence, tag, confidence, source ID or semantic field is
rewritten or augmented after parsing. In particular, unknown fields are **not**
manually injected into `extra` to make the current schema appear stronger.

## Fixtures and two separate groups

`fixtures.json` contains inputs only. `checks.json` identifies literal qualifiers
and unknown-field probes. The evaluator never asks a model to label the output.

| Case | Supported transport exercised | Separate unknown-structure probe |
| --- | --- | --- |
| Condition at the claim tail | Full conditional phrase after character 120 | `conditions` |
| Applicability scope | Tail qualifier also copied into evidence | `scope` |
| Time and version | Effective date plus applicable version in one phrase | `temporal` |
| Negation and exception | Complete negative rule plus exception | `polarity` |
| Two claims in one card | Two qualifiers, two resolvable source IDs and citation markers | `claim_evidence_links` |
| Typed relationship | Two cards with supported `related_to` topology | `typed_relations` |

The first group tests already-supported string/source/association transport.
The second asks whether extra structured fields survive the parser. A missing
unknown field is a **schema-compatibility observation**, not an extraction error,
not an invented model mistake, and not part of the supported-qualifier denominator.
The two-claim and typed-relation cases distinguish untyped card-level linkage from
structured per-claim attribution and relation meaning.

## Metrics and budget handling

Each case stores the actual input response text, parser observations, every native
representation text, every budgeted text, missing IDs, and character offsets.
Summary counts are micro-aggregated over these fixed cards, never generalized to
a population.

- **Complete qualifier-string visibility:** the entire labeled phrase occurs
  literally somewhere in the card output. Parser results additionally check the
  phrase in its original field. A word fragment does not count. A copy in evidence
  can remain visible even if the claim is truncated; this is not proof that an
  agent attaches that qualifier correctly.
- **Source-ID visibility:** full, resolved Entry identifiers occur in the output.
- **Citation-marker visibility:** `[Source N]` markers occur. These are reported
  separately from resolved IDs; neither metric verifies entailment or truth.
- **Association-ID visibility:** the resolved target card identifier occurs.
  This measures untyped topology, not whether a relationship is causal, temporal,
  supportive or contradictory.
- **Unknown-structure retention:** an input probe's key and unchanged value appear
  together at a path in the parsed card. This is reported only as parser schema
  compatibility, separately from downstream string visibility.
- **Characters:** Python `len(str)` Unicode code points, not tokens or UTF-8 bytes.
  Labels, punctuation and metadata count toward representation length.

Native output is measured without an added limit, preserving the production text
renderer’s own 120-character claim cap. A distinct stress test applies the same
per-card prefix budgets of **160, 320, and 640 characters** to each native output.
No padding or reordering is performed. Budgeted JSON may be invalid JSON: this is
only a prefix-visibility stress test, not a proposed API or deployable packing
algorithm. Formats have different overhead, so a cheaper representation does not
automatically mean a better one. No new representation or oracle is compared.

## Reproduce and inspect

Run from the repository root:

```powershell
python evals/representation-boundary/run_diagnostic.py
python -m pytest tests/test_representation_boundary.py -q
```

The current default result is `revisions/2026-09-04.2/report.json`, with its adjacent
`lock.json`. It includes actual texts and grouped per-case missing information,
not only aggregate scores. Inputs, production source, runner and tests are locked;
the runner fails on drift. Input hashes
are exact bytes. Code has both original-byte hashes and CRLF-to-LF-normalized
source hashes; replay checks the latter so checkout line endings alone do not
invalidate the code lock. Each report also records observed raw code hashes.
No production files are normalized or modified. To
intentionally create a reviewed new lock, use:

```powershell
python evals/representation-boundary/run_diagnostic.py --freeze-lock
```

The command refuses to replace an existing lock. Do not re-freeze to bypass a
failure: create a reviewed new revision and preserve the original inputs, lock
and report. A different report also cannot overwrite an existing output path.
Ordinary pytest mechanism tests call `evaluate_current()` without requiring the
current production code to equal a historical hash. A separate test simulates
code-hash drift with monkeypatch; exact historical lock verification is the CLI
runner's responsibility. Future implementation work can therefore update behavior
tests without rewriting historical benchmark assets. Model/embedding entry
points and ordinary outbound socket connections are fail-closed during evaluation;
tests also spy on the real production functions to prevent accidental toy replicas.

## Interpretation and limits

This experiment can locate parser-versus-renderer-versus-index-text loss for these
artificial cases. It cannot show whether a model would extract the qualifiers, how
often these cases occur, whether a citation supports a claim, whether an agent
understands or acts correctly, whether a contradiction was found, or whether a
new representation is superior. Literal visibility is not semantic preservation.

This small run excludes raw/Entry indexing and governed `CardVersion` projection;
therefore unknown structure lost by the ordinary extraction parser must not be
reported as proof that the whole repository lacks evidence or version models.
The repository already has those separate models. A future experiment may inspect
their actual projection and consumers, using actual source-backed artifacts;
that experiment is not implemented or scored here.

## Observed native result on these fixtures

| Representation | Full qualifiers | Resolved source IDs | Association IDs | Total characters over 7 cards |
| --- | ---: | ---: | ---: | ---: |
| Stored JSON | 8/8 | 8/8 | 2/2 | 6,841 |
| Default text | 5/8 | 0/8 | 0/2 | 1,708 |
| Default JSON | 8/8 | 0/8 | 0/2 | 2,446 |
| Detailed text | 8/8 | 8/8 | 2/2 | 6,871 |
| Embedding text | 8/8 | 0/8 | 0/2 | 1,844 |

The parser retained all 8 supported qualifier strings and both untyped links;
none of the 6 unknown structured fields survived. All native views retained 8/8
citation markers, which does not make them resolvable source identifiers.
The default text renderer lost the tail condition, temporal/version restriction
and negation/exception phrase. The scope phrase remained visible through its copy
in evidence. These are transport observations, not model extraction errors.

At the separate 320-character per-card budget, full-qualifier visibility was
7/8, 5/8, 8/8, 4/8 and 8/8 in the table's order. Metadata-heavy formats consume
more of that prefix before reaching the claim. Increasing the outer budget to
640 does not restore the default text renderer's already-truncated claim. These
deliberate stress cases do not establish a generally best format or budget.

The initial report `runs/representation-boundary-v1.json` and initial root
`lock.json` are preserved. `revisions/2026-09-04.1/run_diagnostic.py` snapshots its
runner. Revision `2026-09-04.2` changes artifact creation to exclusive `open("x")`
and the default revision paths only; fixtures, metrics and production calls are
unchanged. Identical existing reports are compared and left untouched; a
different report or existing lock is never overwritten. The historical runner
snapshot must be restored in an isolated checkout at the locked original path
to reproduce that initial lock; running the snapshot directly is not supported.
