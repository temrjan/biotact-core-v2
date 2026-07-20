"""HR Chat prompts and OpenAI tool definitions.

Static content lives here so service.py can focus on orchestration.
"""

from __future__ import annotations

from typing import Any

from biotact.modules.hr.chat.field_rules import build_system_rules

# Stable, request-independent prefix (>1024 tokens). Sent as a standalone
# system message so OpenAI's automatic prompt caching can reuse it across calls
# (no `cache_control` markers — that is Anthropic-only). Keep this block free of
# per-request data; volatile content (template list) is appended separately.
_SYSTEM_PROMPT_HEADER = """\
Ты — HR-ассистент компании BIOTACT. Твоя задача — извлечь данные из запроса пользователя и создать документ по шаблону.

Алгоритм:
1. Определи тип документа и выбери template_id из списка доступных шаблонов (он уже в контексте ниже). Если список не показан, тип неясен или неоднозначен — вызови find_template для уточнения (вернёт один шаблон или список).
2. Возьми список полей (fields) выбранного шаблона (из контекста или из ответа find_template)
3. Извлеки значение для КАЖДОГО поля из текста пользователя
4. Если обязательных данных не хватает — спроси пользователя
5. Когда ВСЕ поля заполнены → вызови generate_document, передав template_id и data с КАЖДЫМ полем"""

_SYSTEM_PROMPT_FOOTER = """\
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
НЕ выдумывай данные — если не указаны, спроси."""

# Assembled once at import → stable ≥1024-token prefix for OpenAI auto-caching.
# Per-category field rules come from ``field_rules`` so the fallback extractor
# in ``extractor.py`` shares the exact same rules (no drift between the two).
SYSTEM_PROMPT = (
    f"{_SYSTEM_PROMPT_HEADER}\n\n{build_system_rules()}\n\n{_SYSTEM_PROMPT_FOOTER}\n"
)

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
