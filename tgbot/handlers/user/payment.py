from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command

from loader import logger
from database import requests as db
from tgbot.keyboards.inline import tariffs_keyboard, back_to_main_menu_keyboard
from tgbot.services import payment

payment_router = Router()

# --- 1. Создаем ОБЩУЮ функцию для показа тарифов ---
async def show_tariffs_logic(event: Message | CallbackQuery):
    """Универсальная логика для показа списка тарифов."""
    active_tariffs = db.get_active_tariffs()
    tariffs_list = list(active_tariffs) if active_tariffs else []

    text = "Пожалуйста, выберите тарифный план:"
    reply_markup = tariffs_keyboard(tariffs_list)

    if not tariffs_list:
        text = "К сожалению, сейчас нет доступных тарифов для покупки."
        reply_markup = back_to_main_menu_keyboard()
    
    # Отправляем или редактируем сообщение
    if isinstance(event, CallbackQuery):
        # Если это нажатие на кнопку - редактируем
        await event.message.edit_text(text, reply_markup=reply_markup)
    else:
        # Если это команда - отправляем новое сообщение
        await event.answer(text, reply_markup=reply_markup)


# --- 2. Хендлер для команды /payment ---
@payment_router.message(Command("payment"))
async def payment_command_handler(message: Message):
    # Просто вызываем общую логику
    await show_tariffs_logic(message)


# --- 3. Хендлер для кнопки "Оплатить" ---
@payment_router.callback_query(F.data == "buy_subscription")
async def buy_subscription_callback_handler(call: CallbackQuery):
    await call.answer()
    # Просто вызываем общую логику
    await show_tariffs_logic(call)

@payment_router.callback_query(F.data.startswith("select_tariff_"))
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
