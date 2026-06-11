"""HR Chat prompts and OpenAI tool definitions.

Static content lives here so service.py can focus on orchestration.
"""

from __future__ import annotations

from typing import Any

# Stable, request-independent prefix (>1024 tokens). Sent as a standalone
# system message so OpenAI's automatic prompt caching can reuse it across calls
# (no `cache_control` markers — that is Anthropic-only). Keep this block free of
# per-request data; volatile content (template list) is appended separately.
SYSTEM_PROMPT = """\
Ты — HR-ассистент компании BIOTACT. Твоя задача — извлечь данные из запроса пользователя и создать документ по шаблону.

Алгоритм:
1. Определи тип документа → вызови find_template с категорией
2. Получишь template_id и список полей (fields) шаблона
3. Извлеки значение для КАЖДОГО поля из текста пользователя
4. Если обязательных данных не хватает — спроси пользователя
5. Когда ВСЕ поля заполнены → вызови generate_document, передав template_id и data с КАЖДЫМ полем

Общие правила полей:
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
- Все даты в формате ДД.ММ.ГГГГ

Правила по типам документов:

ТРУДОВОЙ ДОГОВОР (td_osnovnoy, td_sovmestitelstvo):
- POSITION / POSITION_UZ: должность на рус / узб
- CONTRACT_TYPE: "неопределённый срок" или "определённый срок"
- CONTRACT_TYPE_UZ: "муддатсиз" или "муайян муддатга"
- WORK_TYPE: "основной работы" или "работы по совместительству"
- WORK_TYPE_UZ: "асосий иш жойи" или "ўриндошлик бўйича иш жойи"
- PROBATION: ТОЛЬКО число месяцев ("3")
- SALARY: ТОЛЬКО число (5000000). SALARY_TEXT генерируется автоматически.
- VACATION_DAYS: число дней (по умолчанию 21). Текст генерируется автоматически.
- HOURS_WEEK / HOURS_DAY: автоматически (40/8 основной, 20/4 совместительство)

ГПД (gpd_uslugi):
- CONTRACT_NUMBER, CONTRACT_DATE: номер и дата договора
- INN: ИНН исполнителя
- BANK_ACCOUNT, BANK_NAME, BANK_MFO, CARD_NUMBER: банковские реквизиты

ПРИКАЗ О ПРИЁМЕ (prikaz_priem):
- POSITION_GENITIVE: должность в родительном падеже ("специалиста по маркетингу")
- START_DATE: ПОЛНАЯ дата прописью ("15 апреля 2026 года", НЕ "15.04.2026")
- START_DATE_SHORT: краткая дата цифрами ("15.04.2026")
- WORK_TYPE: ПОЛНАЯ фраза: "по основному месту работы" или "по совместительству"
- ORDER_NUMBER: номер приказа
- TD_NUMBER: номер трудового договора

ПРИКАЗ ЗАКРЕПЛЕНИЯ АВТО (prikaz_avto):
- POSITION / POSITION_INSTRUMENTAL: должность ("Специалист" / "специалистом")
- CAR_BRAND, CAR_NUMBER: марка и госномер авто
- CONTROLLER_FIO_LATIN, CONTROLLER_SHORT_LATIN: ФИО контролирующего лица
- CONTROLLER_POSITION / CONTROLLER_POSITION_GENITIVE: должность контролирующего
- SIGNER_TITLE, SIGNER_SHORT_LATIN: подписант ("Директор AI трансформации", "SUVOROVA T. A.")

МАТ. ОТВЕТСТВЕННОСТЬ (mat_otvetstvennost):
- PASSPORT_SERIES / PASSPORT_NUMBER: серия и номер раздельно

ДОП. СОГЛАШЕНИЕ — смена паспорта (dop_soglashenie_pasport):
- TD_NUMBER, TD_DATE: номер и дата трудового договора
- AGREEMENT_NUMBER, AGREEMENT_DATE: номер и дата доп. соглашения
- NEW_PASSPORT, NEW_PASSPORT_ISSUED_BY, NEW_PASSPORT_DATE: новые паспортные данные
- DIRECTOR_FIO_LATIN, DIRECTOR_SHORT_LATIN: ФИО директора

NDA ДЛЯ РАБОТНИКА (nda_rabotnik):
- SIGNER_TITLE: должность подписанта ("Генеральный директор" или "Директор продаж")
- SIGNER_TITLE_GENITIVE: в родит. падеже ("Генерального директора")
- SIGNER_TITLE_UZ: на узбекском ("Бош директор" или "Савдо директори")
- CITIZEN_GENDER: "гражданин" или "гражданка"
- DIRECTOR_FIO_LATIN: ФИО подписанта ("ISHMATOV SHERZOD RUSTAMOVICH")

NDA ДЛЯ ГПД (nda_gpd):
- CITIZEN_GENDER: "гражданин" или "гражданка"
- DIRECTOR_FIO / DIRECTOR_FIO_NOMINATIVE / DIRECTOR_SHORT: ФИО директора в разных падежах
- GPD_NUMBER, GPD_DATE: номер и дата ГПД, к которому относится NDA (из фраз вида "ГПД №4 от 27.04.2026", "гражданско-правовой договор № X от Y")

ВОЗМЕЩЕНИЕ РАСХОДОВ (soglashenie_vozmeshenie):
- AGREEMENT_DATE: дата соглашения

ОБРАБОТКА ПЕРС. ДАННЫХ (soglashenie_pd):
- AGREEMENT_NUMBER, AGREEMENT_DATE: номер и дата соглашения
- GPD_NUMBER, GPD_DATE: номер и дата ГПД на который ссылается

Категории шаблонов:
- td_osnovnoy — трудовой договор (основное место)
- td_sovmestitelstvo — трудовой договор (совместительство)
- gpd_uslugi — ГПД на оказание услуг
- prikaz_priem — приказ о приёме на работу
- prikaz_avto — приказ закрепления авто
- mat_otvetstvennost — договор мат. ответственности
- dop_soglashenie_pasport — доп. соглашение (смена паспорта)
- nda_rabotnik — NDA для работника
- nda_gpd — NDA для исполнителя по ГПД
- soglashenie_vozmeshenie — соглашение о возмещении расходов
- soglashenie_pd — соглашение об обработке перс. данных

Также ты можешь помогать с корпоративными подарками:
- Создавать заявки на подарки (create_gift_request)
- Показывать предстоящие события из календаря (list_upcoming_events)
- Проверять статус заявки на подарок (get_gift_status)

КРИТИЧНО: в data должны быть ВСЕ поля из fields. Пустые поля = пустые места в документе.
Отвечай коротко, по делу, на русском.
НЕ выдумывай данные — если не указаны, спроси.
"""

OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "find_template",
            "description": (
                "Найти шаблон документа по категории. "
                "Категории: td_osnovnoy, td_sovmestitelstvo, "
                "gpd_uslugi, prikaz_priem, prikaz_avto, "
                "mat_otvetstvennost, dop_soglashenie_pasport, "
                "nda_rabotnik, nda_gpd, "
                "soglashenie_vozmeshenie, soglashenie_pd."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Категория документа",
                    },
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_document",
            "description": (
                "Сгенерировать документ по шаблону с заполненными данными. "
                "Вызывай когда все обязательные поля заполнены."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "integer",
                        "description": "ID шаблона из find_template",
                    },
                    "data": {
                        "type": "object",
                        "description": (
                            "Данные для подстановки. Используй ТОЧНЫЙ список полей "
                            "из find_template (fields). Передай ВСЕ поля."
                        ),
                    },
                },
                "required": ["template_id", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_templates",
            "description": "Показать список всех загруженных шаблонов документов.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_gift_request",
            "description": (
                "Создать заявку на подарок. "
                "Вызывай когда пользователь просит оформить подарок "
                "и у тебя есть все обязательные данные."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "initiator": {
                        "type": "string",
                        "description": "Кто инициирует подарок",
                    },
                    "recipient": {
                        "type": "string",
                        "description": "Получатель подарка",
                    },
                    "occasion": {
                        "type": "string",
                        "description": "Повод (например, День рождения, Юбилей)",
                    },
                    "category": {
                        "type": "string",
                        "description": "Категория подарка",
                    },
                    "budget": {
                        "type": "integer",
                        "description": "Бюджет в сумах",
                    },
                    "gift_name": {
                        "type": "string",
                        "description": "Название подарка (опционально)",
                    },
                    "vendor": {
                        "type": "string",
                        "description": "Поставщик (опционально)",
                    },
                    "presentation_date": {
                        "type": "string",
                        "description": "Дата вручения в формате YYYY-MM-DD (опционально)",
                    },
                    "comment": {
                        "type": "string",
                        "description": "Комментарий (опционально)",
                    },
                    "event_id": {
                        "type": "integer",
                        "description": "ID связанного события из календаря (опционально)",
                    },
                },
                "required": [
                    "initiator",
                    "recipient",
                    "occasion",
                    "category",
                    "budget",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_upcoming_events",
            "description": (
                "Показать предстоящие события из календаря "
                "(Дни рождения, юбилеи, праздники и т.д.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "На сколько дней вперед смотреть (по умолчанию 30)",
                    },
                    "department": {
                        "type": "string",
                        "description": "Фильтр по отделу (опционально)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gift_status",
            "description": "Проверить статус заявки на подарок по её ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gift_id": {
                        "type": "integer",
                        "description": "ID заявки на подарок",
                    },
                },
                "required": ["gift_id"],
            },
        },
    },
]
