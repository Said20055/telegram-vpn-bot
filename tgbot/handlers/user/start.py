# tgbot/handlers/user/start.py

from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
# --- Импорты ---
from loader import logger
from database import channel_repo, user_repo
from tgbot.services import user_service, referral_service, subscription_service, profile_service
from tgbot.services.subscription import check_subscription
from tgbot.services.utils import get_user_attribute, format_traffic
from tgbot.keyboards.inline import (
    main_menu_keyboard, back_to_main_menu_keyboard,
    onboarding_subscribe_keyboard, onboarding_download_app_keyboard,
    onboarding_import_keyboard,
)

# Создаем локальный роутер для этого файла
start_router = Router()


# =============================================================================
# --- ХЕЛПЕР: ОТОБРАЖЕНИЕ ГЛАВНОГО МЕНЮ ---
# =============================================================================

async def _show_main_menu(target: Message | CallbackQuery, user_id: int, full_name: str):
    """Показывает главное меню со статусом подписки из Marzban."""
    user = await user_repo.get(user_id)
    has_email = bool(user and user.email)

    profile_data = await profile_service.get_profile(user_id)

    if profile_data.error or not profile_data.marzban_user:
        text = (
            f"👋 Добро пожаловать, <b>{full_name}</b>!\n\n"
            "📋 У вас пока нет активной подписки.\n"
            "Оформите тариф или получите бесплатный доступ!"
        )
        has_active_sub = False
    else:
        marzban_user = profile_data.marzban_user
        status = get_user_attribute(marzban_user, 'status', 'unknown')
        expire_ts = get_user_attribute(marzban_user, 'expire')
        used_traffic = get_user_attribute(marzban_user, 'used_traffic', 0)
        data_limit = get_user_attribute(marzban_user, 'data_limit')

        used_str = format_traffic(used_traffic)
        limit_str = "Безлимит" if not data_limit else format_traffic(data_limit)

        if expire_ts:
            expire_dt = datetime.fromtimestamp(expire_ts)
            days_left = max(0, (expire_dt - datetime.now()).days)
            date_str = f"{expire_dt.strftime('%d.%m.%Y')} (осталось {days_left} дн.)"
        else:
            date_str = "Безлимит"

        status_icon = "🟢" if status == "active" else "🔴"
        has_active_sub = (status == "active")

        text = (
            f"👋 Добро пожаловать, <b>{full_name}</b>!\n\n"
            f"📋 <b>Ваша подписка:</b>\n"
            f"{status_icon} Статус: {status}\n"
            f"📅 Активна до: {date_str}\n"
            f"📊 Трафик: {used_str} / {limit_str}"
        )

    reply_markup = main_menu_keyboard(has_active_sub=has_active_sub, has_email=has_email)

    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest:
            try:
                await target.message.delete()
            except TelegramBadRequest:
                pass
            await target.message.answer(text, reply_markup=reply_markup)
    else:
        await target.answer(text, reply_markup=reply_markup)

# =============================================================================
# --- БЛОК: СТАРТ БОТА И ОНБОРДИНГ ---
# =============================================================================

@start_router.message(CommandStart())
async def process_start_command(message: Message, command: CommandObject, bot: Bot, state: FSMContext):
    """
    Единый обработчик команды /start.
    Новые пользователи проходят онбординг, существующие видят главное меню.
    """
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username

    # 1. Регистрируем или получаем пользователя
    user, created = await user_service.register_or_get(user_id, full_name, username)

    # 2. Обрабатываем реферальную ссылку
    referrer_id = None
    if command and command.args and command.args.startswith('ref'):
        if created:
            try:
                potential_referrer_id = int(command.args[3:])
                if potential_referrer_id != user_id and await user_service.get_user(potential_referrer_id):
                    referrer_id = potential_referrer_id
            except (ValueError, IndexError, TypeError):
                pass

            if referrer_id:
                await state.update_data(referrer_id=referrer_id)
        else:
            await message.answer("Вы уже зарегистрированы. Реферальная ссылка работает только для новых пользователей.")

    # 3. Если пользователь новый — запускаем онбординг
    if created:
        await _start_onboarding(message, bot, state, referrer_id)
    else:
        # Существующий пользователь — главное меню со статусом подписки
        await _show_main_menu(message, user_id, full_name)


# =============================================================================
# --- ОНБОРДИНГ: ШАГ 1 — ПОДПИСКА НА КАНАЛЫ ---
# =============================================================================

async def _start_onboarding(message: Message, bot: Bot, state: FSMContext, referrer_id: int | None = None):
    """Начинает процесс онбординга для нового пользователя."""
    channels = await channel_repo.get_all()

    if not channels:
        # Если каналов нет — сразу выдаём триал и переходим к скачиванию приложения
        await _activate_and_show_download(message, bot, state, referrer_id)
        return

    welcome_text = (
        f"👋 Привет, <b>{message.from_user.full_name}</b>!\n\n"
        "Добро пожаловать в VPN-бот!\n\n"
        "🎁 Чтобы получить <b>бесплатный пробный период на 7 дней</b>, "
        "подпишитесь на наш канал и нажмите кнопку ниже."
    )

    await message.answer(
        welcome_text,
        reply_markup=onboarding_subscribe_keyboard(channels),
        disable_web_page_preview=True
    )


@start_router.callback_query(F.data == "onboarding_check_sub")
async def onboarding_check_subscription(call: CallbackQuery, bot: Bot, state: FSMContext):
    """Проверяет подписку на каналы и выдаёт триал."""
    user_id = call.from_user.id

    # Проверяем, не получал ли уже триал
    user = await user_service.get_user(user_id)
    if user and user.has_received_trial:
        await call.answer("Вы уже получили пробный период!", show_alert=True)
        await _show_main_menu(call, call.from_user.id, call.from_user.full_name)
        return

    is_subscribed = await check_subscription(bot, user_id)

    if not is_subscribed:
        await call.answer("Вы ещё не подписались на все каналы. Попробуйте снова.", show_alert=True)
        return

    await call.answer("✅ Отлично! Подписка подтверждена!")

    # Получаем referrer_id из FSM
    fsm_data = await state.get_data()
    referrer_id = fsm_data.get("referrer_id")

    await _activate_and_show_download(call, bot, state, referrer_id)


async def _activate_and_show_download(event: Message | CallbackQuery, bot: Bot,
                                       state: FSMContext, referrer_id: int | None = None):
    """Активирует триал/реферальный бонус и показывает шаг скачивания приложения."""
    user_id = event.from_user.id
    trial_days = 7

    try:
        if referrer_id:
            # Реферальный путь: установить реферера + выдать подписку
            await referral_service.activate_new_user_referral(user_id, referrer_id, trial_days)
            try:
                await bot.send_message(
                    referrer_id,
                    f"По вашей ссылке зарегистрировался новый пользователь: {event.from_user.full_name}!"
                )
            except Exception as e:
                logger.error(f"Could not notify referrer {referrer_id}: {e}")
        else:
            # Обычный триал
            await subscription_service.activate_trial(user_id, trial_days)

        logger.info(f"Trial activated for user {user_id} (referrer={referrer_id})")

    except Exception as e:
        logger.error(f"Failed to activate trial for user {user_id}: {e}", exc_info=True)

    # Показываем шаг 2: скачивание приложения
    text = (
        f"🎉 <b>Поздравляем!</b> Вам предоставлен пробный период на <b>{trial_days} дней</b>.\n\n"
        "📲 <b>Шаг 1:</b> Скачайте приложение <b>Happ</b> для вашего устройства:"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=onboarding_download_app_keyboard())
    else:
        await event.answer(text, reply_markup=onboarding_download_app_keyboard())


# =============================================================================
# --- ОНБОРДИНГ: ШАГ 2 — СКАЧИВАНИЕ ПРИЛОЖЕНИЯ ---
# =============================================================================

@start_router.callback_query(F.data == "onboarding_app_installed")
async def onboarding_app_installed(call: CallbackQuery, bot: Bot):
    """Пользователь установил приложение — показываем кнопку импорта."""
    await call.answer()
    user_id = call.from_user.id

    # Получаем subscription_url из профиля
    profile_data = await profile_service.get_profile(user_id)
    if profile_data.error or not profile_data.marzban_user:
        await call.message.edit_text(
            "📲 <b>Шаг 2:</b> Подключите VPN\n\n"
            "Ваш ключ подключения ещё формируется. "
            "Перейдите в главное меню и откройте <b>«Мои ключи»</b>, чтобы получить ключ.",
            reply_markup=main_menu_keyboard(has_active_sub=False)
        )
        return

    sub_url = get_user_attribute(profile_data.marzban_user, 'subscription_url', '')
    from marzban.init_client import MarzClientCache
    marzban: MarzClientCache = profile_service._marzban
    domain = marzban._config.webhook.domain
    full_sub_url = f"https://{domain}:8443{sub_url}" if sub_url else ""

    if full_sub_url:
        text = (
            "📲 <b>Шаг 2:</b> Подключите VPN\n\n"
            "Нажмите кнопку ниже, чтобы автоматически импортировать вашу подписку в приложение <b>Happ</b>.\n\n"
            "После подключения вы сможете пользоваться VPN!"
        )
        await call.message.edit_text(text, reply_markup=onboarding_import_keyboard(full_sub_url))
    else:
        await call.message.edit_text(
            "📲 Ваш профиль ещё создаётся. Перейдите в главное меню и откройте <b>«Мои ключи»</b>.",
            reply_markup=main_menu_keyboard(has_active_sub=False)
        )


# =============================================================================
# --- БЛОК: ОТОБРАЖЕНИЕ РЕФЕРАЛЬНОЙ ПРОГРАММЫ ---
# =============================================================================

async def show_referral_info(message: Message, bot: Bot):
    """Вспомогательная функция для показа информации о реферальной программе."""
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref{user_id}"
    ref_info = await user_service.get_referral_info(user_id)

    text = (
        "🤝 <b>Ваша реферальная программа</b>\n\n"
        "Приглашайте друзей и получайте за это приятные бонусы!\n\n"
        "🔗 <b>Ваша персональная ссылка для приглашений:</b>\n"
        f"<code>{referral_link}</code>\n"
        "<i>(нажмите, чтобы скопировать)</i>\n\n"
        f"👤 <b>Вы пригласили:</b> {ref_info['referral_count']} чел.\n"
        f"🎁 <b>Ваши бонусные дни:</b> {ref_info['bonus_days']} дн.\n\n"
        "Вы будете получать <b>14 бонусных дней</b> за каждую первую оплату подписки вашим другом."
    )

    # Если это колбэк, редактируем сообщение. Если команда - отправляем новое.
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(text, reply_markup=back_to_main_menu_keyboard())
    else:
        await message.answer(text, reply_markup=back_to_main_menu_keyboard())

# Хендлер для команды /referral
@start_router.message(Command("referral"))
async def referral_command_handler(message: Message, bot: Bot):
    await show_referral_info(message, bot)

# Хендлер для кнопки "Реферальная программа"
@start_router.callback_query(F.data == "referral_program")
async def referral_program_handler(call: CallbackQuery, bot: Bot):
    await call.answer()
    await show_referral_info(call, bot)

@start_router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu_handler(call: CallbackQuery, state: FSMContext):
    """Возвращает пользователя в главное меню со статусом подписки."""
    await state.clear()
    await call.answer()
    await _show_main_menu(call, call.from_user.id, call.from_user.full_name)
