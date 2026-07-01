"""Unit tests for the deterministic template matcher.

Pure function — no DB, no LLM, no randomness. Proves one input → one result.
"""

from __future__ import annotations

import pytest

from biotact.modules.hr.library.service import TemplateCandidate, match_template

pytestmark = pytest.mark.unit


def _candidates() -> list[TemplateCandidate]:
    return [
        TemplateCandidate(id=1, category="td_osnovnoy", name="Трудовой договор.docx"),
        TemplateCandidate(id=2, category="nda_rabotnik", name="NDA работник.docx"),
        TemplateCandidate(id=3, category="nda_gpd", name="NDA ГПД.docx"),
    ]


def test_exact_category_slug() -> None:
    match = match_template(_candidates(), "td_osnovnoy")
    assert match is not None
    assert match.id == 1


def test_exact_category_slug_is_normalized() -> None:
    # case / underscores / extra whitespace collapse to the same normalized form
    match = match_template(_candidates(), "  TD   Osnovnoy ")
    assert match is not None
    assert match.id == 1


def test_exact_name() -> None:
    match = match_template(_candidates(), "NDA работник.docx")
    assert match is not None
    assert match.id == 2


def test_containment_single_match() -> None:
    # "работник" is a substring of candidate 2's name only
    match = match_template(_candidates(), "работник")
    assert match is not None
    assert match.id == 2


def test_ambiguous_containment_returns_none() -> None:
    # "nda" is contained in both nda_rabotnik and nda_gpd -> ambiguous
    assert match_template(_candidates(), "nda") is None


def test_empty_query_returns_none() -> None:
    assert match_template(_candidates(), "") is None


def test_whitespace_query_returns_none() -> None:
    assert match_template(_candidates(), "   \t ") is None


def test_no_match_returns_none() -> None:
    assert match_template(_candidates(), "prikaz_avto") is None


def test_no_candidates_returns_none() -> None:
    assert match_template([], "td_osnovnoy") is None


def test_exact_category_beats_containment() -> None:
    # An exact category match wins even if the query is also a substring of names.
    candidates = [
        TemplateCandidate(id=1, category="nda", name="Общий NDA.docx"),
        TemplateCandidate(id=2, category="nda_gpd", name="NDA для ГПД.docx"),
    ]
    match = match_template(candidates, "nda")
    assert match is not None
    assert match.id == 1  # exact category "nda", not the ambiguous containment


def test_deterministic_same_input_same_output() -> None:
    candidates = _candidates()
    assert match_template(candidates, "nda_gpd") == match_template(
        candidates, "nda_gpd"
    )
