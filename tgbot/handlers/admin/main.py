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
    total_users = db.count_all_users()
    active_subs = db.count_active_subscriptions()
    first_payments_total = db.count_users_with_first_payment()
    
    # --- 2. Затем параллельно выполняем все АСИНХРОННЫЕ запросы к API Marzban ---
    # Теперь мы передаем в gather уже вызванные асинхронные функции
    system_stats, nodes = await asyncio.gather(
        marzban.get_system_stats(),
        marzban.get_nodes()
    )
    
    # --- 3. Формируем текст сообщения (этот блок остается без изменений) ---
    online_total = system_stats.get("online_clients", "н/д")
    
    text_parts = [
        "📊 <b>Расширенная статистика</b>\n",
        "<b>Пользователи:</b>",
        f"├ Всего в боте: <b>{total_users}</b>",
        f"└ Активных подписок: <b>{active_subs}</b>",
        "",
        "<b>Конверсия:</b>",
        f"└ Всего первых оплат: <b>{first_payments_total}</b>",
        "",
        "<b>Серверы Marzban:</b>",
        f"├ 🟢 Общий онлайн: <b>{online_total}</b>",
    ]
    
    if nodes:
        # В новых версиях Marzban общая статистика НЕ включает онлайн хоста
        # Его нужно получать отдельно или суммировать
        host_online = 0
        nodes_online_list = []
        for i, node in enumerate(nodes):
            node_name = node.get('name', f"Узел #{i+1}")
            node_online = node.get('users_online', 0)
            
            # Если у узла нет `node_id`, это, скорее всего, основной хост
            if node.get('id') is None or node.get('id') == 0: 
                 host_online = node_online
            else:
                 nodes_online_list.append(f"🌐 {node_name}: <b>{node_online}</b>")

        text_parts.append(f"│  ├─ 🖥️ Основной сервер: <b>{host_online}</b>")
        
        for i, node_line in enumerate(nodes_online_list):
            prefix = "│  └─" if i == len(nodes_online_list) - 1 else "│  ├─"
            text_parts.append(f"{prefix} {node_line}")
    
    text = "\n".join(text_parts)

    # Клавиатура остается такой же
    stats_kb = InlineKeyboardBuilder()
    stats_kb.button(text="🔄 Обновить", callback_data="admin_stats")
    stats_kb.button(text="⬅️ Назад", callback_data="admin_main_menu")
    stats_kb.adjust(1)
    
    await call.message.edit_text(text, reply_markup=stats_kb.as_markup())