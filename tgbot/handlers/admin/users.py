# tgbot/handlers/admin/users.py
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from tgbot.filters.admin import IsAdmin
from tgbot.keyboards.inline import user_manage_keyboard
from database import requests as db
from marzban.init_client import MarzClientCache

admin_users_router = Router()
admin_users_router.message.filter(IsAdmin())
admin_users_router.callback_query.filter(IsAdmin())

class AdminFSM(StatesGroup):
    find_user = State()
    add_days_user_id = State()
    add_days_amount = State()

@admin_users_router.callback_query(F.data == "admin_users_menu")
async def users_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("<b>Управление пользователями</b>\n\nВведите ID или username пользователя для поиска:")
    await state.set_state(AdminFSM.find_user)

@admin_users_router.message(AdminFSM.find_user)
async def find_user(message: Message, state: FSMContext):
    query = message.text
    if query.isdigit():
        user = db.get_user(int(query))
    else:
        # Тут нужна функция поиска по юзернейму в db/requests.py
        # user = db.get_user_by_username(query.replace("@", ""))
        await message.answer("Поиск по username пока не реализован. Введите ID.")
        return # Временно

    await state.clear()

    if not user:
        await message.answer("Пользователь не найден.")
        return

    # Формируем информацию о пользователе
    sub_end = user.subscription_end_date.strftime('%d.%m.%Y') if user.subscription_end_date else "Нет"
    text = (
        f"<b>Информация о пользователе:</b>\n\n"
        f"ID: <code>{user.user_id}</code>\n"
        f"Username: @{user.username}\n"
        f"Имя: {user.full_name}\n"
        f"Подписка до: {sub_end}\n"
        f"Marzban User: <code>{user.marzban_username or 'Нет'}</code>"
    )
    await message.answer(text, reply_markup=user_manage_keyboard(user.user_id))