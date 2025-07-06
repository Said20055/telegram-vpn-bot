# tgbot/handlers/webhook_handlers.py (финальная версия с явной обработкой 409 ошибки)

import logging
import httpx  # <--- ДОБАВЛЕН ВАЖНЫЙ ИМПОРТ
from aiohttp import web
from aiogram import Bot

# Импортируем наши сервисы и утилиты
from tgbot.services import payment
from database import requests as db
from marzban.init_client import MarzClientCache

logger = logging.getLogger(__name__)


async def yookassa_webhook_handler(request: web.Request):
    """
    Принимает и обрабатывает вебхуки от YooKassa.
    Реализована отказоустойчивая логика создания/изменения пользователя Marzban
    с явной обработкой ошибки 409 Conflict.
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
            user_from_db = db.get_user(user_id)
            marzban_username = (user_from_db.marzban_username or f"user_{user_id}").lower()

            try:
                if user_from_db.marzban_username:
                    # Если в нашей БД есть имя, мы ТОЧНО знаем, что юзер должен быть. ПРОДЛЕВАЕМ.
                    logger.info(f"User '{marzban_username}' found in local DB. Modifying...")
                    await marzban.modify_user(username=marzban_username, expire_days=subscription_days)
                    logger.info(f"Successfully modified Marzban user '{marzban_username}'.")
                else:
                    # Если в нашей БД имени нет, мы ПЫТАЕМСЯ СОЗДАТЬ.
                    logger.info(f"User '{marzban_username}' not in local DB. Attempting to create...")
                    await marzban.add_user(username=marzban_username, expire_days=subscription_days)
                    logger.info(f"Successfully created Marzban user '{marzban_username}'.")
                    # И только после успешного создания обновляем нашу БД
                    db.update_user_marzban_username(user_id, marzban_username)

            except httpx.HTTPStatusError as e:
                # ЯВНАЯ ОБРАБОТКА ОШИБКИ 409
                if e.response.status_code == 409: # 409 Conflict - User already exists
                    logger.warning(f"Marzban user '{marzban_username}' already exists (409 Conflict). Modifying instead and fixing local DB.")
                    try:
                        # Пытаемся продлить существующего пользователя
                        await marzban.modify_user(username=marzban_username, expire_days=subscription_days)
                        # Синхронизируем нашу БД, если нужно
                        if not user_from_db.marzban_username:
                            db.update_user_marzban_username(user_id, marzban_username)
                        logger.info(f"Successfully modified existing user '{marzban_username}' after 409 conflict.")
                    except Exception as inner_e:
                        logger.error(f"CRITICAL: Failed to modify Marzban user '{marzban_username}' even after 409 conflict: {inner_e}", exc_info=True)
                        # TODO: Уведомить админа
                else:
                    # Если это любая другая ошибка HTTP (400, 500, и т.д.)
                    logger.error(f"CRITICAL: HTTP error while managing Marzban user {marzban_username}: {e}", exc_info=True)
                    # TODO: Уведомить админа

            except Exception as e:
                # Все остальные ошибки (сетевые и т.д.)
                logger.error(f"CRITICAL: Generic error while managing Marzban user {marzban_username}: {e}", exc_info=True)
                # TODO: Уведомить админа

            # 3. Начисляем бонус рефереру
            if user_from_db and user_from_db.referrer_id and not user_from_db.is_first_payment_made:
                bonus_days = 7
                db.add_bonus_days(user_from_db.referrer_id, days=bonus_days)
                db.set_first_payment_done(user_id)
                logger.info(f"Referral bonus of {bonus_days} days awarded to user {user_from_db.referrer_id}.")
                try:
                    bot: Bot = request.app['bot']
                    await bot.send_message(user_from_db.referrer_id, f"🎉 Ваш реферал совершил первую оплату! Вам начислено **{bonus_days} бонусных дней**.")
                except Exception as e:
                    logger.error(f"Could not send bonus notification to referrer {user_from_db.referrer_id}: {e}")

            # 4. Уведомляем пользователя об успехе
            try:
                bot: Bot = request.app['bot']
                await bot.send_message(user_id, f"✅ Оплата прошла успешно! Ваш тариф '{tariff.name}' активирован на {subscription_days} дней.")
            except Exception as e:
                logger.error(f"Could not send payment success notification to user {user_id}: {e}")

        return web.Response(status=200)

    except Exception as e:
        logger.error(f"FATAL: Unhandled error in yookassa_webhook_handler: {e}", exc_info=True)
        return web.Response(status=500)