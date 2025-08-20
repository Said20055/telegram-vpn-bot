from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
# --- Импорты ---
from loader import logger
from database import requests as db
from marzban.init_client import MarzClientCache
from tgbot.keyboards.inline import channels_subscribe_keyboard, main_menu_keyboard
from tgbot.services.subscription import check_subscription

trial_sub_router = Router()


async def give_trial_subscription(user_id: int, bot: Bot, marzban: MarzClientCache, chat_id: int):
    """
    Создает пользователя в 3x-ui на 14 дней, обновляет БД и отправляет сообщение.
    Принимает только ID, чтобы быть полностью независимой.
    """
    trial_days = 7
    marzban_username = f"user_{user_id}"
    
    try:
        # 1. Создаем пользователя в панели 3x-ui
        result_uuid = await marzban.modify_user(username=marzban_username, expire_days=trial_days)
        if not result_uuid:
            raise Exception("MarzClient failed to create user.")

        logger.info(f"Successfully created 3x-ui user '{marzban_username}' with {trial_days} trial days for user {user_id}.")

        # 2. Обновляем нашу базу данных
        await db.update_user_marzban_username(user_id, marzban_username)
        await db.extend_user_subscription(user_id, days=trial_days)
        await db.set_user_trial_received(user_id)

        # 3. Отправляем поздравительное сообщение
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"🎉 <b>Поздравляем!</b>\n\n"
                f"Вы получили пробную подписку на <b>{trial_days} дней</b>.\n"
                "Чтобы увидеть и импортировать вашу подписку, нажмите кнопку «👤 Мой профиль» в меню ниже."
            ),
            reply_markup=main_menu_keyboard()
        )

    except Exception as e:
        logger.error(f"Failed to give trial subscription to user {user_id}: {e}", exc_info=True)
        await bot.send_message(chat_id, "❌ Произошла ошибка при активации вашего пробного периода. Пожалуйста, обратитесь в поддержку.")
        

@trial_sub_router.callback_query(F.data == "start_trial_process")
async def start_trial_process_handler(call: CallbackQuery, bot: Bot, marzban:  MarzClientCache):
    """
    Запускает процесс получения пробной подписки после нажатия на кнопку.
    Включает проверку на повторное получение.
    """
    user_id = call.from_user.id
    
    # --- НОВАЯ, ВАЖНАЯ ПРОВЕРКА ---
    # 1. Получаем пользователя из БД
    user = await db.get_user(user_id)
    
    # 2. Проверяем, получал ли он уже триал
    if user and user.has_received_trial:
        await call.answer("Вы уже использовали свой пробный период.", show_alert=True)
        # Заменяем приветственное сообщение на стандартное главное меню
        await call.message.edit_text(
            f"👋 Привет, <b>{call.from_user.full_name}</b>!",
            reply_markup=main_menu_keyboard()
        )
        return # Прерываем выполнение функции

    # --- Остальная логика остается без изменений ---
    # 3. Проверяем подписку на каналы
    is_subscribed = await check_subscription(bot, user_id)
    if is_subscribed:
        # Если подписан, сразу выдаем триал
        await call.answer("Проверка пройдена! Активируем пробный период...", show_alert=True)
        await call.message.delete()
        await give_trial_subscription(user_id, bot, marzban, call.message.chat.id)
    else:
        # Если не подписан, показываем каналы
        channels = await db.get_all_channels()
        if not channels:
            logger.warning(f"User {user_id} is starting trial, but no channels are in DB. Giving trial immediately.")
            await call.answer("Активируем пробный период...", show_alert=True)
            await call.message.delete()
            await give_trial_subscription(user_id, bot, marzban, call.message.chat.id)
            return

        keyboard = channels_subscribe_keyboard(channels)
        await call.message.edit_text(
            "❗️ <b>Для получения пробного периода, пожалуйста, подпишитесь на наши каналы.</b>\n\n"
            "После подписки нажмите кнопку «Проверить» ниже.",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

# --- ХЕНДЛЕР ДЛЯ КНОПКИ ПРОВЕРКИ ---
@trial_sub_router.callback_query(F.data == "check_subscription")
async def handle_check_subscription(call: CallbackQuery, bot: Bot, marzban: MarzClientCache):
    user_id = call.from_user.id
    
    user = await db.get_user(user_id)
    if user and user.has_received_trial:
        await call.answer("Вы уже активировали свою подписку.", show_alert=True)
        await call.message.delete()
        await call.message.answer("Воспользуйтесь главным меню.", reply_markup=main_menu_keyboard())
        return

    is_subscribed = await check_subscription(bot, user_id)

    if is_subscribed:
        await call.answer("✅ Отлично! Спасибо за подписку. Активируем пробный период...", show_alert=True)
        await call.message.delete()
        # --- ИЗМЕНЕНИЕ: Убираем bot из вызова ---
        await give_trial_subscription(user_id=user_id, bot=bot, marzban=marzban, chat_id=call.message.chat.id)
    else:
        await call.answer("Вы еще не подписались на все каналы. Пожалуйста, попробуйте снова.", show_alert=True)