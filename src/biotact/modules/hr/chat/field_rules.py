"""Single source of per-category field-extraction rules for HR chat.

Both prompts that ask the LLM to extract field values build their rule text
from here:

* the tool-calling system prompt (``prompts.py``), via :func:`build_system_rules`;
* the fallback extractor (``extractor.py``), via :func:`build_extractor_rules`.

Before this module the two prompts carried their own hand-maintained rule
lists, and they drifted: the system prompt documented ``GPD_NUMBER`` /
``GPD_DATE`` while the fallback extractor did not, so on the fallback path the
GPD number/date never reached ``data``. Keeping the rules in one place removes
that class of drift.
"""

from __future__ import annotations

from dataclasses import dataclass

# Field rules shared by every document category. Language-neutral or common
# identity/contact fields. ``FIO`` (Cyrillic) is included so the fallback
# extractor keeps the rule it historically carried.
COMMON_FIELD_RULES = """Общие правила полей:
- FIO: ФИО кириллицей, ЗАГЛАВНЫМИ (ПЕТРОВ АЛЕКСЕЙ СЕРГЕЕВИЧ)
- FIO_LATIN: ФИО латиницей, ЗАГЛАВНЫМИ (IVANOVA MARIYA PETROVNA)
- FIO_SHORT_LATIN: краткое латиницей (IVANOVA M. P.)
- PASSPORT: серия и номер (AD 1234567)
- PASSPORT_SERIES / PASSPORT_NUMBER: серия и номер раздельно (AD / 1234567)
- PASSPORT_ISSUED_BY: кем выдан (IIV 12345)
- PASSPORT_DATE: дата выдачи (ДД.ММ.ГГГГ)
- ADDRESS: полный адрес
- PHONE: телефон (+998...)
- PINFL: 14-значный номер
- DIRECTOR_SHORT_LATIN: "ISHMATOV SH.R." (по умолчанию)
- HR_DIRECTOR_SHORT_LATIN: "KOROTUN O.A." (по умолчанию)
- Все даты в формате ДД.ММ.ГГГГ"""


@dataclass(frozen=True, slots=True)
class DocTypeRules:
    """Field rules for one document type (which may cover several categories)."""

    label: str
    categories: tuple[str, ...]
    rules: str

    def render(self) -> str:
        """Render as ``LABEL (cat1, cat2):\\n<rules>`` for prompt embedding."""
        return f"{self.label} ({', '.join(self.categories)}):\n{self.rules}"


DOC_TYPE_RULES: tuple[DocTypeRules, ...] = (
    DocTypeRules(
        "ТРУДОВОЙ ДОГОВОР",
        ("td_osnovnoy", "td_sovmestitelstvo"),
        """- POSITION / POSITION_UZ: должность на рус / узб
- CONTRACT_TYPE: "неопределённый срок" или "определённый срок"
- CONTRACT_TYPE_UZ: "муддатсиз" или "муайян муддатга"
- WORK_TYPE: "основной работы" или "работы по совместительству"
- WORK_TYPE_UZ: "асосий иш жойи" или "ўриндошлик бўйича иш жойи"
- PROBATION: ТОЛЬКО число месяцев ("3")
- SALARY: ТОЛЬКО число (5000000). SALARY_TEXT генерируется автоматически.
- VACATION_DAYS: число дней (по умолчанию 21). Текст генерируется автоматически.
- HOURS_WEEK / HOURS_DAY: автоматически (40/8 основной, 20/4 совместительство)""",
    ),
    DocTypeRules(
        "ГПД",
        ("gpd_uslugi",),
        """- CONTRACT_NUMBER, CONTRACT_DATE: номер и дата договора
- INN: ИНН исполнителя
- BANK_ACCOUNT, BANK_NAME, BANK_MFO, CARD_NUMBER: банковские реквизиты""",
    ),
    DocTypeRules(
        "ПРИКАЗ О ПРИЁМЕ",
        ("prikaz_priem",),
        """- POSITION_GENITIVE: должность в родительном падеже ("специалиста по маркетингу")
- START_DATE: ПОЛНАЯ дата прописью ("15 апреля 2026 года", НЕ "15.04.2026")
- START_DATE_SHORT: краткая дата цифрами ("15.04.2026")
- WORK_TYPE: ПОЛНАЯ фраза: "по основному месту работы" или "по совместительству"
- ORDER_NUMBER: номер приказа
- TD_NUMBER: номер трудового договора""",
    ),
    DocTypeRules(
        "ПРИКАЗ ЗАКРЕПЛЕНИЯ АВТО",
        ("prikaz_avto",),
        """- POSITION / POSITION_INSTRUMENTAL: должность ("Специалист" / "специалистом")
- CAR_BRAND, CAR_NUMBER: марка и госномер авто
- CONTROLLER_FIO_LATIN, CONTROLLER_SHORT_LATIN: ФИО контролирующего лица
- CONTROLLER_POSITION / CONTROLLER_POSITION_GENITIVE: должность контролирующего
- SIGNER_TITLE, SIGNER_SHORT_LATIN: подписант ("Директор AI трансформации", "SUVOROVA T. A.")""",
    ),
    DocTypeRules(
        "МАТ. ОТВЕТСТВЕННОСТЬ",
        ("mat_otvetstvennost",),
        "- PASSPORT_SERIES / PASSPORT_NUMBER: серия и номер раздельно",
    ),
    DocTypeRules(
        "ДОП. СОГЛАШЕНИЕ — смена паспорта",
        ("dop_soglashenie_pasport",),
        """- TD_NUMBER, TD_DATE: номер и дата трудового договора
- AGREEMENT_NUMBER, AGREEMENT_DATE: номер и дата доп. соглашения
- NEW_PASSPORT, NEW_PASSPORT_ISSUED_BY, NEW_PASSPORT_DATE: новые паспортные данные
- DIRECTOR_FIO_LATIN, DIRECTOR_SHORT_LATIN: ФИО директора""",
    ),
    DocTypeRules(
        "NDA ДЛЯ РАБОТНИКА",
        ("nda_rabotnik",),
        """- SIGNER_TITLE: должность подписанта ("Генеральный директор" или "Директор продаж")
- SIGNER_TITLE_GENITIVE: в родит. падеже ("Генерального директора")
- SIGNER_TITLE_UZ: на узбекском ("Бош директор" или "Савдо директори")
- CITIZEN_GENDER: "гражданин" или "гражданка"
- DIRECTOR_FIO_LATIN: ФИО подписанта ("ISHMATOV SHERZOD RUSTAMOVICH")""",
    ),
    DocTypeRules(
        "NDA ДЛЯ ГПД",
        ("nda_gpd",),
        """- CITIZEN_GENDER: "гражданин" или "гражданка"
- DIRECTOR_FIO / DIRECTOR_FIO_NOMINATIVE / DIRECTOR_SHORT: ФИО директора в разных падежах
- GPD_NUMBER, GPD_DATE: номер и дата ГПД, к которому относится NDA (из фраз вида "ГПД №4 от 27.04.2026", "гражданско-правовой договор № X от Y")""",
    ),
    DocTypeRules(
        "ВОЗМЕЩЕНИЕ РАСХОДОВ",
        ("soglashenie_vozmeshenie",),
        "- AGREEMENT_DATE: дата соглашения",
    ),
    DocTypeRules(
        "ОБРАБОТКА ПЕРС. ДАННЫХ",
        ("soglashenie_pd",),
        """- AGREEMENT_NUMBER, AGREEMENT_DATE: номер и дата соглашения
- GPD_NUMBER, GPD_DATE: номер и дата ГПД на который ссылается""",
    ),
)

# category -> its DocTypeRules, built once (a category maps to exactly one type).
_RULES_BY_CATEGORY: dict[str, DocTypeRules] = {
    category: doc_type
    for doc_type in DOC_TYPE_RULES
    for category in doc_type.categories
}


def build_system_rules() -> str:
    """Full field-rule text for the system prompt: common + every category."""
    blocks = [COMMON_FIELD_RULES, "Правила по типам документов:"]
    blocks.extend(doc_type.render() for doc_type in DOC_TYPE_RULES)
    return "\n\n".join(blocks)


def build_extractor_rules(category: str) -> str:
    """Field-rule text for the fallback extractor: common + one category.

    Unknown categories (e.g. a freshly uploaded template with a new category)
    degrade to the common rules only — never a ``KeyError`` on the very path
    this module exists to make reliable.
    """
    doc_type = _RULES_BY_CATEGORY.get(category)
    if doc_type is None:
        return COMMON_FIELD_RULES
    return f"{COMMON_FIELD_RULES}\n\n{doc_type.render()}"
