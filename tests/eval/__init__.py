"""Evaluation harness for AskBiotact RAG quality.

Real Qdrant + OpenAI calls (out-of-band of fast unit tests in ``tests/unit/``).
Loaded by ``scripts/run_eval.py`` and integration tests.
"""

from tests.eval.loader import ExpectedAnswerTraits, GoldCase, load_gold_set
from tests.eval.metrics import (
    CaseResult,
    EvalReport,
    must_mention_hits,
    must_not_mention_violations,
    recall_at_5,
    safety_redirect_passed,
)
from tests.eval.runner import aggregate, determine_exit_code

__all__ = [
    "CaseResult",
    "EvalReport",
    "ExpectedAnswerTraits",
    "GoldCase",
    "aggregate",
    "determine_exit_code",
    "load_gold_set",
    "must_mention_hits",
    "must_not_mention_violations",
    "recall_at_5",
    "safety_redirect_passed",
]
