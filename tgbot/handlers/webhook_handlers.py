# tgbot/handlers/webhook_handlers.py (финальная, полная версия)

import logging
from aiohttp import web
from aiogram import Bot

# Импортируем наши сервисы и утилиты
from tgbot.services import payment
from database import requests as db
from marzban.init_client import MarzClientCache # Импортируем клиент Marzban для аннотации типов

logger = logging.getLogger(__name__)


async def yookassa_webhook_handler(request: web.Request):
    """
    Принимает и обрабатывает вебхуки от YooKassa,
    управляет подписками в БД и пользователями в Marzban.
    """
    try:
        request_body = await request.json()
        notification = payment.parse_webhook_notification(request_body)

        if notification is None:
            logger.warning("Received invalid webhook notification from YooKassa.")
            return web.Response(status=400)

        if notification.event == 'payment.succeeded':
            paid_payment = notification.object
            metadata = paid_payment.metadata
            
            try:
                user_id = int(metadata['user_id'])
                tariff_id = int(metadata['tariff_id'])
            except (KeyError, ValueError) as e:
                logger.error(f"Invalid metadata in webhook: {metadata}. Error: {e}")
                return web.Response(status=400)

            tariff = db.get_tariff_by_id(tariff_id)
            if not tariff:
                logger.error(f"Received payment for non-existent tariff_id: {tariff_id} from user {user_id}")
                return web.Response(status=400)

            logger.info(f"Received successful payment for user {user_id} on tariff '{tariff.name}'.")

            # --- ОСНОВНАЯ БИЗНЕС-ЛОГИКА ---

            # 1. Продлеваем подписку в НАШЕЙ БД
            subscription_days = tariff.duration_days
            db.extend_user_subscription(user_id, days=subscription_days)
            logger.info(f"Subscription for user {user_id} in local DB extended by {subscription_days} days.")
            
            # 2. Управляем пользователем в MARZBAN
            marzban: MarzClientCache = request.app['marzban']
            user = db.get_user(user_id)
            
            if not user.marzban_username:
                # Сценарий: Первая оплата -> СОЗДАЕМ пользователя в Marzban
                marzban_username = f"user_{user_id}"
                try:
                    await marzban.add_user(username=marzban_username, expire_days=subscription_days)
                    db.update_user_marzban_username(user_id, marzban_username)
                    logger.info(f"Successfully created Marzban user '{marzban_username}' for user_id {user_id}")
                except Exception as e:
                    logger.error(f"CRITICAL: Failed to create Marzban user for {user_id} after payment: {e}")
                    # Здесь обязательно нужно уведомить администратора о проблеме!
                    bot: Bot = request.app['bot']
                    admin_id = request.app['config'].tg_bot.admin_id
                    await bot.send_message(admin_id, f"⚠️ КРИТИЧЕСКАЯ ОШИБКА ⚠️\n\nНе удалось создать пользователя Marzban для user_id `{user_id}` после успешной оплаты. Проверьте логи!")

            else:
                # Сценарий: Повторная оплата -> ПРОДЛЕВАЕМ пользователя в Marzban
                try:
                    await marzban.modify_user(username=user.marzban_username, expire_days=subscription_days)
                    logger.info(f"Successfully modified Marzban user '{user.marzban_username}', extended subscription.")
                except Exception as e:
                    logger.error(f"CRITICAL: Failed to modify Marzban user {user.marzban_username} after payment: {e}")
                    # Здесь тоже нужно уведомить администратора
                    bot: Bot = request.app['bot']
                    admin_id = request.app['config'].tg_bot.admin_id
                    await bot.send_message(admin_id, f"⚠️ КРИТИЧЕСКАЯ ОШИБКА ⚠️\n\nНе удалось продлить подписку в Marzban для пользователя `{user.marzban_username}` (user_id: `{user_id}`) после успешной оплаты. Проверьте логи!")

            # 3. Начисляем бонус рефереру, если это первая оплата
            if user and user.referrer_id and not user.is_first_payment_made:
                bonus_days = 7  # Бонус рефереру (можно вынести в конфиг)
                db.add_bonus_days(user.referrer_id, days=bonus_days)
                db.set_first_payment_done(user_id) # Отмечаем, что первая оплата совершена
                logger.info(f"Referral bonus of {bonus_days} days awarded to user {user.referrer_id}.")
                
                try:
                    bot: Bot = request.app['bot']
                    await bot.send_message(
                        user.referrer_id,
                        f"🎉 Ваш реферал совершил первую оплату! Вам начислено **{bonus_days} бонусных дней**."
                    )
                except Exception as e:
                    logger.error(f"Could not send bonus notification to referrer {user.referrer_id}: {e}")

            # 4. Уведомляем самого пользователя об успехе
            try:
                bot: Bot = request.app['bot']
                await bot.send_message(user_id, f"✅ Оплата прошла успешно! Ваш тариф '{tariff.name}' активирован на {subscription_days} дней.")
            except Exception as e:
                logger.error(f"Could not send payment success notification to user {user_id}: {e}")

        # Отвечаем YooKassa, что все получили и обработали
        return web.Response(status=200)

    except Exception as e:
        logger.error(f"FATAL: Unhandled error in yookassa_webhook_handler: {e}", exc_info=True)
        return web.Response(status=500)