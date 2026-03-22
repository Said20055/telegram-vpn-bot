# tgbot/handlers/user/payment.py

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command

from loader import logger, config
from database import tariff_repo
from marzban.init_client import MarzClientCache
from tgbot.services import promo_service, subscription_service, payment_service
from tgbot.handlers.user.profile import show_profile_logic
from tgbot.keyboards.inline import cancel_fsm_keyboard, tariffs_keyboard, back_to_main_menu_keyboard
from tgbot.services import payment
from tgbot.states.payment_states import PromoApplyFSM

payment_router = Router()

# =============================================================================
# --- БЛОК 1: ПОКАЗ ТАРИФОВ ---
# =============================================================================

async def show_tariffs_logic(event: Message | CallbackQuery, state: FSMContext):
    """Универсальная логика для показа списка тарифов."""
    fsm_data = await state.get_data()
    discount = fsm_data.get("discount")

    active_tariffs = await tariff_repo.get_active()
    tariffs_list = list(active_tariffs) if active_tariffs else []

    text = "Пожалуйста, выберите тарифный план:"
    if discount:
        text = f"✅ Промокод на <b>{discount}%</b> применен!\n\n" + text

    reply_markup = tariffs_keyboard(tariffs_list, promo_procent=discount or 0)

    if not tariffs_list:
        text = "К сожалению, сейчас нет доступных тарифов для покупки."
        reply_markup = back_to_main_menu_keyboard()

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=reply_markup)
    else:
        await event.answer(text, reply_markup=reply_markup)

@payment_router.message(Command("payment"))
async def payment_command_handler(message: Message, state: FSMContext):
    await show_tariffs_logic(message, state)

@payment_router.callback_query(F.data == "buy_subscription")
async def buy_subscription_callback_handler(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await show_tariffs_logic(call, state)

# =============================================================================
# --- БЛОК 2: ПРИМЕНЕНИЕ ПРОМОКОДА ---
# =============================================================================


@payment_router.callback_query(F.data.startswith("apply_promo_"))
async def apply_promo_from_broadcast(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку с промокодом из рассылки.
    Применяет скидку и показывает меню тарифов.
    """
    await call.answer() # Сразу отвечаем, чтобы убрать "часики"

    try:
        promo_code = call.data.split("_")[2]
    except IndexError:
        await call.answer("Ошибка в данных промокода.", show_alert=True)
        return

    user_id = call.from_user.id

    # --- Валидация промокода через сервис ---
    result = await promo_service.validate(promo_code, user_id, require_discount=True)

    if not result.is_valid:
        # Отдельно обрабатываем случай, когда пользователь уже использовал код
        if "уже использовали" in result.error_message:
            active_tariffs = await tariff_repo.get_active()
            await call.message.edit_text(
                "❗️ <b>Вы уже использовали этот промокод.</b>\n\n"
                "Каждый промокод можно использовать только один раз.\n"
                "Пожалуйста, выберите тариф по стандартной цене:",
                reply_markup=tariffs_keyboard(list(active_tariffs))
            )
        else:
            await call.answer(result.error_message, show_alert=True)
        return

    # --- Применение промокода и показ тарифов ---
    try:
        await promo_service.apply(user_id, result.promo)

        # Сохраняем скидку в FSM для следующего шага
        await state.set_state(None)
        await state.update_data(discount=result.promo.discount_percent, promo_code=promo_code)

        # Вызываем нашу универсальную функцию для показа тарифов со скидкой
        await show_tariffs_logic(call, state)

    except Exception as e:
        logger.error(f"Error applying promo code '{promo_code}' for user {user_id}: {e}", exc_info=True)
        await call.answer("Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже.", show_alert=True)

async def _start_promo_input(event: Message | CallbackQuery, state: FSMContext):
    """
    Универсальная функция для начала сценария ввода промокода.
    """
    await state.set_state(PromoApplyFSM.awaiting_code)

    text = "Введите ваш промокод:"
    reply_markup = back_to_main_menu_keyboard()

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=reply_markup)
    else: # если это Message
        await event.answer(text, reply_markup=reply_markup)


@payment_router.message(Command("promo"))
async def promo_command_handler(message: Message, state: FSMContext):
    """Начинает сценарий ввода промокода по команде."""
    await _start_promo_input(message, state)


# --- ОБНОВЛЕННЫЙ хендлер для кнопки "Ввести промокод" ---
@payment_router.callback_query(F.data == "enter_promo_code")
async def enter_promo_callback_handler(call: CallbackQuery, state: FSMContext):
    """Начинает сценарий ввода промокода по кнопке."""
    await call.answer()
    await _start_promo_input(call, state)

@payment_router.message(PromoApplyFSM.awaiting_code)
async def process_promo_code(message: Message, state: FSMContext, bot: Bot, marzban: MarzClientCache):
    """Обрабатывает введенный промокод."""
    code = message.text.upper()
    user_id = message.from_user.id

    await message.delete() # Сразу удаляем сообщение с кодом

    # --- Валидация через сервис ---
    result = await promo_service.validate(code, user_id)
    if not result.is_valid:
        await message.answer(result.error_message)
        return

    promo = result.promo

    # Отмечаем использование промокода
    await promo_service.apply(user_id, promo)

    if promo.bonus_days > 0:
        await state.clear()
        try:
            await subscription_service.extend(user_id, promo.bonus_days)
            await message.answer(f"✅ Промокод успешно применен! Вам начислено <b>{promo.bonus_days} бонусных дней</b>.")
            # Показываем обновленный профиль
            await show_profile_logic(message, marzban, bot)

        except Exception as e:
            logger.error(f"Failed to apply bonus days for promo code {code} for user {user_id}: {e}", exc_info=True)
            await message.answer("❌ Произошла ошибка при начислении бонусных дней. Обратитесь в поддержку.")

    elif promo.discount_percent > 0:
        # Сохраняем скидку в состояние и показываем тарифы
        await state.set_state(None) # Выходим из состояния ввода промокода
        await state.update_data(discount=promo.discount_percent, promo_code=code)
        await show_tariffs_logic(message, state)

# =============================================================================
# --- БЛОК 3: ВЫБОР ТАРИФА И СОЗДАНИЕ ПЛАТЕЖА ---
# =============================================================================

@payment_router.callback_query(F.data.startswith("select_tariff_"))
async def select_tariff_handler(call: CallbackQuery, state: FSMContext, bot: Bot):
    """Обрабатывает выбор тарифа и генерирует ссылку на оплату."""
    await call.answer()

    user_id = call.from_user.id
    tariff_id = int(call.data.split("_")[2])
    tariff = await tariff_repo.get_by_id(tariff_id)
    if not tariff:
        await call.message.edit_text("Ошибка! Тариф не найден.", reply_markup=back_to_main_menu_keyboard())
        return

    # Проверка на дубликат pending-платежа
    pending = await payment_service.get_pending_payment(user_id)
    if pending:
        pending_tariff = await tariff_repo.get_by_id(pending.tariff_id)
        tariff_name = pending_tariff.name if pending_tariff else "Неизвестный"
        tariff_days = pending_tariff.duration_days if pending_tariff else "?"

        # Пытаемся получить ссылку на оплату из YooKassa
        existing_url = payment.get_payment_url(
            pending.yookassa_payment_id,
            shop_id=config.yookassa.shop_id,
            secret_key=config.yookassa.secret_key,
        )

        price_text = f"<b>{pending.final_amount} RUB</b>"
        if pending.discount_percent:
            price_text = (
                f"<s>{pending.original_amount} RUB</s>\n"
                f"Скидка {pending.discount_percent}% ({pending.promo_code}): <b>{pending.final_amount} RUB</b>"
            )

        kb = InlineKeyboardBuilder()
        if existing_url:
            kb.button(text="💳 Перейти к оплате", url=existing_url)
        kb.button(text="⬅️ Назад", callback_data="buy_subscription")
        kb.adjust(1)

        await call.message.edit_text(
            "⏳ У вас уже есть неоплаченный счёт:\n\n"
            f"Тариф: <b>{tariff_name}</b>\n"
            f"Срок: <b>{tariff_days} дней</b>\n"
            f"Сумма: {price_text}\n\n"
            "Завершите оплату или дождитесь автоматической отмены (10 мин).",
            reply_markup=kb.as_markup()
        )
        return

    fsm_data = await state.get_data()
    discount_percent = fsm_data.get("discount")
    promo_code = fsm_data.get("promo_code")

    original_price = tariff.price
    final_price = original_price

    if discount_percent:
        final_price = round(original_price * (1 - discount_percent / 100), 2)
        price_text = (
            f"<s>{original_price} RUB</s>\n"
            f"Скидка {discount_percent}% ({promo_code}): <b>{final_price} RUB</b>"
        )
    else:
        price_text = f"<b>{original_price} RUB</b>"

    payment_url, yookassa_payment_id = payment.create_payment(
        user_id=user_id,
        amount=final_price,
        description=f"Оплата тарифа '{tariff.name}'" + (f" (скидка {discount_percent}%)" if discount_percent else ""),
        return_url=f"https://t.me/{(await bot.get_me()).username}",
        metadata={'user_id': str(user_id), 'tariff_id': tariff_id},
        shop_id=config.yookassa.shop_id,
        secret_key=config.yookassa.secret_key
    )

    # Сохраняем платёж в БД
    await payment_service.create_payment_record(
        yookassa_payment_id=yookassa_payment_id,
        user_id=user_id,
        tariff_id=tariff_id,
        original_amount=original_price,
        final_amount=final_price,
        source='bot',
        promo_code=promo_code,
        discount_percent=discount_percent or 0,
    )

    logger.info(
        f"Payment created: user={user_id}, tariff={tariff.name}, "
        f"amount={final_price}, original={original_price}, "
        f"discount={discount_percent or 0}%, promo={promo_code or 'none'}, "
        f"yookassa_id={yookassa_payment_id}"
    )

    payment_kb = InlineKeyboardBuilder()
    payment_kb.button(text="💳 Перейти к оплате", url=payment_url)
    payment_kb.button(text="⬅️ Назад к выбору тарифа", callback_data="buy_subscription")
    payment_kb.adjust(1)

    sent_message = await call.message.edit_text(
        f"Вы выбрали тариф: <b>{tariff.name}</b>\n"
        f"Срок: <b>{tariff.duration_days} дней</b>\n\n"
        f"Сумма к оплате: {price_text}\n\n"
        "Нажмите на кнопку ниже, чтобы перейти к оплате.",
        reply_markup=payment_kb.as_markup()
    )
    await state.update_data(payment_message_id=sent_message.message_id)
