"""Snapshot tests for HR chat category post-processing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from freezegun import freeze_time

from biotact.modules.hr.chat.categories import postprocess

_FROZEN_NOW = datetime(2026, 6, 8, 0, 0, 0, tzinfo=UTC)


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_td_osnovnoy() -> None:
    data = {
        "FIO_LATIN": "IVANOVA MARIYA PETROVNA",
        "POSITION": "MARKETOLOG",
        "SALARY": "5000000",
        "PROBATION": "3 месяца",
        "CONTRACT_DATE": "",
    }
    result = postprocess(data, "td_osnovnoy", now=_FROZEN_NOW)
    assert result == {
        "FIO_LATIN": "IVANOVA MARIYA PETROVNA",
        "POSITION": "Marketolog",
        "POSITION_UZ": "Marketolog",
        "SALARY": "5 000 000",
        "SALARY_TEXT": "пять миллионов сум 00 тийин",
        "SALARY_TEXT_UZ": "беш миллион сўм 00 тийин",
        "PROBATION": "3",
        "VACATION_DAYS": "21",
        "VACATION_DAYS_TEXT": "двадцать один",
        "VACATION_DAYS_TEXT_UZ": "йигирма бир",
        "HOURS_WEEK": "40",
        "HOURS_DAY": "8",
        "CONTRACT_DATE": "08.06.2026",
        "DIRECTOR_SHORT_LATIN": "ISHMATOV SH.R.",
        "HR_DIRECTOR_SHORT_LATIN": "KOROTUN O.A.",
    }


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_td_sovmestitelstvo() -> None:
    data = {"POSITION": "BUHGALTER", "SALARY": "3 000 000"}
    result = postprocess(data, "td_sovmestitelstvo", now=_FROZEN_NOW)
    assert result == {
        "POSITION": "Buhgalter",
        "POSITION_UZ": "Buhgalter",
        "SALARY": "3 000 000",
        "SALARY_TEXT": "три миллиона сум 00 тийин",
        "SALARY_TEXT_UZ": "уч миллион сўм 00 тийин",
        "VACATION_DAYS": "21",
        "VACATION_DAYS_TEXT": "двадцать один",
        "VACATION_DAYS_TEXT_UZ": "йигирма бир",
        "HOURS_WEEK": "20",
        "HOURS_DAY": "4",
        "DIRECTOR_SHORT_LATIN": "ISHMATOV SH.R.",
        "HR_DIRECTOR_SHORT_LATIN": "KOROTUN O.A.",
    }


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_gpd_uslugi() -> None:
    data = {"INN": "123456789", "CONTRACT_NUMBER": "5"}
    result = postprocess(data, "gpd_uslugi", now=_FROZEN_NOW)
    assert result == {
        "INN": "123456789",
        "CONTRACT_NUMBER": "5",
        "DIRECTOR_SHORT_LATIN": "ISHMATOV SH.R.",
        "HR_DIRECTOR_SHORT_LATIN": "KOROTUN O.A.",
    }


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_prikaz_priem() -> None:
    data = {
        "START_DATE": "15.04.2026",
        "WORK_TYPE": "совместительство",
        "ORDER_DATE": "",
    }
    result = postprocess(data, "prikaz_priem", now=_FROZEN_NOW)
    assert result == {
        "START_DATE": "15 апреля 2026",
        "WORK_TYPE": "по совместительству",
        "ORDER_DATE": "08.06.2026",
        "DIRECTOR_SHORT_LATIN": "ISHMATOV SH.R.",
        "HR_DIRECTOR_SHORT_LATIN": "KOROTUN O.A.",
    }


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_prikaz_avto() -> None:
    data = {"CAR_BRAND": "Chevrolet", "CAR_NUMBER": "01 A 123 BB"}
    result = postprocess(data, "prikaz_avto", now=_FROZEN_NOW)
    assert result == {
        "CAR_BRAND": "Chevrolet",
        "CAR_NUMBER": "01 A 123 BB",
        "DIRECTOR_SHORT_LATIN": "ISHMATOV SH.R.",
        "HR_DIRECTOR_SHORT_LATIN": "KOROTUN O.A.",
    }


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_mat_otvetstvennost() -> None:
    data = {
        "PASSPORT_SERIES": "AD",
        "PASSPORT_NUMBER": "1234567",
        "AGREEMENT_DATE": "",
    }
    result = postprocess(data, "mat_otvetstvennost", now=_FROZEN_NOW)
    assert result == {
        "PASSPORT_SERIES": "AD",
        "PASSPORT_NUMBER": "1234567",
        "AGREEMENT_DATE": "08.06.2026",
        "DIRECTOR_SHORT_LATIN": "ISHMATOV SH.R.",
        "HR_DIRECTOR_SHORT_LATIN": "KOROTUN O.A.",
    }


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_dop_soglashenie_pasport() -> None:
    data = {"TD_NUMBER": "12", "NEW_PASSPORT": "AA 1234567"}
    result = postprocess(data, "dop_soglashenie_pasport", now=_FROZEN_NOW)
    assert result == {
        "TD_NUMBER": "12",
        "NEW_PASSPORT": "AA 1234567",
        "DIRECTOR_SHORT_LATIN": "ISHMATOV SH.R.",
        "HR_DIRECTOR_SHORT_LATIN": "KOROTUN O.A.",
    }


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_nda_rabotnik() -> None:
    data = {"CITIZEN_GENDER": "женский"}
    result = postprocess(data, "nda_rabotnik", now=_FROZEN_NOW)
    assert result == {
        "CITIZEN_GENDER": "гражданка",
        "SIGNER_TITLE": "Генеральный директор",
        "SIGNER_TITLE_GENITIVE": "Генерального директора",
        "SIGNER_TITLE_UZ": "Бош директор",
        "DIRECTOR_SHORT_LATIN": "ISHMATOV SH.R.",
        "HR_DIRECTOR_SHORT_LATIN": "KOROTUN O.A.",
    }


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_nda_gpd() -> None:
    data = {"CITIZEN_GENDER": "male", "GPD_NUMBER": "7"}
    result = postprocess(data, "nda_gpd", now=_FROZEN_NOW)
    assert result == {
        "CITIZEN_GENDER": "гражданин",
        "GPD_NUMBER": "7",
        "DIRECTOR_SHORT_LATIN": "ISHMATOV SH.R.",
        "HR_DIRECTOR_SHORT_LATIN": "KOROTUN O.A.",
    }


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_soglashenie_vozmeshenie() -> None:
    data = {"AGREEMENT_DATE": ""}
    result = postprocess(data, "soglashenie_vozmeshenie", now=_FROZEN_NOW)
    assert result == {
        "AGREEMENT_DATE": "08.06.2026",
        "DIRECTOR_SHORT_LATIN": "ISHMATOV SH.R.",
        "HR_DIRECTOR_SHORT_LATIN": "KOROTUN O.A.",
    }


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_soglashenie_pd() -> None:
    data = {"AGREEMENT_NUMBER": "9", "AGREEMENT_DATE": ""}
    result = postprocess(data, "soglashenie_pd", now=_FROZEN_NOW)
    assert result == {
        "AGREEMENT_NUMBER": "9",
        "AGREEMENT_DATE": "08.06.2026",
        "DIRECTOR_SHORT_LATIN": "ISHMATOV SH.R.",
        "HR_DIRECTOR_SHORT_LATIN": "KOROTUN O.A.",
    }


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_work_character_translation() -> None:
    data = {"WORK_CHARACTER": "офисный"}
    result = postprocess(data, "td_osnovnoy", now=_FROZEN_NOW)
    assert result["WORK_CHARACTER_UZ"] == "офис"


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_start_date_conversion() -> None:
    data = {"START_DATE": "01.01.2026"}
    result = postprocess(data, "prikaz_priem", now=_FROZEN_NOW)
    assert result["START_DATE"] == "1 января 2026"


@pytest.mark.unit
@freeze_time("2026-06-08T00:00:00Z")
def test_postprocess_clock_injection() -> None:
    """Ensure postprocess uses the injected 'now' and not the wall clock."""
    data = {"CONTRACT_DATE": ""}
    result = postprocess(data, "td_osnovnoy", now=_FROZEN_NOW)
    assert result["CONTRACT_DATE"] == "08.06.2026"
