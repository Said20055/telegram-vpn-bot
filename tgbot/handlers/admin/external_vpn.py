# tgbot/handlers/admin/external_vpn.py

import httpx
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tgbot.keyboards.inline import (
    ext_vpn_server_selection_keyboard,
    ext_vpn_subscriptions_keyboard,
    ext_vpn_sub_manage_keyboard,
    ext_vpn_configs_keyboard,
    external_vpn_menu_keyboard,
    cancel_fsm_keyboard,
)
from tgbot.services import external_vpn_service
from tgbot.services.external_vpn_service import parse_raw_configs
from tgbot.states.external_vpn_states import ExternalVpnFSM

ext_vpn_router = Router()
# IsAdmin() фильтр применяется на уровне admin_router (admin/__init__.py)

# FSM_DATA ключ для временного хранения списка серверов и выбранных индексов
_SERVERS_KEY = "ext_servers"
_SELECTED_KEY = "ext_selected"
_URL_KEY = "ext_url"
_PAGE_KEY = "ext_page"


# ─── Главное меню Внешних VPN ────────────────────────────────────────────────

async def show_ext_vpn_menu(event, state: FSMContext | None = None):
    if state:
        await state.clear()
    subs = await external_vpn_service.get_all_subscriptions()
    text = "🌐 <b>Внешние VPN-конфиги</b>\n\n"
    if subs:
        active = [s for s in subs if s.is_active]
        text += f"Источников подписок: <b>{len(subs)}</b> (активных: <b>{len(active)}</b>)"
    else:
        text += "Внешних подписок пока нет."
    kb = external_vpn_menu_keyboard(len(subs))
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@ext_vpn_router.callback_query(F.data == "admin_ext_vpn")
async def ext_vpn_menu_handler(call: CallbackQuery, state: FSMContext):
    await show_ext_vpn_menu(call, state)


# ─── Добавление по URL: шаг 1 — URL ──────────────────────────────────────────

@ext_vpn_router.callback_query(F.data == "ext_vpn_add")
async def ext_vpn_add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ExternalVpnFSM.waiting_url)
    await call.message.edit_text(
        "🔗 Отправьте URL внешней VPN-подписки.\n\n"
        "Бот отправит запрос с заголовками Happ (x-hwid) "
        "для получения конфигов.",
        reply_markup=cancel_fsm_keyboard("admin_ext_vpn"),
    )


# ─── Добавление raw-конфигов: шаг 1 — вставка ───────────────────────────────

@ext_vpn_router.callback_query(F.data == "ext_vpn_add_raw")
async def ext_vpn_add_raw_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ExternalVpnFSM.waiting_raw_configs)
    await call.message.edit_text(
        "📋 Вставьте VPN-конфиги (по одному на строку):\n\n"
        "<code>vless://...#Сервер1\n"
        "vmess://...#Сервер2\n"
        "trojan://...#Сервер3</code>\n\n"
        "Также можно вставить base64-строку из буфера.",
        reply_markup=cancel_fsm_keyboard("admin_ext_vpn"),
    )


@ext_vpn_router.message(ExternalVpnFSM.waiting_raw_configs)
async def ext_vpn_receive_raw(message: Message, state: FSMContext):
    text = message.text.strip()
    servers = parse_raw_configs(text)

    if not servers:
        await message.answer(
            "❌ Не найдено ни одного VPN-конфига.\n"
            "Поддерживаемые форматы: vless://, vmess://, trojan://, ss://, hysteria2://, hy2://, tuic://",
            reply_markup=cancel_fsm_keyboard("admin_ext_vpn"),
        )
        return

    await state.update_data({
        _URL_KEY: "",
        _SERVERS_KEY: servers,
        _SELECTED_KEY: [],
        _PAGE_KEY: 0,
    })
    await state.set_state(ExternalVpnFSM.waiting_name)
    await message.answer(
        f"✅ Найдено конфигов: <b>{len(servers)}</b>\n\n"
        "Введите название для этого источника (например: <i>CaveVPN EU</i>):",
        reply_markup=cancel_fsm_keyboard("admin_ext_vpn"),
    )


@ext_vpn_router.message(ExternalVpnFSM.waiting_url)
async def ext_vpn_receive_url(message: Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer(
            "❌ Некорректный URL. Введите ссылку начинающуюся с http:// или https://",
            reply_markup=cancel_fsm_keyboard("admin_ext_vpn"),
        )
        return

    wait_msg = await message.answer("⏳ Загружаю подписку...")

    try:
        servers = await external_vpn_service.fetch_and_parse(url)
    except httpx.HTTPError as e:
        await wait_msg.edit_text(
            f"❌ Не удалось загрузить подписку:\n<code>{e}</code>",
            reply_markup=cancel_fsm_keyboard("admin_ext_vpn"),
        )
        return

    if not servers:
        await wait_msg.edit_text(
            "❌ В подписке не найдено ни одного VPN-конфига. "
            "Убедитесь что URL возвращает base64-список vless/vmess/trojan/ss ссылок.",
            reply_markup=cancel_fsm_keyboard("admin_ext_vpn"),
        )
        return

    await state.update_data({
        _URL_KEY: url,
        _SERVERS_KEY: servers,
        _SELECTED_KEY: [],
        _PAGE_KEY: 0,
    })
    await state.set_state(ExternalVpnFSM.waiting_name)
    await wait_msg.edit_text(
        f"✅ Найдено серверов: <b>{len(servers)}</b>\n\n"
        "Введите название для этого источника подписки (например: <i>Provider X EU</i>):",
        reply_markup=cancel_fsm_keyboard("admin_ext_vpn"),
    )


# ─── Добавление новой подписки: шаг 2 — название ─────────────────────────────

@ext_vpn_router.message(ExternalVpnFSM.waiting_name)
async def ext_vpn_receive_name(message: Message, state: FSMContext):
    name = message.text.strip()[:100]
    data = await state.get_data()
    servers = data.get(_SERVERS_KEY, [])

    await state.update_data(ext_name=name)
    await state.set_state(ExternalVpnFSM.selecting_servers)

    kb = ext_vpn_server_selection_keyboard(servers, set(), page=0)
    await message.answer(
        f"📋 <b>{name}</b> — выберите серверы для добавления в пул:\n"
        f"(всего серверов: {len(servers)})",
        reply_markup=kb,
    )


# ─── Выбор серверов: переключение чекбокса ───────────────────────────────────

@ext_vpn_router.callback_query(ExternalVpnFSM.selecting_servers, F.data.startswith("ext_vpn_toggle_"))
async def ext_vpn_toggle_server(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split("_")[-1])
    data = await state.get_data()
    servers = data.get(_SERVERS_KEY, [])
    selected: list = data.get(_SELECTED_KEY, [])
    page = data.get(_PAGE_KEY, 0)

    if idx in selected:
        selected.remove(idx)
    else:
        selected.append(idx)

    await state.update_data({_SELECTED_KEY: selected})
    kb = ext_vpn_server_selection_keyboard(servers, set(selected), page=page)
    await call.message.edit_reply_markup(reply_markup=kb)
    await call.answer()


# ─── Пагинация ───────────────────────────────────────────────────────────────

@ext_vpn_router.callback_query(ExternalVpnFSM.selecting_servers, F.data.startswith("ext_vpn_page_"))
async def ext_vpn_change_page(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split("_")[-1])
    data = await state.get_data()
    servers = data.get(_SERVERS_KEY, [])
    selected = set(data.get(_SELECTED_KEY, []))

    await state.update_data({_PAGE_KEY: page})
    kb = ext_vpn_server_selection_keyboard(servers, selected, page=page)
    await call.message.edit_reply_markup(reply_markup=kb)
    await call.answer()


# ─── Выбрать все ─────────────────────────────────────────────────────────────

@ext_vpn_router.callback_query(ExternalVpnFSM.selecting_servers, F.data == "ext_vpn_select_all")
async def ext_vpn_select_all(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    servers = data.get(_SERVERS_KEY, [])
    all_indices = list(range(len(servers)))
    page = data.get(_PAGE_KEY, 0)

    await state.update_data({_SELECTED_KEY: all_indices})
    kb = ext_vpn_server_selection_keyboard(servers, set(all_indices), page=page)
    await call.message.edit_reply_markup(reply_markup=kb)
    await call.answer(f"Выбрано все ({len(servers)})")


# ─── Сохранение выбранных серверов ───────────────────────────────────────────

@ext_vpn_router.callback_query(ExternalVpnFSM.selecting_servers, F.data == "ext_vpn_save")
async def ext_vpn_save(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    servers: list = data.get(_SERVERS_KEY, [])
    selected: list = data.get(_SELECTED_KEY, [])
    url: str = data.get(_URL_KEY, "")
    name: str = data.get("ext_name", "Внешняя подписка")

    if not selected:
        await call.answer("⚠️ Не выбрано ни одного сервера!", show_alert=True)
        return

    chosen = [servers[i] for i in selected]
    sub, count = await external_vpn_service.save_configs(url=url, name=name, selected=chosen)

    await state.clear()
    await call.message.edit_text(
        f"✅ Сохранено <b>{count}</b> серверов из источника <b>{name}</b>.\n"
        f"Они автоматически добавляются в подписки активных пользователей.",
        reply_markup=external_vpn_menu_keyboard(1),
    )


# ─── Список источников подписок ──────────────────────────────────────────────

@ext_vpn_router.callback_query(F.data == "ext_vpn_list_subs")
async def ext_vpn_list_subs(call: CallbackQuery):
    subs = await external_vpn_service.get_all_subscriptions()
    if not subs:
        await call.answer("Подписок нет.", show_alert=True)
        return
    await call.message.edit_text(
        "📋 Выберите источник для управления:",
        reply_markup=ext_vpn_subscriptions_keyboard(subs),
    )


# ─── Управление конкретным источником ────────────────────────────────────────

@ext_vpn_router.callback_query(F.data.startswith("ext_vpn_sub_"))
async def ext_vpn_sub_detail(call: CallbackQuery):
    sub_id = int(call.data.split("_")[-1])
    configs = await external_vpn_service.get_configs_by_subscription(sub_id)
    subs = await external_vpn_service.get_all_subscriptions()
    sub = next((s for s in subs if s.id == sub_id), None)
    if not sub:
        await call.answer("Источник не найден.", show_alert=True)
        return

    active_count = sum(1 for c in configs if c.is_active)
    await call.message.edit_text(
        f"🌐 <b>{sub.name}</b>\n"
        f"Серверов: <b>{len(configs)}</b> (активных: <b>{active_count}</b>)",
        reply_markup=ext_vpn_sub_manage_keyboard(sub_id, len(configs)),
    )


# ─── Список серверов источника ────────────────────────────────────────────────

@ext_vpn_router.callback_query(F.data.startswith("ext_vpn_configs_"))
async def ext_vpn_configs_list(call: CallbackQuery):
    sub_id = int(call.data.split("_")[-1])
    configs = await external_vpn_service.get_configs_by_subscription(sub_id)
    if not configs:
        await call.answer("Серверов нет.", show_alert=True)
        return
    await call.message.edit_text(
        "🖥️ Серверы (нажмите чтобы вкл/выкл):",
        reply_markup=ext_vpn_configs_keyboard(configs, sub_id),
    )


# ─── Вкл/выкл сервера ────────────────────────────────────────────────────────

@ext_vpn_router.callback_query(F.data.startswith("ext_vpn_cfg_toggle_"))
async def ext_vpn_toggle_config(call: CallbackQuery):
    config_id = int(call.data.split("_")[-1])
    new_state, sub_id = await external_vpn_service.toggle_config(config_id)
    if sub_id is None:
        await call.answer("Конфиг не найден.", show_alert=True)
        return
    icon = "✅" if new_state else "❌"
    await call.answer(f"{icon} {'Включён' if new_state else 'Выключен'}")

    configs = await external_vpn_service.get_configs_by_subscription(sub_id)
    await call.message.edit_reply_markup(
        reply_markup=ext_vpn_configs_keyboard(configs, sub_id)
    )


# ─── Удаление источника подписки ─────────────────────────────────────────────

@ext_vpn_router.callback_query(F.data.startswith("ext_vpn_del_sub_"))
async def ext_vpn_delete_sub(call: CallbackQuery):
    sub_id = int(call.data.split("_")[-1])
    await external_vpn_service.delete_subscription(sub_id)
    await call.answer("🗑️ Источник удалён.", show_alert=True)
    await show_ext_vpn_menu(call)
