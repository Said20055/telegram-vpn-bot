# tgbot/handlers/user/profile.py
import asyncio
from aiogram import Router, F, types, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest
from aiohttp.client_exceptions import ClientConnectionError
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from urllib.parse import urlparse
from datetime import datetime

from loader import logger
from marzban.init_client import MarzClientCache
from tgbot.keyboards.inline import profile_keyboard, back_to_main_menu_keyboard, single_key_view_keyboard
from tgbot.services import qr_generator
from tgbot.services.utils import format_traffic, get_marzban_user_info, get_user_attribute
from urllib.parse import quote_plus

profile_router = Router()


# --- 1. Создаем ОБЩУЮ функцию для показа профиля ---
async def show_profile_logic(event: Message | CallbackQuery, marzban: MarzClientCache, bot: Bot):
    """
    Универсальная логика для отображения профиля пользователя.
    Адаптирована для вызова из webhook_handler.
    """
    
    # Получаем ID пользователя и объект бота из события
    user_id = event.from_user.id

    
    # Получаем информацию о пользователе
    db_user, marzban_user = await get_marzban_user_info(event, marzban)
    if not marzban_user:
        return

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

# --- Хендлер для "Мои ключи" (остается почти без изменений) ---
@profile_router.callback_query(F.data == "my_keys")
async def my_keys_handler(call: CallbackQuery, marzban: MarzClientCache):
    """
    Показывает меню с кнопками для каждого ключа,
    объединяя информацию об узлах и протоколах. (Адаптировано под API, возвращающее список)
    """
    await call.answer("Загружаю список ключей...")
    
    db_user, marzban_user = await get_marzban_user_info(call, marzban)
    if not marzban_user: return

    links = get_user_attribute(marzban_user, 'links', [])
    if not links:
        # ... (обработка, если ключей нет)
        return
        
    # --- ИСПРАВЛЕННАЯ ЛОГИКА ---
    
    # 1. Параллельно получаем все необходимые данные
    nodes, inbounds_list = await asyncio.gather(
        marzban.get_nodes(),
        marzban.get_inbounds() # Этот метод теперь должен возвращать СПИСОК
    )

    # 2. Создаем карты для быстрого поиска
    address_to_name_map = {node['address']: node['name'] for node in nodes}
    main_domain = marzban._config.webhook.domain
    if main_domain not in address_to_name_map:
        address_to_name_map[main_domain] = "Основной сервер"
        
    # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
    # Создаем карту портов, итерируясь по СПИСКУ inbounds_list
    port_to_protocol_map = {}
    for inbound_data in inbounds_list:
        if isinstance(inbound_data, dict):
            port = str(inbound_data.get('port'))
            protocol = inbound_data.get('protocol', 'protocol?').upper()
            port_to_protocol_map[port] = protocol
    
    # 3. Создаем клавиатуру (этот блок остается без изменений)
    keys_keyboard = InlineKeyboardBuilder()
    
    for i, link in enumerate(links):
        try:
            parsed_url = urlparse(link)
            server_address = parsed_url.hostname or parsed_url.netloc.split('@')[-1].split(':')[0]
            server_port = str(parsed_url.port or parsed_url.netloc.split(':')[-1])
        except Exception:
            server_address, server_port = "unknown", "unknown"
            
        node_name = address_to_name_map.get(server_address, "Неизвестный узел")
        protocol_name = port_to_protocol_map.get(server_port, "")
        
        button_text = f"🔑 {node_name}"
        if protocol_name:
            button_text += f" ({protocol_name})"
        
        keys_keyboard.button(text=button_text, callback_data=f"show_key_{i}")
        
    keys_keyboard.button(text="⬅️ Назад в профиль", callback_data="my_profile")
    keys_keyboard.adjust(1)
        
    text = "🔑 <b>Ваши ключи</b>\n\nВыберите сервер и протокол для просмотра ключа:"
    
    try:
        await call.message.edit_text(text, reply_markup=keys_keyboard.as_markup())
    except TelegramBadRequest: # Если старое сообщение было с фото
        await call.message.delete()
        await call.message.answer(text, reply_markup=keys_keyboard.as_markup())

@profile_router.callback_query(F.data.startswith("show_key_"))
async def show_single_key_handler(call: CallbackQuery, marzban: MarzClientCache):
    """Показывает выбранный ключ, снова запрашивая данные."""
    await call.answer()
    
    try:
        key_index = int(call.data.split("_")[2])
        
        # Снова делаем запрос к Marzban, чтобы получить свежие данные
        db_user, marzban_user = await get_marzban_user_info(call, marzban)
        if not marzban_user: return
        
        links = get_user_attribute(marzban_user, 'links', [])
        selected_key = links[key_index]

        text = (
            f"🔑 <b>Ваш ключ #{key_index + 1}</b>\n\n"
            "Нажмите на ключ, чтобы скопировать его:\n\n"
            f"<code>{selected_key}</code>"
        )
        await call.message.edit_text(text, reply_markup=single_key_view_keyboard())

    except (IndexError, ValueError, TypeError):
        await call.answer("Произошла ошибка, ключ не найден. Попробуйте снова.", show_alert=True)