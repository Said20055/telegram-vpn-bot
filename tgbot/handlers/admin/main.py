# tgbot/handlers/admin/main.py
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from tgbot.filters.admin import IsAdmin
from tgbot.keyboards.inline import admin_main_menu_keyboard
from tgbot.services import admin_stats_service
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loader import logger

admin_main_router = Router()
admin_main_router.message.filter(IsAdmin()) # Применяем фильтр ко всем хендлерам в этом роутере

@admin_main_router.message(Command("admin"))
async def admin_start(message: Message):
    await message.answer("Добро пожаловать в админ-панель!", reply_markup=admin_main_menu_keyboard())

@admin_main_router.callback_query(F.data == "admin_main_menu")
async def admin_main_menu(call: CallbackQuery):
    await call.message.edit_text("Добро пожаловать в админ-панель!", reply_markup=admin_main_menu_keyboard())

@admin_main_router.callback_query(F.data == "admin_stats")
async def admin_stats_handler(call: CallbackQuery):
    """Показывает расширенную статистику с разбивкой по узлам."""
    await call.answer("Собираю статистику с серверов...")

    # --- Получаем все данные через сервис ---
    stats = await admin_stats_service.get_dashboard_stats()

    total_users = stats["total_users"]
    active_subs = stats["active_subs"]
    first_payments_total = stats["first_payments"]
    users_today = stats["users_today"]
    users_week = stats["users_week"]
    users_month = stats["users_month"]
    system_stats = stats["system_stats"]
    nodes = stats["nodes"]

    # --- 2. Формируем текст ---

    # Общий онлайн (самое точное число)
    online_total = system_stats.get('online_users', 'н/д')
    # Онлайн на основном сервере (в v0.8.4 это часто то же самое, что и общий)
    host_online = system_stats.get('users_online', online_total)

    text_parts = [
        "📊 <b>Расширенная статистика</b>\n",
        "<b>Пользователи:</b>",
        f"├ Всего в боте: 👥<b>{total_users}</b>",
        f"├ За сегодня: <b>{users_today}</b>\n"
        f"├ За неделю: <b>{users_week}</b>\n"
        f"├ За месяц: <b>{users_month}</b>\n"
        f"└ Активных подписок: ✅<b>{active_subs}</b>",
        "", # Пустая строка для отступа
        "<b>Конверсия:</b>",
        f"└ Всего первых оплат: <b>{first_payments_total}</b>",
        "",
        "<b>Доход:</b>",
        f"├ Сегодня: <b>{stats['revenue_today']['revenue']:.2f} RUB</b> ({stats['revenue_today']['count']} платежей)",
        f"├ За неделю: <b>{stats['revenue_week']['revenue']:.2f} RUB</b> ({stats['revenue_week']['count']})",
        f"├ За месяц: <b>{stats['revenue_month']['revenue']:.2f} RUB</b> ({stats['revenue_month']['count']})",
        f"└ Всего: <b>{stats['revenue_total']['revenue']:.2f} RUB</b> ({stats['revenue_total']['count']})",
        "",
        "<b>Серверы Marzban (v0.8.4):</b>",
        f"└ 🖥️ Онлайн на основном сервере: <b>{host_online}</b>\n", # Показываем онлайн хоста
        "<b>Подключенные узлы (Nodes):</b>",
    ]

    # Показываем список узлов и их статус подключения
    if nodes:
        for i, node in enumerate(nodes):
            node_name = node.get('name', f"Узел #{i+1}")
            node_status = node.get('status', 'неизвестен').capitalize()
            # Иконка в зависимости от статуса
            status_icon = "✅" if node_status == 'Connected' else "❌"

            is_last = (i == len(nodes) - 1)
            prefix = "└─" if is_last else "├─"

            text_parts.append(f"{prefix} {status_icon} {node_name}: <code>{node_status}</code>")
    else:
        text_parts.append("└─ 🤷‍♂️ Внешние узлы не настроены.")

    text = "\n".join(text_parts)

    # Клавиатура остается такой же
    stats_kb = InlineKeyboardBuilder()
    stats_kb.button(text="🔄 Обновить", callback_data="admin_stats")
    stats_kb.button(text="⬅️ Назад", callback_data="admin_main_menu")
    stats_kb.adjust(1)

    try:
        # Пытаемся отредактировать сообщение
        await call.message.edit_text(text, reply_markup=stats_kb.as_markup())
    except TelegramBadRequest as e:
        # Ловим конкретно ошибку "message is not modified"
        if "message is not modified" in e.message:
            # Если это она - просто игнорируем. Это не ошибка, а нормальное поведение.
            # Можно еще раз ответить на колбэк, чтобы пользователь видел, что кнопка сработала
            await call.answer("Данные не изменились.", show_alert=False)
            pass
        else:
            # Если это другая ошибка BadRequest, логируем ее
            logger.error(f"Error editing stats message: {e}")
            await call.answer("Произошла ошибка при обновлении.", show_alert=True)
