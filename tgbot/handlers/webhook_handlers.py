# tgbot/handlers/webhook_handlers.py

from datetime import datetime
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiohttp import web
from aiogram import Bot, Dispatcher

# Импорты
from tgbot.services import payment
from database import requests as db
from marzban.init_client import MarzClientCache
from loader import logger, config
from tgbot.handlers.user.profile import show_profile_logic

# --- 1. Логика продления подписки (Общая для Web и Bot) ---
async def _process_subscription_extension(user_id: int, tariff, marzban: MarzClientCache) -> bool:
    """
    Продлевает подписку в БД и Marzban. 
    Работает и для Telegram (положительный ID), и для Web (отрицательный ID).
    """
    subscription_days = tariff.duration_days
    
    # 1. Продлеваем в БД
    await db.extend_user_subscription(user_id, days=subscription_days)
    logger.info(f"Subscription for user {user_id} in local DB extended by {subscription_days} days.")

    # 2. Получаем данные для Marzban
    user_from_db = await db.get_user(user_id)
    if not user_from_db:
        logger.error(f"User {user_id} not found in DB during payment processing!")
        return False

    # Формируем username. Для Web юзеров он обычно уже есть (web_123), для новых TG может не быть.
    if user_from_db.marzban_username:
        marzban_username = user_from_db.marzban_username.lower()
    else:
        # Fallback для старых юзеров
        if user_id > 0:
            marzban_username = f"user_{user_id}" 
        else:
            marzban_username = f"web_{abs(user_id)}"

    is_new_user_for_marzban = False
    
    # 3. Обновляем Marzban
    try:
        user_in_marzban = await marzban.get_user(marzban_username)
        
        if user_in_marzban:
            # Продлеваем
            await marzban.modify_user(username=marzban_username, expire_days=subscription_days)
        else:
            # Создаем нового
            await marzban.add_user(username=marzban_username, expire_days=subscription_days)
            is_new_user_for_marzban = True
            
        # Если в БД не было записано имя маразабана, записываем
        if not user_from_db.marzban_username:
            await db.update_user_marzban_username(user_id, marzban_username)
            
    except Exception as e:
        logger.error(f"CRITICAL: Failed to sync Marzban user {marzban_username}: {e}", exc_info=True)
    
    return is_new_user_for_marzban


# --- 2. Логика рефералов (Только для TG, для Web пока пропускаем или дорабатываем) ---
async def _handle_referral_bonus(user_who_paid_id: int, marzban: MarzClientCache, bot: Bot):
    """Начисляет бонус рефереру. Работает только если реферер - TG юзер."""
    # Веб-юзеры пока не имеют реферальной системы в твоей модели (referrer_id ссылается на users)
    # Если ты добавишь рефералку на сайт, логика будет похожей.
    
    user_who_paid = await db.get_user(user_who_paid_id)
    if not (user_who_paid and user_who_paid.referrer_id and not user_who_paid.is_first_payment_made):
        return

    bonus_days = 30
    referrer_id = user_who_paid.referrer_id
    referrer = await db.get_user(referrer_id)
    
    if not referrer:
        return

    # Начисляем бонус
    try:
        # Продлеваем в Marzban если есть аккаунт
        if referrer.marzban_username:
            try:
                await marzban.modify_user(username=referrer.marzban_username, expire_days=bonus_days)
            except Exception as e:
                logger.error(f"Failed to extend marzban for referrer {referrer_id}: {e}")

        # Продлеваем в БД
        await db.extend_user_subscription(referrer_id, days=bonus_days)
        await db.add_bonus_days(referrer_id, days=bonus_days)
        
        logger.info(f"Referral bonus: Granted {bonus_days} days to referrer {referrer_id}")

        # Пытаемся уведомить реферера (только если это TG юзер, т.е. ID > 0)
        if referrer_id > 0:
            await bot.send_message(
                referrer_id,
                f"🎉 Ваш реферал совершил первую оплату! Вам начислено <b>{bonus_days} бонусных дней</b>."
            )
            
    except Exception as e:
        logger.error(f"Error handling referral bonus for {referrer_id}: {e}")


# --- 3. Логи уведомлений (Разделяем Web и TG) ---
async def _notify_tg_user(user_id: int, tariff, marzban: MarzClientCache, bot: Bot, request: web.Request):
    """Уведомление ТОЛЬКО для Telegram пользователей."""
    if user_id < 0: 
        return # Веб-юзерам в телеграм писать не можем

    # 1. Очистка состояния (удаление кнопок оплаты)
    try:
        dp: Dispatcher = request.app['dp']
        storage = dp.storage
        state = FSMContext(storage=storage, key=StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id))
        
        fsm_data = await state.get_data()
        msg_id = fsm_data.get("payment_message_id")
        if msg_id:
            await bot.edit_message_text(chat_id=user_id, message_id=msg_id, text="✅ <i>Счет оплачен.</i>", reply_markup=None)
        await state.clear()
    except Exception: 
        pass

    # 2. Сообщение об успехе и показ профиля
    try:
        await bot.send_message(user_id, f"✅ Оплата успешна! Тариф '<b>{tariff.name}</b>' активирован.")
        
        # Фейковое сообщение для вызова профиля
        from aiogram.types import User, Chat, Message
        fake_msg = Message(
            message_id=0, date=datetime.now(), 
            chat=Chat(id=user_id, type="private"), 
            from_user=User(id=user_id, is_bot=False, first_name="User")
        )
        await show_profile_logic(fake_msg, marzban, bot)
    except Exception as e:
        logger.error(f"Failed to notify TG user {user_id}: {e}")


async def _log_transaction(bot: Bot, user_id: int, tariff_name: str, price: float, is_new: bool):
    """Логирование в админ-чат. Пишем, откуда пришла оплата."""
    user = await db.get_user(user_id)
    if not user: return

    # Определяем источник
    source_icon = "🌐 WEB" if user_id < 0 else "🤖 BOT"
    action = "💎 Новая подписка" if is_new else "🔄 Продление"
    
    username_text = f"@{user.username}" if user.username else "Нет"
    
    text = (
        f"{source_icon} | {action}\n\n"
        f"👤 <b>User:</b> {user.full_name} (ID: <code>{user.user_id}</code>)\n"
        f"🏷 <b>Username:</b> {username_text}\n\n"
        f"💳 <b>Тариф:</b> {tariff_name}\n"
        f"💰 <b>Сумма:</b> {price} RUB"
    )
    
    try:
        await bot.send_message(
            chat_id=config.tg_bot.support_chat_id,
            message_thread_id=config.tg_bot.transaction_log_topic_id,
            text=text
        )
    except Exception as e:
        logger.error(f"Failed to send transaction log: {e}")


# --- ГЛАВНЫЙ ХЕНДЛЕР ---
async def yookassa_webhook_handler(request: web.Request):
    try:
        # 1. Парсим запрос
        request_body = await request.json()
        notification = payment.parse_webhook_notification(request_body)

        if not notification or notification.event != 'payment.succeeded':
            return web.Response(status=400)

        # 2. Достаем данные
        metadata = notification.object.metadata
        user_id = int(metadata.get('user_id', 0))
        tariff_id = int(metadata.get('tariff_id', 0))
        
        # 3. Валидация
        tariff = await db.get_tariff_by_id(tariff_id)
        if not tariff or not user_id:
            logger.error(f"Invalid webhook data: user={user_id}, tariff={tariff_id}")
            return web.Response(status=400)

        user_from_db = await db.get_user(user_id)
        if not user_from_db:
             logger.error(f"User {user_id} not found for payment.")
             return web.Response(status=200) # Отвечаем ОК Юкассе, чтобы не слала повторы

        is_first_payment = not user_from_db.is_first_payment_made
        logger.info(f"Payment success: User {user_id}, Tariff {tariff.name}")

        # 4. Получаем зависимости
        bot: Bot = request.app['bot']
        marzban: MarzClientCache = request.app['marzban']

        # --- ОСНОВНАЯ ЛОГИКА ---
        
        # А) Продлеваем подписку (БД + Marzban)
        is_new_marzban_user = await _process_subscription_extension(user_id, tariff, marzban)
        
        # Б) Рефералка (начислит бонус тому, кто пригласил этого юзера)
        await _handle_referral_bonus(user_id, marzban, bot)
        
        # В) Лог транзакции админу
        await _log_transaction(bot, user_id, tariff.name, tariff.price, is_new_marzban_user)
        
        # Г) Уведомление пользователя (только если это TG бот)
        if user_id > 0:
            await _notify_tg_user(user_id, tariff, marzban, bot, request)
        
        # Д) Фиксируем первую оплату
        if is_first_payment:
            await db.set_first_payment_done(user_id)

        return web.Response(status=200)

    except Exception as e:
        logger.error(f"FATAL Webhook Error: {e}", exc_info=True)
        return web.Response(status=500)