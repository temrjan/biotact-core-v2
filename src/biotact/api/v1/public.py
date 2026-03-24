"""Public API endpoints for external bot integration."""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from openai import AsyncOpenAI

from biotact.core.config import get_settings
from biotact.core.database import get_session_context
from biotact.core.dependencies import (
    get_embedding_service,
    get_llm_service,
    get_qdrant_service,
)
from biotact.modules.askbiotact.config import askbiotact_config
from biotact.modules.crm.service import CRMService
from biotact.services.extraction_agent import ExtractionAgent, get_active_insight, archive_insight

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public"])

# Settings
settings = get_settings()
REDIS_HOST = settings.redis_host

# Extraction Agent (async, GPT-4o-mini)
_extraction_agent: ExtractionAgent | None = None

def get_extraction_agent() -> ExtractionAgent:
    global _extraction_agent
    if _extraction_agent is None:
        _extraction_agent = ExtractionAgent()
    return _extraction_agent
REDIS_PORT = settings.redis_port
MAX_HISTORY = 10
HISTORY_TTL = 86400

# Notification settings
NOTIFICATION_BOT_TOKEN = os.getenv("NOTIFICATION_BOT_TOKEN")
SALES_GROUP_CHAT_ID = os.getenv("SALES_GROUP_CHAT_ID")

# Phone patterns
PHONE_PATTERNS = [
    r"\+?998[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}",
    r"998\d{9}",
]

# Product names for context extraction
PRODUCT_NAMES = [
    "BIFOLAK ACTIVE", "BIFOLAK NEO", "BIFOLAK MAGNIY", "BIFOLAK ZINCUM", "BIFOLAK",
    "IMMUNOCOMPLEX KIDS", "IMMUNOCOMPLEX",
    "NEUROCOMPLEX KIDS", "NEUROCOMPLEX",
    "DERMACOMPLEX", "OPHTALMOCOMPLEX",
    "CALCIY TRIACTIVE", "CALCIY",
]

# Product prices in UZS (synced with webhooks.py)
PRODUCT_PRICES: dict[str, int] = {
    "BIFOLAK NEO": 61_000,
    "BIFOLAK ACTIVE": 69_000,
    "BIFOLAK ZINCUM": 69_000,
    "BIFOLAK MAGNIY": 76_000,
    "BIFOLAK ZINCUM+C+D3": 76_000,
    "CALCIY TRIACTIVE D3": 76_000,
    "IMMUNOCOMPLEX": 76_000,
    "IMMUNOCOMPLEX KIDS": 76_000,
    "DERMACOMPLEX": 94_000,
    "NEUROCOMPLEX KIDS": 101_000,
    "OPHTALMOCOMPLEX": 123_000,
    "Аэрогриль BIOTACT": 850_000,
    "Соковыжималка BIOTACT": 820_000,
    "Ручной блендер BIOTACT": 320_000,
    "Электрический блендер BIOTACT": 320_000,
    "Тостер BIOTACT": 255_000,
    "Кухонный комбайн BIOTACT": 230_000,
    "Электрический чайник BIOTACT": 160_000,
}

# Semantic core for price queries (RU + UZ)
PRICE_TRIGGERS = [
    # Russian
    "цена", "стоимость", "сколько стоит", "почем", "прайс", "стоит",
    "дорого", "дешево", "купить", "заказать", "оплата",
    # Uzbek
    "narx", "qancha", "qimmat", "arzon", "sotib olish", "buyurtma",
    "tolov", "pul", "som", "sum",
]

PRICE_ENRICHMENT = "цены на продукты BIOTACT прайс-лист стоимость narxlar BIOTACT mahsulotlari"

# AskBiotact: clean user message template (data only, no instructions)
# All instructions are in the system prompt (askbiotact.txt)
ASKBIOTACT_USER_TEMPLATE = """Данные из базы знаний:
{context}

Сообщение клиента: {question}"""


# =============================================================================
# Schemas
# =============================================================================


class AskRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=4000)
    first_name: str | None = Field(None, max_length=100, description="User's first name from Telegram")
    username: str | None = Field(None, max_length=100, description="User's @username from Telegram")


class AskResponse(BaseModel):
    answer: str
    user_id: str
    order_sent: bool = False


# =============================================================================
# Redis helpers
# =============================================================================

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    return _redis


async def get_chat_history(user_id: str) -> list[dict[str, str]]:
    try:
        r = await get_redis()
        data = await r.get(f"public:{user_id}:history")
        return json.loads(data) if data else []
    except Exception as e:
        logger.warning(f"Redis get error: {e}")
        return []


async def save_chat_history(user_id: str, history: list[dict[str, str]]) -> None:
    try:
        r = await get_redis()
        trimmed = history[-(MAX_HISTORY * 2):]
        await r.set(f"public:{user_id}:history", json.dumps(trimmed, ensure_ascii=False), ex=HISTORY_TTL)
    except Exception as e:
        logger.warning(f"Redis save error: {e}")


async def is_order_already_sent(user_id: str) -> bool:
    """Check if an order was already sent for this user in the last hour."""
    try:
        r = await get_redis()
        return bool(await r.exists(f"public:{user_id}:order_sent"))
    except Exception as e:
        logger.warning(f"Redis order check error: {e}")
        return False


async def mark_order_sent(user_id: str) -> None:
    """Mark that an order was sent. TTL: 1 hour to prevent duplicates."""
    try:
        r = await get_redis()
        await r.set(f"public:{user_id}:order_sent", "1", ex=3600)
    except Exception as e:
        logger.warning(f"Redis order mark error: {e}")


# =============================================================================
# CRM Integration
# =============================================================================


async def get_customer_context(
    telegram_id: int,
    first_name: str | None = None,
    username: str | None = None,
) -> str | None:
    """Load customer profile and format for AI context.
    
    Creates new customer record if not exists.
    Returns formatted context string or None.
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
                logger.info(f"Created new CRM customer: {telegram_id}")
                return None  # New customer, no context yet
            
            # Format context for prompt
            context = service.format_context_for_prompt(customer)
            if context and context != f"Клиент: {first_name or 'Клиент'}":
                logger.info(f"CRM context for {telegram_id}: {context[:100]}...")
                return context
            
            return None
    except Exception as e:
        logger.warning(f"CRM context error: {e}")
        return None


async def update_customer_purchase(telegram_id: int, product: str) -> None:
    """Add purchased product to customer profile."""
    try:
        async with get_session_context() as session:
            service = CRMService(session)
            await service.add_purchase(telegram_id, product)
    except Exception as e:
        logger.warning(f"CRM purchase update error: {e}")


# =============================================================================
# Query Enrichment (Context-Aware Search)
# =============================================================================


def extract_products_from_history(history: list[dict[str, str]]) -> list[str]:
    """Extract product names mentioned in chat history."""
    found_products = []
    text = " ".join([m.get("content", "") for m in history[-6:]])
    text_upper = text.upper()
    
    for product in PRODUCT_NAMES:
        if product.upper() in text_upper:
            found_products.append(product)
    
    return found_products


def is_short_query(message: str) -> bool:
    """Check if query is short/incomplete and needs context."""
    # Short queries or questions about properties
    short_patterns = [
        r"^.{1,30}$",  # Less than 30 chars
        r"(?:какой|что|как|сколько|состав|цена|дозировка|применение|курс)",
    ]
    message_lower = message.lower()
    return any(re.search(p, message_lower) for p in short_patterns)


def enrich_query_with_context(message: str, history: list[dict[str, str]]) -> str:
    """Enrich queries with context for better RAG search.
    
    1. Short/ambiguous queries: prepend last user messages from history
    2. Price queries: add price semantic core for matching prices.txt
    """
    message_lower = message.lower()
    enriched = message
    
    # STEP 1: For short queries, enrich with product names from history (both roles)
    # "да, сколько стоит" -> "BIFOLAK NEO да, сколько стоит"
    if is_short_query(message) and history:
        # Priority: product names from both user AND assistant messages
        products = extract_products_from_history(history)
        if products:
            product_prefix = " ".join(products)
            enriched = f"{product_prefix} {message}"
            logger.info(f"Product-enriched query: {enriched[:80]}...")
        else:
            # Fallback: prepend last user messages (original behavior)
            recent_user_msgs = [
                m["content"] for m in history[-6:]
                if m.get("role") == "user"
            ][-2:]
            if recent_user_msgs:
                context_prefix = " ".join(recent_user_msgs)
                enriched = f"{context_prefix} {message}"
                logger.info(f"History-enriched query: {enriched[:80]}...")
    
    # STEP 2: Price queries - add semantic core for prices.txt matching
    is_price_query = any(trigger in message_lower for trigger in PRICE_TRIGGERS)
    if is_price_query:
        enriched = f"{enriched} {PRICE_ENRICHMENT}"
        logger.info(f"Price query enriched: {message[:50]}...")
    
    return enriched


# =============================================================================
# Order Detection & Sending
# =============================================================================


def extract_phone(text: str) -> str | None:
    for pattern in PHONE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group().replace(" ", "").replace("-", "")
    return None


def detect_order(text: str, history: list[dict[str, str]]) -> dict[str, Any] | None:
    """Detect if message contains order data."""
    phone = extract_phone(text)
    if not phone:
        return None
    
    # Check if recent conversation was about ordering
    recent_texts = " ".join([m["content"].lower() for m in history[-4:]])
    order_keywords = ["заказ", "купить", "оформ", "доставк", "адрес", "телефон", "имя"]
    
    if any(kw in recent_texts for kw in order_keywords):
        return {"raw_text": text, "phone": phone}
    
    return None


async def parse_order_with_llm(
    raw_text: str,
    chat_history: list[dict[str, str]],
) -> dict[str, Any] | None:
    """Parse order details from raw text using GPT-4o-mini."""
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    product_list = "\n".join(f"- {name}" for name in PRODUCT_PRICES)

    history_context = ""
    if chat_history:
        last_messages = chat_history[-6:]
        lines = []
        for msg in last_messages:
            role = "Клиент" if msg["role"] == "user" else "Бот"
            lines.append(f"{role}: {msg['content']}")
        history_context = "\n".join(lines)

    system_prompt = (
        "Ты парсер заказов Biotact. Извлеки из текста заказа структурированные данные.\n\n"
        f"Список валидных продуктов:\n{product_list}\n\n"
        "Правила:\n"
        "- Название продукта должно ТОЧНО совпадать с одним из списка выше\n"
        "- Если пользователь написал название неточно (напр. 'биолак актив'), сопоставь с ближайшим из списка\n"
        "- Если количество не указано, считай qty = 1\n"
        "- Телефон нормализуй в формат +998XXXXXXXXX\n"
        "- Если какое-то поле не найдено, верни null для него\n\n"
        "Верни ТОЛЬКО валидный JSON без markdown:\n"
        '{"name": "Имя клиента или null", "phone": "телефон или null", '
        '"address": "адрес или null", "products": [{"name": "ТОЧНОЕ НАЗВАНИЕ", "qty": 1}]}'
    )

    user_content = raw_text
    if history_context:
        user_content = f"История переписки:\n{history_context}\n\nТекущее сообщение с заказом:\n{raw_text}"

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
        if raw_content is None:
            return None
        resp_content = raw_content.strip()
        parsed = json.loads(resp_content)

        if parsed.get("products"):
            valid_products = []
            for p in parsed["products"]:
                if p.get("name") in PRODUCT_PRICES:
                    valid_products.append({
                        "name": p["name"],
                        "qty": max(1, int(p.get("qty", 1))),
                    })
            parsed["products"] = valid_products

        return parsed  # type: ignore[no-any-return]
    except Exception as e:
        logger.warning(f"Order parsing failed: {e}")
        return None


def format_order_for_sales(
    parsed: dict[str, Any],
    user_info: dict[str, Any],
    phone: str,
) -> str:
    """Format parsed order as a message for the sales group."""
    lines = ["🤖 AskBiotact (через BiotactBot): Новая заявка!\n"]

    total = 0
    products = parsed.get("products", [])
    if products:
        for p in products:
            name = p["name"]
            qty = p["qty"]
            price = PRODUCT_PRICES.get(name, 0)
            subtotal = price * qty
            total += subtotal
            if qty > 1:
                lines.append(f"📦 {name} — {qty} шт. ({subtotal:,} сум)".replace(",", " "))
            else:
                lines.append(f"📦 {name} — 1 шт. ({price:,} сум)".replace(",", " "))
        lines.append(f"💰 Итого: {total:,} сум".replace(",", " "))

    name = parsed.get("name")
    address = parsed.get("address")
    phone_display = parsed.get("phone") or phone

    lines.append("")
    if name:
        lines.append(f"👤 {name}")
    lines.append(f"📞 {phone_display}")
    if address:
        lines.append(f"📍 {address}")

    user_id = user_info.get("user_id", "")
    first_name = user_info.get("first_name", "")
    username = user_info.get("username", "нет")
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

    lines.append(f"\n👤 TG: @{username} (ID: {user_id})")
    if first_name:
        lines.append(f"👋 {first_name}")
    lines.append(f"⏰ {timestamp}")

    return "\n".join(lines)


async def send_order_to_sales(
    order_data: dict[str, Any],
    user_id: str,
    history: list[dict[str, str]],
    first_name: str | None = None,
    username: str | None = None,
) -> bool:
    """Send structured order to sales group.

    Parses order with LLM for structured format with prices.
    Falls back to raw text if parsing fails.
    """
    if not NOTIFICATION_BOT_TOKEN or not SALES_GROUP_CHAT_ID:
        logger.error("Notification bot not configured")
        return False

    user_info = {
        "user_id": user_id,
        "first_name": first_name or "",
        "username": username or "нет",
    }
    phone = order_data.get("phone", "не указан")

    # Try structured parsing with LLM
    parsed = await parse_order_with_llm(order_data.get("raw_text", ""), history)

    if parsed and parsed.get("products"):
        message = format_order_for_sales(parsed, user_info, phone)
        logger.info(f"Order parsed: {len(parsed['products'])} products")
    else:
        # Fallback: raw text format
        logger.warning(f"Order parsing failed, using raw text for {user_id}")
        products = set()
        product_names = ["BIFOLAK", "IMMUNOCOMPLEX", "NEUROCOMPLEX", "DERMACOMPLEX", "OPHTALMOCOMPLEX", "CALCIY"]
        for msg in history:
            msg_content = msg.get("content", "").upper()
            for product in product_names:
                if product in msg_content:
                    products.add(product)

        prods = ", ".join(products) if products else "не определены"
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

        message = (
            f"\U0001f916 AskBiotact (через BiotactBot): Новая заявка!\n\n"
            f"\U0001f464 User ID: {user_id}\n"
            f"\U0001f4de Телефон: {phone}\n\n"
            f"\U0001f4dd Данные заказа:\n{order_data.get('raw_text', '')}\n\n"
            f"\U0001f4e6 Продукты: {prods}\n"
            f"\u23f0 Время: {timestamp}"
        )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{NOTIFICATION_BOT_TOKEN}/sendMessage",
                json={"chat_id": SALES_GROUP_CHAT_ID, "text": message},
                timeout=10.0,
            )
            if response.status_code == 200:
                logger.info(f"Order sent to sales: {user_id}")

                # Update CRM with purchased products
                try:
                    telegram_id = int(user_id)
                    if parsed and parsed.get("products"):
                        for p in parsed["products"]:
                            await update_customer_purchase(telegram_id, p["name"])
                except (ValueError, UnboundLocalError):
                    pass

                return True
            else:
                logger.error(f"Failed to send order: {response.text}")
                return False
    except Exception as e:
        logger.error(f"Send order error: {e}")
        return False



# =============================================================================
# RAG Processing
# =============================================================================


async def process_rag_query(
    message: str,
    chat_history: list[dict[str, str]],
    customer_context: str | None = None,
    telegram_id: int | None = None,
) -> str:
    """Process RAG query with optional customer context."""
    try:
        embedding_service = get_embedding_service()
        qdrant_service = get_qdrant_service()
        llm_service = get_llm_service()
        config = askbiotact_config

        # QUERY ENRICHMENT: Try DB insights first, then regex fallback
        enriched_message = message
        insight = None
        if telegram_id:
            insight = await get_active_insight(telegram_id)
            if insight and insight.get("products"):
                # Use products from extraction agent (most accurate)
                product_prefix = " ".join(insight["products"])
                if is_short_query(message):
                    enriched_message = f"{product_prefix} {message}"
                    logger.info(f"DB-enriched query: {enriched_message[:80]}...")

        # Fallback to regex-based enrichment if DB didn't help
        if enriched_message == message:
            enriched_message = enrich_query_with_context(message, chat_history)

        query_vector = await embedding_service.embed_text(enriched_message)
        search_results = await qdrant_service.search(
            query_vector=query_vector,
            department_id=config.department_filter or "",
            limit=config.rag_limit,
            score_threshold=config.score_threshold,
        )

        logger.info(f"RAG search: query='{enriched_message[:50]}...', results={len(search_results)}")

        # Build system prompt with customer context
        system_prompt = config.system_prompt
        if customer_context:
            system_prompt = f"{system_prompt}\n\n--- ИНФОРМАЦИЯ О КЛИЕНТЕ ---\n{customer_context}\n---\nИспользуй информацию о клиенте для персонализированных рекомендаций."

        # Inject critical constraints (allergies, contraindications) as hard safety block
        constraints = (insight.get("constraints") or []) if insight else []
        if constraints:
            constraints_text = "; ".join(constraints)
            system_prompt = (
                f"{system_prompt}\n\n"
                f"⛔ КРИТИЧЕСКИЕ ОГРАНИЧЕНИЯ КЛИЕНТА: {constraints_text}\n"
                "НИКОГДА не рекомендуй продукты, несовместимые с этими ограничениями."
            )
            logger.info(f"Constraints injected for {telegram_id}: {constraints}")
        
        answer = await llm_service.generate_response(
            question=message,  # Original message for LLM
            context=search_results,
            chat_history=chat_history,
            system_prompt=system_prompt,
            user_message_template=ASKBIOTACT_USER_TEMPLATE,
        )
        return answer
    except Exception as e:
        logger.exception(f"RAG query error: {e}")
        return "Извините, произошла ошибка. Попробуйте позже."


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> AskResponse:
    """Process a question through AskBiotact RAG system."""
    if x_api_key != settings.askbiotact_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    
    history = await get_chat_history(request.user_id)
    history.append({"role": "user", "content": request.message})
    
    # Load CRM customer context
    customer_context = None
    try:
        telegram_id = int(request.user_id)
        customer_context = await get_customer_context(
            telegram_id=telegram_id,
            first_name=request.first_name,
            username=request.username,
        )
    except ValueError:
        pass  # user_id is not a valid telegram_id
    
    # Check for order (with dedup: skip if already sent in the last hour)
    order_sent = False
    if not await is_order_already_sent(request.user_id):
        order_data = detect_order(request.message, history)
        if order_data:
            order_sent = await send_order_to_sales(order_data, request.user_id, history, request.first_name, request.username)
            if order_sent:
                await mark_order_sent(request.user_id)
    
    # Process through RAG with customer context
    telegram_id_int = None
    try:
        telegram_id_int = int(request.user_id)
    except ValueError:
        pass
    
    answer = await process_rag_query(
        request.message, history, customer_context, telegram_id=telegram_id_int,
    )
    
    # Save history
    history.append({"role": "assistant", "content": answer})
    await save_chat_history(request.user_id, history)
    
    # ASYNC: Fire extraction agent (does NOT block response)
    if telegram_id_int:
        try:
            agent = get_extraction_agent()
            asyncio.create_task(
                agent.process_and_save(telegram_id_int, request.message, answer)
            )
        except Exception as e:
            logger.warning(f"Extraction agent fire error: {e}")
    
    return AskResponse(answer=answer, user_id=request.user_id, order_sent=order_sent)


@router.post("/ask/reset")
async def reset_history(
    user_id: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> dict[str, Any]:
    """Reset chat history for a user."""
    if x_api_key != settings.askbiotact_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    
    try:
        # Archive conversation insights before clearing history
        try:
            telegram_id = int(user_id)
            await archive_insight(telegram_id)
        except (ValueError, Exception) as e:
            logger.warning(f"Archive insight error: {e}")

        r = await get_redis()
        await r.delete(f"public:{user_id}:history")
        return {"ok": True, "message": "History cleared"}
    except Exception as e:
        logger.error(f"Reset error: {e}")
        return {"ok": False, "message": str(e)}
