# tgbot/keyboards/inline.py (чистая, финальная версия)

import logging
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db import Tariff  # Корректный импорт для вашей структуры

logger = logging.getLogger(__name__)


def main_menu_keyboard():
    """Главная клавиатура, которая будет показываться пользователю в основном меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text='💎 Продлить / Оплатить', callback_data='buy_subscription')
    builder.button(text='👤 Мой профиль', callback_data='my_profile')
    builder.button(text='🔑 Мои ключи', callback_data='my_keys')
    builder.button(text='🤝 Реферальная программа', callback_data='referral_program')
    builder.button(text='ℹ️ Помощь', callback_data='help_info')
    
    # Расставляем кнопки: 1, 2, 2. Выглядит аккуратно.
    builder.adjust(1, 2, 2)
    return builder.as_markup()


def tariffs_keyboard(tariffs: list[Tariff]):
    """Создает клавиатуру со списком тарифов."""
    builder = InlineKeyboardBuilder()
    for tariff in tariffs:
        # В callback_data передаем ID тарифа
        builder.button(
            text=f"{tariff.name} - {tariff.price} RUB",
            callback_data=f"select_tariff_{tariff.id}"
        )
    builder.button(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu")
    builder.adjust(1) # Каждый тариф на новой строке для лучшей читаемости
    return builder.as_markup()


def profile_keyboard():
    """Клавиатура для раздела "Мой профиль"."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔑 Мои ключи", callback_data="my_keys")
    builder.button(text="🔄 Обновить", callback_data="my_profile")
    builder.button(text="⬅️ Назад в меню", callback_data="back_to_main_menu")
    builder.adjust(1)
    return builder.as_markup()
    

def help_keyboard():
    """Клавиатура для раздела "Помощь" со ссылкой на инструкции."""
    builder = InlineKeyboardBuilder()
    builder.button(text='Клиенты для подключения', url='https://marzban-docs.sm1ky.com/start/reality_app/')
    builder.button(text='⬅️ Назад в главное меню', callback_data='back_to_main_menu')
    builder.adjust(1)
    return builder.as_markup()


def back_to_main_menu_keyboard():
    """Простая клавиатура с одной кнопкой "Назад в главное меню"."""
    builder = InlineKeyboardBuilder()
    builder.button(text='⬅️ Назад в главное меню', callback_data='back_to_main_menu')
    return builder.as_markup()

def admin_main_menu_keyboard():
    """Главное меню админ-панели."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Управление пользователями", callback_data="admin_users_menu")
    builder.button(text="📈 Статистика", callback_data="admin_stats")
    # Добавим позже:
    # builder.button(text="💳 Управление тарифами", callback_data="admin_tariffs_menu")
    # builder.button(text="📢 Рассылка", callback_data="admin_broadcast")
    builder.adjust(1)
    return builder.as_markup()

def user_manage_keyboard(user_id: int):
    """Клавиатура для управления конкретным пользователем."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Добавить дни", callback_data=f"admin_add_days_{user_id}")
    builder.button(text="🔄 Сбросить ключ", callback_data=f"admin_reset_user_{user_id}")
    builder.button(text="🗑 Удалить пользователя", callback_data=f"admin_delete_user_{user_id}")
    builder.button(text="⬅️ Назад к поиску", callback_data="admin_users_menu")
    builder.adjust(1)
    return builder.as_markup()