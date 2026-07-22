"""HR Chat service — AI extracts data, docxtpl renders document."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from openai import AsyncOpenAI, OpenAIError
from sqlalchemy.exc import SQLAlchemyError

from biotact.modules.hr.chat.documents import generate_hr_document
from biotact.modules.hr.chat.prompts import OPENAI_TOOLS, SYSTEM_PROMPT
from biotact.modules.hr.events.service import list_events
from biotact.modules.hr.gifts.schemas import GiftCreateRequest
from biotact.modules.hr.gifts.service import create_gift, get_gift
from biotact.modules.hr.library.service import (
    list_render_eligible,
    resolve_template,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from biotact.core.config import Settings
    from biotact.modules.hr.chat.schemas import ChatMessage

logger = logging.getLogger(__name__)


def _cached_tokens(usage: Any) -> int:
    """Cached prompt tokens reported by OpenAI, or 0 when unavailable.

    Defensive: both ``usage`` and ``prompt_tokens_details`` are optional on the
    SDK model (CompletionUsage) and absent from lightweight test doubles.
    """
    details = getattr(usage, "prompt_tokens_details", None)
    return getattr(details, "cached_tokens", None) or 0


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
        """Pre-fetch available templates to inject into system prompt.

        Only render-eligible ones: a category can hold several versions, and the
        line below carries no ``version`` or ``is_active``, so a superseded row
        reaching the model would be indistinguishable from the current one.
        """
        try:
            templates = await list_render_eligible(self.db)
            if not templates:
                return ""
            lines = [
                f"- id={t.id} name={t.name} category={t.category} fields={t.template_fields or []}"
                for t in templates
            ]
            return (
                "Доступные шаблоны (уже загружены, find_template не нужен):\n"
                + "\n".join(lines)
                + "\n\nЕсли пользователь просит создать документ и все данные собраны, сразу вызывай generate_document с нужным template_id и ВСЕМИ полями."
            )
        except SQLAlchemyError:
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
        # Keep the stable instruction block as its own system message so OpenAI
        # auto-caches it (identical ≥1024-token prefix across calls). The volatile
        # template list goes in a second system message so it never invalidates
        # the cached prefix.
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        template_context = await self._get_template_context()
        if template_context:
            messages.append({"role": "system", "content": template_context})

        if history:
            for msg in history[-self._history_window :]:
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
            except OpenAIError as e:
                logger.exception("HR chat OpenAI error round=%d", round_num)
                return {"message": f"Ошибка LLM: {e}", "document_url": None}

            choice = response.choices[0]
            usage = getattr(response, "usage", None)
            logger.info(
                "HR chat round=%d finish=%s tools=%s prompt_tokens=%s cached_tokens=%d",
                round_num,
                choice.finish_reason,
                bool(choice.message.tool_calls),
                getattr(usage, "prompt_tokens", None),
                _cached_tokens(usage),
            )

            if choice.message.tool_calls:
                tool_call = choice.message.tool_calls[0]
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                logger.info(
                    "HR tool: %s args_keys=%s",
                    func_name,
                    sorted(func_args),  # top-level keys only — never field VALUES
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
        """Execute a tool call by dispatching to a named handler."""
        tool_method = getattr(self, f"_tool_{name}", None)
        if tool_method is not None:
            handler = cast("Callable[[dict[str, Any]], Awaitable[str]]", tool_method)
            return await handler(args)
        return f"Неизвестный инструмент: {name}"

    async def _tool_find_template(self, args: dict[str, Any]) -> str:
        query = args.get("category", "")
        result = await resolve_template(self.db, query)

        if result.match is not None:
            return json.dumps(
                {
                    "template_id": result.match.id,
                    "name": result.match.name,
                    "fields": result.match.template_fields or [],
                },
                ensure_ascii=False,
            )

        # No single match. Offer the render-eligible templates deterministically;
        # "upload a template" is said ONLY when the library has nothing renderable.
        if not result.candidates:
            return "Библиотека шаблонов пуста. Загрузите шаблон документа."
        lines = [
            f"- id={c.id} категория={c.category} название={c.name}"
            for c in result.candidates
        ]
        return "Уточните, какой шаблон нужен:\n" + "\n".join(lines)

    async def _tool_generate_document(self, args: dict[str, Any]) -> str:
        return await generate_hr_document(
            self.db,
            args,
            openai=self.openai,
            model=self.model,
            user_id=self._user_id,
            messages_context=self._messages_context,
            now=self._now(),
        )

    async def _tool_list_available_templates(self, _args: dict[str, Any]) -> str:
        """List templates for the model. Same source as the system context.

        This listing shows neither id nor version, so a superseded row here is
        even less distinguishable than in the system context — filtering is what
        keeps the two chat-facing paths from disagreeing.
        """
        templates = await list_render_eligible(self.db)
        if not templates:
            return "Библиотека пуста. Загрузите шаблоны документов."
        lines = [
            f"- {t.name} (категория: {t.category}, "
            f"полей: {len(t.template_fields or [])})"
            for t in templates
        ]
        return "Доступные шаблоны:\n" + "\n".join(lines)

    async def _tool_create_gift_request(self, args: dict[str, Any]) -> str:
        required = ("initiator", "recipient", "occasion", "category", "budget")
        missing = [f for f in required if f not in args]
        if missing:
            return (
                "Не хватает обязательных полей: "
                f"{', '.join(missing)}. Спроси недостающие данные."
            )

        presentation_date_str = args.get("presentation_date")
        presentation_date: date | None = None
        if presentation_date_str:
            try:
                presentation_date = date.fromisoformat(presentation_date_str)
            except ValueError:
                return (
                    f"Неверный формат даты: {presentation_date_str}. "
                    "Используйте YYYY-MM-DD."
                )

        # responsible_person_id is not accepted from the model: the gifts
        # service always assigns the authenticated user (self._user_id).
        data = GiftCreateRequest(
            event_id=args.get("event_id"),
            initiator=args["initiator"],
            recipient=args["recipient"],
            occasion=args["occasion"],
            category=args["category"],
            gift_name=args.get("gift_name"),
            budget=args["budget"],
            vendor=args.get("vendor"),
            presentation_date=presentation_date,
            comment=args.get("comment"),
        )
        gift_obj = await create_gift(self.db, data, user_id=self._user_id)
        return json.dumps(
            {
                "gift_id": gift_obj.id,
                "status": gift_obj.status.value,
                "message": f"Заявка на подарок #{gift_obj.id} создана.",
            },
            ensure_ascii=False,
        )

    async def _tool_list_upcoming_events(self, args: dict[str, Any]) -> str:
        days = args.get("days", 30)
        if not isinstance(days, int) or days < 1:
            days = 30
        today = date.today()
        to_date = today + timedelta(days=days)
        events_result = await list_events(
            self.db,
            from_date=today,
            to_date=to_date,
            department=args.get("department"),
            size=100,
        )
        if not events_result.items:
            return "Предстоящих событий не найдено."
        lines = [
            f"- {e.date}: {e.employee_name} ({e.occasion_type.value}, "
            f"отдел: {e.department})"
            for e in events_result.items
        ]
        return "Предстоящие события:\n" + "\n".join(lines)

    async def _tool_get_gift_status(self, args: dict[str, Any]) -> str:
        gift_id_raw = args.get("gift_id")
        if gift_id_raw is None:
            return "Не указан ID заявки."
        try:
            gift_id = int(gift_id_raw)
        except (TypeError, ValueError):
            return "Неверный формат ID заявки."
        gift_obj = await get_gift(self.db, gift_id)
        if not gift_obj:
            return f"Заявка на подарок #{gift_id} не найдена."
        return json.dumps(
            {
                "gift_id": gift_obj.id,
                "status": gift_obj.status.value,
                "recipient": gift_obj.recipient,
                "occasion": gift_obj.occasion,
                "budget": gift_obj.budget,
                "gift_name": gift_obj.gift_name,
                "presentation_date": (
                    gift_obj.presentation_date.isoformat()
                    if gift_obj.presentation_date
                    else None
                ),
            },
            ensure_ascii=False,
        )
