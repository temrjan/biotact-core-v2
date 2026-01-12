"""Dashboard module configuration."""

from typing import Any

from biotact.modules.base import CommandModuleConfig

DASHBOARD_SYSTEM_PROMPT = """Ты финансовый ассистент платформы BIOTACT.
Твоя задача — помогать пользователям отслеживать доходы и расходы компании.

Доступные категории: {categories}
Типы транзакций: expense (расход), income (доход)
Периоды: monthly (месячный), quarterly (квартальный), yearly (годовой)

Текущая дата: {current_date}

ВАЖНО: Форматы сумм от пользователя:
- "15 млн" или "15 миллионов" = 15,000,000
- "500 тыс" или "500 тысяч" = 500,000
- Просто число без указания — считай миллионами (15 = 15,000,000)

Когда пользователь просит добавить запись — используй add_financial_record.
Когда пользователь просит отчёт — используй get_financial_report.

Всегда подтверждай детали перед выполнением операции.
Отвечай кратко и по делу. Используй эмодзи ✓ для успеха.
"""

DASHBOARD_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "add_financial_record",
            "description": "Добавить финансовую запись (доход или расход)",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["expense", "income"],
                        "description": "Тип операции: expense (расход) или income (доход)",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Сумма в сумах (базовых единицах)",
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "hosting",
                            "marketing",
                            "salary",
                            "inventory",
                            "office",
                            "logistics",
                            "other",
                            "sales",
                        ],
                        "description": "Категория транзакции",
                    },
                    "period": {
                        "type": "string",
                        "enum": ["monthly", "quarterly", "yearly"],
                        "description": "Период учёта",
                    },
                    "description": {
                        "type": "string",
                        "description": "Описание операции",
                    },
                },
                "required": ["type", "amount", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_financial_report",
            "description": "Получить финансовый отчёт за период",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["monthly", "quarterly", "yearly"],
                        "description": "Фильтр по периоду",
                    },
                },
                "required": [],
            },
        },
    },
]

# Category display names for Russian interface
CATEGORY_NAMES: dict[str, str] = {
    "hosting": "Хостинг",
    "marketing": "Маркетинг",
    "salary": "Зарплата",
    "inventory": "Закупки",
    "office": "Офис",
    "logistics": "Логистика",
    "other": "Прочее",
    "sales": "Продажи",
}

# Create module config
dashboard_config = CommandModuleConfig(
    department_id="dashboard",
    display_name="Финансовый дашборд",
    description="Управление финансами через естественный язык",
    system_prompt=DASHBOARD_SYSTEM_PROMPT,
    tools=DASHBOARD_TOOLS,
    max_clarification_turns=3,
)
