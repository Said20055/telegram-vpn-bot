# tgbot/keyboards/inline.py (чистая, финальная версия)

from aiogram.utils.keyboard import InlineKeyboardBuilder
from db import Tariff  # Корректный импорт для вашей структуры
from loader import logger



def main_menu_keyboard():
    """Главная клавиатура, которая будет показываться пользователю в основном меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text='💎 Продлить / Оплатить', callback_data='buy_subscription')
    builder.button(text='👤 Мой профиль', callback_data='my_profile')
    builder.button(text='🔑 Мои ключи', callback_data='my_keys')
    builder.button(text='🤝 Реферальная программа', callback_data='referral_program')
    builder.button(text="📲 Инструкция", callback_data="instruction_info")
    builder.button(text="💬 Поддержка", callback_data="support_chat_start")
    
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
    builder.button(text="💳 Управление тарифами", callback_data="admin_tariffs_menu")
    builder.button(text="📢 Рассылка", callback_data="admin_broadcast")
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

def confirm_delete_keyboard(user_id_to_delete: int):
    """
    Клавиатура для подтверждения удаления пользователя.
    Предлагает два варианта: подтвердить или отменить.
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка для окончательного удаления. В callback_data передаем ID юзера.
    builder.button(text="✅ Да, удалить", callback_data=f"admin_confirm_delete_user_{user_id_to_delete}")
    
    # Кнопка для отмены. Возвращает админа к карточке этого же пользователя.
    builder.button(
        text="❌ Отмена", 
        callback_data=f"admin_show_user_{user_id_to_delete}"
    )
    
    builder.adjust(1) # Располагаем кнопки друг под другом для наглядности
    return builder.as_markup()

def cancel_fsm_keyboard(back_callback_data: str):
    """
    Универсальная клавиатура для отмены любого состояния FSM.
    Принимает callback_data для кнопки "Назад".
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=back_callback_data)
    return builder.as_markup()

def confirm_broadcast_keyboard():
    """Клавиатура для подтверждения рассылки."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Начать рассылку", callback_data="broadcast_start")
    builder.button(text="❌ Отмена", callback_data="admin_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def tariffs_list_keyboard(tariffs):
    """Показывает список всех тарифов с кнопкой "Добавить новый"."""
    builder = InlineKeyboardBuilder()
    for tariff in tariffs:
        status_icon = "✅" if tariff.is_active else "❌"
        builder.button(
            text=f"{status_icon} {tariff.name} - {tariff.price} RUB",
            callback_data=f"admin_manage_tariff_{tariff.id}"
        )
    builder.button(text="➕ Добавить новый тариф", callback_data="admin_add_tariff")
    builder.button(text="⬅️ Назад в админ-меню", callback_data="admin_main_menu")
    builder.adjust(1)
    return builder.as_markup()


def single_tariff_manage_keyboard(tariff_id: int, is_active: bool):
    """Клавиатура для управления одним тарифом."""
    builder = InlineKeyboardBuilder()
    
    # Кнопки для редактирования полей
    builder.button(text="✏️ Изменить название", callback_data=f"admin_edit_tariff_name_{tariff_id}")
    builder.button(text="💰 Изменить цену", callback_data=f"admin_edit_tariff_price_{tariff_id}")
    builder.button(text="⏳ Изменить срок (дни)", callback_data=f"admin_edit_tariff_duration_{tariff_id}")
    
    # Кнопка для вкл/выкл
    if is_active:
        builder.button(text="❌ Отключить", callback_data=f"admin_toggle_tariff_{tariff_id}")
    else:
        builder.button(text="✅ Включить", callback_data=f"admin_toggle_tariff_{tariff_id}")
        
    builder.button(text="🗑️ Удалить тариф", callback_data=f"admin_delete_tariff_{tariff_id}")
    builder.button(text="⬅️ Назад к списку тарифов", callback_data="admin_tariffs_menu")
    builder.adjust(1)
    return builder.as_markup()

def confirm_delete_tariff_keyboard(tariff_id: int):
    """Клавиатура для подтверждения удаления тарифа."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"admin_confirm_delete_tariff_{tariff_id}")
    builder.button(text="❌ Нет, отмена", callback_data=f"admin_manage_tariff_{tariff_id}")
    builder.adjust(1)
    return builder.as_markup()

def close_support_chat_keyboard():
    """Клавиатура для закрытия чата с поддержкой."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Завершить диалог", callback_data="support_chat_close")
    return builder.as_markup()