"""Webhook handlers for Telegram bot.

Thin Telegram adapter: commands, catalog, callbacks, order confirmation.
All AI logic delegated to AskBiotactService.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Request
from pydantic import BaseModel

from biotact.modules.askbiotact.constants import (
    CATEGORIES,
    PRODUCTS,
    Product,
    extract_phone,
    format_product_card,
)
from biotact.modules.askbiotact.schemas import ParsedOrder, UserInfo
from biotact.modules.askbiotact.service import get_askbiotact_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# =============================================================================
# Constants
# =============================================================================

TELEGRAM_BOT_TOKEN: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
MESSAGE_MAX_LENGTH: int = 4000

MAIN_KEYBOARD: dict[str, Any] = {
    "keyboard": [
        [{"text": "\U0001f504 Новый чат"}, {"text": "\U0001f4cb Каталог"}],
        [{"text": "\U0001f4de Связаться"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "Задайте вопрос о здоровье...",
}


# =============================================================================
# Pydantic Schemas
# =============================================================================


class WebhookResponse(BaseModel):
    ok: bool = True


class WebhookStatusResponse(BaseModel):
    status: str
    webhook: str
    storage: str
    buttons: bool


# =============================================================================
# Pending Order (Redis, webhook-specific interactive confirmation)
# =============================================================================

_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", "6379"))
        _redis = aioredis.Redis(host=host, port=port, decode_responses=True)
    return _redis


async def save_pending_order(chat_id: int, order_data: dict[str, Any]) -> None:
    """Save pending order for confirmation flow (1h TTL)."""
    try:
        r = await _get_redis()
        await r.set(
            f"chat:{chat_id}:pending_order",
            json.dumps(order_data, ensure_ascii=False),
            ex=3600,
        )
    except Exception as e:
        logger.warning("Redis save order error: %s", e)


async def get_pending_order(chat_id: int) -> dict[str, Any] | None:
    """Retrieve pending order from Redis."""
    try:
        r = await _get_redis()
        data = await r.get(f"chat:{chat_id}:pending_order")
        return json.loads(data) if data else None
    except Exception as e:
        logger.warning("Redis get order error: %s", e)
        return None


async def clear_pending_order(chat_id: int) -> None:
    """Remove pending order from Redis."""
    try:
        r = await _get_redis()
        await r.delete(f"chat:{chat_id}:pending_order")
    except Exception as e:
        logger.warning("Redis delete order error: %s", e)


# =============================================================================
# Telegram API Functions
# =============================================================================


async def send_telegram_message(
    chat_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = None,
) -> bool:
    """Send message to Telegram chat."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not configured")
        return False

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
        logger.error("Failed to send message: %s", e)
        return False


async def send_telegram_photo(
    chat_id: int,
    photo: str,
    caption: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = None,
) -> bool:
    """Send photo with caption to Telegram chat."""
    if not TELEGRAM_BOT_TOKEN:
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
        logger.error("Failed to send photo: %s", e)
        return False


async def edit_telegram_message(
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = None,
) -> bool:
    """Edit existing Telegram message."""
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
        logger.error("Failed to edit message: %s", e)
        return False


async def delete_telegram_message(chat_id: int, message_id: int) -> bool:
    """Delete a Telegram message."""
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
        logger.error("Failed to delete message: %s", e)
        return False


async def answer_callback_query(callback_id: str) -> None:
    """Answer Telegram callback query to remove loading state."""
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
        logger.warning("Failed to answer callback: %s", e)


async def register_bot_commands() -> None:
    """Register bot commands via Telegram setMyCommands API."""
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
                    "Failed to register bot commands: %s", response.status_code
                )
    except httpx.HTTPError as e:
        logger.warning("Failed to register bot commands: %s", e)


# =============================================================================
# Order Confirmation (webhook-specific interactive flow)
# =============================================================================


def format_order_confirmation(order: ParsedOrder, phone: str) -> str:
    """Format parsed order as a confirmation message for the user."""
    from biotact.modules.askbiotact.constants import PRODUCT_PRICES

    lines = ["\U0001f4cb Ваша заявка:\n"]

    total = 0
    if order.products:
        for p in order.products:
            price = PRODUCT_PRICES.get(p.name, 0)
            subtotal = price * p.qty
            total += subtotal
            if p.qty > 1:
                lines.append(
                    f"\U0001f4e6 {p.name} \u2014 {p.qty} шт. "
                    f"({price:,} \u00d7 {p.qty} = {subtotal:,} сум)".replace(",", " ")
                )
            else:
                lines.append(
                    f"\U0001f4e6 {p.name} \u2014 1 шт. ({price:,} сум)".replace(
                        ",", " "
                    )
                )
        lines.append(f"\n\U0001f4b0 Итого: {total:,} сум".replace(",", " "))

    phone_display = order.phone or phone
    lines.append("")
    if order.name:
        lines.append(f"\U0001f464 {order.name}")
    lines.append(f"\U0001f4de {phone_display}")
    if order.address:
        lines.append(f"\U0001f4cd {order.address}")

    lines.append("\n\u0412\u0441\u0451 верно?")
    return "\n".join(lines)


# =============================================================================
# Catalog Navigation
# =============================================================================


def build_catalog_keyboard() -> dict[str, Any]:
    """Build inline keyboard with product categories."""
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": f"cat:{key}"}]
            for key, label in CATEGORIES.items()
        ]
    }


def build_category_keyboard(category: str) -> dict[str, Any]:
    """Build inline keyboard with products in a category."""
    buttons: list[list[dict[str, str]]] = []
    for slug, product in PRODUCTS.items():
        if product.category == category:
            price_fmt = f"{product.price:,}".replace(",", " ")
            buttons.append(
                [
                    {
                        "text": f"{product.name} \u2014 {price_fmt} сум",
                        "callback_data": f"prod:{slug}",
                    }
                ]
            )
    buttons.append([{"text": "\u2b05\ufe0f К категориям", "callback_data": "catalog"}])
    return {"inline_keyboard": buttons}


def build_product_keyboard(slug: str, product: Product) -> dict[str, Any]:
    """Build inline keyboard for a product card."""
    return {
        "inline_keyboard": [
            [{"text": "\U0001f6d2 Заказать", "callback_data": f"order:{slug}"}],
            [
                {
                    "text": "\u2b05\ufe0f Назад",
                    "callback_data": f"cat:{product.category}",
                }
            ],
        ]
    }


# =============================================================================
# Callback Query Handler
# =============================================================================


async def handle_callback(callback: dict[str, Any]) -> WebhookResponse:
    """Handle Telegram callback query (button press)."""
    callback_id = callback.get("id")
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    user = callback.get("from", {})

    if callback_id:
        await answer_callback_query(callback_id)

    # Catalog: show categories
    if data == "catalog":
        await edit_telegram_message(
            chat_id,
            message_id,
            "Выберите категорию:",
            reply_markup=build_catalog_keyboard(),
        )

    # Category: show products
    elif data.startswith("cat:"):
        category = data[4:]
        cat_label = CATEGORIES.get(category, "Категория")
        await edit_telegram_message(
            chat_id,
            message_id,
            f"{cat_label}\n\nВыберите продукт:",
            reply_markup=build_category_keyboard(category),
        )

    # Product card
    elif data.startswith("prod:"):
        slug = data[5:]
        product = PRODUCTS.get(slug)
        if not product:
            await edit_telegram_message(chat_id, message_id, "Продукт не найден.")
            return WebhookResponse()

        card_text = format_product_card(product)
        keyboard = build_product_keyboard(slug, product)
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

    # Order from catalog
    elif data.startswith("order:"):
        slug = data[6:]
        product = PRODUCTS.get(slug)
        if product:
            price_fmt = f"{product.price:,}".replace(",", " ")
            text = (
                f"\U0001f6d2 <b>{product.name}</b> \u2014 {price_fmt} сум\n\n"
                f"Для оформления заказа напишите ваш номер телефона "
                f"в формате +998 XX XXX XX XX.\n\n"
                f"Менеджер свяжется с вами для подтверждения."
            )
        else:
            text = (
                "Для оформления заказа напишите ваш номер телефона "
                "в формате +998 XX XXX XX XX."
            )
        await delete_telegram_message(chat_id, message_id)
        await send_telegram_message(
            chat_id, text, reply_markup=MAIN_KEYBOARD, parse_mode="HTML"
        )

    # Order confirmation
    elif data == "confirm_order":
        pending = await get_pending_order(chat_id)
        if pending:
            service = get_askbiotact_service()
            user_info = UserInfo(
                user_id=str(user.get("id", "")),
                first_name=user.get("first_name", ""),
                username=user.get("username", "нет"),
            )
            history = await service.get_chat_history(str(chat_id), "chat")
            success = await service.send_order_to_sales(pending, user_info, history)

            if success:
                await edit_telegram_message(
                    chat_id,
                    message_id,
                    "\u2705 Заявка отправлена! Менеджер свяжется с вами. \U0001f49a",
                )
            else:
                await edit_telegram_message(
                    chat_id,
                    message_id,
                    "\u274c Ошибка отправки. Позвоните: +998 93 555 17 47",
                )
            await clear_pending_order(chat_id)
        else:
            await edit_telegram_message(
                chat_id,
                message_id,
                "\u26a0\ufe0f Заказ не найден. Попробуйте снова.",
            )

    # Order cancellation
    elif data == "cancel_order":
        await edit_telegram_message(
            chat_id,
            message_id,
            "Заказ отменён. Если передумаете \u2014 напишите! \U0001f49a",
        )
        await clear_pending_order(chat_id)

    return WebhookResponse()


# =============================================================================
# Webhook Endpoints
# =============================================================================


@router.post("/telegram", response_model=WebhookResponse)
async def telegram_webhook(request: Request) -> WebhookResponse:
    """Handle incoming Telegram webhook updates."""
    try:
        data = await request.json()
        logger.info("Webhook update received: %s", data.get("update_id"))

        # Callback query (button press)
        callback = data.get("callback_query")
        if callback:
            return await handle_callback(callback)

        # Message
        message = data.get("message")
        if not message:
            return WebhookResponse()

        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        user = message.get("from", {})

        if not chat_id or not text:
            return WebhookResponse()

        user_id = str(user.get("id", ""))
        service = get_askbiotact_service()

        # /start
        if text.startswith("/start"):
            await service.clear_chat_history(user_id, "chat")
            await send_telegram_message(
                chat_id,
                "Здравствуйте! \U0001f49a\n\n"
                "Я консультант Biotact. Помогу подобрать продукт для здоровья.\n\n"
                "Расскажите, что вас беспокоит?",
                reply_markup=MAIN_KEYBOARD,
            )
            return WebhookResponse()

        # /reset
        if text.startswith("/reset"):
            await service.reset_conversation(user_id, "chat")
            await send_telegram_message(
                chat_id,
                "История очищена! \U0001f504",
                reply_markup=MAIN_KEYBOARD,
            )
            return WebhookResponse()

        # "Новый чат" / /new
        if text in ("\U0001f504 Новый чат", "/new"):
            await service.reset_conversation(user_id, "chat")
            await send_telegram_message(
                chat_id,
                "Новый чат начат! \U0001f49a\n\nРасскажите, что вас беспокоит?",
                reply_markup=MAIN_KEYBOARD,
            )
            return WebhookResponse()

        # "Каталог" / /products
        if text in ("\U0001f4cb Каталог", "/products"):
            await send_telegram_message(
                chat_id,
                "Выберите категорию:",
                reply_markup=build_catalog_keyboard(),
            )
            return WebhookResponse()

        # "Связаться" / /contact
        if text in ("\U0001f4de Связаться", "/contact"):
            await send_telegram_message(
                chat_id,
                "\U0001f4de +998 93 555 17 47\n"
                "\U0001f4f1 @biotact_manager\n\n"
                "Менеджер ответит в рабочее время.",
                reply_markup=MAIN_KEYBOARD,
            )
            return WebhookResponse()

        # Phone detected → interactive order confirmation
        phone = extract_phone(text)
        if phone:
            history = await service.get_chat_history(user_id, "chat")
            parsed = await service.parse_order(text, history)

            order_data: dict[str, Any] = {
                "raw_text": text,
                "phone": phone,
            }

            if parsed and parsed.products:
                # Store parsed products for sales message
                order_data["parsed_products"] = [
                    {"name": p.name, "qty": p.qty} for p in parsed.products
                ]
                order_data["parsed_name"] = parsed.name
                order_data["parsed_phone"] = parsed.phone
                order_data["parsed_address"] = parsed.address
                confirmation = format_order_confirmation(parsed, phone)
            else:
                confirmation = (
                    f"\U0001f4cb Данные заказа получены!\n\n"
                    f"\U0001f4de Телефон: {phone}\n\n"
                    f"Нажмите \u00abПодтвердить\u00bb для отправки заявки."
                )

            await save_pending_order(chat_id, order_data)
            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": "\u2705 Подтвердить",
                            "callback_data": "confirm_order",
                        },
                        {"text": "\u274c Отмена", "callback_data": "cancel_order"},
                    ]
                ]
            }
            await send_telegram_message(chat_id, confirmation, reply_markup=keyboard)
            return WebhookResponse()

        # Regular message → full AI pipeline (CRM + enrichment + RAG + extraction)
        answer = await service.get_ai_response(
            user_id=user_id,
            message=text,
            history_prefix="chat",
            first_name=user.get("first_name"),
            username=user.get("username"),
        )
        await send_telegram_message(chat_id, answer, reply_markup=MAIN_KEYBOARD)

        return WebhookResponse()

    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in webhook: %s", e)
        return WebhookResponse()
    except Exception as e:
        logger.exception("Webhook error: %s", e)
        return WebhookResponse()


@router.get("/telegram", response_model=WebhookStatusResponse)
async def telegram_webhook_verify() -> WebhookStatusResponse:
    """Verify webhook endpoint is active."""
    return WebhookStatusResponse(
        status="ok",
        webhook="telegram",
        storage="redis",
        buttons=True,
    )
