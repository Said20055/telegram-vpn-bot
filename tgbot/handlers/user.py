# tgbot/handlers/user.py (финальная, чистая версия с HTML)

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiohttp.client_exceptions import ClientConnectionError

# --- Импорты ---
from datetime import datetime
from loader import logger
from database import requests as db
from marzban.init_client import MarzClientCache

# Импортируем клавиатуры
from tgbot.keyboards.inline import (
    main_menu_keyboard,
    help_keyboard,
    back_to_main_menu_keyboard,
    tariffs_keyboard,
    profile_keyboard
)

# Импортируем сервисы
from tgbot.services import payment
from tgbot.services import qr_generator
from tgbot.services.utils import format_traffic, get_marzban_user_info, get_user_attribute


user_router = Router()


# =============================================================================
# --- БЛОК: СТАРТ БОТА И РЕФЕРАЛЬНАЯ СИСТЕМА ---
# =============================================================================

@user_router.message(CommandStart(deep_link=True, magic=F.args.startswith('ref')))
async def start_with_referral(message: Message, command: CommandObject, bot: Bot):
    """Обрабатывает запуск бота по реферальной ссылке."""
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username
    
    referrer_id = None
    try:
        potential_referrer_id = int(command.args[3:])
        if potential_referrer_id != user_id and db.get_user(potential_referrer_id):
            referrer_id = potential_referrer_id
    except (ValueError, IndexError, TypeError):
        pass

    user, created = db.get_or_create_user(user_id, full_name, username)

    if created and referrer_id:
        db.set_user_referrer(user_id, referrer_id)
        db.add_bonus_days(user_id, 3)
        await message.answer("🎉 Добро пожаловать! Вы пришли по приглашению и получили <b>3 бонусных дня</b> подписки!")
        try:
            await bot.send_message(referrer_id, f"По вашей ссылке зарегистрировался новый пользователь: {full_name}!")
        except Exception as e:
            logger.error(f"Could not send notification to referrer {referrer_id}: {e}")
    elif not created:
        await message.answer("Вы уже зарегистрированы в боте. Реферальная ссылка работает только для новых пользователей.")

    await message.answer(f'👋 Привет, {full_name}!', reply_markup=main_menu_keyboard())


@user_router.message(CommandStart())
async def user_start_default(message: Message):
    """Обрабатывает обычный запуск бота командой /start."""
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username
    db.get_or_create_user(user_id, full_name, username)
    
    await message.answer(
        f'👋 Привет, {full_name}!\n\n'
        'Я помогу тебе с VPN.\n'
        'Исходный код бота - <a href="https://github.com/yarodya1/telegram-vpn-bot">GitHub</a>',
        reply_markup=main_menu_keyboard(), disable_web_page_preview=True
    )


# =============================================================================
# --- БЛОК: ОСНОВНЫЕ РАЗДЕЛЫ МЕНЮ ---
# =============================================================================

@user_router.callback_query(F.data == 'help_info')
async def help_callback_handler(callback_query: CallbackQuery):
    """Показывает раздел помощи."""
    await callback_query.answer()
    text = (
        'ℹ️ <b>Помощь и информация</b>\n\n'
        'Бот предоставляет доступ к VPN на базе '
        '<a href="https://github.com/XTLS/Xray-core">Xray-core</a> и созданный с использованием Python.\n\n'
        'Для подключения используйте один из рекомендованных клиентов:'
    )
    # Используем edit_text, чтобы не слать новое сообщение, а менять старое
    await callback_query.message.edit_text(text, reply_markup=help_keyboard(), disable_web_page_preview=True)


@user_router.callback_query(F.data == "referral_program")
async def referral_program_handler(call: CallbackQuery, bot: Bot):
    """Показывает информацию о реферальной программе."""
    await call.answer()
    user_id = call.from_user.id
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref{user_id}"
    user_data = db.get_user(user_id)
    referral_count = db.count_user_referrals(user_id)
    
    text = (
        "🤝 <b>Ваша реферальная программа</b>\n\n"
        "Приглашайте друзей и получайте за это приятные бонусы!\n\n"
        "🔗 <b>Ваша персональная ссылка для приглашений:</b>\n"
        f"<code>{referral_link}</code>\n"
        "<i>(нажмите, чтобы скопировать)</i>\n\n"
        f"👤 <b>Вы пригласили:</b> {referral_count} чел.\n"
        f"🎁 <b>Ваши бонусные дни:</b> {user_data.referral_bonus_days} дн.\n\n"
        "Вы будете получать <b>7 бонусных дней</b> за каждую первую оплату подписки вашим другом."
    )
    await call.message.edit_text(text, reply_markup=back_to_main_menu_keyboard())


@user_router.callback_query(F.data == "my_profile")
async def my_profile_handler(call: CallbackQuery, marzban: MarzClientCache):
    """Показывает профиль пользователя с данными из Marzban и QR-кодом."""
    await call.answer("Загружаю информацию...")
    
    db_user, marzban_user = await get_marzban_user_info(call, marzban)
    if not marzban_user:
        return

    status = get_user_attribute(marzban_user, 'status', 'unknown')
    expire_ts = get_user_attribute(marzban_user, 'expire')
    expire_date = datetime.fromtimestamp(expire_ts).strftime('%d.%m.%Y %H:%M') if expire_ts else "Никогда"
    
    used_traffic = get_user_attribute(marzban_user, 'used_traffic', 0)
    data_limit = get_user_attribute(marzban_user, 'data_limit')
    used_traffic_str = format_traffic(used_traffic)
    data_limit_str = "Безлимит" if data_limit == 0 or data_limit is None else format_traffic(data_limit)

    sub_url = get_user_attribute(marzban_user, 'subscription_url', '')
    full_sub_url = f"https://{marzban._config.webhook.domain}{sub_url}" if sub_url else ""

    profile_text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🔑 <b>Статус:</b> <code>{status}</code>\n"
        f"🗓 <b>Подписка активна до:</b> <code>{expire_date}</code>\n\n"
        f"📊 <b>Трафик:</b>\n"
        f"Использовано: <code>{used_traffic_str}</code>\n"
        f"Лимит: <code>{data_limit_str}</code>\n\n"
        f"🔗 <b>Ссылка для подписки (нажмите, чтобы скопировать):</b>\n<code>{full_sub_url}</code>"
    )

    try:
        full_sub_url = get_user_attribute(marzban_user, 'subscription_url', '')
        if not full_sub_url:
            raise ValueError("Subscription URL is empty, can't generate QR code.")
        
        # Marzban возвращает относительный URL, делаем его полным
        full_sub_url = f"https://{marzban._config.webhook.domain}{full_sub_url}"

        # --- ИСПРАВЛЕННАЯ ЛОГИКА ---
        qr_code_stream = qr_generator.create_qr_code(full_sub_url)
        qr_photo = BufferedInputFile(qr_code_stream.getvalue(), filename="qr.png")
        
        # Сначала удаляем старое сообщение, чтобы избежать конфликтов
        await call.message.delete()
        # Отправляем новое с фото
        await call.message.answer_photo(photo=qr_photo, caption=profile_text, reply_markup=profile_keyboard())

    except (ClientConnectionError, TelegramBadRequest) as e:
            logger.error(f"Network or Telegram API error while sending profile: {e}", exc_info=True)
        # Если отправка с фото не удалась из-за сети или API, отправим просто текст
            await call.message.answer(profile_text, reply_markup=profile_keyboard())
    except Exception as e:
        logger.error(f"Generic error while sending profile with QR code: {e}", exc_info=True)
        # На случай других ошибок (например, пустой URL)
    await call.message.edit_text(profile_text, reply_markup=profile_keyboard())


# tgbot/handlers/user.py (исправленный my_keys_handler)

@user_router.callback_query(F.data == "my_keys")
async def my_keys_handler(call: CallbackQuery, marzban: MarzClientCache):
    """Показывает пользователю его ключи для подключения."""
    await call.answer()
    
    db_user, marzban_user = await get_marzban_user_info(call, marzban)
    if not marzban_user:
        return

    links = get_user_attribute(marzban_user, 'links', [])

    if not links:
        # --- ИСПРАВЛЕННАЯ ЛОГИКА ОТПРАВКИ ---
        text = "К сожалению, для вашей подписки не найдено ключей. Обратитесь в поддержку."
        reply_markup = back_to_main_menu_keyboard()
        try:
            await call.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest:
            await call.message.delete()
            await call.message.answer(text, reply_markup=reply_markup)
        return

    formatted_links = [f"<code>{link}</code>" for link in links]
    message_text = (
        "🔑 <b>Вот ваши ключи для подключения:</b>\n\n"
        "<i>Нажмите на ключ, чтобы скопировать его, а затем вставьте в вашем VPN-клиенте.</i>\n\n" +
        "\n\n".join(formatted_links)
    )

    # --- ИСПРАВЛЕННАЯ ЛОГИКА ОТПРАВКИ ---
    reply_markup = back_to_main_menu_keyboard()
    try:
        # Пытаемся изменить текущее сообщение (с фото) на новое текстовое
        await call.message.edit_text(
            text=message_text,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except TelegramBadRequest:
        # Если не получилось (потому что это было фото), удаляем старое и шлем новое
        try:
            await call.message.delete()
        except TelegramBadRequest:
            pass # Если не можем удалить - не страшно
        await call.message.answer(
            text=message_text,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
# =============================================================================
# --- БЛОК: ПОКУПКА И ОПЛАТА ---
# =============================================================================

@user_router.callback_query(F.data == "buy_subscription")
async def buy_subscription_handler(call: CallbackQuery):
    """Показывает пользователю доступные тарифы."""
    await call.answer()
    active_tariffs = db.get_active_tariffs()
    tariffs_list = list(active_tariffs) if active_tariffs else []
        
    if not tariffs_list:
        logger.error("No active tariffs found for user %s.", call.from_user.id)
        await call.message.edit_text(
            "К сожалению, сейчас нет доступных тарифов для покупки. Попробуйте позже.",
            reply_markup=back_to_main_menu_keyboard()
        )
        return
        
    await call.message.edit_text(
        "Пожалуйста, выберите тарифный план:",
        reply_markup=tariffs_keyboard(tariffs_list)
    )


@user_router.callback_query(F.data.startswith("select_tariff_"))
async def select_tariff_handler(call: CallbackQuery, bot: Bot):
    """Обрабатывает выбор тарифа и генерирует ссылку на оплату."""
    await call.answer()
    try:
        tariff_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        await call.message.edit_text("Ошибка! Некорректный тариф.", reply_markup=back_to_main_menu_keyboard())
        return
    
    tariff = db.get_tariff_by_id(tariff_id)
    if not tariff:
        await call.message.edit_text("Ошибка! Тариф не найден.", reply_markup=back_to_main_menu_keyboard())
        return

    payment_url, _ = payment.create_payment(
        user_id=call.from_user.id,
        amount=tariff.price,
        description=f"Оплата тарифа '{tariff.name}'",
        bot_username=(await bot.get_me()).username,
        metadata={'user_id': str(call.from_user.id), 'tariff_id': tariff_id}
    )
    
    payment_kb = InlineKeyboardBuilder()
    payment_kb.button(text="💳 Перейти к оплате", url=payment_url)
    payment_kb.button(text="⬅️ Назад к выбору тарифа", callback_data="buy_subscription")
    payment_kb.adjust(1)
    
    await call.message.edit_text(
        f"Вы выбрали тариф: <b>{tariff.name}</b>\n"
        f"Срок: <b>{tariff.duration_days} дней</b>\n"
        f"Сумма к оплате: <b>{tariff.price} RUB</b>\n\n"
        "Нажмите на кнопку ниже, чтобы перейти к оплате.",
        reply_markup=payment_kb.as_markup()
    )


# =============================================================================
# --- БЛОК: ВСПОМОГАТЕЛЬНЫЕ ХЕНДЛЕРЫ ---
# =============================================================================

@user_router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu_handler(call: CallbackQuery):
    """Возвращает пользователя в главное меню."""
    await call.answer()
    text = f'👋 Привет, {call.from_user.full_name}!'
    reply_markup = main_menu_keyboard()
    
    try:
        await call.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try:
            await call.message.delete()
        except TelegramBadRequest:
            pass
        await call.message.answer(text, reply_markup=reply_markup)