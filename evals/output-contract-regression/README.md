# Output-contract regression (2026-09-22)

This is a **post-hoc, offline mechanical diagnosis** of the known v3 synthetic
experiment. It does not run an LLM, read gold, repair model answers, or alter old
scores. The experimental fact schema is not the production KnowledgeCard schema.

```powershell
python evals/output-contract-regression/audit.py
python evals/output-contract-regression/audit.py --check evals/output-contract-regression/report.json
python -m pytest tests/test_output_contract_regression.py -q
```

The runner prints a report to stdout and never writes a file. The checked-in
report binds the inputs, original request/response receipts, final answer plan,
reuse mappings, and diagnostic code identity. It verifies receipt checksums and
payload identity; it is not a fresh independent audit of provider authenticity.
No tokenizer download, model credentials, user knowledge base, or network is needed.

## What was separated

- Four extraction batches exceed the original 40-fact limit. All facts are still
  examined so the count error does not hide an additional quote failure.
- Six of 310 facts have non-verbatim quotes: five in x04 and one in x06. The
  remaining 304 pass mechanical schema/quote checks, **not semantic entailment**.
  Known missing/denial/conflict type errors remain outside this diagnostic.
- The old all-or-nothing contract accepts three bundles (101 facts). A hypothetical
  policy that quarantines individual invalid facts while keeping the 40-fact limit
  would leave four bundles and 135 facts. It is **not activated**: removing evidence
  can change an answer, so this is not an accuracy gain or a safe fallback proof.
- All 84 actual final answers have consistent decision/method/state fields; 60
  preparation-failure positions remain visible. Simple field checks therefore do
  **not** fix the previously observed contradictions between reason prose and the
  final decision. There is no reason-to-decision rewriting or keyword guesswork.

## Next decision

Make incomplete or partially accepted production outputs visible first. Do not
relax the old experiment's limit or punctuation rules to improve its score. Before
enabling partial facts for answering, define how missing evidence is signalled and
evaluate a new small independent sample. Free-text semantic consistency and correct
fact types still require semantic evaluation; adding another JSON validator is not
a demonstrated solution.
