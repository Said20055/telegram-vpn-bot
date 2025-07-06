import logging
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db import Tariff 
logger = logging.getLogger(__name__)


def main_menu_keyboard():  # Переименовал keyboard_start для ясности
    """
    Главная клавиатура, которая будет показываться пользователю
    в основном меню и после различных действий.
    """
    builder = InlineKeyboardBuilder()
    # Новые кнопки в соответствии с нашей логикой
    builder.button(text='💎 Получить VPN', callback_data='get_vpn')
    builder.button(text='👤 Мой профиль', callback_data='my_profile')
    builder.button(text='🤝 Реферальная программа', callback_data='referral_program')
    builder.button(text='ℹ️ Помощь', callback_data='help_info')
    builder.button(text='💎 Продлить / Оплатить', callback_data='buy_subscription')
    
    # Расставляем кнопки по 2 в ряд, последняя будет одна на всю ширину
    builder.adjust(2, 1)
    return builder.as_markup()

def tariffs_keyboard(tariffs: list[Tariff]):
    """Создает клавиатуру со списком тарифов."""
    logger.info("--- Entering tariffs_keyboard function ---")
    builder = InlineKeyboardBuilder()
    
    for i, tariff in enumerate(tariffs):
        # --- ОТЛАДКА ---
        # Проверяем каждое поле тарифа перед использованием
        tariff_id = tariff.id
        tariff_name = tariff.name
        tariff_price = tariff.price
        
        logger.info(f"Processing tariff #{i}: ID={tariff_id}, Name='{tariff_name}', Price={tariff_price}")
        
        if not tariff_id:
            logger.error(f"CRITICAL: Tariff #{i} has an empty ID! Skipping this button.")
            continue # Пропускаем этот тариф, если у него нет ID

        callback_data_str = f"select_tariff_{tariff_id}"
        button_text = f"{tariff_name} - {tariff_price} RUB"
        
        logger.info(f"Creating button: Text='{button_text}', Callback='{callback_data_str}'")

        builder.button(
            text=button_text,
            callback_data=callback_data_str
        )

    builder.button(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu")
    builder.adjust(1)
    
    logger.info("--- Exiting tariffs_keyboard function ---")
    return builder.as_markup()
def help_keyboard(): # Переименовал keyboard_help для единообразия
    """
    Клавиатура для раздела "Помощь" со ссылкой на инструкции.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text='Клиенты для подключения', url='https://marzban-docs.sm1ky.com/start/reality_app/')
    # Добавим кнопку для возврата в главное меню
    builder.button(text='⬅️ Назад', callback_data='back_to_main_menu')
    builder.adjust(1) # Каждая кнопка на новой строке
    return builder.as_markup()


def back_to_main_menu_keyboard():
    """
    Простая клавиатура с одной кнопкой "Назад".
    Будет полезна во многих местах, например, в профиле или реферальной программе.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text='⬅️ Назад в главное меню', callback_data='back_to_main_menu')
    return builder.as_markup()

# Ваша функция keyboard_cancel() была для FSM, пока оставим её как есть, если она где-то используется.
def keyboard_cancel():
    """Клавиатура для отмены какого-либо состояния (FSM)."""
    builder = InlineKeyboardBuilder()
    builder.button(text='❌ Отмена', callback_data='cancel_fsm') # Рекомендую делать callback_data более явными
    return builder.as_markup()