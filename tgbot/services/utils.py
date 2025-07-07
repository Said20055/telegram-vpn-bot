# tgbot/services/utils.py (ПРАВИЛЬНАЯ ВЕРСИЯ)

from datetime import datetime
from marzban.init_client import MarzClientCache
from database import requests as db
from aiogram.types import CallbackQuery
# Импортируем клавиатуру напрямую, чтобы не зависеть от хендлеров
from tgbot.keyboards.inline import back_to_main_menu_keyboard
from loader import logger


def format_traffic(byte_count: int | None) -> str:
    """Красиво форматирует байты в Кб, Мб, Гб."""
    if byte_count is None:
        return "Неизвестно"
    if byte_count == 0:
        return "0 Гб"
    
    power = 1024
    n = 0
    power_labels = {0: 'Б', 1: 'Кб', 2: 'Мб', 3: 'Гб'}
    while byte_count >= power and n < len(power_labels) - 1:
        byte_count /= power
        n += 1
    return f"{byte_count:.2f} {power_labels.get(n, 'Тб')}"


async def get_marzban_user_info(call: CallbackQuery, marzban: MarzClientCache):
    """
    Универсальная функция для получения данных пользователя из БД и Marzban.
    Возвращает кортеж (user_from_db, marzban_user_object).
    В случае ошибки отправляет сообщение пользователю и возвращает (user_from_db, None).
    """
    user_id = call.from_user.id
    user = db.get_user(user_id)

    if not user or not user.marzban_username:
        await call.message.edit_text(
            "У вас еще нет активной подписки. Пожалуйста, оплатите тариф, чтобы получить доступ.",
            reply_markup=back_to_main_menu_keyboard()
        )
        return user, None

    try:
        marzban_user = await marzban.get_user(user.marzban_username)
        if not marzban_user:
            raise ValueError("User not found in Marzban panel")
        return user, marzban_user
    except Exception as e:
        logger.error(f"Failed to get user {user.marzban_username} from Marzban: {e}", exc_info=True)
        await call.message.edit_text(
            "Не удалось получить данные о вашей подписке. Пожалуйста, обратитесь в поддержку.",
            reply_markup=back_to_main_menu_keyboard()
        )
        return user, None


def get_user_attribute(user_obj, key, default=None):
    """Безопасно получает атрибут из объекта Marzban (словаря или объекта)."""
    if isinstance(user_obj, dict):
        return user_obj.get(key, default)
    return getattr(user_obj, key, default)