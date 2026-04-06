"""HR Chat service — OpenAI function calling with Anthropic fallback."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from biotact.modules.hr.library.service import get_template_by_category, list_templates

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from biotact.core.config import Settings

logger = logging.getLogger(__name__)


def _strip_markdown(text: str) -> str:
    """Remove Markdown formatting symbols from document text."""
    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove bold **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    # Remove italic *text* (but not in words)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    # Remove heading markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove blockquotes
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\*{3,}$", "", text, flags=re.MULTILINE)
    # Replace bullet lists with spaces
    text = re.sub(r"^[\-\*]\s+", "  ", text, flags=re.MULTILINE)
    # Clean up multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# System prompt for the HR assistant
SYSTEM_PROMPT = """\
Ты — HR-ассистент компании BIOTACT. Твоя основная задача — создавать документы по образцам.

Как ты работаешь:
1. Пользователь просит создать документ (договор, приказ, инструкцию и т.д.)
2. Ты ищешь подходящий образец в библиотеке через get_template
3. Читаешь образец ЦЕЛИКОМ
4. Подставляешь данные, которые дал пользователь
5. Возвращаешь ГОТОВЫЙ текст документа

Правила:
- ВСЕГДА сначала ищи образец через get_template. Не выдумывай формат документа.
- Если образца нет — скажи пользователю загрузить образец в библиотеку.
- Если пользователь не дал все нужные данные — спроси недостающее.
- Сохраняй структуру и стиль образца. Меняй ТОЛЬКО персональные данные.
- Отвечай на русском языке.

КРИТИЧЕСКИ ВАЖНО — формат вывода гото��ого документа:
- Выводи ЧИСТЫЙ ТЕКСТ. Никакого Markdown.
- НЕ используй символы: # * ** ` ``` --- > -
- Заголовки пиши ЗАГЛАВНЫМИ БУКВАМИ.
- Нум��рацию пиши как: 1. 2. 3. или 1.1. 1.2.
- Списки пиши через нумерацию, без тире и звёздочек.
- ��ирный и к��рсив — не нужны, пиши обычным текстом.
- О��разец может содержать Markdown-разметку — это только для структуры. В готовом документе её бы��ь НЕ ДОЛЖНО.
"""

# OpenAI function definitions
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_template",
            "description": (
                "Найти образец документа в библиотеке по категории. "
                "Категории: трудовой_договор, гпд, приказ, должностная_инструкция, "
                "мат_ответственность, соглашение_конфиденциальности, "
                "соглашение_персданные, соглашение_возмещение, другое. "
                "Возвращает ПОЛНЫЙ текст образца."
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
            "name": "list_available_templates",
            "description": "Показать список всех загруженных образцов документов в библиотеке.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


class HRChatService:
    """HR Chat with OpenAI function calling (primary) for document generation."""

    def __init__(self, settings: Settings, db: AsyncSession) -> None:
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-5.4-mini"
        self.db = db

    async def process_message(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Process user message with function calling loop.

        Returns: {"message": str, "document_text": str | None}
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        # Add history
        if history:
            for msg in history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": message})

        document_text: str | None = None

        # Function calling loop (up to 5 rounds)
        for _ in range(5):
            response = await self.openai.chat.completions.create(
                model=self.model,
                max_completion_tokens=8192,
                messages=messages,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
            )

            choice = response.choices[0]

            # If the model wants to call a function
            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                tool_call = choice.message.tool_calls[0]
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)

                # Execute the tool
                tool_result = await self._execute_tool(func_name, func_args)

                # Add assistant message + tool result
                messages.append(choice.message.model_dump())
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )
                continue

            # Model finished — extract text
            final_text = choice.message.content or ""

            # Check if the response contains a generated document
            if len(final_text) > 500:
                document_text = _strip_markdown(final_text)

            return {"message": final_text, "document_text": document_text}

        return {
            "message": "Не удалось обработать запрос. Попробуйте ещё раз.",
            "document_text": None,
        }

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        """Execute a tool call and return result text."""
        if name == "get_template":
            category = args.get("category", "")
            template = await get_template_by_category(self.db, category)
            if not template or not template.extracted_text:
                return (
                    f"Образец для кат��гории '{category}' не найден в библиотеке. "
                    f"Попросите ��ользователя загрузить образец."
                )
            return f"ОБРАЗЕЦ ДОКУМЕНТА ({template.name}):\n\n{template.extracted_text}"

        if name == "list_available_templates":
            result = await list_templates(self.db)
            if not result.items:
                return "Библиотека пуста. Попросите пользователя загрузить образцы документов."
            lines = [f"- {t.name} (к��тегория: {t.category})" for t in result.items]
            return "Доступные образцы:\n" + "\n".join(lines)

        return f"Неизвестный инструм��нт: {name}"
