# tgbot/handlers/admin/main.py
import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from marzban.init_client import MarzClientCache
from tgbot.filters.admin import IsAdmin
from tgbot.keyboards.inline import admin_main_menu_keyboard
from database import requests as db 
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
async def admin_stats_handler(call: CallbackQuery, marzban: MarzClientCache):
    """Показывает расширенную статистику с разбивкой по узлам."""
    await call.answer("Собираю статистику с серверов...")
    
    # --- 1. Сначала выполняем все СИНХРОННЫЕ запросы к нашей БД ---
    total_users = await db.count_all_users()
    active_subs = await db.count_active_subscriptions()
    first_payments_total = await db.count_users_with_first_payment()
    
    # --- 2. Затем параллельно выполняем все АСИНХРОННЫЕ запросы к API Marzban ---
    # Теперь мы передаем в gather уже вызванные асинхронные функции
    system_stats = await marzban.get_system_stats()
    nodes = await marzban.get_nodes()
    
    # --- 2. Формируем текст ---
    
    # Общий онлайн (самое точное число)
    online_total = system_stats.get('online_users', 'н/д')
    # Онлайн на основном сервере (в v0.8.4 это часто то же самое, что и общий)
    host_online = system_stats.get('users_online', online_total) 

    text_parts = [
        "📊 <b>Расширенная статистика</b>\n",
        "<b>Пользователи:</b>",
        f"├ Всего в боте: 👥<b>{total_users}</b>",
        f"└ Активных подписок: ✅<b>{active_subs}</b>",
        "", # Пустая строка для отступа
        "<b>Конверсия:</b>",
        f"└ Всего первых оплат: <b>{first_payments_total}</b>",
        "",
        "<b>Серверы Marzban (v0.8.4):</b>",
        f"├ 🟢 Общий онлайн: <b>{online_total}</b>",
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
    
    await call.message.edit_text(text, reply_markup=stats_kb.as_markup())