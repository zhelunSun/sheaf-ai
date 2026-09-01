# Core Algorithm Offline Evaluation

This suite is Sheaf's fast, deterministic release gate for its three core
algorithm paths. It uses only synthetic entries, fixed semantic scores, frozen
crystallization responses, and the checked-in evidence-memory scenario.

Run it from the repository root:

```bash
python evals/core-algorithms/run_offline_eval.py
```

The process exits non-zero if any required check fails and emits structured
JSON for CI. It currently checks:

- retrieval ranking and fusion with fixed semantic scores;
- rejection of invented or unresolved crystallization sources;
- strict validation of source-backed cards;
- idempotency, contest preservation, correction, replay, and source integrity
  in incremental memory evolution.

It does **not** test a live embedding model, a live LLM, network collectors,
human usefulness, or superiority over another product. Those require the
versioned datasets and experiments described in
[`../../docs/ARCHITECTURE-AND-EVALUATION.md`](../../docs/ARCHITECTURE-AND-EVALUATION.md).
