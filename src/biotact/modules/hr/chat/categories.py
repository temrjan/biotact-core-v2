"""HR Chat category post-processing rules.

Pure functions that transform LLM-extracted fields into template-ready
data. Kept separate from service.py so they can be unit-tested without
an OpenAI client or database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from biotact.modules.hr.num_to_text import (
    format_salary,
    num_to_text_ru,
    num_to_text_uz,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime


@dataclass(frozen=True)
class CategoryRules:
    """Post-processing rules for one document category.

    required_fields and field_rules_for_llm are declared now and will be
    wired into the system prompt in a future PR (PR-13/15). For PR-4 we
    only move the postprocess callables out of service.py.
    """

    required_fields: tuple[str, ...]
    defaults: dict[str, str]
    postprocess: Callable[[dict[str, str], str, datetime], dict[str, str]]
    field_rules_for_llm: str


def _parse_int(value: str) -> int | None:
    """Extract integer from string like '5000000' or '5 000 000'."""
    digits = "".join(c for c in value if c.isdigit())
    return int(digits) if digits else None


_MONTHS_RU = [
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]


def _is_short_date(value: str) -> bool:
    """Check if value looks like DD.MM.YYYY."""
    return bool(re.match(r"^\d{1,2}\.\d{2}\.\d{4}$", value.strip()))


def _date_to_full_russian(short_date: str) -> str:
    """Convert '15.04.2026' to '15 апреля 2026'.

    Note: no 'года' suffix — templates add 'г.' or 'й.' themselves.
    """
    parts = short_date.strip().split(".")
    if len(parts) != 3:
        return short_date
    day, month, year = parts
    month_int = int(month)
    if 1 <= month_int <= 12:
        return f"{int(day)} {_MONTHS_RU[month_int]} {year}"
    return short_date


def _default_directors(data: dict[str, str]) -> None:
    """Fill company-wide director defaults when missing."""
    from biotact.core.config import get_settings

    settings = get_settings()
    if not data.get("DIRECTOR_SHORT_LATIN"):
        data["DIRECTOR_SHORT_LATIN"] = settings.hr_director_short_latin
    if not data.get("HR_DIRECTOR_SHORT_LATIN"):
        data["HR_DIRECTOR_SHORT_LATIN"] = settings.hr_hr_director_short_latin


def _normalize_gender(data: dict[str, str]) -> None:
    """Normalize CITIZEN_GENDER to canonical values."""
    cg = data.get("CITIZEN_GENDER", "")
    if cg and cg not in ("гражданин", "гражданка"):
        if any(w in cg.lower() for w in ("жен", "female", "ка")):
            data["CITIZEN_GENDER"] = "гражданка"
        else:
            data["CITIZEN_GENDER"] = "гражданин"


def _normalize_probation(data: dict[str, str]) -> None:
    """Strip PROBATION to digits only ('3 месяца' -> '3')."""
    prob = data.get("PROBATION", "")
    if prob:
        prob_int = _parse_int(prob)
        if prob_int:
            data["PROBATION"] = str(prob_int)


def _apply_hours_defaults(data: dict[str, str], category: str) -> None:
    """Set HOURS_WEEK / HOURS_DAY based on TD type."""
    if not category.startswith("td_"):
        return
    is_sovm = category == "td_sovmestitelstvo"
    if not data.get("HOURS_WEEK"):
        data["HOURS_WEEK"] = "20" if is_sovm else "40"
    if not data.get("HOURS_DAY"):
        data["HOURS_DAY"] = "4" if is_sovm else "8"


def _format_salary(data: dict[str, str]) -> None:
    """Format SALARY and generate SALARY_TEXT / SALARY_TEXT_UZ."""
    salary_raw = data.get("SALARY", "")
    salary_int = _parse_int(salary_raw) if salary_raw else None
    if salary_int:
        data["SALARY"] = format_salary(salary_raw)
        data["SALARY_TEXT"] = num_to_text_ru(salary_int) + " сум 00 тийин"
        data["SALARY_TEXT_UZ"] = num_to_text_uz(salary_int) + " сўм 00 тийин"


def _format_vacation(data: dict[str, str], category: str) -> None:
    """Format VACATION_DAYS and generate text variants (TD only)."""
    if not category.startswith("td_"):
        return
    vac = data.get("VACATION_DAYS", "")
    if not vac:
        data["VACATION_DAYS"] = "21"
        vac = "21"
    vac_int = _parse_int(vac)
    if vac_int:
        if not data.get("VACATION_DAYS_TEXT"):
            data["VACATION_DAYS_TEXT"] = num_to_text_ru(vac_int)
        if not data.get("VACATION_DAYS_TEXT_UZ"):
            data["VACATION_DAYS_TEXT_UZ"] = num_to_text_uz(vac_int)


def _normalize_positions(data: dict[str, str]) -> None:
    """Normalize POSITION* case and fallback POSITION_UZ."""
    for pos_field in (
        "POSITION",
        "POSITION_UZ",
        "POSITION_GENITIVE",
        "POSITION_INSTRUMENTAL",
    ):
        val = data.get(pos_field, "")
        if val and val == val.upper() and len(val) > 3:
            data[pos_field] = val.capitalize()
    if not data.get("POSITION_UZ") and data.get("POSITION"):
        data["POSITION_UZ"] = data["POSITION"]


def _translate_work_character(data: dict[str, str]) -> None:
    """Translate WORK_CHARACTER to Uzbek."""
    wc = data.get("WORK_CHARACTER", "")
    if wc and not data.get("WORK_CHARACTER_UZ"):
        wc_map = {
            "офисный": "офис",
            "офис": "офис",
            "разъездной": "саёҳат",
            "в пути": "йўлда",
            "на производстве": "ишлаб чиқариш",
            "производство": "ишлаб чиқариш",
            "производственный": "ишлаб чиқариш",
        }
        data["WORK_CHARACTER_UZ"] = wc_map.get(wc.lower(), wc)


def _convert_start_date(data: dict[str, str]) -> None:
    """Convert short START_DATE to full Russian format if needed."""
    start_date = data.get("START_DATE", "")
    if start_date and _is_short_date(start_date):
        data["START_DATE"] = _date_to_full_russian(start_date)


def _normalize_work_type(data: dict[str, str], category: str) -> None:
    """Ensure full WORK_TYPE phrase for prikaz_priem."""
    if category != "prikaz_priem":
        return
    wt = data.get("WORK_TYPE", "")
    if wt and "по " not in wt:
        if "совместител" in wt:
            data["WORK_TYPE"] = "по совместительству"
        else:
            data["WORK_TYPE"] = "по основному месту работы"


def _fill_date_defaults(data: dict[str, str], now: datetime) -> None:
    """Default CONTRACT_DATE / AGREEMENT_DATE / ORDER_DATE to today."""
    today = now.strftime("%d.%m.%Y")
    for date_field in ("CONTRACT_DATE", "AGREEMENT_DATE", "ORDER_DATE"):
        if date_field in data and not data[date_field]:
            data[date_field] = today


def _postprocess_nda_rabotnik(data: dict[str, str]) -> None:
    """NDA employee-specific signer defaults."""
    if not data.get("SIGNER_TITLE"):
        data["SIGNER_TITLE"] = "Генеральный директор"
    if not data.get("SIGNER_TITLE_GENITIVE"):
        title = data.get("SIGNER_TITLE", "")
        if "Генеральный директор" in title:
            data["SIGNER_TITLE_GENITIVE"] = "Генерального директора"
        elif "Директор продаж" in title:
            data["SIGNER_TITLE_GENITIVE"] = "Директора продаж"
        else:
            data["SIGNER_TITLE_GENITIVE"] = title
    if not data.get("SIGNER_TITLE_UZ"):
        title = data.get("SIGNER_TITLE", "")
        if "Генеральный директор" in title:
            data["SIGNER_TITLE_UZ"] = "Бош директор"
        elif "Директор продаж" in title:
            data["SIGNER_TITLE_UZ"] = "Савдо директори"
        else:
            data["SIGNER_TITLE_UZ"] = title


def postprocess(data: dict[str, str], category: str, now: datetime) -> dict[str, str]:
    """Generate computed fields programmatically after LLM extraction.

    Handles auto-generation for all document types:
    - TD: SALARY_TEXT, VACATION_DAYS_TEXT, HOURS, POSITION_UZ, CONTRACT_DATE
    - All: DIRECTOR_SHORT_LATIN, HR_DIRECTOR_SHORT_LATIN defaults
    - PROBATION: extract just the number
    """
    _default_directors(data)
    if category == "nda_rabotnik":
        _postprocess_nda_rabotnik(data)
    _normalize_gender(data)
    _normalize_probation(data)
    _apply_hours_defaults(data, category)
    _format_salary(data)
    _format_vacation(data, category)
    _normalize_positions(data)
    _translate_work_character(data)
    _convert_start_date(data)
    _normalize_work_type(data, category)
    _fill_date_defaults(data, now)
    return data


# Module-level constant for future use (PR-13/15 will wire field rules
# into the system prompt). Postprocess functions are referenced here so
# the service layer can dispatch by category without hard-coding logic.
POSTPROCESS_BY_CATEGORY: dict[
    str, Callable[[dict[str, str], str, datetime], dict[str, str]]
] = {
    "td_osnovnoy": postprocess,
    "td_sovmestitelstvo": postprocess,
    "gpd_uslugi": postprocess,
    "prikaz_priem": postprocess,
    "prikaz_avto": postprocess,
    "mat_otvetstvennost": postprocess,
    "dop_soglashenie_pasport": postprocess,
    "nda_rabotnik": postprocess,
    "nda_gpd": postprocess,
    "soglashenie_vozmeshenie": postprocess,
    "soglashenie_pd": postprocess,
}
