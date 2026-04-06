"""HR Chat service — Anthropic tool_use for document generation from templates."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from anthropic import AsyncAnthropic

from biotact.modules.hr.library.service import get_template_by_category, list_templates

if TYPE_CHECKING:
    from anthropic.types import MessageParam, ToolParam
    from sqlalchemy.ext.asyncio import AsyncSession

    from biotact.core.config import Settings

logger = logging.getLogger(__name__)


def _strip_markdown(text: str) -> str:
    """Remove Markdown formatting symbols from document text.

    Cleans: # headings, ** bold **, * italic *, ``` code blocks ```,
    > blockquotes, --- separators, - list bullets.
    Preserves numbered lists (1. 2. 3.) and plain text structure.
    """
    import re

    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove bold **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    # Remove italic *text* or _text_ (but not in words like файл_имя)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    # Remove heading markers (# ## ### etc.)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove blockquotes
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\*{3,}$", "", text, flags=re.MULTILINE)
    # Replace bullet lists (- or *) with numbered-style
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

КРИТИЧЕСКИ ВАЖНО — формат вывода готового документа:
- Выводи ЧИСТЫЙ ТЕКСТ. Никакого Markdown.
- НЕ используй символы: # * ** ` ``` --- > -
- Заголовки пиши ЗАГЛАВНЫМИ БУКВАМИ.
- Нумерацию пиши как: 1. 2. 3. или 1.1. 1.2.
- Списки пиши через нумерацию, без тире и звёздочек.
- Жирный и курсив — не нужны, пиши обычным текстом.
- Образец может содержать Markdown-разметку — это только для структуры. В готовом документе её быть НЕ ДОЛЖНО.
"""

# Tools available to the LLM
HR_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_template",
        "description": (
            "Найти образец документа в библиотеке по категории. "
            "Категории: трудовой_договор, приказ_приём, приказ_увольнение, "
            "приказ_перевод, приказ_отпуск, должностная_инструкция, "
            "kpi_карта, план_онбординга, правила_распорядка, "
            "вопросы_интервью, аттестация, вакансия, оффер. "
            "Возвращает ПОЛНЫЙ текст образца."
        ),
        "input_schema": {
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
    {
        "name": "list_available_templates",
        "description": "Показать список всех загруженных образцов документов в библиотеке.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


class HRChatService:
    """HR Chat with Anthropic tool_use for document generation."""

    def __init__(self, settings: Settings, db: AsyncSession) -> None:
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"
        self.db = db

    async def process_message(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Process user message with tool_use loop.

        Returns: {"message": str, "document_text": str | None}
        """
        messages: list[MessageParam] = []

        # Add history
        if history:
            for msg in history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})  # type: ignore[typeddict-item]

        messages.append({"role": "user", "content": message})

        document_text: str | None = None
        tools = cast("list[ToolParam]", HR_TOOLS)

        # Tool use loop (up to 5 rounds)
        for _ in range(5):
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )

            # If the model wants to use a tool
            if response.stop_reason == "tool_use":
                # Find the tool use block
                tool_block = next(
                    (b for b in response.content if b.type == "tool_use"),
                    None,
                )
                if not tool_block:
                    break

                # Execute the tool
                tool_input = cast("dict[str, Any]", tool_block.input)
                tool_result = await self._execute_tool(tool_block.name, tool_input)

                # Add assistant response + tool result to messages
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_block.id,
                                "content": tool_result,
                            }
                        ],
                    }
                )
                continue

            # Model finished — extract text response
            text_parts = [b.text for b in response.content if hasattr(b, "text")]
            final_text = "\n".join(text_parts)

            # Check if the response contains a generated document
            # (heuristic: if it's long and structured, it's a document)
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
                return f"Образец для категории '{category}' не найден в библиотеке. Попросите пользователя загрузить образец."
            return f"ОБРАЗЕЦ ДОКУМЕНТА ({template.name}):\n\n{template.extracted_text}"

        if name == "list_available_templates":
            result = await list_templates(self.db)
            if not result.items:
                return "Библиотека пуста. Попросите пользователя загрузить образцы документов."
            lines = [f"- {t.name} (категория: {t.category})" for t in result.items]
            return "Доступные образцы:\n" + "\n".join(lines)

        return f"Неизвестный инструмент: {name}"
