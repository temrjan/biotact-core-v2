"""Webhook handlers for Telegram and Instagram.

This module provides webhook endpoints for processing incoming messages
from Telegram bots, handling RAG queries, and managing order workflows.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Request
from openai import AsyncOpenAI
from pydantic import BaseModel

from biotact.core.config import get_settings
from biotact.core.dependencies import (
    get_embedding_service,
    get_llm_service,
    get_qdrant_service,
)
from biotact.modules.askbiotact.config import askbiotact_config
from biotact.services.extraction_agent import archive_insight

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ═══════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
NOTIFICATION_BOT_TOKEN: str | None = os.getenv("NOTIFICATION_BOT_TOKEN")
SALES_GROUP_CHAT_ID: str | None = os.getenv("SALES_GROUP_CHAT_ID")
REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
MAX_HISTORY: int = 10
HISTORY_TTL: int = 86400  # 24 hours
MESSAGE_MAX_LENGTH: int = 4000

# Phone number patterns for Uzbekistan
PHONE_PATTERNS: list[str] = [
    r"\+998[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}",
    r"998\d{9}",
    r"\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}",
]


# ═══════════════════════════════════════════════════════════════════
# Product Catalog
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Product:
    """Product catalog item."""

    name: str
    price: int
    category: str  # "probiotics" | "vitamins" | "kitchen"
    description: str
    image_url: str  # URL or file_id; empty string = no photo


CATEGORIES: dict[str, str] = {
    "probiotics": "🦠 Пробиотики",
    "vitamins": "💊 Витамины и комплексы",
    "kitchen": "🍳 Кухонная техника",
}

PRODUCTS: dict[str, Product] = {
    "bifolak_neo": Product(
        name="BIFOLAK NEO",
        price=61_000,
        category="probiotics",
        description=(
            "Синбиотик нового поколения для восстановления микрофлоры "
            "кишечника. Содержит пробиотики и пребиотики."
        ),
        image_url="",
    ),
    "bifolak_active": Product(
        name="BIFOLAK ACTIVE",
        price=69_000,
        category="probiotics",
        description=(
            "Усиленная формула с повышенной концентрацией полезных "
            "бактерий для активной поддержки пищеварения."
        ),
        image_url="",
    ),
    "bifolak_zincum": Product(
        name="BIFOLAK ZINCUM",
        price=69_000,
        category="probiotics",
        description=(
            "Пробиотик с цинком для укрепления иммунитета "
            "и поддержки микрофлоры кишечника."
        ),
        image_url="",
    ),
    "bifolak_magniy": Product(
        name="BIFOLAK MAGNIY",
        price=76_000,
        category="probiotics",
        description=(
            "Пробиотик с магнием для поддержки нервной системы, "
            "снижения стресса и нормализации пищеварения."
        ),
        image_url="",
    ),
    "bifolak_zincum_cd3": Product(
        name="BIFOLAK ZINCUM+C+D3",
        price=76_000,
        category="probiotics",
        description=(
            "Комплексная формула: пробиотики + цинк + витамин C + D3 "
            "для максимальной поддержки иммунитета."
        ),
        image_url="",
    ),
    "calciy_triactive": Product(
        name="CALCIY TRIACTIVE D3",
        price=76_000,
        category="vitamins",
        description=(
            "Тройная формула кальция с витамином D3 для укрепления "
            "костей, зубов и суставов."
        ),
        image_url="",
    ),
    "immunocomplex": Product(
        name="IMMUNOCOMPLEX",
        price=76_000,
        category="vitamins",
        description=(
            "Комплекс для укрепления иммунитета с витаминами, "
            "минералами и растительными экстрактами."
        ),
        image_url="",
    ),
    "immunocomplex_kids": Product(
        name="IMMUNOCOMPLEX KIDS",
        price=76_000,
        category="vitamins",
        description=(
            "Детский иммунокомплекс с мягкой формулой, "
            "адаптированной для детского организма."
        ),
        image_url="",
    ),
    "dermacomplex": Product(
        name="DERMACOMPLEX",
        price=94_000,
        category="vitamins",
        description=(
            "Комплекс для здоровья кожи, волос и ногтей. "
            "Содержит коллаген, биотин и антиоксиданты."
        ),
        image_url="",
    ),
    "neurocomplex_kids": Product(
        name="NEUROCOMPLEX KIDS",
        price=101_000,
        category="vitamins",
        description=(
            "Детский нейрокомплекс для поддержки развития мозга, "
            "внимания и когнитивных функций."
        ),
        image_url="",
    ),
    "ophtalmocomplex": Product(
        name="OPHTALMOCOMPLEX",
        price=123_000,
        category="vitamins",
        description=(
            "Комплекс для здоровья глаз с лютеином, зеаксантином "
            "и черникой. Защита зрения."
        ),
        image_url="",
    ),
    "aerogrill": Product(
        name="Аэрогриль BIOTACT",
        price=850_000,
        category="kitchen",
        description=(
            "Многофункциональный аэрогриль для здорового приготовления "
            "без масла. Гриль, выпечка, сушка."
        ),
        image_url="",
    ),
    "juicer": Product(
        name="Соковыжималка BIOTACT",
        price=820_000,
        category="kitchen",
        description=(
            "Мощная соковыжималка для свежевыжатых соков "
            "из фруктов и овощей каждый день."
        ),
        image_url="",
    ),
    "hand_blender": Product(
        name="Ручной блендер BIOTACT",
        price=320_000,
        category="kitchen",
        description=(
            "Компактный ручной блендер для смузи, супов-пюре и детского питания."
        ),
        image_url="",
    ),
    "elec_blender": Product(
        name="Электрический блендер BIOTACT",
        price=320_000,
        category="kitchen",
        description=(
            "Стационарный блендер с мощным мотором для смузи, коктейлей и измельчения."
        ),
        image_url="",
    ),
    "toaster": Product(
        name="Тостер BIOTACT",
        price=255_000,
        category="kitchen",
        description=(
            "Стильный тостер с регулировкой прожарки для идеальных тостов каждое утро."
        ),
        image_url="",
    ),
    "food_processor": Product(
        name="Кухонный комбайн BIOTACT",
        price=230_000,
        category="kitchen",
        description=(
            "Универсальный кухонный комбайн: нарезка, шинковка, "
            "замес теста и многое другое."
        ),
        image_url="",
    ),
    "elec_kettle": Product(
        name="Электрический чайник BIOTACT",
        price=160_000,
        category="kitchen",
        description=(
            "Быстрый электрический чайник из нержавеющей стали с автоотключением."
        ),
        image_url="",
    ),
}

# Backward compatibility: PRODUCT_PRICES for order parsing
PRODUCT_PRICES: dict[str, int] = {p.name: p.price for p in PRODUCTS.values()}

# Persistent reply keyboard for the bot
MAIN_KEYBOARD: dict[str, Any] = {
    "keyboard": [
        [{"text": "🔄 Новый чат"}, {"text": "📋 Каталог"}],
        [{"text": "📞 Связаться"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "Задайте вопрос о здоровье...",
}


# ═══════════════════════════════════════════════════════════════════
# Pydantic Schemas
# ═══════════════════════════════════════════════════════════════════


class WebhookResponse(BaseModel):
    """Response model for webhook endpoints."""

    ok: bool = True


class WebhookStatusResponse(BaseModel):
    """Response model for webhook status endpoint."""

    status: str
    webhook: str
    storage: str
    buttons: bool


# ═══════════════════════════════════════════════════════════════════
# Redis Connection
# ═══════════════════════════════════════════════════════════════════

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get or create Redis connection.

    Returns:
        Redis client instance.
    """
    global _redis
    if _redis is None:
        _redis = aioredis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
        )
    return _redis


# ═══════════════════════════════════════════════════════════════════
# Chat History Management
# ═══════════════════════════════════════════════════════════════════


async def get_chat_history(chat_id: int) -> list[dict[str, str]]:
    """Retrieve chat history from Redis.

    Args:
        chat_id: Telegram chat identifier.

    Returns:
        List of message dictionaries with role and content.
    """
    try:
        r = await get_redis()
        data = await r.get(f"chat:{chat_id}:history")
        return json.loads(data) if data else []
    except aioredis.RedisError as e:
        logger.warning(
            "Redis get error",
            extra={"chat_id": chat_id, "error": str(e)},
        )
        return []


async def save_chat_history(chat_id: int, history: list[dict[str, str]]) -> None:
    """Save chat history to Redis with TTL.

    Args:
        chat_id: Telegram chat identifier.
        history: List of message dictionaries to save.
    """
    try:
        r = await get_redis()
        # Keep only last MAX_HISTORY*2 messages (user + assistant pairs)
        trimmed_history = history[-(MAX_HISTORY * 2) :]
        await r.set(
            f"chat:{chat_id}:history",
            json.dumps(trimmed_history, ensure_ascii=False),
            ex=HISTORY_TTL,
        )
    except aioredis.RedisError as e:
        logger.warning(
            "Redis save error",
            extra={"chat_id": chat_id, "error": str(e)},
        )


# ═══════════════════════════════════════════════════════════════════
# Pending Order Management
# ═══════════════════════════════════════════════════════════════════


async def save_pending_order(chat_id: int, order_data: dict[str, Any]) -> None:
    """Save pending order to Redis for confirmation.

    Args:
        chat_id: Telegram chat identifier.
        order_data: Order details including phone, user info, etc.
    """
    try:
        r = await get_redis()
        await r.set(
            f"chat:{chat_id}:pending_order",
            json.dumps(order_data, ensure_ascii=False),
            ex=3600,  # 1 hour TTL
        )
    except aioredis.RedisError as e:
        logger.warning(
            "Redis save order error",
            extra={"chat_id": chat_id, "error": str(e)},
        )


async def get_pending_order(chat_id: int) -> dict[str, Any] | None:
    """Retrieve pending order from Redis.

    Args:
        chat_id: Telegram chat identifier.

    Returns:
        Order data dictionary or None if not found.
    """
    try:
        r = await get_redis()
        data = await r.get(f"chat:{chat_id}:pending_order")
        return json.loads(data) if data else None
    except aioredis.RedisError as e:
        logger.warning(
            "Redis get order error",
            extra={"chat_id": chat_id, "error": str(e)},
        )
        return None


async def clear_pending_order(chat_id: int) -> None:
    """Remove pending order from Redis.

    Args:
        chat_id: Telegram chat identifier.
    """
    try:
        r = await get_redis()
        await r.delete(f"chat:{chat_id}:pending_order")
    except aioredis.RedisError as e:
        logger.warning(
            "Redis delete order error",
            extra={"chat_id": chat_id, "error": str(e)},
        )


# ═══════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════


def extract_phone(text: str) -> str | None:
    """Extract phone number from text using Uzbekistan patterns.

    Args:
        text: Input text to search for phone number.

    Returns:
        Normalized phone number or None if not found.
    """
    for pattern in PHONE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            # Normalize: remove spaces and dashes
            return match.group().replace(" ", "").replace("-", "")
    return None


def format_product_card(product: Product) -> str:
    """Format product info as a card caption (HTML).

    Args:
        product: Product dataclass instance.

    Returns:
        HTML-formatted product card string.
    """
    price_fmt = f"{product.price:,}".replace(",", " ")
    return f"<b>{product.name}</b>\n\n{product.description}\n\n💰 {price_fmt} сум"


def _get_slug_by_product_name(name: str) -> str | None:
    """Find product slug by display name.

    Args:
        name: Product display name.

    Returns:
        Product slug key or None.
    """
    for slug, product in PRODUCTS.items():
        if product.name == name:
            return slug
    return None


# ═══════════════════════════════════════════════════════════════════
# Order Parsing (LLM)
# ═══════════════════════════════════════════════════════════════════


async def parse_order_with_llm(
    raw_text: str,
    chat_history: list[dict[str, str]],
) -> dict[str, Any] | None:
    """Parse order details from raw text using GPT-4o-mini.

    Extracts name, phone, address, and products from free-form order text.

    Args:
        raw_text: User's raw order message.
        chat_history: Recent chat history for context.

    Returns:
        Parsed order dict or None on failure.
    """
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    product_list = "\n".join(f"- {name}" for name in PRODUCT_PRICES)

    # Build context from last few messages
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
        content = raw_content.strip()
        parsed = json.loads(content)

        # Validate products exist in PRODUCT_PRICES
        if parsed.get("products"):
            valid_products = []
            for p in parsed["products"]:
                if p.get("name") in PRODUCT_PRICES:
                    valid_products.append(
                        {
                            "name": p["name"],
                            "qty": max(1, int(p.get("qty", 1))),
                        }
                    )
            parsed["products"] = valid_products

        return parsed  # type: ignore[no-any-return]
    except Exception as e:
        logger.warning(
            "Order parsing failed", extra={"error": str(e), "raw_text": raw_text[:200]}
        )
        return None


def format_order_confirmation(parsed: dict[str, Any], phone: str) -> str:
    """Format parsed order as a confirmation message for the user.

    Args:
        parsed: Parsed order data from LLM.
        phone: Extracted phone number.

    Returns:
        Formatted confirmation string.
    """
    lines = ["📋 Ваша заявка:\n"]

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
                lines.append(
                    f"📦 {name} — {qty} шт. ({price:,} × {qty} = {subtotal:,} сум)".replace(
                        ",", " "
                    )
                )
            else:
                lines.append(f"📦 {name} — 1 шт. ({price:,} сум)".replace(",", " "))
        lines.append(f"\n💰 Итого: {total:,} сум".replace(",", " "))

    # Customer info
    name = parsed.get("name")
    address = parsed.get("address")
    phone_display = parsed.get("phone") or phone

    lines.append("")
    if name:
        lines.append(f"👤 {name}")
    lines.append(f"📞 {phone_display}")
    if address:
        lines.append(f"📍 {address}")

    lines.append("\nВсё верно?")
    return "\n".join(lines)


def format_order_for_sales(
    parsed: dict[str, Any],
    user_info: dict[str, Any],
    phone: str,
) -> str:
    """Format parsed order as a message for the sales group.

    Args:
        parsed: Parsed order data from LLM.
        user_info: Telegram user information.
        phone: Extracted phone number.

    Returns:
        Formatted sales notification string.
    """
    lines = ["🤖 AskBiotactBot: Новая заявка!\n"]

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
                lines.append(
                    f"📦 {name} — {qty} шт. ({subtotal:,} сум)".replace(",", " ")
                )
            else:
                lines.append(f"📦 {name} — 1 шт. ({price:,} сум)".replace(",", " "))
        lines.append(f"💰 Итого: {total:,} сум".replace(",", " "))

    # Customer info
    name = parsed.get("name")
    address = parsed.get("address")
    phone_display = parsed.get("phone") or phone

    lines.append("")
    if name:
        lines.append(f"👤 {name}")
    lines.append(f"📞 {phone_display}")
    if address:
        lines.append(f"📍 {address}")

    # Telegram info
    username = user_info.get("username", "нет")
    user_id = user_info.get("id")
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

    lines.append(f"\n👤 TG: @{username} (ID: {user_id})")
    lines.append(f"⏰ {timestamp}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Telegram API Functions
# ═══════════════════════════════════════════════════════════════════


async def send_telegram_message(
    chat_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = None,
) -> bool:
    """Send message to Telegram chat.

    Args:
        chat_id: Telegram chat identifier.
        text: Message text (will be truncated if too long).
        reply_markup: Optional keyboard markup.
        parse_mode: Optional parse mode ("HTML", "Markdown", etc.).

    Returns:
        True if message sent successfully, False otherwise.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not configured")
        return False

    # Truncate long messages
    if len(text) > MESSAGE_MAX_LENGTH:
        text = text[:MESSAGE_MAX_LENGTH] + "..."

    try:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        if parse_mode:
            payload["parse_mode"] = parse_mode

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json=payload,
                timeout=10.0,
            )
            return response.status_code == 200
    except httpx.HTTPError as e:
        logger.error(
            "Failed to send message",
            extra={"chat_id": chat_id, "error": str(e)},
        )
        return False


async def send_telegram_photo(
    chat_id: int,
    photo: str,
    caption: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = None,
) -> bool:
    """Send photo with caption to Telegram chat.

    Args:
        chat_id: Telegram chat identifier.
        photo: Photo URL or Telegram file_id.
        caption: Photo caption text.
        reply_markup: Optional inline keyboard markup.
        parse_mode: Optional parse mode for caption.

    Returns:
        True if photo sent successfully, False otherwise.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not configured")
        return False

    try:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "photo": photo,
            "caption": caption,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        if parse_mode:
            payload["parse_mode"] = parse_mode

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                json=payload,
                timeout=10.0,
            )
            return response.status_code == 200
    except httpx.HTTPError as e:
        logger.error(
            "Failed to send photo",
            extra={"chat_id": chat_id, "error": str(e)},
        )
        return False


async def edit_telegram_message(
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = None,
) -> bool:
    """Edit existing Telegram message.

    Args:
        chat_id: Telegram chat identifier.
        message_id: Message ID to edit.
        text: New message text.
        reply_markup: Optional inline keyboard markup.
        parse_mode: Optional parse mode ("HTML", "Markdown", etc.).

    Returns:
        True if message edited successfully, False otherwise.
    """
    if not TELEGRAM_BOT_TOKEN:
        return False

    try:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        if parse_mode:
            payload["parse_mode"] = parse_mode

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText",
                json=payload,
                timeout=10.0,
            )
            return response.status_code == 200
    except httpx.HTTPError as e:
        logger.error(
            "Failed to edit message",
            extra={"chat_id": chat_id, "message_id": message_id, "error": str(e)},
        )
        return False


async def delete_telegram_message(chat_id: int, message_id: int) -> bool:
    """Delete a Telegram message.

    Args:
        chat_id: Telegram chat identifier.
        message_id: Message ID to delete.

    Returns:
        True if message deleted successfully, False otherwise.
    """
    if not TELEGRAM_BOT_TOKEN:
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id},
                timeout=10.0,
            )
            return response.status_code == 200
    except httpx.HTTPError as e:
        logger.error(
            "Failed to delete message",
            extra={"chat_id": chat_id, "message_id": message_id, "error": str(e)},
        )
        return False


async def answer_callback_query(callback_id: str) -> None:
    """Answer Telegram callback query to remove loading state.

    Args:
        callback_id: Callback query identifier.
    """
    if not TELEGRAM_BOT_TOKEN:
        return

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                json={"callback_query_id": callback_id},
                timeout=5.0,
            )
    except httpx.HTTPError as e:
        logger.warning(
            "Failed to answer callback",
            extra={"callback_id": callback_id, "error": str(e)},
        )


async def register_bot_commands() -> None:
    """Register bot commands via Telegram setMyCommands API.

    Registers /start, /new, /products, /contact in the Telegram command menu.
    Should be called once at application startup.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Cannot register commands: TELEGRAM_BOT_TOKEN not set")
        return

    commands = [
        {"command": "start", "description": "Начать заново"},
        {"command": "new", "description": "Новый чат"},
        {"command": "products", "description": "Каталог продуктов"},
        {"command": "contact", "description": "Связаться с менеджером"},
    ]
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setMyCommands",
                json={"commands": commands},
                timeout=10.0,
            )
            if response.status_code == 200:
                logger.info("Bot commands registered successfully")
            else:
                logger.warning(
                    "Failed to register bot commands",
                    extra={"status": response.status_code},
                )
    except httpx.HTTPError as e:
        logger.warning(
            "Failed to register bot commands",
            extra={"error": str(e)},
        )


# ═══════════════════════════════════════════════════════════════════
# Order Processing
# ═══════════════════════════════════════════════════════════════════


async def send_order_to_sales(
    order_data: dict[str, Any],
    user_info: dict[str, Any],
) -> bool:
    """Send order notification to sales group.

    Args:
        order_data: Order details from user.
        user_info: Telegram user information.

    Returns:
        True if notification sent successfully, False otherwise.
    """
    if not NOTIFICATION_BOT_TOKEN or not SALES_GROUP_CHAT_ID:
        logger.error(
            "Notification bot not configured",
            extra={
                "has_token": bool(NOTIFICATION_BOT_TOKEN),
                "has_chat_id": bool(SALES_GROUP_CHAT_ID),
            },
        )
        return False

    # Use structured format if parsed data is available
    parsed = order_data.get("parsed")
    if parsed:
        phone = order_data.get("phone", "")
        message = format_order_for_sales(parsed, user_info, phone)
    else:
        # Fallback to raw text format
        username = user_info.get("username", "нет")
        user_id = user_info.get("id")
        first_name = user_info.get("first_name", "")
        raw_text = order_data.get("raw_text", "")
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

        message = (
            f"🤖 AskBiotactBot: Новая заявка!\n\n"
            f"👤 @{username}\n"
            f"📱 ID: {user_id}\n"
            f"👋 {first_name}\n\n"
            f"📝 {raw_text}\n\n"
            f"⏰ {timestamp}"
        )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{NOTIFICATION_BOT_TOKEN}/sendMessage",
                json={"chat_id": SALES_GROUP_CHAT_ID, "text": message},
                timeout=10.0,
            )
            success = response.status_code == 200
            if success:
                logger.info(
                    "Order sent to sales",
                    extra={
                        "user_id": user_info.get("id"),
                        "username": user_info.get("username"),
                    },
                )
            return success
    except httpx.HTTPError as e:
        logger.error(
            "Failed to send order to sales",
            extra={"user_id": user_info.get("id"), "error": str(e)},
        )
        return False


# ═══════════════════════════════════════════════════════════════════
# RAG Processing
# ═══════════════════════════════════════════════════════════════════


async def process_rag_query(
    message: str,
    chat_history: list[dict[str, str]],
) -> str:
    """Process user message through RAG pipeline.

    Args:
        message: User's question or message.
        chat_history: Previous conversation history.

    Returns:
        Generated response from LLM.
    """
    try:
        embedding_service = get_embedding_service()
        qdrant_service = get_qdrant_service()
        llm_service = get_llm_service()
        config = askbiotact_config

        query_vector = await embedding_service.embed_text(message)
        search_results = await qdrant_service.search(
            query_vector=query_vector,
            department_id=config.department_filter or "",
            limit=config.rag_limit,
            score_threshold=config.score_threshold,
        )
        answer = await llm_service.generate_response(
            question=message,
            context=search_results,
            chat_history=chat_history,
            system_prompt=config.system_prompt,
        )
        return answer
    except Exception as e:
        logger.exception(
            "RAG query error",
            extra={"message_preview": message[:100], "error": str(e)},
        )
        return "Извините, произошла ошибка. Попробуйте позже."


# ═══════════════════════════════════════════════════════════════════
# Catalog Navigation Helpers
# ═══════════════════════════════════════════════════════════════════


def build_catalog_keyboard() -> dict[str, Any]:
    """Build inline keyboard with product categories.

    Returns:
        Telegram inline keyboard markup.
    """
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": f"cat:{key}"}]
            for key, label in CATEGORIES.items()
        ]
    }


def build_category_keyboard(category: str) -> dict[str, Any]:
    """Build inline keyboard with products in a category.

    Args:
        category: Category key (probiotics, vitamins, kitchen).

    Returns:
        Telegram inline keyboard markup with product buttons + back.
    """
    buttons: list[list[dict[str, str]]] = []
    for slug, product in PRODUCTS.items():
        if product.category == category:
            price_fmt = f"{product.price:,}".replace(",", " ")
            buttons.append(
                [
                    {
                        "text": f"{product.name} — {price_fmt} сум",
                        "callback_data": f"prod:{slug}",
                    }
                ]
            )
    buttons.append([{"text": "⬅️ К категориям", "callback_data": "catalog"}])
    return {"inline_keyboard": buttons}


def build_product_keyboard(slug: str, product: Product) -> dict[str, Any]:
    """Build inline keyboard for a product card.

    Args:
        slug: Product slug key.
        product: Product dataclass instance.

    Returns:
        Telegram inline keyboard markup with order + back buttons.
    """
    return {
        "inline_keyboard": [
            [{"text": "🛒 Заказать", "callback_data": f"order:{slug}"}],
            [{"text": "⬅️ Назад", "callback_data": f"cat:{product.category}"}],
        ]
    }


# ═══════════════════════════════════════════════════════════════════
# Callback Query Handler
# ═══════════════════════════════════════════════════════════════════


async def handle_callback(callback: dict[str, Any]) -> WebhookResponse:
    """Handle Telegram callback query (button press).

    Args:
        callback: Callback query data from Telegram.

    Returns:
        Webhook response indicating success.
    """
    callback_id = callback.get("id")
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    user = callback.get("from", {})

    # Answer callback to remove loading state
    if callback_id:
        await answer_callback_query(callback_id)

    # ── Catalog: show categories ──
    if data == "catalog":
        await edit_telegram_message(
            chat_id,
            message_id,
            "Выберите категорию:",
            reply_markup=build_catalog_keyboard(),
        )

    # ── Category: show products list ──
    elif data.startswith("cat:"):
        category = data[4:]
        cat_label = CATEGORIES.get(category, "Категория")
        await edit_telegram_message(
            chat_id,
            message_id,
            f"{cat_label}\n\nВыберите продукт:",
            reply_markup=build_category_keyboard(category),
        )

    # ── Product card ──
    elif data.startswith("prod:"):
        slug = data[5:]
        product = PRODUCTS.get(slug)
        if not product:
            await edit_telegram_message(chat_id, message_id, "Продукт не найден.")
            return WebhookResponse()

        card_text = format_product_card(product)
        keyboard = build_product_keyboard(slug, product)

        # Delete the old text message, then send photo or text card
        await delete_telegram_message(chat_id, message_id)

        if product.image_url:
            await send_telegram_photo(
                chat_id,
                photo=product.image_url,
                caption=card_text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        else:
            await send_telegram_message(
                chat_id,
                card_text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )

    # ── Order from catalog card ──
    elif data.startswith("order:"):
        slug = data[6:]
        product = PRODUCTS.get(slug)
        if product:
            price_fmt = f"{product.price:,}".replace(",", " ")
            text = (
                f"🛒 <b>{product.name}</b> — {price_fmt} сум\n\n"
                f"Для оформления заказа напишите ваш номер телефона "
                f"в формате +998 XX XXX XX XX.\n\n"
                f"Менеджер свяжется с вами для подтверждения."
            )
        else:
            text = (
                "Для оформления заказа напишите ваш номер телефона "
                "в формате +998 XX XXX XX XX."
            )

        # Delete old message (could be photo or text) and send new text
        await delete_telegram_message(chat_id, message_id)
        await send_telegram_message(
            chat_id,
            text,
            reply_markup=MAIN_KEYBOARD,
            parse_mode="HTML",
        )

    # ── Order confirmation/cancellation ──
    elif data == "confirm_order":
        order_data = await get_pending_order(chat_id)
        if order_data:
            user_info = {
                "id": user.get("id"),
                "username": user.get("username"),
                "first_name": user.get("first_name"),
            }
            success = await send_order_to_sales(order_data, user_info)
            if success:
                await edit_telegram_message(
                    chat_id,
                    message_id,
                    "✅ Заявка отправлена! Менеджер свяжется с вами. 💚",
                )
            else:
                await edit_telegram_message(
                    chat_id,
                    message_id,
                    "❌ Ошибка отправки. Позвоните: +998 93 555 17 47",
                )
            await clear_pending_order(chat_id)
        else:
            await edit_telegram_message(
                chat_id,
                message_id,
                "⚠️ Заказ не найден. Попробуйте снова.",
            )

    elif data == "cancel_order":
        await edit_telegram_message(
            chat_id,
            message_id,
            "Заказ отменён. Если передумаете — напишите! 💚",
        )
        await clear_pending_order(chat_id)

    return WebhookResponse()


# ═══════════════════════════════════════════════════════════════════
# Webhook Endpoints
# ═══════════════════════════════════════════════════════════════════


@router.post("/telegram", response_model=WebhookResponse)
async def telegram_webhook(request: Request) -> WebhookResponse:
    """Handle incoming Telegram webhook updates.

    Processes messages, commands, and callback queries from Telegram.

    Args:
        request: FastAPI request object containing webhook payload.

    Returns:
        Webhook response indicating success.
    """
    try:
        data = await request.json()
        update_id = data.get("update_id")
        logger.info("Webhook update received", extra={"update_id": update_id})

        # Handle callback query (button press)
        callback = data.get("callback_query")
        if callback:
            return await handle_callback(callback)

        # Handle message
        message = data.get("message")
        if not message:
            return WebhookResponse()

        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        user = message.get("from", {})

        if not chat_id or not text:
            return WebhookResponse()

        user_id = user.get("id")
        logger.info(
            "Processing message",
            extra={"chat_id": chat_id, "user_id": user_id},
        )

        # Handle /start command
        if text.startswith("/start"):
            await save_chat_history(chat_id, [])
            await send_telegram_message(
                chat_id,
                "Здравствуйте! 💚\n\n"
                "Я консультант Biotact. Помогу подобрать продукт для здоровья.\n\n"
                "Расскажите, что вас беспокоит?",
                reply_markup=MAIN_KEYBOARD,
            )
            return WebhookResponse()

        # Handle /reset command
        if text.startswith("/reset"):
            await save_chat_history(chat_id, [])
            await send_telegram_message(
                chat_id,
                "История очищена! 🔄",
                reply_markup=MAIN_KEYBOARD,
            )
            return WebhookResponse()

        # Handle "🔄 Новый чат" button or /new command
        if text in ("🔄 Новый чат", "/new"):
            await save_chat_history(chat_id, [])
            try:
                await archive_insight(user_id)
            except Exception:
                logger.debug("No insight to archive", extra={"user_id": user_id})
            await send_telegram_message(
                chat_id,
                "Новый чат начат! 💚\n\nРасскажите, что вас беспокоит?",
                reply_markup=MAIN_KEYBOARD,
            )
            return WebhookResponse()

        # Handle "📋 Каталог" button or /products command
        if text in ("📋 Каталог", "/products"):
            await send_telegram_message(
                chat_id,
                "Выберите категорию:",
                reply_markup=build_catalog_keyboard(),
            )
            return WebhookResponse()

        # Handle "📞 Связаться" button or /contact command
        if text in ("📞 Связаться", "/contact"):
            await send_telegram_message(
                chat_id,
                "📞 +998 93 555 17 47\n"
                "📱 @biotact_manager\n\n"
                "Менеджер ответит в рабочее время.",
                reply_markup=MAIN_KEYBOARD,
            )
            return WebhookResponse()

        # Load history early (needed for both order parsing and RAG)
        history = await get_chat_history(chat_id)

        # Check for phone number (order intent)
        phone = extract_phone(text)
        if phone:
            # Parse order with LLM for structured data
            parsed = await parse_order_with_llm(text, history)

            order_data = {
                "raw_text": text,
                "phone": phone,
                "user_id": user.get("id"),
                "username": user.get("username"),
                "first_name": user.get("first_name"),
            }

            if parsed:
                order_data["parsed"] = parsed
                confirmation = format_order_confirmation(parsed, phone)
            else:
                # Fallback: simple confirmation without structured data
                confirmation = (
                    f"📋 Данные заказа получены!\n\n"
                    f"📞 Телефон: {phone}\n\n"
                    f"Нажмите «Подтвердить» для отправки заявки."
                )

            await save_pending_order(chat_id, order_data)

            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Подтвердить", "callback_data": "confirm_order"},
                        {"text": "❌ Отмена", "callback_data": "cancel_order"},
                    ]
                ]
            }
            await send_telegram_message(chat_id, confirmation, reply_markup=keyboard)
            return WebhookResponse()

        # Regular message - process through RAG
        history.append({"role": "user", "content": text})

        answer = await process_rag_query(text, history)

        history.append({"role": "assistant", "content": answer})
        await save_chat_history(chat_id, history)
        await send_telegram_message(chat_id, answer, reply_markup=MAIN_KEYBOARD)

        return WebhookResponse()

    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in webhook", extra={"error": str(e)})
        return WebhookResponse()
    except Exception as e:
        logger.exception("Webhook error", extra={"error": str(e)})
        return WebhookResponse()


@router.get("/telegram", response_model=WebhookStatusResponse)
async def telegram_webhook_verify() -> WebhookStatusResponse:
    """Verify webhook endpoint is active.

    Returns:
        Status response with webhook configuration details.
    """
    return WebhookStatusResponse(
        status="ok",
        webhook="telegram",
        storage="redis",
        buttons=True,
    )
