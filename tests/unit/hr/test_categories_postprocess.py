"""Snapshot-style unit tests for HR category post-processing.

Uses freezegun for deterministic date defaults.
"""

from __future__ import annotations

from datetime import UTC, datetime

from freezegun import freeze_time

from biotact.modules.hr.chat.categories import postprocess


@freeze_time("2026-06-09")
class TestPostprocessTDOsnovnoy:
    """Post-processing for td_osnovnoy category."""

    def test_salary_text_generated(self) -> None:
        data = {"SALARY": "5000000"}
        result = postprocess(data, "td_osnovnoy", datetime.now(UTC))
        assert result["SALARY"] == "5 000 000"
        assert "сум 00 тийин" in result["SALARY_TEXT"]
        assert "сўм 00 тийин" in result["SALARY_TEXT_UZ"]

    def test_vacation_defaults_to_21(self) -> None:
        data: dict[str, str] = {}
        result = postprocess(data, "td_osnovnoy", datetime.now(UTC))
        assert result["VACATION_DAYS"] == "21"
        assert result["VACATION_DAYS_TEXT"] == "двадцать один"

    def test_hours_default_to_full_time(self) -> None:
        data: dict[str, str] = {}
        result = postprocess(data, "td_osnovnoy", datetime.now(UTC))
        assert result["HOURS_WEEK"] == "40"
        assert result["HOURS_DAY"] == "8"

    def test_contract_date_defaults_to_today(self) -> None:
        data = {"CONTRACT_DATE": ""}
        result = postprocess(data, "td_osnovnoy", datetime.now(UTC))
        assert result["CONTRACT_DATE"] == "09.06.2026"

    def test_director_defaults(self) -> None:
        data: dict[str, str] = {}
        result = postprocess(data, "td_osnovnoy", datetime.now(UTC))
        assert result["DIRECTOR_SHORT_LATIN"] == "ISHMATOV SH.R."
        assert result["HR_DIRECTOR_SHORT_LATIN"] == "KOROTUN O.A."


@freeze_time("2026-06-09")
class TestPostprocessTDSovmestitelstvo:
    """Post-processing for td_sovmestitelstvo category."""

    def test_hours_default_to_part_time(self) -> None:
        data: dict[str, str] = {}
        result = postprocess(data, "td_sovmestitelstvo", datetime.now(UTC))
        assert result["HOURS_WEEK"] == "20"
        assert result["HOURS_DAY"] == "4"


@freeze_time("2026-06-09")
class TestPostprocessPrikazPriem:
    """Post-processing for prikaz_priem category."""

    def test_work_type_normalization(self) -> None:
        data = {"WORK_TYPE": "совместитель"}
        result = postprocess(data, "prikaz_priem", datetime.now(UTC))
        assert result["WORK_TYPE"] == "по совместительству"

    def test_work_type_main(self) -> None:
        data = {"WORK_TYPE": "основной"}
        result = postprocess(data, "prikaz_priem", datetime.now(UTC))
        assert result["WORK_TYPE"] == "по основному месту работы"


@freeze_time("2026-06-09")
class TestPostprocessNDA:
    """Post-processing for nda_rabotnik category."""

    def test_signer_defaults(self) -> None:
        data: dict[str, str] = {}
        result = postprocess(data, "nda_rabotnik", datetime.now(UTC))
        assert result["SIGNER_TITLE"] == "Генеральный директор"
        assert result["SIGNER_TITLE_GENITIVE"] == "Генерального директора"
        assert result["SIGNER_TITLE_UZ"] == "Бош директор"


@freeze_time("2026-06-09")
class TestPostprocessGender:
    """Gender normalization across categories."""

    def test_female_detected(self) -> None:
        data = {"CITIZEN_GENDER": "женский"}
        result = postprocess(data, "td_osnovnoy", datetime.now(UTC))
        assert result["CITIZEN_GENDER"] == "гражданка"

    def test_male_detected(self) -> None:
        data = {"CITIZEN_GENDER": "мужской"}
        result = postprocess(data, "td_osnovnoy", datetime.now(UTC))
        assert result["CITIZEN_GENDER"] == "гражданин"

    def test_already_canonical(self) -> None:
        data = {"CITIZEN_GENDER": "гражданка"}
        result = postprocess(data, "td_osnovnoy", datetime.now(UTC))
        assert result["CITIZEN_GENDER"] == "гражданка"


@freeze_time("2026-06-09")
class TestPostprocessProbation:
    """Probation field stripping."""

    def test_strip_to_digits(self) -> None:
        data = {"PROBATION": "3 месяца"}
        result = postprocess(data, "td_osnovnoy", datetime.now(UTC))
        assert result["PROBATION"] == "3"

    def test_no_digits_unchanged(self) -> None:
        data = {"PROBATION": "без испытательного срока"}
        result = postprocess(data, "td_osnovnoy", datetime.now(UTC))
        assert result["PROBATION"] == "без испытательного срока"
