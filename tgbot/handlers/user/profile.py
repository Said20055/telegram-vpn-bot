# tgbot/handlers/user/profile.py
from aiogram import Router, F, types, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from datetime import datetime

from loader import logger
from marzban.init_client import MarzClientCache
from tgbot.keyboards.inline import profile_keyboard, back_to_main_menu_keyboard, keys_screen_keyboard
from tgbot.services import qr_generator, profile_service, payment_service
from tgbot.services.utils import format_traffic, get_user_attribute
from utils.url import build_import_url

profile_router = Router()


# --- 1. Создаем ОБЩУЮ функцию для показа профиля ---
async def show_profile_logic(event: Message | CallbackQuery, marzban: MarzClientCache, bot: Bot):
    """
    Универсальная логика для отображения профиля пользователя.
    Адаптирована для вызова из webhook_handler.
    """

    # Получаем ID пользователя и объект бота из события
    user_id = event.from_user.id


    # Получаем информацию о пользователе через сервис
    profile_data = await profile_service.get_profile(user_id)
    if profile_data.error:
        text = profile_data.error
        reply_markup = back_to_main_menu_keyboard()
        if isinstance(event, types.CallbackQuery):
            try:
                await event.message.edit_text(text, reply_markup=reply_markup)
            except TelegramBadRequest:
                await event.message.delete()
                await event.message.answer(text, reply_markup=reply_markup)
        else:
            await event.answer(text, reply_markup=reply_markup)
        return

    marzban_user = profile_data.marzban_user

    # --- Форматирование данных (ваш код) ---
    status = get_user_attribute(marzban_user, 'status', 'unknown')
    expire_ts = get_user_attribute(marzban_user, 'expire')
    expire_date = datetime.fromtimestamp(expire_ts).strftime('%d.%m.%Y %H:%M') if expire_ts else "Никогда"

    used_traffic = get_user_attribute(marzban_user, 'used_traffic', 0)
    data_limit = get_user_attribute(marzban_user, 'data_limit')
    used_traffic_str = format_traffic(used_traffic)
    data_limit_str = "Безлимит" if data_limit == 0 or data_limit is None else format_traffic(data_limit)

    sub_url = get_user_attribute(marzban_user, 'subscription_url', '')
    full_sub_url = f"https://{marzban._config.webhook.domain}:8443{sub_url}" if sub_url else ""

    profile_text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🔑 <b>Статус:</b> <code>{status}</code>\n"
        f"🗓 <b>Подписка активна до:</b> <code>{expire_date}</code>\n\n"
        f"📊 <b>Трафик:</b>\n"
        f"Использовано: <code>{used_traffic_str}</code>\n"
        f"Лимит: <code>{data_limit_str}</code>\n\n"
        f"🔗 <b>Ссылка для подписки (нажмите, чтобы скопировать):</b>\n<code>{full_sub_url}</code>"
    )

    # --- Отправка ответа с QR-кодом ---
    try:
        qr_code_stream = qr_generator.create_qr_code(full_sub_url)
        qr_photo = types.BufferedInputFile(qr_code_stream.getvalue(), filename="qr.png")

        # --- ИСПРАВЛЕННАЯ ЛОГИКА ОТПРАВКИ ---

        # Если это было нажатие на кнопку, пытаемся удалить старое сообщение
        if isinstance(event, types.CallbackQuery):
            try:
                await event.message.delete()
            except TelegramBadRequest:
                pass # Игнорируем, если не получилось

        # Отправляем новое сообщение с фото напрямую через объект bot
        await bot.send_photo(
            chat_id=user_id,
            photo=qr_photo,
            caption=profile_text,
            reply_markup=profile_keyboard(full_sub_url)
        )

    except Exception as e:
        logger.error(f"Error sending profile with QR: {e}", exc_info=True)
        # Если что-то пошло не так, отправляем просто текст

        # --- ИСПРАВЛЕННАЯ ЛОГИКА ОТПРАВКИ ---
        await bot.send_message(
            chat_id=user_id,
            text=profile_text,
            reply_markup=profile_keyboard(full_sub_url)
        )


# --- 2. Хендлеры для команды и кнопки ---
@profile_router.message(Command("profile"))
async def profile_command_handler(message: Message, marzban: MarzClientCache, bot: Bot):
    await show_profile_logic(message, marzban, bot)

@profile_router.callback_query(F.data == "my_profile")
async def my_profile_callback_handler(call: CallbackQuery, marzban: MarzClientCache, bot: Bot):
    await call.answer("Загружаю информацию...")
    await show_profile_logic(call, marzban, bot)

# --- Хендлер для "Мои ключи" — упрощённый экран с импортом ---
@profile_router.callback_query(F.data == "my_keys")
async def my_keys_handler(call: CallbackQuery):
    """Показывает subscription URL и кнопку импорта в Happ."""
    await call.answer("Загружаю данные...")

    profile_data = await profile_service.get_profile(call.from_user.id)
    if profile_data.error or not profile_data.marzban_user:
        error_text = profile_data.error or "Не удалось получить данные подписки."
        try:
            await call.message.edit_text(error_text, reply_markup=back_to_main_menu_keyboard())
        except TelegramBadRequest:
            await call.message.delete()
            await call.message.answer(error_text, reply_markup=back_to_main_menu_keyboard())
        return

    marzban_user = profile_data.marzban_user
    sub_url = get_user_attribute(marzban_user, 'subscription_url', '')
    domain = profile_service._marzban._config.webhook.domain
    full_sub_url = f"https://{domain}:8443{sub_url}" if sub_url else ""

    if not full_sub_url:
        error_text = "❌ Ссылка для подключения недоступна. Обратитесь в поддержку."
        try:
            await call.message.edit_text(error_text, reply_markup=back_to_main_menu_keyboard())
        except TelegramBadRequest:
            await call.message.delete()
            await call.message.answer(error_text, reply_markup=back_to_main_menu_keyboard())
        return

    text = (
        "🔑 <b>Ваши ключи VPN</b>\n\n"
        "Для автоматического подключения нажмите кнопку ниже.\n"
        "Или скопируйте ссылку для ручной настройки:\n\n"
        f"<code>{full_sub_url}</code>"
    )
    try:
        await call.message.edit_text(text, reply_markup=keys_screen_keyboard(build_import_url(full_sub_url)))
    except TelegramBadRequest:
        await call.message.delete()
        await call.message.answer(text, reply_markup=keys_screen_keyboard(build_import_url(full_sub_url)))


# --- Хендлер для истории платежей пользователя ---
@profile_router.callback_query(F.data == "my_payments")
async def my_payments_handler(call: CallbackQuery):
    """Показывает историю платежей пользователя."""
    await call.answer("Загружаю историю платежей...")
    user_id = call.from_user.id

    payments = await payment_service.get_user_payments(user_id)

    if not payments:
        try:
            await call.message.edit_text(
                "💳 <b>Мои платежи</b>\n\n"
                "У вас пока нет платежей.",
                reply_markup=back_to_main_menu_keyboard()
            )
        except TelegramBadRequest:
            await call.message.delete()
            await call.message.answer(
                "💳 <b>Мои платежи</b>\n\nУ вас пока нет платежей.",
                reply_markup=back_to_main_menu_keyboard()
            )
        return

    status_labels = {
        'pending': '⏳ Ожидает', 'succeeded': '✅ Оплачен', 'failed': '❌ Ошибка',
        'refunded': '💸 Возврат', 'cancelled': '🚫 Отменён'
    }

    lines = ["💳 <b>Мои платежи</b>\n"]
    for p in payments[:10]:
        label = status_labels.get(p.status, p.status)
        date_str = p.created_at.strftime('%d.%m.%Y') if p.created_at else '—'
        discount_info = f" (скидка {p.discount_percent}%)" if p.discount_percent else ""
        lines.append(f"{label} | {date_str} | <b>{p.final_amount:.2f} RUB</b>{discount_info}")

    try:
        await call.message.edit_text("\n".join(lines), reply_markup=back_to_main_menu_keyboard())
    except TelegramBadRequest:
        await call.message.delete()
        await call.message.answer("\n".join(lines), reply_markup=back_to_main_menu_keyboard())
