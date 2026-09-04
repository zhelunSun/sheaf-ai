"""Regressions must keep diagnostic gains separate from answer-quality claims."""
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "test_repair_runner", ROOT / "evals/repair-regression/run_regression.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_current_regression_keeps_uncertain_recoveries_and_limitations_explicit():
    report = runner.run()
    assert "post-hoc known-label" in report["scope"]
    assert report["policy"]["tuned"] is False
    captures = report["retrieval"]["captures"]
    recovered = 0
    for query_id, review in captures["review-v4"].items():
        strict = captures["strict-v4"][query_id]
        if not strict["rankings"] and review["rankings"]:
            recovered += 1
            assert review["diagnostics"]["retrieval_gate_status"] == "review_required"
            assert review["diagnostics"]["retrieval_gate_passed"] is False
        assert review["diagnostics"]["retrieval_gate_answerable"] is None
        assert review["diagnostics"]["retrieval_gate_version"] == report["policy"]["version"]
    assert recovered > 0
    assert report["retrieval"]["evaluation"]["review-v4"]["no_answer_false_positive_count"] > 0
    assert all(check["all_ids_bound"] for check in report["representation"]["binding_checks"])
    assert report["representation"]["api_or_network_attempts"] == 0
