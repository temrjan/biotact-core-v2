"""Unit tests for HR chat helper functions (pure, no DB)."""

from __future__ import annotations

from biotact.modules.hr.chat.categories import (
    _date_to_full_russian,
    _is_short_date,
    _parse_int,
)


class TestParseInt:
    """_parse_int extracts digits from various string formats."""

    def test_plain_number(self) -> None:
        assert _parse_int("5000000") == 5_000_000

    def test_spaced_number(self) -> None:
        assert _parse_int("5 000 000") == 5_000_000

    def test_number_with_suffix(self) -> None:
        assert _parse_int("3 месяца") == 3

    def test_no_digits_returns_none(self) -> None:
        assert _parse_int("договорная") is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_int("") is None


class TestIsShortDate:
    """_is_short_date recognises DD.MM.YYYY patterns."""

    def test_valid_date(self) -> None:
        assert _is_short_date("15.04.2026") is True

    def test_single_day_digit(self) -> None:
        assert _is_short_date("5.04.2026") is True

    def test_invalid_format(self) -> None:
        assert _is_short_date("2026-04-15") is False

    def test_garbage(self) -> None:
        assert _is_short_date("не дата") is False

    def test_empty(self) -> None:
        assert _is_short_date("") is False


class TestDateToFullRussian:
    """_date_to_full_russian converts DD.MM.YYYY to 'D month YYYY'."""

    def test_valid_conversion(self) -> None:
        assert _date_to_full_russian("15.04.2026") == "15 апреля 2026"

    def test_january(self) -> None:
        assert _date_to_full_russian("01.01.2025") == "1 января 2025"

    def test_december(self) -> None:
        assert _date_to_full_russian("31.12.2024") == "31 декабря 2024"

    def test_invalid_returns_original(self) -> None:
        assert _date_to_full_russian("not-a-date") == "not-a-date"

    def test_empty_returns_empty(self) -> None:
        assert _date_to_full_russian("") == ""
