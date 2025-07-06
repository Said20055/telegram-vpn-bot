from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
# --- ИЗМЕНЕНИЯ В ИМПОРТАХ ---
# 1. Импортируем Bot из aiogram, т.к. теперь он передается в хендлеры
# 2. Убираем импорт bot из loader, т.к. он больше не нужен напрямую здесь
# 3. Импортируем наши новые клавиатуры
from tgbot.keyboards.inline import (main_menu_keyboard, help_keyboard, 
                                    back_to_main_menu_keyboard, tariffs_keyboard)
# 4. Импортируем наш модуль для работы с БД
from database import requests as db
from tgbot.services import payment
from utils import logger
import logging

logger = logging.getLogger(__name__)
user_router = Router()

# --- ОБНОВЛЕННЫЙ ОБРАБОТЧИК /start ---
# Он теперь обрабатывает и обычный старт, и реферальный
@user_router.message(CommandStart(deep_link=True, magic=F.args.startswith('ref')))
async def start_with_referral(message: Message, command: CommandObject, bot: Bot):
    """
    Этот хендлер сработает ТОЛЬКО если команда /start содержит deep-link,
    и этот deep-link начинается с 'ref'.
    Пример: /start ref123456
    """
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username
    
    # command.args — это и есть наш payload, например, 'ref123456'
    referrer_id = None
    try:
        potential_referrer_id = int(command.args[3:]) # Убираем 'ref'
        if potential_referrer_id != user_id:
            if db.get_user(potential_referrer_id):
                referrer_id = potential_referrer_id
    except (ValueError, IndexError, TypeError):
        pass # Если ID некорректный, просто игнорируем

    user, created = db.get_or_create_user(user_id, full_name, username)

    if created and referrer_id:
        db.set_user_referrer(user_id, referrer_id)
        db.add_bonus_days(user_id, 3)
        await message.answer("🎉 Добро пожаловать! Вы пришли по приглашению и получили **3 бонусных дня** подписки!")
        try:
            await bot.send_message(referrer_id, f"По вашей ссылке зарегистрировался новый пользователь: {full_name}!")
        except Exception as e:
            # Логируем ошибку, чтобы понять, почему не отправилось уведомление
            logger.error(f"Could not send notification to referrer {referrer_id}: {e}")
            pass
    elif not created:
        await message.answer("Вы уже зарегистрированы в боте. Реферальная ссылка работает только для новых пользователей.")

    # В любом случае показываем главное меню
    await message.answer(f'👋 Привет, {full_name}!',
                         reply_markup=main_menu_keyboard())


@user_router.message(CommandStart())
async def user_start_default(message: Message):
    """
    Этот хендлер сработает для обычной команды /start БЕЗ аргументов.
    Он должен идти ПОСЛЕ хендлера с deep-link.
    """
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username

    # Просто создаем или получаем пользователя
    db.get_or_create_user(user_id, full_name, username)
    
    await message.answer(f'👋 Привет, {full_name}!\n\n'
                         'Я помогу тебе с VPN.\n'
                         'Исходный код бота - <a href="https://github.com/yarodya1/telegram-vpn-bot">GitHub</a>',
                         reply_markup=main_menu_keyboard(), disable_web_page_preview=True)

# --- ОБРАБОТЧИК ДЛЯ /help И КНОПКИ 'help_info' ---
# Объединил вашу логику для команды и колбэка, чтобы не дублировать код
async def show_help_info(message: Message):
    text = (
        'ℹ️ **Помощь и информация**\n\n'
        'Бот предоставляет доступ к VPN на базе '
        '<a href="https://github.com/XTLS/Xray-core">Xray-core</a> и созданный с использованием Python.\n\n'
        'Для подключения используйте один из рекомендованных клиентов:'
    )
    await message.answer(text, reply_markup=help_keyboard(), disable_web_page_preview=True)

@user_router.message(Command('help'))
async def help_command_handler(message: Message):
    await show_help_info(message)

# Меняем callback_data на 'help_info' в соответствии с новой клавиатурой
@user_router.callback_query(F.data == 'help_info')
async def help_callback_handler(callback_query: CallbackQuery):
    # Используем edit_text, чтобы не слать новое сообщение, а менять старое
    await callback_query.answer()
    await show_help_info(callback_query.message)


# --- НОВЫЕ ОБРАБОТЧИКИ ДЛЯ РЕФЕРАЛЬНОЙ СИСТЕМЫ И ПРОФИЛЯ ---

@user_router.callback_query(F.data == "referral_program")
async def referral_program_handler(call: CallbackQuery, bot: Bot):
    await call.answer()
    user_id = call.from_user.id
    bot_info = await bot.get_me()
    
    referral_link = f"https://t.me/{bot_info.username}?start=ref{user_id}"
    user_data = db.get_user(user_id)
    referral_count = db.count_user_referrals(user_id)
    
    text = (
        "🤝 **Ваша реферальная программа**\n\n"
        "Приглашайте друзей и получайте за это приятные бонусы!\n\n"
        "🔗 **Ваша персональная ссылка для приглашений:**\n"
        f"`{referral_link}`\n"
        "(нажмите, чтобы скопировать)\n\n"
        f"👤 **Вы пригласили:** {referral_count} чел.\n"
        f"🎁 **Ваши бонусные дни:** {user_data.referral_bonus_days} дн.\n\n"
        "Вы будете получать **7 бонусных дней** за каждую первую оплату подписки вашим другом."
    )
    
    await call.message.edit_text(text, reply_markup=back_to_main_menu_keyboard())


# Обработчик для кнопки "Назад"
@user_router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu_handler(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(f'👋 Привет, {call.from_user.full_name}!',
                                 reply_markup=main_menu_keyboard())

@user_router.callback_query(F.data == "buy_subscription")
async def buy_subscription_handler(call: CallbackQuery):
    await call.answer()
    
    # --- ОТЛАДКА ---
    logger.info(f"User {call.from_user.id} requested tariffs. Trying to fetch from DB...")
    
    # Получаем активные тарифы из БД
    active_tariffs = db.get_active_tariffs()
    
    # --- ОТЛАДКА ---
    # Проверим, что вернулось из базы данных
    if active_tariffs:
        # Конвертируем в список, если это итератор, чтобы можно было посчитать
        tariffs_list = list(active_tariffs)
        logger.info(f"Successfully fetched {len(tariffs_list)} tariffs from DB.")
        # Выведем в лог названия тарифов для проверки
        for t in tariffs_list:
            logger.info(f" - Tariff: {t.name}, Price: {t.price}")
    else:
        logger.warning("db.get_active_tariffs() returned None or empty list.")
        
    if not tariffs_list:
        logger.error("No active tariffs found. Showing error message to user.")
        await call.message.edit_text("К сожалению, сейчас нет доступных тарифов для покупки. Попробуйте позже.")
        return
        
    await call.message.edit_text(
        "Пожалуйста, выберите тарифный план:",
        reply_markup=tariffs_keyboard(tariffs_list)
    )
@user_router.callback_query(F.data.startswith("select_tariff_"))
async def select_tariff_handler(call: CallbackQuery, bot: Bot):
    await call.answer()
    tariff_id = int(call.data.split("_")[2]) # Извлекаем ID тарифа из "select_tariff_1"
    
    tariff = db.get_tariff_by_id(tariff_id)
    if not tariff:
        await call.message.edit_text("Ошибка! Тариф не найден.")
        return

    user_id = call.from_user.id
    
    # Формируем описание и цену из тарифа
    amount = tariff.price
    description = f"Оплата тарифа '{tariff.name}'"
    
    bot_info = await bot.get_me()
    
    # Создаем платеж, но теперь в metadata добавляем еще и tariff_id!
    payment_url, payment_id = payment.create_payment(
        user_id=user_id, 
        amount=amount, 
        description=description, 
        bot_username=bot_info.username,
        # --- ВАЖНОЕ ДОПОЛНЕНИЕ ---
        metadata={'user_id': str(user_id), 'tariff_id': tariff_id}
    )
    
    payment_kb = InlineKeyboardBuilder()
    payment_kb.button(text="💳 Перейти к оплате", url=payment_url)
    payment_kb.button(text="⬅️ Назад к выбору тарифа", callback_data="buy_subscription")
    payment_kb.adjust(1)
    
    await call.message.edit_text(
        f"Вы выбрали тариф: **{tariff.name}**\n"
        f"Срок: **{tariff.duration_days} дней**\n"
        f"Сумма к оплате: **{tariff.price} RUB**\n\n"
        "Нажмите на кнопку ниже, чтобы перейти к оплате.",
        reply_markup=payment_kb.as_markup()
    )
# --- Здесь будут обработчики для кнопок "Получить VPN" и "Мой профиль" ---
# Пока что сделаем заглушки

@user_router.callback_query(F.data == "get_vpn")
async def get_vpn_handler(call: CallbackQuery):
    await call.answer("Раздел 'Получить VPN' в разработке.", show_alert=True)

@user_router.callback_query(F.data == "my_profile")
async def my_profile_handler(call: CallbackQuery):
    # Здесь в будущем будет информация о подписке пользователя
    await call.answer("Раздел 'Мой профиль' в разработке.", show_alert=True)