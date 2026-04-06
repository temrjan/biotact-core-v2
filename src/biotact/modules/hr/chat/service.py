"""HR Chat service — AI extracts data, docxtpl renders document."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from biotact.modules.hr.documents.renderer import render_template
from biotact.modules.hr.library.service import (
    get_template_by_category,
    list_templates,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from biotact.core.config import Settings

logger = logging.getLogger(__name__)

# Directory for rendered files (temporary)
RENDER_DIR = Path("data/hr_rendered")

SYSTEM_PROMPT = """\
Ты — HR-ассистент. Твоя задача — извлечь данные из запроса пользователя и создать документ по шаблону.

Как ты работаешь:
1. Определи какой документ нужен → вызови find_template
2. Получишь template_id и список полей шаблона
3. Извлеки данные из текста пользователя для каждого поля
4. Если каких-то обязательных данных не хватает (ФИО, паспорт, должность, оклад) — спроси пользователя
5. Когда данные собраны → вызови generate_document с template_id и заполненными полями

Правила:
- Отвечай коротко, по делу, на русском языке.
- НЕ выдумывай данные. Если пользователь не дал — спроси.
- Для SALARY_TEXT переведи число в текст прописью (напр. 8 000 000 → восемь миллионов).
- Для FIO_SHORT сократи ФИО (Иванова Мария Петровна → Иванова М.П.)
"""

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_template",
            "description": (
                "Найти шаблон документа по категории. "
                "Категории: трудовой_договор, гпд, приказ, должностная_инструкция, "
                "мат_ответственность, соглашение_конфиденциальности, "
                "соглашение_персданные, соглашение_возмещение, другое."
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
                            "Данные для подстановки. Ключи — метки шаблона: "
                            "FIO, FIO_SHORT, PASSPORT, PASSPORT_ISSUED_BY, PASSPORT_DATE, "
                            "POSITION, DEPARTMENT, SALARY, SALARY_TEXT, "
                            "CONTRACT_NUMBER, CONTRACT_DATE, START_DATE, "
                            "PROBATION, HOURS_WEEK, HOURS_DAY, VACATION_DAYS, VACATION_DAYS_TEXT, "
                            "ADDRESS, PHONE, PINFL, INN, WORK_TYPE, CONTRACT_TYPE, WORK_CHARACTER"
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
]


class HRChatService:
    """HR Chat — AI extracts data from user text, docxtpl renders DOCX."""

    def __init__(self, settings: Settings, db: AsyncSession) -> None:
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-5.4-mini"
        self.db = db

    async def process_message(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Process user message.

        Returns: {"message": str, "document_url": str | None}
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        if history:
            for msg in history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": message})

        document_url: str | None = None

        # Function calling loop (up to 5 rounds)
        for round_num in range(5):
            try:
                response = await self.openai.chat.completions.create(
                    model=self.model,
                    max_completion_tokens=4096,
                    messages=messages,
                    tools=OPENAI_TOOLS,
                    tool_choice="auto",
                )
            except Exception as e:
                logger.exception("HR chat OpenAI error round=%d", round_num)
                return {"message": f"Ошибка LLM: {e}", "document_url": None}

            choice = response.choices[0]
            logger.info(
                "HR chat round=%d finish=%s tools=%s",
                round_num,
                choice.finish_reason,
                bool(choice.message.tool_calls),
            )

            if choice.message.tool_calls:
                tool_call = choice.message.tool_calls[0]
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                logger.info("HR tool: %s(%s)", func_name, list(func_args.keys()))

                tool_result = await self._execute_tool(func_name, func_args)

                # If generate_document returned a URL, capture it
                if func_name == "generate_document" and tool_result.startswith("/api/"):
                    document_url = tool_result
                    # Let the model generate a final message
                    tool_result_for_model = (
                        "Документ успешно создан и готов к скачиванию."
                    )
                else:
                    tool_result_for_model = tool_result

                messages.append(
                    {
                        "role": "assistant",
                        "content": choice.message.content or "",
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": func_name,
                                    "arguments": tool_call.function.arguments,
                                },
                            }
                        ],
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result_for_model,
                    }
                )
                continue

            # Model finished
            final_text = choice.message.content or ""
            return {"message": final_text, "document_url": document_url}

        return {
            "message": "Не удалось обработать запрос. Попробуйте ещё раз.",
            "document_url": None,
        }

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> str:  # noqa: PLR0911
        """Execute a tool call."""
        if name == "find_template":
            category = args.get("category", "")
            template = await get_template_by_category(self.db, category)
            if not template:
                return f"Шаблон для категории '{category}' не найден. Попросите загрузить шаблон."
            return json.dumps(
                {
                    "template_id": template.id,
                    "name": template.name,
                    "fields": template.template_fields or [],
                },
                ensure_ascii=False,
            )

        if name == "generate_document":
            template_id = args.get("template_id")
            data = args.get("data", {})

            if not template_id:
                return "Ошибка: не указан template_id"

            # Get template file path
            from sqlalchemy import select

            from biotact.modules.hr.library.models import HRTemplate

            result = await self.db.execute(
                select(HRTemplate).where(HRTemplate.id == template_id)
            )
            db_template = result.scalar_one_or_none()
            if not db_template:
                return "Ошибка: шаблон не найден"

            # Render DOCX
            try:
                RENDER_DIR.mkdir(parents=True, exist_ok=True)
                file_id = uuid.uuid4().hex[:12]
                out_path = RENDER_DIR / f"{file_id}.docx"

                buffer = render_template(db_template.file_path, data)
                out_path.write_bytes(buffer.read())

                logger.info("Document rendered: %s fields=%d", out_path, len(data))
                return f"/api/v1/hr/documents/download/{file_id}"
            except Exception as e:
                logger.exception("Render failed for template %d", template_id)
                return f"Ошибка рендеринга: {e}"

        if name == "list_available_templates":
            result = await list_templates(self.db)
            if not result.items:
                return "Библиотека пуста. Загрузите шаблоны документов."
            lines = [
                f"- {t.name} (категория: {t.category}, полей: {len(t.template_fields or [])})"
                for t in result.items
            ]
            return "Доступные шаблоны:\n" + "\n".join(lines)

        return f"Неизвестный инструмент: {name}"
