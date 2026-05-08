"""Number-to-words conversion for HR documents (Russian + Uzbek)."""

from __future__ import annotations

from num2words import num2words

# --- Uzbek number-to-words (latin script used in legal docs) ---

_UZ_ONES = [
    "",
    "бир",
    "икки",
    "уч",
    "тўрт",
    "беш",
    "олти",
    "етти",
    "саккиз",
    "тўққиз",
]
_UZ_TENS = [
    "",
    "ўн",
    "йигирма",
    "ўттиз",
    "қирқ",
    "эллик",
    "олтмиш",
    "етмиш",
    "саксон",
    "тўқсон",
]
_UZ_SCALES = [
    (1_000_000_000, "миллиард"),
    (1_000_000, "миллион"),
    (1_000, "минг"),
]


def _uz_below_1000(n: int) -> str:
    """Convert 0-999 to Uzbek words."""
    if n == 0:
        return ""
    parts: list[str] = []
    if n >= 100:
        h = n // 100
        parts.append(f"{_UZ_ONES[h]} юз" if h > 1 else "юз")
        n %= 100
    if n >= 10:
        parts.append(_UZ_TENS[n // 10])
        n %= 10
    if n > 0:
        parts.append(_UZ_ONES[n])
    return " ".join(parts)


def num_to_text_uz(n: int) -> str:
    """Convert integer to Uzbek words.

    >>> num_to_text_uz(5_000_000)
    'беш миллион'
    >>> num_to_text_uz(21)
    'йигирма бир'
    >>> num_to_text_uz(8_500_000)
    'саккиз миллион беш юз минг'
    """
    if n == 0:
        return "нол"
    if n < 0:
        return f"минус {num_to_text_uz(-n)}"

    parts: list[str] = []
    for scale_value, scale_name in _UZ_SCALES:
        if n >= scale_value:
            count = n // scale_value
            chunk = _uz_below_1000(count)
            parts.append(f"{chunk} {scale_name}" if chunk != "бир" else scale_name)
            n %= scale_value

    remainder = _uz_below_1000(n)
    if remainder:
        parts.append(remainder)

    return " ".join(parts)


def num_to_text_ru(n: int) -> str:
    """Convert integer to Russian words using num2words.

    >>> num_to_text_ru(5_000_000)
    'пять миллионов'
    """
    return num2words(n, lang="ru")  # type: ignore[no-any-return]


def format_salary(value: str) -> str:
    """Format salary number with space separators.

    >>> format_salary("5000000")
    '5 000 000'
    >>> format_salary("5 000 000")
    '5 000 000'
    """
    digits = "".join(c for c in value if c.isdigit())
    if not digits:
        return value
    return f"{int(digits):,}".replace(",", " ")
