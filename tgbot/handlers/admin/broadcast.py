# tgbot/handlers/admin/broadcast.py (Полная, исправленная, финальная версия)


import asyncio
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from tgbot.states.broadcast_states import BroadcastFSM
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loader import logger

from database import user_repo
from tgbot.services import promo_service
from tgbot.keyboards.inline import (broadcast_audience_keyboard, broadcast_promo_keyboard,
                                    confirm_broadcast_keyboard, cancel_fsm_keyboard, admin_main_menu_keyboard)

admin_broadcast_router = Router()

# --- Начало сценария ---
@admin_broadcast_router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(call: CallbackQuery, state: FSMContext):
    logger.debug(f"Broadcast start initiated by admin {call.from_user.id}")
    await state.clear()
    await state.set_state(BroadcastFSM.choose_audience)
    await call.message.edit_text(
        "📣 <b>Рассылка сообщений</b>\n\n<b>Шаг 1/4:</b> Выберите аудиторию:",
        reply_markup=broadcast_audience_keyboard()
    )

# --- Шаг 1: Выбор аудитории ---
@admin_broadcast_router.callback_query(F.data.startswith("broadcast_audience_"), BroadcastFSM.choose_audience)
async def choose_audience(call: CallbackQuery, state: FSMContext):
    audience = call.data.split("_")[2]
    await state.update_data(audience=audience)
    logger.debug(f"Admin {call.from_user.id} chose audience: '{audience}'. State data: {await state.get_data()}")

    await state.set_state(BroadcastFSM.get_message)
    await call.message.edit_text(
        "<b>Шаг 2/4:</b> Пришлите сообщение для рассылки.",
        reply_markup=cancel_fsm_keyboard("admin_broadcast")
    )

# --- Шаг 2: Получение сообщения ---
@admin_broadcast_router.message(BroadcastFSM.get_message)
async def get_message(message: Message, state: FSMContext):
    await state.update_data(
        message_to_send_chat_id=message.chat.id,
        message_to_send_id=message.message_id
    )
    data = await state.get_data()
    logger.debug(f"Admin {message.from_user.id} provided a message. Current state data: {data}")

    if data.get("audience") == "never":
        await state.set_state(BroadcastFSM.attach_promo)
        await message.answer(
            "<b>Шаг 3/4:</b> Хотите прикрепить промокод на скидку?",
            reply_markup=broadcast_promo_keyboard()
        )
    else:
        await state.set_state(BroadcastFSM.confirm)
        await message.answer(
            "<b>Шаг 4/4:</b> Подтвердите рассылку.",
            reply_markup=confirm_broadcast_keyboard()
        )

# --- Шаг 3 (опциональный): Прикрепление промокода ---
@admin_broadcast_router.callback_query(F.data == "broadcast_skip_promo", BroadcastFSM.attach_promo)
async def skip_promo(call: CallbackQuery, state: FSMContext):
    logger.debug(f"Admin {call.from_user.id} skipped promo attachment.")
    await state.set_state(BroadcastFSM.confirm)
    await call.message.edit_text(
        "<b>Шаг 4/4:</b> Вы уверены, что хотите разослать это сообщение без промокода?",
        reply_markup=confirm_broadcast_keyboard()
    )

@admin_broadcast_router.callback_query(F.data == "broadcast_attach_promo", BroadcastFSM.attach_promo)
async def attach_promo(call: CallbackQuery, state: FSMContext):
    logger.debug(f"Admin {call.from_user.id} wants to attach a promo code.")
    await state.set_state(BroadcastFSM.awaiting_promo)
    await call.message.edit_text("Введите текст существующего скидочного промокода.")

@admin_broadcast_router.message(BroadcastFSM.awaiting_promo)
async def get_promo(message: Message, state: FSMContext):
    promo_code = message.text.strip().upper()
    logger.debug(f"Admin {message.from_user.id} entered promo code: '{promo_code}'")

    promo = await promo_service.get_by_code(promo_code)
    if not promo or promo.discount_percent == 0:
        await message.answer("❌ Ошибка: промокод не найден или он не является скидочным. Введите другой.")
        return

    await state.update_data(promo_code=promo_code)
    logger.debug(f"Promo code '{promo_code}' is valid. State data: {await state.get_data()}")
    await state.set_state(BroadcastFSM.confirm)
    await message.answer(
        f"Отлично! Кнопка с промокодом <code>{promo_code}</code> будет добавлена.\n\n"
        "<b>Шаг 4/4:</b> Теперь подтвердите рассылку.",
        reply_markup=confirm_broadcast_keyboard()
    )


# --- Шаг 4: Подтверждение и запуск ---
@admin_broadcast_router.callback_query(F.data == "broadcast_start", BroadcastFSM.confirm)
async def confirm_and_run_broadcast(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    logger.debug(f"Broadcast confirmed by admin {call.from_user.id}. Final data: {data}")

    msg_chat_id = data.get("message_to_send_chat_id")
    msg_id = data.get("message_to_send_id")
    audience = data.get("audience")
    promo_code = data.get("promo_code")
    await state.clear()

    if not (msg_chat_id and msg_id and audience):
        logger.error(f"Broadcast failed for admin {call.from_user.id}: data was lost. State data: {data}")
        await call.message.edit_text("❌ <b>Ошибка:</b> Данные для рассылки были утеряны. Попробуйте снова.")
        return

    # --- ОПРЕДЕЛЕНИЕ АУДИТОРИИ С ЛОГИРОВАНИЕМ ---
    users_ids = []
    audience_text = ""
    logger.debug(f"Fetching audience '{audience}' from DB...")
    if audience == "all":
        users_ids = await user_repo.get_all_ids()
        audience_text = "всем пользователям"
    elif audience == "never":
        users_ids = await user_repo.get_without_first_payment()
        audience_text = "пользователям, не совершавшим покупку"

    # --- ЛОГИРОВАНИЕ РЕЗУЛЬТАТА ИЗ БД ---
    logger.debug(f"DB returned {len(users_ids)} user(s) for audience '{audience}'. User IDs: {users_ids[:20]}...") # Показываем первые 20 ID
    if not users_ids:
        await call.message.edit_text("⚠️ Аудитория для рассылки пуста. Никому не отправлено.", reply_markup=admin_main_menu_keyboard())
        return

    # Формируем клавиатуру, если есть промокод
    reply_markup = None
    if promo_code:
        promo_kb = InlineKeyboardBuilder()
        promo_kb.button(text=f"🎁 Использовать промокод {promo_code}", callback_data=f"apply_promo_{promo_code}")
        reply_markup = promo_kb.as_markup()

    await call.message.edit_text(f"🚀 Рассылка для <b>{len(users_ids)}</b> {audience_text} запущена...")

    # --- Процесс рассылки ---
    success_count = 0
    errors_count = 0
    for user_id in users_ids:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=msg_chat_id,
                message_id=msg_id,
                reply_markup=reply_markup
            )
            success_count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            errors_count += 1
            logger.warning(f"Broadcast failed for user {user_id}. Error: {e}")

    await call.bot.send_message(
        chat_id=call.from_user.id,
        text=f"✅ <b>Рассылка завершена!</b>\n\n👍 Отправлено: <b>{success_count}</b>\n👎 Ошибок: <b>{errors_count}</b>"
    )

# --- Обработчик для отмены FSM ---
@admin_broadcast_router.callback_query(F.data == "admin_broadcast", BroadcastFSM.get_message)
@admin_broadcast_router.callback_query(F.data == "admin_main_menu")
async def cancel_broadcast_handler(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Рассылка отменена.", reply_markup=admin_main_menu_keyboard())
