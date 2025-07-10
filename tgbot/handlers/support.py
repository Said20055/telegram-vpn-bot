from aiogram import Router, F, Bot, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder # Добавили
from loader import logger, config
from tgbot.filters.admin import IsAdmin 
from database import requests as db
from tgbot.keyboards.inline import close_support_chat_keyboard, main_menu_keyboard

support_router = Router()

class SupportFSM(StatesGroup):
    in_chat = State()


# --- Шаг 1: Приветственное сообщение по команде /support или кнопке ---

def support_intro_keyboard():
    """Клавиатура с одной кнопкой "Начать диалог"."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✍️ Начать диалог с поддержкой", callback_data="confirm_start_support")
    return builder.as_markup()


async def show_support_intro(event: types.Message | types.CallbackQuery):
    """Показывает приветственное сообщение поддержки."""
    text = (
        "💬 <b>Поддержка</b>\n\n"
        "Если у вас возникли вопросы или проблемы, вы можете связаться с нашей службой поддержки.\n\n"
        "Нажмите кнопку ниже, чтобы начать диалог."
    )
    reply_markup = support_intro_keyboard()

    if isinstance(event, types.CallbackQuery):
        # Если это нажатие на кнопку (например, из главного меню)
        await event.message.edit_text(text, reply_markup=reply_markup)
    else:
        # Если это команда /support
        await event.answer(text, reply_markup=reply_markup)

# Хендлер для команды /support
@support_router.message(Command("support"))
async def support_command_handler(message: types.Message):
    await show_support_intro(message)

# Хендлер для кнопки "Поддержка" из главного меню
@support_router.callback_query(F.data == "support_chat_start")
async def support_callback_handler(call: types.CallbackQuery):
    await call.answer()
    await show_support_intro(call)


# --- Шаг 2: Реальное начало диалога после подтверждения ---

@support_router.callback_query(F.data == "confirm_start_support")
async def start_support_chat(call: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    user_id = call.from_user.id
    user = db.get_user(user_id)

    if user and user.support_topic_id:
        topic_id = user.support_topic_id
        text = "Вы уже в чате с поддержкой. Просто продолжайте писать сообщения ниже."
    else:
        try:
            topic = await bot.create_forum_topic(
                chat_id=config.tg_bot.support_chat_id,
                name=f"Тикет #{user_id} | @{call.from_user.username or 'NoUsername'}"
            )
            topic_id = topic.message_thread_id
            db.set_user_support_topic(user_id, topic_id)
            
            await bot.send_message(
                chat_id=config.tg_bot.support_chat_id,
                message_thread_id=topic_id,
                text=f"👤 Пользователь <b>{call.from_user.full_name}</b> (ID: <code>{user_id}</code>) открыл новый тикет."
            )
            text = "Вы начали диалог с поддержкой. Опишите вашу проблему, и вам скоро ответят."
        except Exception as e:
            logger.error(f"Failed to create support topic for user {user_id}: {e}")
            await call.answer("Не удалось создать чат с поддержкой. Попробуйте позже.", show_alert=True)
            return

    await call.message.edit_text(text, reply_markup=close_support_chat_keyboard())
    await state.set_state(SupportFSM.in_chat)
    await call.answer()

@support_router.callback_query(F.data == "support_chat_close", SupportFSM.in_chat)
async def close_support_chat_by_user(call: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    user_id = call.from_user.id
    user = db.get_user(user_id)
    
    if user and user.support_topic_id:
        await bot.send_message(
            chat_id=config.tg_bot.support_chat_id,
            message_thread_id=user.support_topic_id,
            text="💬 Пользователь завершил диалог."
        )
    
    db.clear_user_support_topic(user_id)
    await call.message.edit_text("Диалог с поддержкой завершен.", reply_markup=main_menu_keyboard())

@support_router.message(SupportFSM.in_chat)
async def user_message_to_support_topic(message: Message, bot: Bot, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not user or not user.support_topic_id:
        await state.clear()
        await message.answer("Произошла ошибка. Пожалуйста, начните чат с поддержкой заново.", reply_markup=main_menu_keyboard())
        return

    await message.forward(
        chat_id=config.tg_bot.support_chat_id,
        message_thread_id=user.support_topic_id
    )

# --- НОВЫЙ БЛОК: ОБРАБОТКА ОТВЕТОВ ИЗ ГРУППЫ ПОДДЕРЖКИ ---
@support_router.message(
    F.chat.id == config.tg_bot.support_chat_id, 
    F.message_thread_id,
    Command("close") # <--- Ловим именно команду
)
async def admin_close_topic_command(message: Message, bot: Bot):
    """Закрывает тикет по команде /close."""
    user_to_reply = db.get_user_by_support_topic(message.message_thread_id)
    if not user_to_reply:
        await message.reply("Не удалось найти пользователя для этой темы.")
        return

    try:
        await bot.send_message(
            user_to_reply.user_id, 
            "Оператор поддержки завершил ваш диалог. Если у вас возникнут новые вопросы, вы всегда можете открыть новый тикет."
        )
    except Exception as e:
        logger.warning(f"Could not send '/close' notification to user {user_to_reply.user_id}: {e}")
    
    db.clear_user_support_topic(user_to_reply.user_id)
    await bot.close_forum_topic(config.tg_bot.support_chat_id, message.message_thread_id)
    await message.reply("✅ Тикет успешно закрыт.")


# --- Хендлер №2: Для всех остальных сообщений от админа (НИЗШИЙ ПРИОРИТЕТ) ---
@support_router.message(
    F.chat.id == config.tg_bot.support_chat_id, 
    F.message_thread_id
)
async def admin_reply_to_user_from_topic(message: Message, bot: Bot):
    """Пересылает ответ админа пользователю."""
    # Проверка на сообщения от бота, чтобы не было циклов
    if message.from_user.id == bot.id:
        return

    user_to_reply = db.get_user_by_support_topic(message.message_thread_id)
    if not user_to_reply:
        return

    # --- Упрощенная и надежная логика пересылки ---
    try:
        # Просто копируем сообщение. Это самый универсальный способ.
        # Если возникнет ошибка "can't be copied", это будет означать, 
        # что админ пытается переслать что-то специфическое (например, опрос).
        await message.copy_to(chat_id=user_to_reply.user_id)
    except Exception as e:
        logger.error(f"Failed to send admin's reply to user {user_to_reply.user_id}: {e}", exc_info=True)
        await message.reply(f"❌ Не удалось отправить ответ пользователю. Ошибка: {e}")