"""AskBiotact unified service — single AI pipeline for all channels.

Composable methods: webhook bot and public API both call these.
CRM context, query enrichment, RAG, extraction agent, order processing.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import Any

import httpx
import redis.asyncio as aioredis
from openai import AsyncOpenAI

from biotact.core.config import get_settings
from biotact.core.database import get_session_context
from biotact.core.dependencies import (
    get_embedding_service,
    get_llm_service,
    get_qdrant_service,
)
from biotact.modules.askbiotact.config import askbiotact_config
from biotact.modules.askbiotact.constants import (
    ORDER_KEYWORDS,
    PRODUCT_PRICES,
    enrich_query,
    extract_phone,
    is_short_query,
)
from biotact.modules.askbiotact.safety_filter import (
    apply_safety_filter,
    detect_safety_trigger,
)
from biotact.modules.askbiotact.schemas import (
    OrderProduct,
    ParsedOrder,
    UserInfo,
)
from biotact.modules.crm.service import CRMService
from biotact.services.extraction_agent import (
    ExtractionAgent,
    archive_insight,
    get_active_insight,
)

logger = logging.getLogger(__name__)

# Chat history limits
MAX_HISTORY: int = 10
HISTORY_TTL: int = 86400  # 24 hours
ORDER_DEDUP_TTL: int = 3600  # 1 hour

# User message template (data only, instructions in system prompt)
USER_TEMPLATE: str = """Данные из базы знаний:
{context}

Сообщение клиента: {question}"""


class AskBiotactService:
    """Unified AI pipeline for AskBiotact.

    Provides composable methods so each adapter (webhook, public API)
    can use them in its own flow.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._redis: aioredis.Redis | None = None
        self._redis_host: str = settings.redis_host
        self._redis_port: int = settings.redis_port
        self._extraction_agent: ExtractionAgent | None = None
        self._openai_client: AsyncOpenAI | None = None
        self._openai_api_key: str = settings.openai_api_key
        self._notification_bot_token: str | None = os.getenv("NOTIFICATION_BOT_TOKEN")
        self._sales_group_chat_id: str | None = os.getenv("SALES_GROUP_CHAT_ID")

    # =========================================================================
    # Redis
    # =========================================================================

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=self._redis_host,
                port=self._redis_port,
                decode_responses=True,
            )
        return self._redis

    async def get_chat_history(
        self,
        user_id: str,
        prefix: str,
    ) -> list[dict[str, str]]:
        """Load chat history from Redis.

        Args:
            user_id: Telegram user ID or external ID.
            prefix: Namespace prefix ("chat" for webhook, "public" for API).
        """
        try:
            r = await self._get_redis()
            data = await r.get(f"{prefix}:{user_id}:history")
            return json.loads(data) if data else []
        except Exception as e:
            logger.warning("Redis get error: %s", e)
            return []

    async def save_chat_history(
        self,
        user_id: str,
        prefix: str,
        history: list[dict[str, str]],
    ) -> None:
        """Save chat history to Redis with TTL."""
        try:
            r = await self._get_redis()
            trimmed = history[-(MAX_HISTORY * 2) :]
            await r.set(
                f"{prefix}:{user_id}:history",
                json.dumps(trimmed, ensure_ascii=False),
                ex=HISTORY_TTL,
            )
        except Exception as e:
            logger.warning("Redis save error: %s", e)

    async def clear_chat_history(self, user_id: str, prefix: str) -> None:
        """Delete chat history from Redis."""
        try:
            r = await self._get_redis()
            await r.delete(f"{prefix}:{user_id}:history")
        except Exception as e:
            logger.warning("Redis delete error: %s", e)

    async def is_order_already_sent(self, user_id: str) -> bool:
        """Check dedup flag (1 hour TTL)."""
        try:
            r = await self._get_redis()
            return bool(await r.exists(f"order_sent:{user_id}"))
        except Exception as e:
            logger.warning("Redis order check error: %s", e)
            return False

    async def mark_order_sent(self, user_id: str) -> None:
        """Set dedup flag after order sent."""
        try:
            r = await self._get_redis()
            await r.set(f"order_sent:{user_id}", "1", ex=ORDER_DEDUP_TTL)
        except Exception as e:
            logger.warning("Redis order mark error: %s", e)

    # =========================================================================
    # CRM
    # =========================================================================

    async def get_customer_context(
        self,
        telegram_id: int,
        first_name: str | None = None,
        username: str | None = None,
    ) -> str | None:
        """Load CRM profile and format for AI context.

        Auto-creates customer if not exists. Returns None for new customers.
        """
        try:
            async with get_session_context() as session:
                service = CRMService(session)
                customer, created = await service.get_or_create(
                    telegram_id=telegram_id,
                    first_name=first_name,
                    username=username,
                )
                if created:
                    logger.info("Created new CRM customer: %s", telegram_id)
                    return None

                context = service.format_context_for_prompt(customer)
                if context and context != f"Клиент: {first_name or 'Клиент'}":
                    logger.info("CRM context for %s: %s...", telegram_id, context[:100])
                    return context
                return None
        except Exception as e:
            logger.warning("CRM context error: %s", e)
            return None

    async def update_customer_purchase(
        self,
        telegram_id: int,
        product: str,
    ) -> None:
        """Add purchased product to CRM profile."""
        try:
            async with get_session_context() as session:
                service = CRMService(session)
                await service.add_purchase(telegram_id, product)
        except Exception as e:
            logger.warning("CRM purchase update error: %s", e)

    # =========================================================================
    # RAG Pipeline
    # =========================================================================

    async def get_ai_response(
        self,
        user_id: str,
        message: str,
        history_prefix: str,
        first_name: str | None = None,
        username: str | None = None,
    ) -> str:
        """Full RAG pipeline: history → CRM → enrichment → search → generate → extraction → save.

        Args:
            user_id: User identifier (telegram_id as string).
            message: User's message text.
            history_prefix: Redis namespace ("chat" or "public").
            first_name: User's first name for CRM.
            username: User's @username for CRM.

        Returns:
            AI-generated response text.
        """
        # 1. Load history + append user message
        history = await self.get_chat_history(user_id, history_prefix)
        history.append({"role": "user", "content": message})

        # 2. CRM context
        customer_context: str | None = None
        telegram_id: int | None = None
        with contextlib.suppress(ValueError):
            telegram_id = int(user_id)
        if telegram_id:
            customer_context = await self.get_customer_context(
                telegram_id,
                first_name,
                username,
            )

        # 3. RAG query with enrichment
        answer = await self._process_rag_query(
            message,
            history,
            customer_context,
            telegram_id,
        )

        # 4. Save history
        history.append({"role": "assistant", "content": answer})
        await self.save_chat_history(user_id, history_prefix, history)

        # 5. Fire extraction agent (async, no latency impact)
        if telegram_id:
            try:
                agent = self._get_extraction_agent()
                _task = asyncio.create_task(  # noqa: RUF006
                    agent.process_and_save(telegram_id, message, answer)
                )
            except Exception as e:
                logger.warning("Extraction agent fire error: %s", e)

        return answer

    async def process_pure(
        self,
        message: str,
        chat_history: list[dict[str, str]],
        customer_context: str | None = None,
        telegram_id: int | None = None,
    ) -> str:
        """Pure RAG pipeline for evaluation harness.

        Same logic as the path inside ``get_ai_response`` but without side
        effects: does NOT load/save Redis history, does NOT fire the
        ExtractionAgent, does NOT run order detection. Caller passes
        ``chat_history`` explicitly.

        Used by ``tests/eval/`` and ``scripts/run_eval.py`` to measure
        retrieval/answer quality without polluting production state.
        """
        return await self._process_rag_query(
            message,
            chat_history,
            customer_context,
            telegram_id,
        )

    async def _process_rag_query(
        self,
        message: str,
        chat_history: list[dict[str, str]],
        customer_context: str | None = None,
        telegram_id: int | None = None,
    ) -> str:
        """Internal: enrichment → vector search → LLM generate."""
        try:
            embedding_service = get_embedding_service()
            qdrant_service = get_qdrant_service()
            llm_service = get_llm_service()
            config = askbiotact_config

            # Query enrichment: DB insights first, then regex fallback
            enriched_message = message
            insight: dict[str, Any] | None = None

            if telegram_id:
                insight = await get_active_insight(telegram_id)
                if insight and insight.get("products") and is_short_query(message):
                    product_prefix = " ".join(insight["products"])
                    enriched_message = f"{product_prefix} {message}"
                    logger.info("DB-enriched query: %s...", enriched_message[:80])

            # Regex fallback if DB didn't help
            if enriched_message == message:
                enriched_message = enrich_query(message, chat_history)

            # Vector search
            query_vector = await embedding_service.embed_text(enriched_message)
            search_results = await qdrant_service.search(
                query_vector=query_vector,
                department_id=config.department_filter or "",
                limit=config.rag_limit,
                score_threshold=config.score_threshold,
            )
            logger.info(
                "RAG search: query='%s...', results=%d",
                enriched_message[:50],
                len(search_results),
            )

            # Build system prompt with CRM + safety constraints
            system_prompt = config.system_prompt

            if customer_context:
                system_prompt = (
                    f"{system_prompt}\n\n"
                    f"--- ИНФОРМАЦИЯ О КЛИЕНТЕ ---\n{customer_context}\n---\n"
                    "Используй информацию о клиенте для персонализированных рекомендаций."
                )

            constraints = (insight.get("constraints") or []) if insight else []
            if constraints:
                constraints_text = "; ".join(constraints)
                system_prompt = (
                    f"{system_prompt}\n\n"
                    f"\u26d4 КРИТИЧЕСКИЕ ОГРАНИЧЕНИЯ КЛИЕНТА: {constraints_text}\n"
                    "НИКОГДА не рекомендуй продукты, несовместимые с этими ограничениями."
                )
                logger.info("Constraints injected for %s: %s", telegram_id, constraints)

            # Generate response
            answer = await llm_service.generate_response(
                question=message,
                context=search_results,
                chat_history=chat_history,
                system_prompt=system_prompt,
                user_message_template=USER_TEMPLATE,
            )

            # Phase 0.6 — code-level safety guard. Insurance over the
            # prompt-level rules: if the user message hits a safety trigger
            # (pregnancy / child<3 / cardiac / chronic), strip product names
            # and ensure a doctor redirect is present.
            trigger = detect_safety_trigger(message)
            if trigger is not None:
                answer = apply_safety_filter(answer, message, trigger)
                logger.info(
                    "Safety filter applied: trigger=%s telegram_id=%s",
                    trigger,
                    telegram_id,
                )

            return answer
        except Exception as e:
            logger.exception("RAG query error: %s", e)
            return "Извините, произошла ошибка. Попробуйте позже."

    # =========================================================================
    # Order Processing
    # =========================================================================

    def detect_order(
        self,
        message: str,
        history: list[dict[str, str]],
    ) -> dict[str, str] | None:
        """Detect if message contains order data (phone + order keywords).

        Returns dict with raw_text and phone, or None.
        """
        phone = extract_phone(message)
        if not phone:
            return None

        recent_texts = " ".join(m["content"].lower() for m in history[-4:])
        if any(kw in recent_texts for kw in ORDER_KEYWORDS):
            return {"raw_text": message, "phone": phone}
        return None

    async def parse_order(
        self,
        raw_text: str,
        chat_history: list[dict[str, str]],
    ) -> ParsedOrder | None:
        """Parse order details from raw text using GPT-4o-mini.

        Returns structured ParsedOrder or None on failure.
        """
        client = self._get_openai_client()
        product_list = "\n".join(f"- {name}" for name in PRODUCT_PRICES)

        history_context = ""
        if chat_history:
            lines = []
            for msg in chat_history[-6:]:
                role = "Клиент" if msg["role"] == "user" else "Бот"
                lines.append(f"{role}: {msg['content']}")
            history_context = "\n".join(lines)

        system_prompt = (
            "Ты парсер заказов Biotact. Извлеки из текста заказа структурированные данные.\n\n"
            f"Список валидных продуктов:\n{product_list}\n\n"
            "Правила:\n"
            "- Название продукта должно ТОЧНО совпадать с одним из списка выше\n"
            "- Если пользователь написал название неточно (напр. 'биолак актив'), "
            "сопоставь с ближайшим из списка\n"
            "- Если количество не указано, считай qty = 1\n"
            "- Телефон нормализуй в формат +998XXXXXXXXX\n"
            "- Если какое-то поле не найдено, верни null для него\n\n"
            "Верни ТОЛЬКО валидный JSON без markdown:\n"
            '{"name": "Имя клиента или null", "phone": "телефон или null", '
            '"address": "адрес или null", "products": [{"name": "ТОЧНОЕ НАЗВАНИЕ", "qty": 1}]}'
        )

        user_content = raw_text
        if history_context:
            user_content = (
                f"История переписки:\n{history_context}\n\n"
                f"Текущее сообщение с заказом:\n{raw_text}"
            )

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0,
                max_tokens=500,
            )
            raw_content = response.choices[0].message.content
            if not raw_content:
                return None

            parsed = json.loads(raw_content.strip())

            # Validate products against catalog
            valid_products = []
            for p in parsed.get("products") or []:
                if p.get("name") in PRODUCT_PRICES:
                    valid_products.append(
                        OrderProduct(name=p["name"], qty=max(1, int(p.get("qty", 1))))
                    )

            return ParsedOrder(
                name=parsed.get("name"),
                phone=parsed.get("phone"),
                address=parsed.get("address"),
                products=valid_products,
                raw_text=raw_text,
            )
        except Exception as e:
            logger.warning("Order parsing failed: %s", e)
            return None

    def format_order_for_sales(
        self,
        order: ParsedOrder,
        user_info: UserInfo,
        phone: str,
    ) -> str:
        """Format parsed order as a message for the sales Telegram group."""
        lines = ["\U0001f916 AskBiotact: Новая заявка!\n"]

        total = 0
        if order.products:
            for p in order.products:
                price = PRODUCT_PRICES.get(p.name, 0)
                subtotal = price * p.qty
                total += subtotal
                if p.qty > 1:
                    lines.append(
                        f"\U0001f4e6 {p.name} — {p.qty} шт. ({subtotal:,} сум)".replace(
                            ",", " "
                        )
                    )
                else:
                    lines.append(
                        f"\U0001f4e6 {p.name} — 1 шт. ({price:,} сум)".replace(",", " ")
                    )
            lines.append(f"\U0001f4b0 Итого: {total:,} сум".replace(",", " "))

        phone_display = order.phone or phone
        lines.append("")
        if order.name:
            lines.append(f"\U0001f464 {order.name}")
        lines.append(f"\U0001f4de {phone_display}")
        if order.address:
            lines.append(f"\U0001f4cd {order.address}")

        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
        lines.append(
            f"\n\U0001f464 TG: @{user_info.username} (ID: {user_info.user_id})"
        )
        if user_info.first_name:
            lines.append(f"\U0001f44b {user_info.first_name}")
        lines.append(f"\u23f0 {timestamp}")

        return "\n".join(lines)

    async def send_order_to_sales(
        self,
        order_data: dict[str, str],
        user_info: UserInfo,
        history: list[dict[str, str]],
    ) -> bool:
        """Parse order with LLM and send to sales group.

        Full flow: detect_order → parse_order → format → send → CRM update.
        """
        if not self._notification_bot_token or not self._sales_group_chat_id:
            logger.error("Notification bot not configured")
            return False

        phone = order_data.get("phone", "не указан")
        parsed = await self.parse_order(order_data.get("raw_text", ""), history)

        if parsed and parsed.products:
            message = self.format_order_for_sales(parsed, user_info, phone)
            logger.info("Order parsed: %d products", len(parsed.products))
        else:
            # Fallback: raw text
            logger.warning(
                "Order parsing failed, using raw text for %s", user_info.user_id
            )
            products = set()
            base_names = [
                "BIFOLAK",
                "IMMUNOCOMPLEX",
                "NEUROCOMPLEX",
                "DERMACOMPLEX",
                "OPHTALMOCOMPLEX",
                "CALCIY",
            ]
            for msg in history:
                msg_upper = msg.get("content", "").upper()
                for name in base_names:
                    if name in msg_upper:
                        products.add(name)

            prods = ", ".join(products) if products else "не определены"
            timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
            message = (
                f"\U0001f916 AskBiotact: Новая заявка!\n\n"
                f"\U0001f464 User ID: {user_info.user_id}\n"
                f"\U0001f4de Телефон: {phone}\n\n"
                f"\U0001f4dd Данные заказа:\n{order_data.get('raw_text', '')}\n\n"
                f"\U0001f4e6 Продукты: {prods}\n"
                f"\u23f0 Время: {timestamp}"
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{self._notification_bot_token}/sendMessage",
                    json={"chat_id": self._sales_group_chat_id, "text": message},
                    timeout=10.0,
                )
                if response.status_code == 200:
                    logger.info("Order sent to sales: %s", user_info.user_id)
                    # Update CRM
                    if parsed and parsed.products:
                        with contextlib.suppress(ValueError):
                            tid = int(user_info.user_id)
                            for p in parsed.products:
                                await self.update_customer_purchase(tid, p.name)
                    return True
                logger.error("Failed to send order: %s", response.text)
                return False
        except Exception as e:
            logger.error("Send order error: %s", e)
            return False

    # =========================================================================
    # Conversation Management
    # =========================================================================

    async def reset_conversation(self, user_id: str, prefix: str) -> None:
        """Clear history and archive insights."""
        with contextlib.suppress(ValueError, Exception):
            telegram_id = int(user_id)
            await archive_insight(telegram_id)
        await self.clear_chat_history(user_id, prefix)

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _get_extraction_agent(self) -> ExtractionAgent:
        if self._extraction_agent is None:
            self._extraction_agent = ExtractionAgent()
        return self._extraction_agent

    def _get_openai_client(self) -> AsyncOpenAI:
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(api_key=self._openai_api_key)
        return self._openai_client


@lru_cache(maxsize=1)
def get_askbiotact_service() -> AskBiotactService:
    """Get singleton AskBiotactService instance."""
    return AskBiotactService()
