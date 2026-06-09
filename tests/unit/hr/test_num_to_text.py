"""Unit tests for num_to_text conversion and salary formatting."""

from __future__ import annotations

from biotact.modules.hr.num_to_text import format_salary, num_to_text_ru, num_to_text_uz


class TestNumToTextUz:
    """Uzbek number-to-words edge cases."""

    def test_zero(self) -> None:
        assert num_to_text_uz(0) == "нол"

    def test_negative(self) -> None:
        assert num_to_text_uz(-5) == "минус беш"
        assert num_to_text_uz(-21) == "минус йигирма бир"

    def test_ones(self) -> None:
        assert num_to_text_uz(1) == "бир"
        assert num_to_text_uz(9) == "тўққиз"

    def test_tens(self) -> None:
        assert num_to_text_uz(10) == "ўн"
        assert num_to_text_uz(20) == "йигирма"
        assert num_to_text_uz(99) == "тўқсон тўққиз"

    def test_hundreds(self) -> None:
        assert num_to_text_uz(100) == "юз"
        assert num_to_text_uz(200) == "икки юз"
        assert num_to_text_uz(999) == "тўққиз юз тўқсон тўққиз"

    def test_thousands(self) -> None:
        assert num_to_text_uz(1_000) == "минг"
        assert num_to_text_uz(2_000) == "икки минг"
        assert num_to_text_uz(5_000_000) == "беш миллион"

    def test_millions(self) -> None:
        assert num_to_text_uz(1_000_000) == "миллион"
        assert num_to_text_uz(1_000_000_000) == "миллиард"
        assert num_to_text_uz(2_000_000_000) == "икки миллиард"

    def test_complex(self) -> None:
        assert num_to_text_uz(8_500_000) == "саккиз миллион беш юз минг"
        assert num_to_text_uz(21) == "йигирма бир"
        assert num_to_text_uz(101) == "юз бир"


class TestNumToTextRu:
    """Russian number-to-words via num2words."""

    def test_zero(self) -> None:
        assert num_to_text_ru(0) == "ноль"

    def test_ones(self) -> None:
        assert num_to_text_ru(1) == "один"
        assert num_to_text_ru(5) == "пять"

    def test_thousands(self) -> None:
        assert num_to_text_ru(1_000) == "одна тысяча"
        assert num_to_text_ru(5_000_000) == "пять миллионов"

    def test_millions(self) -> None:
        assert "миллион" in num_to_text_ru(1_000_000)


class TestFormatSalary:
    """Salary formatting with space separators."""

    def test_plain_digits(self) -> None:
        assert format_salary("5000000") == "5 000 000"

    def test_already_formatted(self) -> None:
        assert format_salary("5 000 000") == "5 000 000"

    def test_mixed_input(self) -> None:
        assert format_salary("5,000,000") == "5 000 000"

    def test_empty_returns_empty(self) -> None:
        assert format_salary("") == ""

    def test_non_digits_returns_original(self) -> None:
        assert format_salary("договорная") == "договорная"
