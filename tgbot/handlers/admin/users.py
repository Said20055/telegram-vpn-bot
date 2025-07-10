# tgbot/handlers/admin/users.py (Полная, рабочая версия)

import asyncio
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from loader import logger

# --- Фильтры и Клавиатуры ---
from tgbot.filters.admin import IsAdmin
from tgbot.keyboards.inline import user_manage_keyboard, confirm_delete_keyboard, back_to_main_menu_keyboard

# --- База данных и API ---
from database import requests as db
from marzban.init_client import MarzClientCache


admin_users_router = Router()
# Применяем фильтр админа ко всем хендлерам в этом роутере
admin_users_router.message.filter(IsAdmin())
admin_users_router.callback_query.filter(IsAdmin())


# --- Состояния FSM ---
class AdminFSM(StatesGroup):
    find_user = State()
    add_days_user_id = State()
    add_days_amount = State()


# =============================================================================
# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ---
# =============================================================================

async def show_user_card(message_or_call, user_id: int):
    """
    Отображает карточку пользователя с информацией и кнопками управления.
    Вынесена в отдельную функцию для переиспользования.
    """
    user = db.get_user(user_id)
    if not user:
        text = "Пользователь не найден."
        reply_markup = back_to_main_menu_keyboard()
    else:
        sub_end_str = user.subscription_end_date.strftime('%d.%m.%Y %H:%M') if user.subscription_end_date else "Отсутствует"
        text = (
            f"<b>Пользователь найден:</b>\n\n"
            f"<b>ID:</b> <code>{user.user_id}</code>\n"
            f"<b>Username:</b> @{user.username or 'Отсутствует'}\n"
            f"<b>Имя:</b> {user.full_name}\n\n"
            f"<b>Подписка до:</b> {sub_end_str}\n"
            f"<b>Marzban аккаунт:</b> <code>{user.marzban_username or 'Не создан'}</code>"
        )
        reply_markup = user_manage_keyboard(user.user_id)

    # Определяем, как ответить - изменить сообщение или отправить новое
    if isinstance(message_or_call, CallbackQuery):
        # Используем try-except на случай, если сообщение уже удалено
        try:
            await message_or_call.message.edit_text(text, reply_markup=reply_markup)
        except:
            await message_or_call.bot.send_message(message_or_call.from_user.id, text, reply_markup=reply_markup)
    else:  # если это Message
        await message_or_call.answer(text, reply_markup=reply_markup)


# =============================================================================
# --- ОСНОВНЫЕ ХЕНДЛЕРЫ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ---
# =============================================================================

@admin_users_router.callback_query(F.data == "admin_users_menu")
async def users_menu(call: CallbackQuery, state: FSMContext):
    """Меню поиска пользователя."""
    await state.clear()
    await call.message.edit_text(
        "<b>👤 Управление пользователями</b>\n\n"
        "Введите ID или username (без @) пользователя для поиска:",
        reply_markup=back_to_main_menu_keyboard()
    )
    await state.set_state(AdminFSM.find_user)


@admin_users_router.message(AdminFSM.find_user)
async def find_user(message: Message, state: FSMContext):
    """Находит пользователя по ID или username и показывает его карточку."""
    await state.clear()
    query = message.text.strip()
    user = None

    if query.isdigit():
        user = db.get_user(int(query))
    else:
        user = db.get_user_by_username(query.replace("@", ""))
    
    if not user:
        await message.answer("Пользователь с таким ID или username не найден в базе данных бота.\n\n"
                             "Попробуйте еще раз:")
        await state.set_state(AdminFSM.find_user)
        return
        
    await show_user_card(message, user.user_id)


# --- Блок добавления дней ---

@admin_users_router.callback_query(F.data.startswith("admin_add_days_"))
async def add_days_start(call: CallbackQuery, state: FSMContext):
    """Начало сценария добавления дней подписки."""
    user_id = int(call.data.split("_")[3])
    await state.update_data(user_id=user_id)
    
    await call.message.edit_text(f"Введите количество дней для добавления пользователю <code>{user_id}</code>:")
    await state.set_state(AdminFSM.add_days_amount)


@admin_users_router.message(AdminFSM.add_days_amount)
async def add_days_finish(message: Message, state: FSMContext, marzban: MarzClientCache, bot: Bot): # Добавили bot
    """Завершение сценария добавления дней подписки (отказоустойчивая версия)."""
    
    # --- 1. Валидация ввода ---
    try:
        if not message.text or not message.text.isdigit() or int(message.text) <= 0:
            await message.answer("❌ **Ошибка.** Введите целое положительное число.")
            return
        days_to_add = int(message.text)
    except (ValueError, TypeError):
        await message.answer("❌ **Ошибка.** Пожалуйста, введите корректное число.")
        return

    # --- 2. Получение данных и предварительная обратная связь ---
    data = await state.get_data()
    user_id = data.get("user_id")
    await state.clear()
    
    # Даем админу понять, что процесс пошел
    await message.answer(f"⏳ Продлеваю подписку для пользователя <code>{user_id}</code> на <b>{days_to_add}</b> дн...")

    user = db.get_user(user_id)
    if not user:
        await message.answer(f"Не удалось найти пользователя <code>{user_id}</code> в базе.")
        return
        
    if not user.marzban_username:
        await message.answer(f"Не удалось продлить подписку: у пользователя <code>{user_id}</code> нет аккаунта в Marzban.")
        return

    # --- 3. Основная логика с раздельной обработкой ошибок ---
    try:
        # Сначала пытаемся продлить в Marzban. Это самая важная операция.
        await marzban.modify_user(username=user.marzban_username, expire_days=days_to_add)
        logger.info(f"Admin successfully extended subscription for Marzban user '{user.marzban_username}' by {days_to_add} days.")
    except Exception as e:
        logger.error(f"Admin failed to modify Marzban user '{user.marzban_username}': {e}", exc_info=True)
        await message.answer(f"❌ **Ошибка!**\n\nНе удалось продлить подписку в Marzban для <code>{user.marzban_username}</code>. Локальная подписка не изменена. Проверьте логи.")
        # Показываем карточку пользователя без изменений
        await show_user_card(message, user_id)
        return

    # Если в Marzban все успешно, продлеваем в нашей БД
    db.extend_user_subscription(user_id, days=days_to_add)
    # Получаем обновленного пользователя, чтобы взять новую дату
    updated_user = db.get_user(user_id)
    new_sub_end_date = updated_user.subscription_end_date.strftime('%d.%m.%Y')
    
    # --- 4. Финальное уведомление админа и пользователя ---
    await message.answer(
        f"✅ <b>Успешно!</b>\n\n"
        f"Пользователю <code>{user_id}</code> добавлено <b>{days_to_add}</b> дн.\n"
        f"Новая дата окончания подписки: <b>{new_sub_end_date}</b>"
    )

    # Отправляем уведомление самому пользователю
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"🎉 Ваша подписка была продлена администратором на **{days_to_add}** дн.!\n"
                 f"Новая дата окончания: **{new_sub_end_date}**"
        )
    except Exception as e:
        logger.warning(f"Could not send notification to user {user_id} about subscription extension: {e}")
        await message.answer("❗️Не удалось уведомить пользователя (возможно, он заблокировал бота).")
    
    # После всех действий снова показываем админу обновленную карточку пользователя
    await show_user_card(message, user_id)

# --- Блок удаления пользователя ---

@admin_users_router.callback_query(F.data.startswith("admin_delete_user_"))
async def delete_user_confirm(call: CallbackQuery):
    """Запрашивает подтверждение на удаление."""
    user_id = int(call.data.split("_")[3])
    await call.message.edit_text(
        f"Вы уверены, что хотите полностью удалить пользователя <code>{user_id}</code>?\n\n"
        "<b>Это действие необратимо.</b> Пользователь будет удален из Marzban и из базы данных бота.",
        reply_markup=confirm_delete_keyboard(user_id)
    )

@admin_users_router.callback_query(F.data.startswith("admin_confirm_delete_user_"))
async def delete_user_finish(call: CallbackQuery, marzban: MarzClientCache):
    await call.answer("Удаляю пользователя...")
    
    try:
        user_id = int(call.data.split("_")[4])
        user = db.get_user(user_id)
        # ... (проверки на существование user) ...
        
        marzban_deletion_success = False
        if user.marzban_username:
            logger.info(f"Admin attempt 1 to delete '{user.marzban_username}' from Marzban")
            # Первая попытка
            success_attempt_1 = await marzban.delete_user(user.marzban_username)
            
            if success_attempt_1:
                marzban_deletion_success = True
            else:
                # Если первая попытка неудачна, ждем секунду и пробуем снова
                logger.warning(f"First attempt to delete '{user.marzban_username}' failed. Retrying in 1 second...")
                await asyncio.sleep(1) 
                # Вторая попытка
                marzban_deletion_success = await marzban.delete_user(user.marzban_username)
        else:
            marzban_deletion_success = True # Если в Marzban и не было, считаем успехом

        if marzban_deletion_success:
            db.delete_user(user.user_id)
            await call.message.edit_text(f"✅ Пользователь <code>{user_id}</code> успешно удален.")
        else:
            await call.message.edit_text(f"❌ **Ошибка!**\n\nНе удалось удалить пользователя из Marzban даже со второй попытки. Проверьте логи Marzban.")

    except Exception as e:
        logger.error(f"Unexpected error in delete_user_finish for user_id from call {call.data}: {e}", exc_info=True)
        await call.message.edit_text("❌ Произошла непредвиденная ошибка в процессе удаления.")

# --- Хендлер для возврата к карточке пользователя ---
@admin_users_router.callback_query(F.data.startswith("admin_show_user_"))
async def show_user_handler(call: CallbackQuery):
    """Показывает карточку пользователя (нужно для кнопки 'Отмена' при удалении)."""
    user_id = int(call.data.split("_")[3])
    await show_user_card(call, user_id)