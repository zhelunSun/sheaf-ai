# Core Algorithm Offline Evaluation

This suite is Sheaf's fast, deterministic release gate for its three core
algorithm paths. It uses synthetic entries, a deterministic fixture embedder,
frozen crystallization responses, and checked-in evidence-memory scenarios.

Run it from the repository root:

```bash
python evals/core-algorithms/run_offline_eval.py
```

The process exits non-zero if any required check fails and emits structured
JSON for CI. It currently checks:

- the production Entry index, manifest, retrieval service, ranking, and fusion
  with a deterministic fixture embedder;
- rejection of invented or unresolved crystallization sources;
- strict validation of source-backed cards;
- idempotency, contest preservation, correction, replay, and source integrity
  in its checked-in evidence-memory scenario.

Separate pytest regression suites—not this core runner—cover schema-3
quote/character-span identity, old-ledger migration, persisted near-duplicate
relations, scoped authority, and SPLIT/NOOP decision traces. The SPLIT tests use
an atomic fake. This repository does not yet contain a production adapter that
atomically commits UPDATE + CREATE to evidence memory, so the decision-trace
module is a conditional protocol rather than a shipped end-to-end split
executor.

It does **not** test a live embedding model, a live LLM, network collectors,
cross-file transactions, human usefulness, or superiority over another
product. The larger frozen retrieval experiment and its current negative result
are documented in [`../retrieval-frozen/README.md`](../retrieval-frozen/README.md).
Further work follows the versioned datasets and experiments described in
[`../../docs/ARCHITECTURE-AND-EVALUATION.md`](../../docs/ARCHITECTURE-AND-EVALUATION.md).
