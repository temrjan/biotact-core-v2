"""HR Chat service — AI extracts data, docxtpl renders document."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from biotact.modules.hr.chat.documents import generate_hr_document
from biotact.modules.hr.chat.prompts import OPENAI_TOOLS, SYSTEM_PROMPT
from biotact.modules.hr.library.service import (
    get_template_by_category,
    list_templates,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from biotact.core.config import Settings
    from biotact.modules.hr.chat.schemas import ChatMessage

logger = logging.getLogger(__name__)


class HRChatService:
    """HR Chat — AI extracts data from user text, docxtpl renders DOCX."""

    def __init__(
        self,
        settings: Settings,
        db: AsyncSession,
        *,
        user_id: int = 0,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.hr_chat_model
        self._max_tool_rounds = settings.hr_max_tool_rounds
        self._history_window = settings.hr_history_window
        self.db = db
        self._user_id = user_id
        self._now = now_fn
        self._messages_context = ""

    async def _get_template_context(self) -> str:
        """Pre-fetch available templates to inject into system prompt."""
        try:
            templates_result = await list_templates(self.db)
            if not templates_result.items:
                return ""
            lines = [
                f"- id={t.id} name={t.name} category={t.category} fields={t.template_fields or []}"
                for t in templates_result.items
            ]
            return (
                "\n\nДоступные шаблоны (уже загружены, find_template не нужен):\n"
                + "\n".join(lines)
                + "\n\nЕсли пользователь просит создать документ и все данные собраны, сразу вызывай generate_document с нужным template_id и ВСЕМИ полями."
            )
        except Exception:
            logger.exception("Failed to pre-fetch templates")
            return ""

    async def process_message(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
    ) -> dict[str, Any]:
        """Process user message.

        Returns: {"message": str, "document_url": str | None}
        """
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT + await self._get_template_context(),
            },
        ]

        if history:
            for msg in history[-self._history_window:]:
                messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": message})

        self._messages_context = "\n".join(
            f"{m['role']}: {m['content']}"
            for m in messages
            if m["role"] in ("user", "assistant") and m.get("content")
        )

        document_url: str | None = None
        for round_num in range(self._max_tool_rounds):
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

                if func_name == "generate_document" and tool_result.startswith("/api/"):
                    document_url = tool_result
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

            return {
                "message": choice.message.content or "",
                "document_url": document_url,
            }

        return {
            "message": "Не удалось обработать запрос. Попробуйте ещё раз.",
            "document_url": None,
        }

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
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
            return await generate_hr_document(
                self.db,
                args,
                openai=self.openai,
                model=self.model,
                user_id=self._user_id,
                messages_context=self._messages_context,
                now=self._now(),
            )

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
