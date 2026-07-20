"""Tests for the TD-template rebuild verifier (PR-B tooling).

Covers the four checks and the clause-number / normalization helpers. The
adversarial cases encode the review MINORs: date typos must NOT be eaten by the
number-stripper (MINOR-1), NBSP must not read as a difference (MINOR-3), and
many numId on one abstractNum must pass (NIT-1).
"""

from __future__ import annotations

import io

import pytest
from docx import Document

from biotact.modules.hr.tooling.docx_text import (
    normalize,
    starts_with_clause_number,
    strip_leading_clause_number,
)
from biotact.modules.hr.tooling.td_verify import (
    _has_literal_digit,
    check_numbering,
    check_placeholders,
    check_structure,
    check_text_1to1,
)


def _reload(doc: object) -> object:
    buffer = io.BytesIO()
    doc.save(buffer)  # type: ignore[attr-defined]
    buffer.seek(0)
    return Document(buffer)


def _doc(
    rows: list[tuple[str, str]], *, numbered: bool = True, style: str = "List Number"
) -> object:
    """One 2-column table, one paragraph per cell (numbered via a list style)."""
    doc = Document()
    table = doc.add_table(rows=len(rows), cols=2)
    for row_index, (left, right) in enumerate(rows):
        for col_index, text in enumerate((left, right)):
            paragraph = table.cell(row_index, col_index).paragraphs[0]
            paragraph.text = text
            if numbered and text:
                paragraph.style = doc.styles[style]
    return _reload(doc)


# Original carries typed numbers (as the real template does); the clean
# candidate carries none — the stripper is asymmetric.
_ORIGINAL = [("МЕҲНАТ ПРЕДМЕТИ", "1. ПРЕДМЕТ"), ("иш", "2. ФУНКЦИИ {{ FIO }}")]
_CANDIDATE_OK = [("МЕҲНАТ ПРЕДМЕТИ", "ПРЕДМЕТ"), ("иш", "ФУНКЦИИ {{ FIO }}")]


class TestHelpers:
    def test_strip_clause_number_but_not_date(self) -> None:
        assert strip_leading_clause_number("2.1. текст") == "текст"
        # A date must survive — it is not a clause number.
        assert strip_leading_clause_number("05.01.2026 йилдаги") == "05.01.2026 йилдаги"

    def test_starts_with_clause_number(self) -> None:
        assert starts_with_clause_number("2. ФУНКЦИИ")
        assert not starts_with_clause_number("05.01.2026 йил")

    def test_normalize_collapses_nbsp(self) -> None:
        assert normalize("a  b\tc") == "a b c"
        # Quotes/dashes are a real legal difference — not normalized away.
        assert normalize("«текст»") != normalize('"текст"')

    def test_has_literal_digit(self) -> None:
        assert not _has_literal_digit("%1.")
        assert not _has_literal_digit("%1.%2.")
        assert _has_literal_digit("5.")
        assert _has_literal_digit("%1.10.")


class TestTextOneToOne:
    def test_clean_candidate_matches_original(self) -> None:
        result = check_text_1to1(_doc(_ORIGINAL), _doc(_CANDIDATE_OK))
        assert result.ok, result.problems

    def test_date_typo_is_caught(self) -> None:
        original = [("иш", "срок с 05.01.2026 г.")]
        candidate = [("иш", "срок с 05.01.2027 г.")]  # typo in the year
        result = check_text_1to1(_doc(original), _doc(candidate))
        assert not result.ok

    def test_candidate_typed_number_is_caught(self) -> None:
        candidate = [("МЕҲНАТ ПРЕДМЕТИ", "2. ФУНКЦИИ {{ FIO }}")]  # digit typed as text
        result = check_text_1to1(_doc(_ORIGINAL), _doc(candidate))
        assert not result.ok
        assert any("typed a literal number" in p for p in result.problems)

    def test_altered_body_is_caught(self) -> None:
        candidate = [
            ("МЕҲНАТ ПРЕДМЕТИ", "ПРЕДМЕТ"),
            ("иш", "ФУНКЦИИ ИЗМЕНЕНО {{ FIO }}"),
        ]
        result = check_text_1to1(_doc(_ORIGINAL), _doc(candidate))
        assert not result.ok

    def test_reordered_clause_is_caught(self) -> None:
        # Same clauses, RU column order swapped — a multiset check would pass;
        # the ordered per-column check must fail (author moved a clause).
        original = [("а", "ПЕРВЫЙ ПУНКТ"), ("б", "ВТОРОЙ ПУНКТ")]
        candidate = [("а", "ВТОРОЙ ПУНКТ"), ("б", "ПЕРВЫЙ ПУНКТ")]
        result = check_text_1to1(_doc(original), _doc(candidate))
        assert not result.ok


class TestPlaceholders:
    def test_matching_placeholders_pass(self) -> None:
        assert check_placeholders(_doc(_ORIGINAL), _doc(_CANDIDATE_OK)).ok

    def test_missing_placeholder_caught(self) -> None:
        candidate = [
            ("МЕҲНАТ ПРЕДМЕТИ", "ПРЕДМЕТ"),
            ("иш", "ФУНКЦИИ"),
        ]  # {{ FIO }} dropped
        result = check_placeholders(_doc(_ORIGINAL), _doc(candidate))
        assert not result.ok
        assert any("missing placeholders" in p for p in result.problems)

    def test_unexpected_placeholder_caught(self) -> None:
        candidate = [
            ("МЕҲНАТ ПРЕДМЕТИ", "ПРЕДМЕТ {{ EXTRA }}"),
            ("иш", "ФУНКЦИИ {{ FIO }}"),
        ]
        result = check_placeholders(_doc(_ORIGINAL), _doc(candidate))
        assert not result.ok
        assert any("unexpected placeholders" in p for p in result.problems)


class TestNumbering:
    def test_single_clean_list_passes(self) -> None:
        assert check_numbering(_doc(_CANDIDATE_OK)).ok

    def test_many_numids_one_abstract_passes(self) -> None:
        # Every List Number paragraph gets its own numId but one abstractNum —
        # legitimate Word output, must not be a false red (NIT-1).
        doc = _doc([("а", "b"), ("в", "г"), ("д", "е")])
        result = check_numbering(doc)
        assert result.ok, result.problems

    def test_two_distinct_definitions_caught(self) -> None:
        # List Number + List Bullet resolve to two different abstractNums.
        doc = Document()
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 1).paragraphs[0].text = "ФУНКЦИИ"
        table.cell(0, 1).paragraphs[0].style = doc.styles["List Number"]
        table.cell(1, 1).paragraphs[0].text = "пункт"
        table.cell(1, 1).paragraphs[0].style = doc.styles["List Bullet"]
        result = check_numbering(_reload(doc))
        assert not result.ok
        assert any("numbering definitions" in p for p in result.problems)

    def test_no_numbered_clauses_caught(self) -> None:
        assert not check_numbering(_doc(_CANDIDATE_OK, numbered=False)).ok


class TestStructure:
    def test_flat_two_column_rows_pass(self) -> None:
        assert check_structure(_doc(_CANDIDATE_OK)).ok

    def test_nested_table_in_cell_caught(self) -> None:
        doc = Document()
        table = doc.add_table(rows=1, cols=2)
        table.cell(0, 0).add_table(rows=1, cols=1)  # nested table
        table.cell(0, 1).paragraphs[0].text = "ПРЕДМЕТ"
        result = check_structure(_reload(doc))
        assert not result.ok
        assert any("nested table" in p for p in result.problems)

    def test_empty_cell_caught_unless_whitelisted(self) -> None:
        rows = [("МЕҲНАТ", ""), ("иш", "ФУНКЦИИ")]  # row 0 RU empty
        assert not check_structure(_doc(rows)).ok
        assert check_structure(_doc(rows), empty_cell_rows=frozenset({0})).ok

    def test_wrong_table_count_caught(self) -> None:
        doc = Document()
        doc.add_paragraph("no table here")
        assert not check_structure(_reload(doc)).ok


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
