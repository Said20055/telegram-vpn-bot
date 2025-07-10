# tgbot/handlers/webhook_handlers.py (Оптимиз
from datetime import datetime
from aiohttp import web
from aiogram import Bot

# Импортируем сервисы, БД, клиент и логгер
from tgbot.services import payment
from database import requests as db
from marzban.init_client import MarzClientCache
from loader import logger

# Импортируем нашу функцию для показа профиля из хендлеров
from tgbot.handlers.user.profile import show_profile_logic


# --- 1. Логика управления основным пользователем ---
async def _handle_user_payment(user_id: int, tariff, marzban: MarzClientCache):
    """Продлевает подписку в БД и создает/модифицирует пользователя в Marzban."""
    subscription_days = tariff.duration_days
    db.extend_user_subscription(user_id, days=subscription_days)
    logger.info(f"Subscription for user {user_id} in local DB extended by {subscription_days} days.")

    user_from_db = db.get_user(user_id)
    marzban_username = (user_from_db.marzban_username or f"user_{user_id}").lower()

    try:
        if await marzban.get_user(marzban_username):
            await marzban.modify_user(username=marzban_username, expire_days=subscription_days)
        else:
            await marzban.add_user(username=marzban_username, expire_days=subscription_days)
        
        if not user_from_db.marzban_username:
            db.update_user_marzban_username(user_id, marzban_username)
            
    except Exception as e:
        logger.error(f"CRITICAL: Failed to create/modify Marzban user {marzban_username}: {e}", exc_info=True)
        # TODO: Добавить отправку уведомления админу о критической ошибке


# --- 2. Логика начисления реферального бонуса ---
async def _handle_referral_bonus(user_who_paid_id: int, marzban: MarzClientCache, bot: Bot):
    """Проверяет и начисляет бонус рефереру."""
    user_who_paid = db.get_user(user_who_paid_id)
    if not (user_who_paid and user_who_paid.referrer_id and not user_who_paid.is_first_payment_made):
        return # Если нет реферера или это не первая оплата - выходим

    bonus_days = 7
    referrer = db.get_user(user_who_paid.referrer_id)
    if not referrer:
        return

    # Если у реферера есть активный аккаунт, продлеваем его везде
    if referrer.marzban_username:
        try:
            await marzban.modify_user(username=referrer.marzban_username, expire_days=bonus_days)
            db.extend_user_subscription(referrer.user_id, days=bonus_days)
            logger.info(f"Referral bonus: Extended subscription for referrer {referrer.user_id} by {bonus_days} days.")
            await bot.send_message(
                referrer.user_id,
                f"🎉 Ваш реферал совершил первую оплату! Вам начислено <b>{bonus_days} бонусных дней</b> подписки."
            )
        except Exception as e:
            logger.error(f"Failed to apply referral bonus to user {referrer.user_id}: {e}")
            db.add_bonus_days(referrer.user_id, days=bonus_days) # Начисляем виртуальные дни
            await bot.send_message(referrer.user_id, "Не удалось продлить вашу подписку, бонусные дни зачислены на ваш баланс.")
    else:
        # Если у реферера нет аккаунта, просто даем виртуальные дни
        db.add_bonus_days(referrer.user_id, days=bonus_days)
        logger.info(f"Referral bonus: Added {bonus_days} virtual bonus days to user {referrer.user_id}.")
        try:
            await bot.send_message(referrer.user_id, f"🎉 Ваш реферал совершил первую оплату! Вам начислено <b>{bonus_days} бонусных дней</b>.")
        except Exception: pass
            
    db.set_first_payment_done(user_who_paid_id)


# --- 3. Логика уведомления пользователя об оплате и показ ключей ---
async def _notify_user_and_show_keys(user_id: int, tariff, marzban: MarzClientCache, bot: Bot, request: web.Request):
    """Уведомляет пользователя об успехе и показывает его профиль с ключами."""
    try:
        await bot.send_message(
            user_id, 
            f"✅ Оплата прошла успешно! Ваш тариф '<b>{tariff.name}</b>' активирован на <b>{tariff.duration_days} дней</b>."
        )
        
        # --- ВЫЗОВ "МОИ КЛЮЧИ" ---
        # Создаем фейковый объект Message, чтобы передать его в show_profile_logic
        from aiogram.types import User, Chat, Message
        fake_user = User(id=user_id, is_bot=False, first_name="N/A")
        fake_chat = Chat(id=user_id, type="private")
        fake_message = Message(message_id=0, date=datetime.now(), chat=fake_chat, from_user=fake_user, bot=bot)
        
        # Вызываем функцию показа профиля, которую мы уже написали
        await show_profile_logic(fake_message, marzban, bot)
        
    except Exception as e:
        logger.error(f"Could not send payment success notification to user {user_id}: {e}")


# --- ГЛАВНЫЙ ХЕНДЛЕР ВЕБХУКА ---
async def yookassa_webhook_handler(request: web.Request):
    """
    Принимает вебхуки от YooKassa и делегирует задачи соответствующим функциям.
    """
    try:
        request_body = await request.json()
        notification = payment.parse_webhook_notification(request_body)

        if notification is None or notification.event != 'payment.succeeded':
            return web.Response(status=400)

        metadata = notification.object.metadata
        user_id = int(metadata['user_id'])
        tariff_id = int(metadata['tariff_id'])
        tariff = db.get_tariff_by_id(tariff_id)

        if not tariff:
            logger.error(f"Webhook for non-existent tariff_id: {tariff_id}")
            return web.Response(status=400)
            
        logger.info(f"Webhook: Processing successful payment for user {user_id}, tariff '{tariff.name}'.")

        # Получаем объекты бота и клиента Marzban из приложения
        bot: Bot = request.app['bot']
        marzban: MarzClientCache = request.app['marzban']

        # Вызываем наши функции последовательно
        await _handle_user_payment(user_id, tariff, marzban)
        await _handle_referral_bonus(user_id, marzban, bot)
        await _notify_user_and_show_keys(user_id, tariff, marzban, bot, request)

        return web.Response(status=200)

    except Exception as e:
        logger.error(f"FATAL: Unhandled error in yookassa_webhook_handler: {e}", exc_info=True)
        return web.Response(status=500)