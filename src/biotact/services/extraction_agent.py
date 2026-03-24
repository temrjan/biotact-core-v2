"""Extraction Agent — async entity extraction from conversations.

Uses GPT-4o-mini to extract structured entities (products, symptoms, family,
intent, summary) from each message exchange. Runs AFTER response is sent
to the user (no latency impact).

Updates conversation_insights table for:
- Query enrichment (next message gets better RAG context)
- CRM auto-population (symptoms, family, products)
- Analytics (intent tracking, conversation summaries)
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import get_settings
from biotact.core.database import get_session_context

logger = logging.getLogger(__name__)

# Valid product names — agent can ONLY record these
VALID_PRODUCTS = {
    "BIFOLAK ACTIVE",
    "BIFOLAK NEO",
    "BIFOLAK ZINCUM",
    "BIFOLAK ZINCUM+C+D3",
    "BIFOLAK MAGNIY",
    "IMMUNOCOMPLEX",
    "IMMUNOCOMPLEX KIDS",
    "NEUROCOMPLEX",
    "NEUROCOMPLEX KIDS",
    "DERMACOMPLEX",
    "OPHTALMOCOMPLEX",
    "CALCIY TRIACTIVE",
    # Tech
    "Аэрогриль BIOTACT",
    "Блендер BIOTACT",
    "Соковыжималка BIOTACT",
    "Пароварка BIOTACT",
    "Тостер BIOTACT",
    "Чайник BIOTACT",
    "Мясорубка BIOTACT",
}

EXTRACTION_PROMPT = """Ты аналитик диалогов BIOTACT. Извлеки сущности из нового обмена.

Текущий контекст: {current_summary}

Новый обмен:
Клиент: {user_message}
Консультант: {assistant_message}

Верни ТОЛЬКО валидный JSON (без markdown, без ```):
{{
  "products": [],
  "symptoms": [],
  "constraints": [],
  "family": [],
  "client_age": null,
  "intent": null,
  "phone": null,
  "summary": ""
}}

Поля:
- products: названия продуктов ТОЛЬКО из списка: {product_list}
- symptoms: симптомы/жалобы клиента (краткие фразы на русском)
- constraints: КРИТИЧЕСКИЕ ограничения клиента — аллергии, непереносимости, противопоказания.
  Примеры: "аллергия на цинк", "беременность", "диабет 2 типа", "лактация", "непереносимость лактозы".
  Извлекать ТОЛЬКО если клиент явно упомянул. Фразы краткие, на русском.
- family: члены семьи [{{"relation": "сын/дочь/муж/жена", "age": число_или_null}}]
- client_age: возраст самого клиента (число или null)
- intent: один из: consultation, order, price_check, info, complaint
- phone: номер телефона если клиент оставил (или null)
- summary: обновлённое краткое описание всей ситуации (1-2 предложения)

Правила:
- Продукты СТРОГО из списка. Если бот назвал несуществующий продукт — игнорируй.
- Если для поля нет новых данных — оставь пустым ([] для массивов, null для скаляров).
- constraints НИКОГДА не очищать — они накапливаются на протяжении всего диалога.
- summary: ОБНОВИ текущий контекст с учётом нового обмена. Если контекст "Новый диалог" — создай с нуля.
- Пиши summary на русском."""


class ExtractionAgent:
    """Async extraction agent using GPT-4o-mini."""

    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o-mini"

    async def extract(
        self,
        user_message: str,
        assistant_message: str,
        current_summary: str | None = None,
    ) -> dict[str, Any] | None:
        """Extract entities from a message pair.

        Args:
            user_message: User's message.
            assistant_message: Bot's response.
            current_summary: Current semantic summary (or None for new dialog).

        Returns:
            Dict with extracted entities, or None on failure.
        """
        prompt = EXTRACTION_PROMPT.format(
            current_summary=current_summary or "Новый диалог",
            user_message=user_message,
            assistant_message=assistant_message,
            product_list=", ".join(sorted(VALID_PRODUCTS)),
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0,
            )

            raw = response.choices[0].message.content or ""
            # Strip markdown code blocks if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

            data = json.loads(raw)

            # Validate products against whitelist
            if "products" in data:
                data["products"] = [
                    p
                    for p in data["products"]
                    if any(p.upper().startswith(v.upper()) for v in VALID_PRODUCTS)
                ]

            return data  # type: ignore[no-any-return]

        except json.JSONDecodeError as e:
            logger.warning(f"Extraction JSON parse error: {e}, raw: {raw[:200]}")
            return None
        except Exception as e:
            logger.error(f"Extraction agent error: {e}")
            return None

    async def process_and_save(
        self,
        telegram_id: int,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Extract entities and save to conversation_insights.

        This is the main entry point — called via asyncio.create_task()
        after the response is sent to the user.
        """
        try:
            async with get_session_context() as session:
                # Get current active insight (if exists)
                current = await self._get_active_insight(session, telegram_id)
                current_summary = current["semantic_summary"] if current else None

                # Extract entities
                data = await self.extract(
                    user_message, assistant_message, current_summary
                )
                if not data:
                    logger.warning(f"Extraction returned None for {telegram_id}")
                    return

                # Merge with existing data
                await self._upsert_insight(session, telegram_id, data, current)

                logger.info(
                    f"Extraction OK for {telegram_id}: "
                    f"products={data.get('products', [])}, "
                    f"intent={data.get('intent')}, "
                    f"summary={data.get('summary', '')[:60]}..."
                )

        except Exception as e:
            logger.error(f"Extraction process_and_save error: {e}")

    async def _get_active_insight(
        self,
        session: AsyncSession,
        telegram_id: int,
    ) -> dict[str, Any] | None:
        """Get active conversation insight for a user."""
        result = await session.execute(
            select(_conversation_insights).where(
                _conversation_insights.c.telegram_id == telegram_id,
                _conversation_insights.c.is_active == True,  # noqa: E712
            )
        )
        row = result.first()
        if row:
            return dict(row._mapping)
        return None

    async def _upsert_insight(
        self,
        session: AsyncSession,
        telegram_id: int,
        data: dict[str, Any],
        current: dict[str, Any] | None,
    ) -> None:
        """Insert or update conversation insight."""
        now = datetime.now(UTC)

        if current:
            # Merge arrays (deduplicate)
            new_products = data.get("products") or []
            products = new_products if new_products else (current.get("products") or [])
            symptoms = list(
                set((current.get("symptoms") or []) + (data.get("symptoms") or []))
            )
            # constraints accumulate — never overwrite with empty
            constraints = list(
                set(
                    (current.get("constraints") or []) + (data.get("constraints") or [])
                )
            )

            # Merge family (by relation)
            existing_family = current.get("family_members") or []
            new_family = data.get("family") or []
            family = self._merge_family(existing_family, new_family)

            # Update
            await session.execute(
                update(_conversation_insights)
                .where(
                    _conversation_insights.c.id == current["id"],
                )
                .values(
                    products=products,
                    symptoms=symptoms,
                    constraints=constraints,
                    family_members=family,
                    client_age=data.get("client_age") or current.get("client_age"),
                    intent=data.get("intent") or current.get("intent"),
                    phone=data.get("phone") or current.get("phone"),
                    semantic_summary=data.get("summary")
                    or current.get("semantic_summary"),
                    message_count=(current.get("message_count") or 0) + 1,
                    updated_at=now,
                )
            )
        else:
            # Insert new
            await session.execute(
                _conversation_insights.insert().values(
                    telegram_id=telegram_id,
                    products=data.get("products") or [],
                    symptoms=data.get("symptoms") or [],
                    constraints=data.get("constraints") or [],
                    family_members=data.get("family") or [],
                    client_age=data.get("client_age"),
                    intent=data.get("intent"),
                    phone=data.get("phone"),
                    semantic_summary=data.get("summary"),
                    message_count=1,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )

    def _merge_family(
        self,
        existing: list[dict[str, Any]],
        new: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge family members by relation."""
        by_relation = {}
        for member in existing:
            rel = member.get("relation", "").lower()
            if rel:
                by_relation[rel] = member
        for member in new:
            rel = member.get("relation", "").lower()
            if rel:
                # New data overwrites (might have age now)
                merged = by_relation.get(rel, {})
                merged.update({k: v for k, v in member.items() if v is not None})
                by_relation[rel] = merged
        return list(by_relation.values())


# ---------------------------------------------------------------------------
# SQLAlchemy table/column helpers (raw SQL approach, no ORM model needed)
# ---------------------------------------------------------------------------
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

_metadata = MetaData()
_conversation_insights = Table(
    "conversation_insights",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("telegram_id", BigInteger, nullable=False),
    Column(
        "products", JSON().with_variant(ARRAY(String), "postgresql"), nullable=False
    ),
    Column(
        "symptoms", JSON().with_variant(ARRAY(String), "postgresql"), nullable=False
    ),
    Column(
        "constraints", JSON().with_variant(ARRAY(String), "postgresql"), nullable=False
    ),
    Column("family_members", JSON().with_variant(JSONB, "postgresql"), nullable=False),
    Column("client_age", Integer),
    Column("intent", String(30)),
    Column("phone", String(20)),
    Column("semantic_summary", Text),
    Column("message_count", Integer, nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


def sa_table(name: str) -> Table:
    """Get SQLAlchemy table reference."""
    return _conversation_insights


def sa_col(name: str) -> Column[Any]:
    """Get column from conversation_insights table."""
    return _conversation_insights.c[name]


# ---------------------------------------------------------------------------
# Helper: read active insight (for use in enrichment, outside agent)
# ---------------------------------------------------------------------------
async def get_active_insight(telegram_id: int) -> dict[str, Any] | None:
    """Read active conversation insight for enrichment.

    Returns dict with products, symptoms, semantic_summary etc. or None.
    Called synchronously in the request pipeline (fast DB read).
    """
    try:
        async with get_session_context() as session:
            result = await session.execute(
                select(_conversation_insights).where(
                    _conversation_insights.c.telegram_id == telegram_id,
                    _conversation_insights.c.is_active == True,  # noqa: E712
                )
            )
            row = result.first()
            if row:
                return dict(row._mapping)
            return None
    except Exception as e:
        logger.warning(f"get_active_insight error: {e}")
        return None


async def archive_insight(telegram_id: int) -> None:
    """Archive active insight (called on history reset)."""
    try:
        async with get_session_context() as session:
            await session.execute(
                update(_conversation_insights)
                .where(
                    _conversation_insights.c.telegram_id == telegram_id,
                    _conversation_insights.c.is_active == True,  # noqa: E712
                )
                .values(is_active=False, updated_at=datetime.now(UTC))
            )
    except Exception as e:
        logger.warning(f"archive_insight error: {e}")
