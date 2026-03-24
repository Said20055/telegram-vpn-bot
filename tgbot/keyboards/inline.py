# tgbot/keyboards/inline.py

from typing import List
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardMarkup

# Импортируем модели только для аннотации типов, чтобы избежать циклических импортов
from db import Tariff, PromoCode, Channel
from utils.url import build_import_url


# =============================================================================
# === 1. КЛАВИАТУРЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ (ОСНОВНОЕ МЕНЮ) ===
# =============================================================================

def main_menu_keyboard(has_active_sub: bool = True, has_email: bool = True) -> InlineKeyboardMarkup:
    """Главная клавиатура пользователя. Условные кнопки зависят от статуса подписки и email."""
    builder = InlineKeyboardBuilder()
    builder.button(text='💎 Оплатить', callback_data='buy_subscription')
    builder.button(text='🛜 Подключиться', callback_data='my_keys')
    builder.button(text='👥 Пригласить друга', callback_data='referral_program')
    builder.button(text="💬 Поддержка", callback_data="support_chat_start")
    rows = [1, 1, 2]
    if not has_active_sub:
        builder.button(text="🌟 Бесплатная подписка", callback_data="start_trial_process")
        rows.append(1)
    if not has_email:
        builder.button(text="📧 Привязать Email", callback_data="link_email")
        rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def onboarding_subscribe_keyboard(channels: List[Channel]) -> InlineKeyboardMarkup:
    """Клавиатура для первого шага онбординга — подписка на каналы."""
    builder = InlineKeyboardBuilder()
    for i, channel in enumerate(channels):
        builder.button(text=f"📢 {channel.title}", url=channel.invite_link)
    builder.button(text="✅ Я подписался, продолжить", callback_data="onboarding_check_sub")
    builder.adjust(1)
    return builder.as_markup()


def onboarding_download_app_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для второго шага — скачать приложение Happ."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 iOS (App Store)", url="https://apps.apple.com/app/happ-proxy-utility/id6504287215")
    builder.button(text="🤖 Android (Google Play)", url="https://play.google.com/store/apps/details?id=com.happproxy.app")
    builder.button(text="➡️ Приложение установлено", callback_data="onboarding_app_installed")
    builder.adjust(2, 1)
    return builder.as_markup()


def onboarding_import_keyboard(subscription_url: str) -> InlineKeyboardMarkup:
    """Клавиатура для третьего шага — импорт подключения в Happ."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📲 Подключить VPN в Happ", url=build_import_url(subscription_url))
    builder.button(text="➡️ Перейти в главное меню", callback_data="back_to_main_menu")
    builder.adjust(1)
    return builder.as_markup()


def profile_keyboard(subscription_url: str) -> InlineKeyboardMarkup:
    """Клавиатура для раздела "Мой профиль" с полным набором действий."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📲 Импортировать в Happ", url=build_import_url(subscription_url))
    builder.button(text="🔄 Обновить", callback_data="my_profile")
    builder.button(text="⬅️ Назад в меню", callback_data="back_to_main_menu")
    builder.adjust(1)
    return builder.as_markup()


def simple_profile_keyboard() -> InlineKeyboardMarkup:
    """Простая клавиатура профиля."""
    builder = InlineKeyboardBuilder()
    builder.button(text='👤 Мой профиль', callback_data='my_profile')
    return builder.as_markup()


def tariffs_keyboard(tariffs: list[Tariff], promo_procent: int = 0) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком тарифов для покупки."""
    builder = InlineKeyboardBuilder()
    if promo_procent > 0:
        for tariff in tariffs:
            discounted_price = int(tariff.price * (1-promo_procent / 100))
            builder.button(
                text=f"{tariff.name} - {discounted_price} RUB (скидка {promo_procent}%)",
                callback_data=f"select_tariff_{tariff.id}"
            )
    else:
        for tariff in tariffs:
            builder.button(
                text=f"{tariff.name} - {tariff.price} RUB",
                callback_data=f"select_tariff_{tariff.id}"
            )
        builder.button(text="🎁 У меня есть промокод", callback_data="enter_promo_code")
    builder.button(text="💳 История платежей", callback_data="my_payments")
    builder.button(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu")
    builder.adjust(1)
    return builder.as_markup()


def keys_screen_keyboard(import_url: str) -> InlineKeyboardMarkup:
    """Клавиатура экрана 'Мои ключи': импорт в Happ, инструкция, назад."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📲 Импортировать в Happ", url=import_url)
    builder.button(text="📖 Инструкция", callback_data="instruction_info")
    builder.button(text="⬅️ Назад в меню", callback_data="back_to_main_menu")
    builder.adjust(1)
    return builder.as_markup()


def channels_subscribe_keyboard(channels: List[Channel]) -> InlineKeyboardMarkup:
    """Создает клавиатуру со ссылками на каналы и кнопкой проверки."""
    builder = InlineKeyboardBuilder()
    for i, channel in enumerate(channels):
        builder.button(text=f"Канал {i+1}: {channel.title}", url=channel.invite_link)
    builder.button(text="✅ Я подписался, проверить", callback_data="check_subscription")
    builder.button(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def close_support_chat_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для закрытия чата с поддержкой."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Завершить диалог", callback_data="support_chat_close")
    return builder.as_markup()

# --- 1. Клавиатура со ссылками на клиенты ---
def os_client_keyboard():
    """Создает клавиатуру со ссылками на рекомендованные клиенты для VLESS."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Мой профиль", callback_data="my_profile")
    builder.button(text="🤖 Android (Happ)", url="https://play.google.com/store/apps/details?id=com.happproxy")
    builder.button(text="🍏 iOS (Happ)", url="https://apps.apple.com/us/app/happ-proxy-utility/id6504287215")
    builder.button(text="💻 Windows (Happ)", url="https://github.com/Happ-proxy/happ-desktop/releases")
    builder.button(text="🍎 macOS (Happ)", url="https://apps.apple.com/us/app/happ-proxy-utility/id6504287215?platform=mac")
    builder.button(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu")
    builder.adjust(1) # Располагаем кнопки по одной в ряд
    return builder.as_markup()


# =============================================================================
# === 2. КЛАВИАТУРЫ ДЛЯ АДМИН-ПАНЕЛИ ===
# =============================================================================

def admin_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню админ-панели."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📈 Статистика", callback_data="admin_stats")
    builder.button(text="👤 Управление пользователями", callback_data="admin_users_menu")
    builder.button(text="📢 Управление каналами", callback_data="admin_channels_menu")
    builder.button(text="💳 Управление тарифами", callback_data="admin_tariffs_menu")
    builder.button(text="🎁 Промокоды", callback_data="admin_promo_codes")
    builder.button(text="🌐 Внешние VPN", callback_data="admin_ext_vpn")
    builder.button(text="📤 Рассылка", callback_data="admin_broadcast")
    builder.button(text="⬅️ Выйти из админ-панели", callback_data="back_to_main_menu")
    builder.adjust(1)
    return builder.as_markup()

# --- 2.1. Управление пользователями ---

def user_manage_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для управления конкретным пользователем."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Добавить дни", callback_data=f"admin_add_days_{user_id}")
    builder.button(text="💳 История платежей", callback_data=f"admin_payments_{user_id}")
    builder.button(text="🔄 Сбросить ключ", callback_data=f"admin_reset_user_{user_id}")
    builder.button(text="🗑 Удалить пользователя", callback_data=f"admin_delete_user_{user_id}")
    builder.button(text="⬅️ Назад к поиску", callback_data="admin_users_menu")
    builder.adjust(1)
    return builder.as_markup()


def confirm_delete_keyboard(user_id_to_delete: int) -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения удаления пользователя."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"admin_confirm_delete_user_{user_id_to_delete}")
    builder.button(text="❌ Отмена", callback_data=f"admin_show_user_{user_id_to_delete}")
    builder.adjust(1)
    return builder.as_markup()

# --- 2.2. Управление каналами (НОВОЕ) ---

def manage_channels_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для добавления/удаления каналов."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить канал", callback_data="admin_add_channel")
    builder.button(text="➖ Удалить канал", callback_data="admin_delete_channel")
    builder.button(text="⬅️ Назад в админ-меню", callback_data="admin_main_menu")
    builder.adjust(2, 1)
    return builder.as_markup()

# --- 2.3. Управление тарифами ---

def tariffs_list_keyboard(tariffs: list[Tariff]) -> InlineKeyboardMarkup:
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


def single_tariff_manage_keyboard(tariff_id: int, is_active: bool) -> InlineKeyboardMarkup:
    """Клавиатура для управления одним тарифом."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить название", callback_data=f"admin_edit_tariff_name_{tariff_id}")
    builder.button(text="💰 Изменить цену", callback_data=f"admin_edit_tariff_price_{tariff_id}")
    builder.button(text="⏳ Изменить срок (дни)", callback_data=f"admin_edit_tariff_duration_{tariff_id}")
    
    action_text, action_cb = ("❌ Отключить", "admin_toggle_tariff_") if is_active else ("✅ Включить", "admin_toggle_tariff_")
    builder.button(text=action_text, callback_data=f"{action_cb}{tariff_id}")
        
    builder.button(text="🗑️ Удалить тариф", callback_data=f"admin_delete_tariff_{tariff_id}")
    builder.button(text="⬅️ Назад к списку тарифов", callback_data="admin_tariffs_menu")
    builder.adjust(1)
    return builder.as_markup()

def confirm_delete_tariff_keyboard(tariff_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения удаления тарифа."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"admin_confirm_delete_tariff_{tariff_id}")
    builder.button(text="❌ Нет, отмена", callback_data=f"admin_manage_tariff_{tariff_id}")
    builder.adjust(1)
    return builder.as_markup()

# --- 2.4. Управление промокодами ---

def promo_codes_list_keyboard(promo_codes: list[PromoCode]) -> InlineKeyboardMarkup:
    """Показывает список всех промокодов с кнопкой 'Удалить' и 'Добавить'."""
    builder = InlineKeyboardBuilder()
    if promo_codes:
        for code in promo_codes:
            info = []
            if code.bonus_days > 0: info.append(f"{code.bonus_days} дн.")
            if code.discount_percent > 0: info.append(f"{code.discount_percent}%")
            info.append(f"{code.uses_left}/{code.max_uses} исп.")
            builder.button(text=f"🗑️ {code.code} ({', '.join(info)})", callback_data=f"admin_delete_promo_{code.id}")
    
    builder.button(text="➕ Добавить новый промокод", callback_data="admin_add_promo")
    builder.button(text="⬅️ Назад в админ-меню", callback_data="admin_main_menu")
    builder.adjust(1)
    return builder.as_markup()


def promo_type_keyboard() -> InlineKeyboardMarkup:
    """Предлагает выбрать тип создаваемого промокода."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Бонусные дни", callback_data="promo_type_days")
    builder.button(text="💰 Скидка (%)", callback_data="promo_type_discount")
    builder.adjust(1)
    return builder.as_markup()

# --- 2.5. Рассылка ---


# tgbot/keyboards/inline.py (или admin_keyboards.py)

def broadcast_audience_keyboard():
    """Клавиатура для выбора аудитории рассылки."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Всем пользователям", callback_data="broadcast_audience_all")
    builder.button(text="⏳ Тем, кто не покупал", callback_data="broadcast_audience_never")
    builder.button(text="❌ Отмена", callback_data="admin_main_menu")
    builder.adjust(1)
    return builder.as_markup()

def broadcast_promo_keyboard():
    """Клавиатура для добавления промокода к рассылке."""
    builder = InlineKeyboardBuilder()
    # Эта кнопка будет вести в FSM для ввода промокода
    builder.button(text="🎁 Прикрепить промокод", callback_data="broadcast_attach_promo")
    # Эта кнопка пропустит шаг с промокодом
    builder.button(text="➡️ Продолжить без промокода", callback_data="broadcast_skip_promo")
    builder.button(text="❌ Отмена", callback_data="admin_main_menu")
    builder.adjust(1)
    return builder.as_markup()


def confirm_broadcast_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения рассылки."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Начать рассылку", callback_data="broadcast_start")
    builder.button(text="❌ Отмена", callback_data="admin_panel") # Изменено для единообразия
    builder.adjust(1)
    return builder.as_markup()



# =============================================================================
# === 3. УНИВЕРСАЛЬНЫЕ И СЛУЖЕБНЫЕ КЛАВИАТУРЫ ===
# =============================================================================

def back_to_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Простая клавиатура с одной кнопкой "Назад в главное меню"."""
    builder = InlineKeyboardBuilder()
    builder.button(text='⬅️ Назад в главное меню', callback_data='back_to_main_menu')
    return builder.as_markup()


def back_to_admin_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой "Назад в админ-меню"."""
    builder = InlineKeyboardBuilder()
    builder.button(text='⬅️ Назад в админ-меню', callback_data='admin_main_menu')
    return builder.as_markup()


def cancel_fsm_keyboard(back_callback_data: str) -> InlineKeyboardMarkup:
    """Универсальная клавиатура для отмены любого состояния FSM."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=back_callback_data)
    return builder.as_markup()

def back_to_promo_list_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для возврата к списку промокодов."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ К списку промокодов", callback_data="admin_promo_codes")
    return builder.as_markup()


# =============================================================================
# === 4. КЛАВИАТУРЫ ДЛЯ ВНЕШНИХ VPN-КОНФИГОВ ===
# =============================================================================

def external_vpn_menu_keyboard(subs_count: int) -> InlineKeyboardMarkup:
    """Главное меню управления внешними VPN."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Добавить по URL", callback_data="ext_vpn_add")
    builder.button(text="📋 Вставить конфиги", callback_data="ext_vpn_add_raw")
    if subs_count > 0:
        builder.button(text="🖥️ Управление серверами", callback_data="ext_vpn_list_subs")
    builder.button(text="⬅️ Назад в админ-меню", callback_data="admin_main_menu")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def ext_vpn_server_selection_keyboard(
    servers: list[dict],
    selected_indices: set[int],
    page: int = 0,
    page_size: int = 8,
) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора серверов с пагинацией.
    servers: [{name, raw_link}, ...]
    selected_indices: set индексов выбранных серверов
    """
    builder = InlineKeyboardBuilder()
    total = len(servers)
    start = page * page_size
    end = min(start + page_size, total)

    for i in range(start, end):
        icon = "✅" if i in selected_indices else "⬜"
        name = servers[i]["name"][:40]
        builder.button(text=f"{icon} {name}", callback_data=f"ext_vpn_toggle_{i}")

    # Навигация — prev и next на одной строке если оба есть
    nav_buttons = 0
    if page > 0:
        builder.button(text="◀️ Назад", callback_data=f"ext_vpn_page_{page - 1}")
        nav_buttons += 1
    if end < total:
        builder.button(text="▶️ Вперёд", callback_data=f"ext_vpn_page_{page + 1}")
        nav_buttons += 1

    builder.button(text="✅ Выбрать все", callback_data="ext_vpn_select_all")
    builder.button(text="💾 Сохранить выбранные", callback_data="ext_vpn_save")
    builder.button(text="❌ Отмена", callback_data="admin_ext_vpn")

    row_layout = [1] * (end - start)
    if nav_buttons > 0:
        row_layout.append(nav_buttons)
    row_layout += [1, 1, 1]
    builder.adjust(*row_layout)
    return builder.as_markup()


def ext_vpn_subscriptions_keyboard(subs) -> InlineKeyboardMarkup:
    """Список источников подписок для управления."""
    builder = InlineKeyboardBuilder()
    for sub in subs:
        icon = "✅" if sub.is_active else "❌"
        builder.button(text=f"{icon} {sub.name}", callback_data=f"ext_vpn_sub_{sub.id}")
    builder.button(text="⬅️ Назад", callback_data="admin_ext_vpn")
    builder.adjust(1)
    return builder.as_markup()


def ext_vpn_sub_manage_keyboard(sub_id: int, configs_count: int) -> InlineKeyboardMarkup:
    """Управление конкретным источником подписки."""
    builder = InlineKeyboardBuilder()
    if configs_count > 0:
        builder.button(text="🖥️ Серверы", callback_data=f"ext_vpn_configs_{sub_id}")
    builder.button(text="🗑️ Удалить источник", callback_data=f"ext_vpn_del_sub_{sub_id}")
    builder.button(text="⬅️ Назад к списку", callback_data="ext_vpn_list_subs")
    builder.adjust(1)
    return builder.as_markup()


def ext_vpn_configs_keyboard(configs, sub_id: int) -> InlineKeyboardMarkup:
    """Список серверов конкретного источника с возможностью вкл/выкл."""
    builder = InlineKeyboardBuilder()
    for cfg in configs:
        icon = "✅" if cfg.is_active else "❌"
        builder.button(text=f"{icon} {cfg.name[:35]}", callback_data=f"ext_vpn_cfg_toggle_{cfg.id}")
    builder.button(text="⬅️ Назад", callback_data=f"ext_vpn_sub_{sub_id}")
    builder.adjust(1)
    return builder.as_markup()