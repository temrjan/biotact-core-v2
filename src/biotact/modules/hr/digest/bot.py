"""Interactive Telegram bot for HR Digest with User Management."""

import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import Message, BotCommand, BotCommandScopeDefault, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from biotact.core.config import get_settings
from biotact.core.database import AsyncSessionLocal
from biotact.modules.hr.digest.service import digest_service

logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
settings = get_settings()
bot = Bot(
    token=settings.hr_digest_bot_token.get_secret_value(),
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ============================================================================
# FSM States for User Management
# ============================================================================

class AddUserStates(StatesGroup):
    """States for adding new user."""
    waiting_for_user_id = State()
    waiting_for_confirmation = State()


# ============================================================================
# Reply Keyboard
# ============================================================================

def get_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Get main reply keyboard with icons.

    Args:
        is_admin: Show admin buttons if True.
    """
    keyboard = [
        [
            KeyboardButton(text="📋 Дайджест"),
            KeyboardButton(text="📚 История"),
        ],
        [
            KeyboardButton(text="🔄 Создать"),
            KeyboardButton(text="❓ Справка"),
        ],
    ]

    # Add admin row
    if is_admin:
        keyboard.append([
            KeyboardButton(text="➕ Добавить пользователя"),
            KeyboardButton(text="👥 Список пользователей"),
        ])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def is_admin(user_id: int) -> bool:
    """Check if user is admin (first in allowed_users list)."""
    allowed = settings.allowed_users.split(',')
    if not allowed or not allowed[0].strip():
        return False
    admin_id = int(allowed[0].strip())
    return user_id == admin_id


def get_allowed_users() -> list[int]:
    """Get list of allowed user IDs."""
    allowed = settings.allowed_users.split(',')
    return [int(uid.strip()) for uid in allowed if uid.strip()]


def add_user_to_allowed(new_user_id: int) -> bool:
    """Add user to allowed list and persist to file.

    Args:
        new_user_id: Telegram user ID to add.

    Returns:
        True if added successfully, False if already exists.
    """
    current_users = get_allowed_users()

    if new_user_id in current_users:
        return False

    current_users.append(new_user_id)
    new_allowed_str = ','.join(str(uid) for uid in current_users)

    # Update settings in memory
    settings.allowed_users = new_allowed_str

    # Save to persistent file (in mounted volume)
    users_file = '/app/.sessions/allowed_users.txt'

    try:
        os.makedirs(os.path.dirname(users_file), exist_ok=True)

        with open(users_file, 'w') as f:
            f.write(new_allowed_str)

        logger.info(f"Added user {new_user_id} to allowed list (saved to {users_file})")
        return True

    except Exception as e:
        logger.error(f"Failed to save users file: {e}")
        # Still return True as we updated in memory
        logger.warning("User added only in memory (will be lost on restart)")
        return True


def load_users_from_file() -> None:
    """Load allowed users from persistent file if exists."""
    users_file = '/app/.sessions/allowed_users.txt'

    try:
        if os.path.exists(users_file):
            with open(users_file, 'r') as f:
                content = f.read().strip()
                if content:
                    settings.allowed_users = content
                    logger.info(f"Loaded users from file: {content}")
    except Exception as e:
        logger.error(f"Failed to load users file: {e}")


# ============================================================================
# Middleware for access control
# ============================================================================

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from typing import Callable, Dict, Any, Awaitable


class AuthMiddleware(BaseMiddleware):
    """Middleware to restrict bot access to allowed users."""

    def __init__(self):
        super().__init__()
        logger.info(f"Auth middleware initialized. Allowed users: {get_allowed_users()}")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Check if user is allowed."""
        user_id = None

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None

        # Get current allowed users
        allowed_users = get_allowed_users()

        # Allow if no restrictions or user is allowed
        if not allowed_users or user_id in allowed_users:
            logger.info(f"Access granted for user {user_id}")
            return await handler(event, data)

        # Deny access
        logger.warning(f"Access denied for user {user_id}. Allowed: {allowed_users}")
        if isinstance(event, Message):
            await event.answer("У вас нет доступа к этому боту.")
        return


# ============================================================================
# Command Handlers
# ============================================================================

@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Handle /start command."""
    user_is_admin = is_admin(message.from_user.id)

    await message.answer(
        f"Привет, {message.from_user.full_name}!\n\n"
        "Я — HR Digest бот Biotact Deutschland.\n\n"
        "Используй кнопки ниже или команды:\n"
        "/digest — показать последний дайджест\n"
        "/history — история дайджестов\n"
        "/generate — создать новый дайджест\n"
        "/help — справка\n\n"
        "📰 Каждый день в 08:00 я автоматически отправляю\n"
        "дайджест с новостями из 7 источников.",
        reply_markup=get_main_keyboard(user_is_admin)
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    user_is_admin = is_admin(message.from_user.id)

    help_text = (
        "📚 *Справка по командам*\n\n"
        "*Основные команды:*\n"
        "/digest — последний дайджест\n"
        "/history — показать последние 5 дайджестов\n"
        "/generate — создать новый дайджест (вручную)\n\n"
        "*Источники новостей:*\n"
        "📰 Веб-сайты (5): lex.uz, mehnat.uz, gazeta.uz, spot.uz, hh.uz\n"
        "💬 Telegram (2): @bhblaw, @pravoinf\n\n"
        "*Автоматическая отправка:*\n"
        "Каждый день в 08:00 (Tashkent) генерируется\n"
        "дайджест с новостями за последние 24 часа."
    )

    if user_is_admin:
        help_text += (
            "\n\n*Команды администратора:*\n"
            "➕ Добавить пользователя — дать доступ к боту\n"
            "👥 Список пользователей — показать всех\n"
            "/cleanup — очистить старые дайджесты"
        )

    await message.answer(help_text, reply_markup=get_main_keyboard(user_is_admin))


@dp.message(Command("digest"))
async def cmd_digest(message: Message) -> None:
    """Handle /digest command - show latest digest."""
    user_is_admin = is_admin(message.from_user.id)

    try:
        async with AsyncSessionLocal() as db:
            digest = await digest_service.get_latest_digest(db)

            if not digest:
                await message.answer("❌ Дайджесты ещё не создавались", reply_markup=get_main_keyboard(user_is_admin))
                return

            # Format date
            date_str = digest.date.strftime('%d.%m.%Y')

            # Send header
            header = (
                f"📋 *HR Digest за {date_str}*\n"
                f"📊 Новостей: {digest.news_count}\n"
                f"🕐 Создан: {digest.created_at.strftime('%H:%M')}\n"
                f"\n"
            )

            # Send digest (split if too long)
            full_text = header + digest.content_markdown

            if len(full_text) > 4000:
                await message.answer(header)
                sections = digest.content_markdown.split("\n## ")

                for i, section in enumerate(sections):
                    if i == 0:
                        await message.answer(section)
                    else:
                        section_text = f"## {section}"
                        if len(section_text) > 4000:
                            chunks = [section_text[i:i+4000] for i in range(0, len(section_text), 4000)]
                            for chunk in chunks:
                                await message.answer(chunk)
                        else:
                            await message.answer(section_text)

                await message.answer("---", reply_markup=get_main_keyboard(user_is_admin))
            else:
                await message.answer(full_text, reply_markup=get_main_keyboard(user_is_admin))

    except Exception as e:
        logger.exception(f"Error in /digest command: {e}")
        await message.answer(f"❌ Ошибка при получении дайджеста: {e}", reply_markup=get_main_keyboard(user_is_admin))


@dp.message(Command("history"))
async def cmd_history(message: Message) -> None:
    """Handle /history command - show digest history."""
    user_is_admin = is_admin(message.from_user.id)

    try:
        async with AsyncSessionLocal() as db:
            digests = await digest_service.get_digest_history(limit=5, db=db)

            if not digests:
                await message.answer("❌ История дайджестов пуста", reply_markup=get_main_keyboard(user_is_admin))
                return

            history_text = "📚 *История дайджестов (последние 5)*\n\n"

            for digest in digests:
                date_str = digest.date.strftime('%d.%m.%Y')
                time_str = digest.created_at.strftime('%H:%M')
                history_text += (
                    f"🗓 *{date_str}* ({time_str})\n"
                    f"   📊 {digest.news_count} новостей\n"
                    f"\n"
                )

            history_text += "\nИспользуй 📋 Дайджест для просмотра последнего"

            await message.answer(history_text, reply_markup=get_main_keyboard(user_is_admin))

    except Exception as e:
        logger.exception(f"Error in /history command: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=get_main_keyboard(user_is_admin))


@dp.message(Command("generate"))
async def cmd_generate(message: Message) -> None:
    """Handle /generate command - manually generate digest."""
    user_is_admin = is_admin(message.from_user.id)

    try:
        await message.answer("⏳ Создаю дайджест...\n\nЭто может занять 1-2 минуты.")

        async with AsyncSessionLocal() as db:
            digest = await digest_service.generate_and_save(
                db=db,
                hours=24,
                generated_by=f"user_{message.from_user.id}"
            )

            date_str = digest.date.strftime('%d.%m.%Y')

            await message.answer(
                f"✅ *Дайджест создан!*\n\n"
                f"📅 Дата: {date_str}\n"
                f"📊 Новостей: {digest.news_count}\n\n"
                f"Используй 📋 Дайджест для просмотра",
                reply_markup=get_main_keyboard(user_is_admin)
            )

    except Exception as e:
        logger.exception(f"Error in /generate command: {e}")
        await message.answer(f"❌ Ошибка при создании дайджеста: {e}", reply_markup=get_main_keyboard(user_is_admin))


@dp.message(Command("cleanup"))
async def cmd_cleanup(message: Message) -> None:
    """Handle /cleanup command - manually cleanup old digests (admin only)."""
    user_is_admin = is_admin(message.from_user.id)

    if not user_is_admin:
        await message.answer("❌ Только администратор может запускать очистку", reply_markup=get_main_keyboard(False))
        return

    try:
        await message.answer("⏳ Запускаю очистку старых дайджестов...")

        async with AsyncSessionLocal() as db:
            deleted_count = await digest_service.cleanup_old_digests(
                db=db,
                retention_days=settings.digest_retention_days
            )

            if deleted_count > 0:
                await message.answer(
                    f"✅ *Очистка завершена!*\n\n"
                    f"🗑️ Удалено дайджестов: {deleted_count}\n"
                    f"📅 Хранятся за: {settings.digest_retention_days} дней\n\n"
                    f"_Новости удалены автоматически (cascade)_",
                    reply_markup=get_main_keyboard(user_is_admin)
                )
            else:
                await message.answer(
                    f"✅ Нечего удалять!\n\n"
                    f"Все дайджесты моложе {settings.digest_retention_days} дней.",
                    reply_markup=get_main_keyboard(user_is_admin)
                )

    except Exception as e:
        logger.exception(f"Error in /cleanup command: {e}")
        await message.answer(f"❌ Ошибка при очистке: {e}", reply_markup=get_main_keyboard(user_is_admin))


# ============================================================================
# User Management (Admin Only)
# ============================================================================

@dp.message(F.text == "➕ Добавить пользователя")
async def btn_add_user(message: Message, state: FSMContext) -> None:
    """Handle 'Добавить пользователя' button - admin only."""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Только администратор может добавлять пользователей")
        return

    await message.answer(
        "👤 *Добавление нового пользователя*\n\n"
        "Отправь мне Telegram ID пользователя, которому нужно дать доступ.\n\n"
        "_Чтобы узнать ID, пользователь может написать боту @userinfobot_\n\n"
        "Или отправь /cancel для отмены."
    )

    await state.set_state(AddUserStates.waiting_for_user_id)


@dp.message(AddUserStates.waiting_for_user_id)
async def process_new_user_id(message: Message, state: FSMContext) -> None:
    """Process user ID input."""
    user_is_admin = is_admin(message.from_user.id)

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=get_main_keyboard(user_is_admin))
        return

    # Validate ID
    try:
        new_user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат!\n\n"
            "ID должен быть числом, например: 123456789\n\n"
            "Попробуй ещё раз или отправь /cancel"
        )
        return

    # Check if already exists
    current_users = get_allowed_users()
    if new_user_id in current_users:
        await state.clear()
        await message.answer(
            f"ℹ️ Пользователь `{new_user_id}` уже имеет доступ к боту!",
            reply_markup=get_main_keyboard(user_is_admin)
        )
        return

    # Save for confirmation
    await state.update_data(new_user_id=new_user_id)
    await state.set_state(AddUserStates.waiting_for_confirmation)

    await message.answer(
        f"❓ *Подтверждение*\n\n"
        f"Добавить пользователя с ID `{new_user_id}` в список разрешенных?\n\n"
        f"Он получит доступ ко всем функциям бота.\n\n"
        f"Отправь:\n"
        f"• *Да* — подтвердить\n"
        f"• *Нет* — отменить"
    )


@dp.message(AddUserStates.waiting_for_confirmation)
async def process_confirmation(message: Message, state: FSMContext) -> None:
    """Process confirmation."""
    user_is_admin = is_admin(message.from_user.id)

    answer = message.text.strip().lower()

    if answer not in ['да', 'нет', 'yes', 'no']:
        await message.answer(
            "❌ Непонятный ответ!\n\n"
            "Отправь *Да* или *Нет*"
        )
        return

    if answer in ['нет', 'no']:
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=get_main_keyboard(user_is_admin))
        return

    # Get saved user ID
    data = await state.get_data()
    new_user_id = data.get('new_user_id')

    # Add user
    success = add_user_to_allowed(new_user_id)

    await state.clear()

    if success:
        await message.answer(
            f"✅ *Пользователь добавлен!*\n\n"
            f"ID: `{new_user_id}`\n\n"
            f"Теперь он может использовать бота.",
            reply_markup=get_main_keyboard(user_is_admin)
        )
        logger.info(f"Admin {message.from_user.id} added user {new_user_id}")
    else:
        await message.answer(
            f"❌ Не удалось добавить пользователя.\n\n"
            f"Проверь логи или попробуй позже.",
            reply_markup=get_main_keyboard(user_is_admin)
        )


@dp.message(F.text == "👥 Список пользователей")
async def btn_list_users(message: Message) -> None:
    """Handle 'Список пользователей' button - admin only."""
    user_is_admin = is_admin(message.from_user.id)

    if not user_is_admin:
        await message.answer("❌ Только администратор может просматривать список")
        return

    users = get_allowed_users()

    if not users:
        await message.answer(
            "ℹ️ Список пользователей пуст",
            reply_markup=get_main_keyboard(user_is_admin)
        )
        return

    users_text = "👥 *Список пользователей с доступом:*\n\n"

    for i, uid in enumerate(users, 1):
        if i == 1:
            users_text += f"{i}. `{uid}` 👑 _(админ)_\n"
        else:
            users_text += f"{i}. `{uid}`\n"

    users_text += f"\n_Всего пользователей: {len(users)}_"

    await message.answer(users_text, reply_markup=get_main_keyboard(user_is_admin))


# ============================================================================
# Button Handlers (Reply Keyboard)
# ============================================================================

@dp.message(F.text == "📋 Дайджест")
async def btn_digest(message: Message) -> None:
    """Handle 'Дайджест' button."""
    await cmd_digest(message)


@dp.message(F.text == "📚 История")
async def btn_history(message: Message) -> None:
    """Handle 'История' button."""
    await cmd_history(message)


@dp.message(F.text == "🔄 Создать")
async def btn_generate(message: Message) -> None:
    """Handle 'Создать' button."""
    await cmd_generate(message)


@dp.message(F.text == "❓ Справка")
async def btn_help(message: Message) -> None:
    """Handle 'Справка' button."""
    await cmd_help(message)


# ============================================================================
# Main
# ============================================================================

async def setup_bot_commands(bot: Bot) -> None:
    """Setup bot commands menu (disabled - using Reply Keyboard instead)."""
    # Remove commands menu - using Reply Keyboard instead
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    logger.info("Bot commands menu removed (using Reply Keyboard)")


async def send_daily_digest() -> None:
    """Scheduled job: generate digest and send to chat."""
    logger.info("Starting automatic daily digest generation...")

    try:
        async with AsyncSessionLocal() as db:
            digest_response = await digest_service.generate_and_save(
                db=db, hours=24, generated_by="auto"
            )

        logger.info(f"Digest generated: {digest_response.news_count} items")

        # Send to Telegram chat
        text = digest_response.content_markdown
        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                await bot.send_message(
                    chat_id=settings.hr_digest_chat_id,
                    text=text[i:i+4000],
                    parse_mode="Markdown",
                )
        else:
            await bot.send_message(
                chat_id=settings.hr_digest_chat_id,
                text=text,
                parse_mode="Markdown",
            )

        logger.info("Digest sent to Telegram")

    except Exception as e:
        logger.error(f"Failed to generate/send digest: {e}", exc_info=True)


async def cleanup_old_data() -> None:
    """Scheduled job: cleanup old digests."""
    try:
        async with AsyncSessionLocal() as db:
            deleted = await digest_service.cleanup_old_digests(
                db=db, retention_days=settings.digest_retention_days
            )
            if deleted > 0:
                logger.info(f"Cleanup: {deleted} old digests removed")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)


async def start_bot() -> None:
    """Start the bot with scheduler."""
    logger.info("HR Digest Bot starting...")

    # Load users from persistent file
    load_users_from_file()

    logger.info(f"Chat ID: {settings.hr_digest_chat_id}")
    logger.info(f"Allowed users: {get_allowed_users()}")

    # Setup authentication middleware
    dp.message.middleware(AuthMiddleware())

    # Setup bot commands menu
    await setup_bot_commands(bot)

    # Clear any stale webhook/polling state
    await bot.delete_webhook(drop_pending_updates=False)

    # Setup scheduler for daily digest generation
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(
        send_daily_digest,
        trigger="cron",
        hour=8,
        minute=0,
        id="hr_digest_daily",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        cleanup_old_data,
        trigger="cron",
        hour=0,
        minute=0,
        id="hr_digest_cleanup",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("Scheduler started: digest at 08:00, cleanup at 00:00 (Tashkent)")

    try:
        logger.info("Starting polling...")
        await dp.start_polling(bot, skip_updates=False)
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        scheduler.shutdown()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(start_bot())
