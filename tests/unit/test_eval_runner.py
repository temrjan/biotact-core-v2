"""Tests for the pure aggregation + exit-code logic of the eval harness.

Locks down:
  - ``determine_exit_code`` matrix (clean / errored / safety-fail / safety-none)
  - ``aggregate`` recall@5 mean ignores cases without retrieval expectations
    (regression test for /kreview Finding CORR-1)
  - ``aggregate`` handles empty inputs without ZeroDivisionError
"""

from __future__ import annotations

from tests.eval.loader import ExpectedAnswerTraits, GoldCase
from tests.eval.metrics import CaseResult
from tests.eval.runner import aggregate, determine_exit_code


def _case(
    *,
    case_id: str = "t",
    error: str | None = None,
    safety_redirect_ok: bool | None = None,
    recall: float = 0.0,
    answer_faithful: bool | None = None,
    must_mention_hits: list[str] | None = None,
    must_not_mention_violations: list[str] | None = None,
    category: str = "symptoms",
    lang: str = "ru",
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        category=category,
        lang=lang,
        recall_at_5=recall,
        answer="",
        answer_faithful=answer_faithful,
        safety_redirect_ok=safety_redirect_ok,
        must_mention_hits=must_mention_hits or [],
        must_not_mention_violations=must_not_mention_violations or [],
        retrieved_count=0,
        error=error,
    )


def _gold(
    *,
    case_id: str = "t",
    expected_chunk_substrings: list[str] | None = None,
    must_mention: list[str] | None = None,
    must_not_mention: list[str] | None = None,
    should_redirect: bool = False,
) -> GoldCase:
    return GoldCase(
        id=case_id,
        category="symptoms",
        lang="ru",
        dialog=[{"role": "user", "content": "x"}],
        expected_chunk_substrings=expected_chunk_substrings or [],
        expected_answer_traits=ExpectedAnswerTraits(
            must_mention=must_mention or [],
            must_not_mention=must_not_mention or [],
            should_redirect_to_doctor=should_redirect,
        ),
    )


class TestDetermineExitCode:
    """Exit-code matrix that ``smoke.sh`` and ``/verify`` depend on."""

    def test_clean_returns_zero(self) -> None:
        report = aggregate(
            [_case(safety_redirect_ok=True), _case()],
            [_gold(should_redirect=True), _gold(case_id="t2")],
        )
        assert determine_exit_code(report) == 0

    def test_errored_case_fails(self) -> None:
        report = aggregate([_case(error="boom")], [_gold()])
        assert determine_exit_code(report) == 1

    def test_safety_failure_fails(self) -> None:
        report = aggregate(
            [_case(safety_redirect_ok=False)],
            [_gold(should_redirect=True)],
        )
        assert determine_exit_code(report) == 1

    def test_safety_none_does_not_fail(self) -> None:
        # Non-safety cases have safety_redirect_ok=None — must not trip exit code
        report = aggregate(
            [_case(safety_redirect_ok=None)],
            [_gold(should_redirect=False)],
        )
        assert determine_exit_code(report) == 0


class TestAggregateRecallSkipsEmptyExpected:
    """Regression test for /kreview Finding CORR-1.

    Cases with no ``expected_chunk_substrings`` (typically safety / redirect)
    must NOT be averaged into ``recall_at_5_mean`` — otherwise their
    forced-zero score biases the mean down even when retrieval is perfect.
    """

    def test_empty_expected_excluded_from_recall_mean(self) -> None:
        cases = [
            _gold(case_id="r1", expected_chunk_substrings=["BIFOLAK"]),
            _gold(case_id="r2", expected_chunk_substrings=["IMMUNO"]),
            _gold(case_id="s1", expected_chunk_substrings=[]),
            _gold(case_id="s2", expected_chunk_substrings=[]),
        ]
        results = [
            _case(case_id="r1", recall=1.0),
            _case(case_id="r2", recall=1.0),
            _case(case_id="s1", recall=0.0),
            _case(case_id="s2", recall=0.0),
        ]
        report = aggregate(results, cases)
        assert report.recall_at_5_mean == 1.0

    def test_only_empty_expected_yields_zero_mean(self) -> None:
        cases = [_gold(case_id="s1", expected_chunk_substrings=[])]
        results = [_case(case_id="s1", recall=0.0)]
        report = aggregate(results, cases)
        assert report.recall_at_5_mean == 0.0


class TestAggregateEmptyInputs:
    """``aggregate`` must not raise ZeroDivisionError on edge cases."""

    def test_empty_results(self) -> None:
        report = aggregate([], [])
        assert report.total_cases == 0
        assert report.recall_at_5_mean == 0.0
        assert report.faithfulness_mean is None
        assert report.safety_redirect_rate is None
        assert report.must_mention_coverage == 0.0
        assert report.must_not_mention_violation_rate == 0.0

    def test_all_errored(self) -> None:
        cases = [_gold(case_id="e1"), _gold(case_id="e2")]
        results = [
            _case(case_id="e1", error="x"),
            _case(case_id="e2", error="y"),
        ]
        report = aggregate(results, cases)
        assert report.total_cases == 2
        assert report.recall_at_5_mean == 0.0
        assert report.faithfulness_mean is None
        assert report.safety_redirect_rate is None
