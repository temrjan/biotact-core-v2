"""Pure aggregation + exit-code logic for the eval harness.

Extracted from ``scripts/run_eval.py`` so unit tests can import the pure
functions without spinning up the script's CLI / sys.path machinery.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from tests.eval.metrics import EvalReport

if TYPE_CHECKING:
    from tests.eval.loader import GoldCase
    from tests.eval.metrics import CaseResult


def aggregate(results: list[CaseResult], cases: list[GoldCase]) -> EvalReport:
    """Aggregate per-case results into an :class:`EvalReport`.

    Recall@5 is averaged ONLY over cases that declared
    ``expected_chunk_substrings`` — safety / redirect cases without a
    retrieval expectation must not bias the mean down.
    """
    by_category = dict(Counter(r.category for r in results))
    successful = [r for r in results if r.error is None]
    case_by_id = {c.id: c for c in cases}

    recall_evaluated = [
        r
        for r in successful
        if (case := case_by_id.get(r.case_id)) is not None
        and case.expected_chunk_substrings
    ]
    recall_mean = (
        sum(r.recall_at_5 for r in recall_evaluated) / len(recall_evaluated)
        if recall_evaluated
        else 0.0
    )

    judged = [r for r in successful if r.answer_faithful is not None]
    faithfulness_mean: float | None = (
        sum(1.0 for r in judged if r.answer_faithful) / len(judged) if judged else None
    )

    safety_runs = [r for r in successful if r.safety_redirect_ok is not None]
    safety_rate: float | None = (
        sum(1.0 for r in safety_runs if r.safety_redirect_ok) / len(safety_runs)
        if safety_runs
        else None
    )

    mm_passes: list[float] = []
    mnm_violations: list[float] = []
    for r in successful:
        case = case_by_id.get(r.case_id)
        if case is None:
            continue
        if case.expected_answer_traits.must_mention:
            mm_passes.append(1.0 if r.must_mention_hits else 0.0)
        if case.expected_answer_traits.must_not_mention:
            mnm_violations.append(1.0 if r.must_not_mention_violations else 0.0)
    mm_coverage = sum(mm_passes) / len(mm_passes) if mm_passes else 0.0
    mnm_violation_rate = (
        sum(mnm_violations) / len(mnm_violations) if mnm_violations else 0.0
    )

    return EvalReport(
        total_cases=len(results),
        by_category=by_category,
        recall_at_5_mean=recall_mean,
        faithfulness_mean=faithfulness_mean,
        safety_redirect_rate=safety_rate,
        must_mention_coverage=mm_coverage,
        must_not_mention_violation_rate=mnm_violation_rate,
        cases=results,
    )


def determine_exit_code(report: EvalReport) -> int:
    """Non-zero exit when any safety case failed redirect or any case errored.

    Used by ``smoke.sh`` and ``/verify`` integration. Quality regressions on
    non-safety metrics are reported but do not fail the run — that is for
    nightly /loop comparison vs baseline.
    """
    if any(c.error for c in report.cases):
        return 1
    if any(c.safety_redirect_ok is False for c in report.cases):
        return 1
    return 0
