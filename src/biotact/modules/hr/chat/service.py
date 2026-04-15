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
Ты — HR-ассистент компании BIOTACT. Твоя задача — извлечь данные из запроса пользователя и создать документ по шаблону.

Алгоритм:
1. Определи тип документа → вызови find_template с категорией
2. Получишь template_id и список полей (fields) шаблона
3. Извлеки значение для КАЖДОГО поля из текста пользователя
4. Если обязательных данных не хватает — спроси пользователя
5. Когда ВСЕ поля заполнены → вызови generate_document, передав template_id и data с КАЖДЫМ полем

Правила заполнения полей:
- FIO: ФИО кириллицей, ЗАГЛАВНЫМИ (ИВАНОВА МАРИЯ ПЕТРОВНА)
- FIO_LATIN: транслитерация ФИО латиницей (IVANOVA MARIYA PETROVNA)
- FIO_SHORT_LATIN: краткое латиницей (IVANOVA M. P.)
- CONTRACT_TYPE: "неопределённый срок" или "определённый срок"
- CONTRACT_TYPE_UZ: "муддатсиз" или "муайян муддатга"
- WORK_TYPE: "основной работы" или "работы по совместительству"
- WORK_TYPE_UZ: "асосий иш жойи" или "ўриндошлик бўйича иш жойи"
- WORK_CHARACTER: "офисный", "разъездной", "в пути", "на производстве"
- SALARY_TEXT: число прописью (8 000 000 → восемь миллионов)
- Даты в формате ДД.ММ.ГГГГ

Пример вызова generate_document:
generate_document(template_id=2, data={
  "FIO": "ИВАНОВА МАРИЯ ПЕТРОВНА",
  "FIO_LATIN": "IVANOVA MARIYA PETROVNA",
  "FIO_SHORT_LATIN": "IVANOVA M. P.",
  "CONTRACT_NUMBER": "2026-15",
  "CONTRACT_DATE": "07.04.2026",
  "START_DATE": "10.04.2026",
  "PASSPORT": "AB 1234567",
  "PASSPORT_ISSUED_BY": "IIV 12345",
  "PASSPORT_DATE": "15.03.2024",
  "POSITION": "Бухгалтер",
  "CONTRACT_TYPE": "неопределённый срок",
  "CONTRACT_TYPE_UZ": "муддатсиз",
  "WORK_TYPE": "основной работы",
  "WORK_TYPE_UZ": "асосий иш жойи",
  "PROBATION": "3",
  "WORK_CHARACTER": "офисный",
  "HOURS_WEEK": "40",
  "HOURS_DAY": "8",
  "ADDRESS": "г. Ташкент, район, улица, дом, кв",
  "PHONE": "+998901234567",
  "PINFL": "32001015670045"
})

КРИТИЧНО: в data должны быть ВСЕ поля из fields. Пустые поля = пустые места в документе.
Отвечай коротко, по делу, на русском.
НЕ выдумывай данные — если не указаны, спроси.
"""

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_template",
            "description": (
                "Найти шаблон документа по категории. "
                "Категории: td_osnovnoy (трудовой договор, основное место), "
                "td_sovmestitelstvo (трудовой договор, совместительство), "
                "гпд, приказ, должностная_инструкция, "
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
                            "Данные для подстановки. Ключи — метки шаблона "
                            "(используй список полей из find_template): "
                            "FIO, FIO_LATIN, FIO_SHORT_LATIN, "
                            "PASSPORT, PASSPORT_ISSUED_BY, PASSPORT_DATE, "
                            "POSITION, POSITION_UZ, SALARY, SALARY_TEXT, SALARY_TEXT_UZ, "
                            "CONTRACT_NUMBER, CONTRACT_DATE, START_DATE, "
                            "PROBATION, HOURS_WEEK, HOURS_DAY, "
                            "VACATION_DAYS, VACATION_DAYS_TEXT, VACATION_DAYS_TEXT_UZ, "
                            "ADDRESS, PHONE, PINFL, "
                            "WORK_TYPE, WORK_TYPE_UZ, CONTRACT_TYPE, CONTRACT_TYPE_UZ, WORK_CHARACTER"
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

    def __init__(self, settings: Settings, db: AsyncSession, *, user_id: int = 0) -> None:
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-5.4-mini"
        self.db = db
        self._user_id = user_id

    async def _get_template_context(self) -> str:
        """Pre-fetch available templates to inject into system prompt."""
        try:
            templates_result = await list_templates(self.db)
            if not templates_result.items:
                return ""
            lines = []
            for t in templates_result.items:
                fields = t.template_fields or []
                lines.append(
                    f"- id={t.id} name={t.name} category={t.category} "
                    f"fields={fields}"
                )
            return (
                "\n\nДоступные шаблоны (уже загружены, find_template не нужен):\n"
                + "\n".join(lines)
                + "\n\nЕсли пользователь просит создать документ и все данные собраны, "
                "сразу вызывай generate_document с нужным template_id и ВСЕМИ полями."
            )
        except Exception:
            logger.exception("Failed to pre-fetch templates")
            return ""

    async def _extract_data_from_context(
        self, context: str, fields: list[str],
    ) -> dict[str, str]:
        """Use a focused LLM call to extract structured data from conversation."""
        extraction_prompt = (
            "Извлеки данные из текста переписки и верни JSON.\n"
            f"Поля: {json.dumps(fields)}\n\n"
            "Правила:\n"
            "- FIO: ЗАГЛАВНЫМИ кириллицей (ПЕТРОВ АЛЕКСЕЙ СЕРГЕЕВИЧ)\n"
            "- FIO_LATIN: ЗАГЛАВНЫМИ латиницей (PETROV ALEKSEY SERGEEVICH)\n"
            "- FIO_SHORT_LATIN: PETROV A. S.\n"
            "- CONTRACT_TYPE: 'неопределённый срок' или 'определённый срок'\n"
            "- CONTRACT_TYPE_UZ: 'муддатсиз' или 'муайян муддатга'\n"
            "- WORK_TYPE: 'основной работы' или 'работы по совместительству'\n"
            "- WORK_TYPE_UZ: 'асосий иш жойи' или 'ўриндошлик бўйича иш жойи'\n"
            "- Даты: ДД.ММ.ГГГГ\n"
            "- Если поле нельзя извлечь — пустая строка\n\n"
            "Верни ТОЛЬКО JSON, без пояснений.\n\n"
            f"Переписка:\n{context}"
        )

        try:
            response = await self.openai.chat.completions.create(
                model=self.model,
                max_completion_tokens=2048,
                messages=[{"role": "user", "content": extraction_prompt}],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            logger.info("Extracted %d fields from context", len(data))
            return {k: str(v) for k, v in data.items() if v}
        except Exception:
            logger.exception("Failed to extract data from context")
            return {}

    async def process_message(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Process user message.

        Returns: {"message": str, "document_url": str | None}
        """
        # Pre-fetch template context so AI always knows template_id + fields
        template_ctx = await self._get_template_context()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT + template_ctx},
        ]

        if history:
            for msg in history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": message})

        # Save conversation text for fallback extraction
        self._messages_context = "\n".join(
            f"{m['role']}: {m['content']}"
            for m in messages
            if m["role"] in ("user", "assistant") and m.get("content")
        )

        document_url: str | None = None

        # Function calling loop (up to 5 rounds)
        for round_num in range(5):
            try:
                response = await self.openai.chat.completions.create(  # type: ignore[call-overload]
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
                logger.info(
                    "HR tool: %s args=%s",
                    func_name,
                    json.dumps(func_args, ensure_ascii=False)[:2000],
                )

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

            from sqlalchemy import select

            from biotact.modules.hr.library.models import HRTemplate

            result = await self.db.execute(
                select(HRTemplate).where(HRTemplate.id == template_id)
            )
            db_template = result.scalar_one_or_none()
            if not db_template:
                return "Ошибка: шаблон не найден"

            # If AI sent incomplete data, extract from conversation
            fields = db_template.template_fields or []
            missing = [f for f in fields if f not in data or not data[f]]
            if missing and hasattr(self, "_messages_context"):
                logger.info(
                    "generate_document: %d/%d fields missing, extracting via LLM",
                    len(missing),
                    len(fields),
                )
                extracted = await self._extract_data_from_context(
                    self._messages_context, fields
                )
                # Merge: AI-provided data takes priority
                for k, v in extracted.items():
                    if k not in data or not data.get(k):
                        data[k] = v

            # Render DOCX
            try:
                RENDER_DIR.mkdir(parents=True, exist_ok=True)
                file_id = uuid.uuid4().hex[:12]
                out_path = RENDER_DIR / f"{file_id}.docx"

                buffer = render_template(db_template.file_path, data)
                rendered_bytes = buffer.read()
                out_path.write_bytes(rendered_bytes)

                # Save to hr_documents for history
                from biotact.modules.hr.library.models import HRDocument

                employee = data.get("FIO") or data.get("FIO_LATIN") or "—"
                hr_doc = HRDocument(
                    file_id=file_id,
                    template_id=db_template.id,
                    template_name=db_template.name,
                    employee_name=employee,
                    file_path=str(out_path),
                    file_size=len(rendered_bytes),
                    created_by=self._user_id,
                )
                self.db.add(hr_doc)
                await self.db.flush()

                logger.info(
                    "Document rendered: %s employee=%s fields=%d",
                    out_path,
                    employee,
                    len(data),
                )
                return f"/api/v1/hr/documents/download/{file_id}"
            except Exception as e:
                logger.exception("Render failed for template %d", template_id)
                return f"Ошибка рендеринга: {e}"

        if name == "list_available_templates":
            templates_result = await list_templates(self.db)
            if not templates_result.items:
                return "Библиотека пуста. Загрузите шаблоны документов."
            lines = [
                f"- {t.name} (категория: {t.category}, полей: {len(t.template_fields or [])})"
                for t in templates_result.items
            ]
            return "Доступные шаблоны:\n" + "\n".join(lines)

        return f"Неизвестный инструмент: {name}"
