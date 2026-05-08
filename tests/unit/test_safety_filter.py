"""Tests for the Phase 0.6 code-level safety guard."""

from __future__ import annotations

import pytest

from biotact.modules.askbiotact.safety_filter import (
    apply_safety_filter,
    detect_safety_trigger,
)


class TestDetectPregnancy:
    @pytest.mark.parametrize(
        "msg",
        [
            "Я беременна, можно ли мне пить BIFOLAK?",
            "Беременна сейчас, что посоветуете?",
            "Кормлю грудью, какие БАДы можно?",
            "Homiladorman, BIFOLAK ichish mumkinmi?",
            "Emizish davrida nima ichsam bo'ladi?",
        ],
    )
    def test_detects(self, msg: str) -> None:
        assert detect_safety_trigger(msg) == "pregnancy"


class TestDetectChildUnder3:
    @pytest.mark.parametrize(
        "msg",
        [
            "Дочери год, можно ли давать ей витамины?",
            "Сыну 2 года, что посоветуете?",
            "Ребёнку 18 месяцев",
            "У меня новорождённый, какие добавки?",
            "Bolaning 1 yoshi, vitamin ichsa bo'ladimi?",
            "Farzandim 2 yoshda",
        ],
    )
    def test_detects(self, msg: str) -> None:
        assert detect_safety_trigger(msg) == "child_under_3"

    @pytest.mark.parametrize(
        "msg",
        [
            "Сыну 8 лет, у него плохая память",
            "Дочери 7 лет, проблемы с иммунитетом",
            "Ребёнку 5 лет, какие витамины?",
        ],
    )
    def test_does_not_trigger_on_older_kids(self, msg: str) -> None:
        assert detect_safety_trigger(msg) != "child_under_3"


class TestDetectCardiac:
    @pytest.mark.parametrize(
        "msg",
        [
            "У меня болит сердце, что посоветуете?",
            "Сердце колет",
            "Yuragim og'riydi, nima ichish kerak?",
            "Yuragim achishyapti",
            "Беспокоит одышка с болью в груди",
        ],
    )
    def test_detects(self, msg: str) -> None:
        assert detect_safety_trigger(msg) == "cardiac"


class TestDetectChronic:
    @pytest.mark.parametrize(
        "msg",
        [
            "У меня диабет 2 типа, могу ли пить BIFOLAK?",
            "Гипертония давно, что подойдёт?",
            "Онкология в анамнезе",
            "Qandli diabetim bor",
            "Surunkali kasallik bor",
        ],
    )
    def test_detects(self, msg: str) -> None:
        assert detect_safety_trigger(msg) == "chronic"


class TestNoTrigger:
    @pytest.mark.parametrize(
        "msg",
        [
            "Сколько стоит BIFOLAK NEO?",
            "Что входит в состав CALCIY TRIACTIVE?",
            "BIFOLAK ACTIVE narxi qancha?",
            "У меня выпадают волосы, мне 35 лет",
            "Хочу для зрения",
        ],
    )
    def test_no_trigger(self, msg: str) -> None:
        assert detect_safety_trigger(msg) is None


class TestApplyFilter:
    def test_strips_product_name_in_meta_context(self) -> None:
        # safety-ru-004 reproducer
        answer = (
            "С хроническим заболеванием БАДы должны согласовываться "
            "с лечащим врачом. Если хотите, я могу подсказать, какой "
            "вопрос лучше задать вашему врачу по BIFOLAK для пищеварения."
        )
        out = apply_safety_filter(answer, "У меня диабет 2 типа", "chronic")
        assert "BIFOLAK" not in out
        assert "врач" in out.lower()

    def test_strips_multiword_product_name(self) -> None:
        answer = "BIFOLAK MAGNIY подходит беременным."
        out = apply_safety_filter(answer, "Я беременна", "pregnancy")
        assert "BIFOLAK MAGNIY" not in out
        # Trailing 'MAGNIY' should also be cleaned via base-token pattern
        assert "MAGNIY" not in out
        assert "врач" in out.lower() or "гинеколог" in out.lower()

    def test_adds_doctor_when_missing(self) -> None:
        answer = "Этот вопрос лучше прояснить с профессионалом."
        out = apply_safety_filter(answer, "Я беременна", "pregnancy")
        assert "гинеколог" in out.lower()

    def test_idempotent(self) -> None:
        answer = "BIFOLAK NEO подходит для пищеварения."
        once = apply_safety_filter(answer, "У меня диабет", "chronic")
        twice = apply_safety_filter(once, "У меня диабет", "chronic")
        assert once == twice

    def test_uz_uses_uz_specialist(self) -> None:
        answer = "BIFOLAK ZINCUM yaxshi mahsulot."
        out = apply_safety_filter(answer, "Qandli diabetim bor", "chronic")
        assert "BIFOLAK" not in out
        assert "shifokor" in out.lower() or "ginekolog" in out.lower() \
            or "kardiolog" in out.lower() or "pediatr" in out.lower()

    def test_does_not_add_doctor_if_already_present(self) -> None:
        answer = "Обратитесь к гинекологу."
        out = apply_safety_filter(answer, "Я беременна", "pregnancy")
        # Should not duplicate the redirect
        assert out.lower().count("гинеколог") == 1
