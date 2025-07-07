# tgbot/handlers/webhook_handlers.py (с реальным начислением бонусов)
import httpx
from aiohttp import web
from aiogram import Bot

# Импортируем наши сервисы и утилиты
from tgbot.services import payment
from database import requests as db
from marzban.init_client import MarzClientCache
from loader import logger


async def yookassa_webhook_handler(request: web.Request):
    """
    Принимает и обрабатывает вебхуки от YooKassa.
    Реализована отказоустойчивая логика управления пользователями Marzban
    и реальное начисление реферальных бонусов.
    """
    try:
        request_body = await request.json()
        notification = payment.parse_webhook_notification(request_body)

        if notification is None:
            logger.warning("Received invalid webhook notification from YooKassa.")
            return web.Response(status=400)

        if notification.event == 'payment.succeeded':
            # --- Блок получения данных (без изменений) ---
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

            # --- Управление пользователем, который оплатил (без изменений) ---
            subscription_days = tariff.duration_days
            db.extend_user_subscription(user_id, days=subscription_days)
            logger.info(f"Subscription for user {user_id} in local DB extended by {subscription_days} days.")

            marzban: MarzClientCache = request.app['marzban']
            user_from_db = db.get_user(user_id)
            marzban_username = (user_from_db.marzban_username or f"user_{user_id}").lower()

            try:
                # ... (вся ваша отказоустойчивая логика add/modify user с обработкой 409 ошибки остается здесь)
                if user_from_db.marzban_username:
                    await marzban.modify_user(username=marzban_username, expire_days=subscription_days)
                else:
                    await marzban.add_user(username=marzban_username, expire_days=subscription_days)
                    db.update_user_marzban_username(user_id, marzban_username)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 409:
                    logger.warning(f"Marzban user '{marzban_username}' already exists. Modifying and fixing DB.")
                    await marzban.modify_user(username=marzban_username, expire_days=subscription_days)
                    if not user_from_db.marzban_username:
                        db.update_user_marzban_username(user_id, marzban_username)
                else:
                    logger.error(f"CRITICAL: HTTP error for {marzban_username}: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"CRITICAL: Generic error for {marzban_username}: {e}", exc_info=True)


            # =================================================================
            # === НАЧАЛО ОБНОВЛЕННОГО БЛОКА НАЧИСЛЕНИЯ БОНУСОВ ===
            # =================================================================

            bot: Bot = request.app['bot'] # Получаем бота заранее

            if user_from_db and user_from_db.referrer_id and not user_from_db.is_first_payment_made:
                bonus_days = 7
                referrer = db.get_user(user_from_db.referrer_id)

                # Проверяем, есть ли у реферера активная подписка
                if referrer and referrer.marzban_username:
                    try:
                        # 1. Реально продлеваем подписку в Marzban
                        await marzban.modify_user(username=referrer.marzban_username, expire_days=bonus_days)
                        # 2. Реально продлеваем подписку в нашей БД
                        db.extend_user_subscription(referrer.user_id, days=bonus_days)

                        logger.info(f"Referral bonus: Extended subscription for referrer {referrer.user_id} by {bonus_days} days.")

                        # 3. Уведомляем реферера об успехе
                        await bot.send_message(
                            referrer.user_id,
                            f"🎉 Ваш реферал совершил первую оплату! Вам начислено <b>{bonus_days} бонусных дней</b> подписки."
                        )
                    except Exception as e:
                        # Если не удалось продлить, начисляем виртуальные дни и уведомляем
                        logger.error(f"Failed to apply referral bonus to user {referrer.user_id}: {e}")
                        db.add_bonus_days(referrer.user_id, days=bonus_days)
                        await bot.send_message(
                            referrer.user_id,
                            f"🎉 Ваш реферал совершил первую оплату! Вам начислено <b>{bonus_days} бонусных дней</b>. Они будут применены при следующей оплате."
                        )
                else:
                    # Если у реферера вообще нет подписки, просто начисляем виртуальные дни
                    if referrer:
                        db.add_bonus_days(referrer.user_id, days=bonus_days)
                        logger.info(f"Referral bonus: Added {bonus_days} virtual bonus days to user {referrer.user_id}.")
                        try:
                            await bot.send_message(
                                referrer.user_id,
                                f"🎉 Ваш реферал совершил первую оплату! Вам начислено <b>{bonus_days} бонусных дней</b>."
                            )
                        except Exception:
                            pass

                # В любом случае отмечаем, что первая оплата совершена
                db.set_first_payment_done(user_id)

            # =================================================================
            # === КОНЕЦ ОБНОВЛЕННОГО БЛОКА ===
            # =================================================================

            # Уведомляем пользователя, который оплатил
            try:
                await bot.send_message(user_id, f"✅ Оплата прошла успешно! Ваш тариф '<b>{tariff.name}</b>' активирован на <b>{subscription_days} дней</b>.")
            except Exception as e:
                logger.error(f"Could not send payment success notification to user {user_id}: {e}")

        return web.Response(status=200)

    except Exception as e:
        logger.error(f"FATAL: Unhandled error in yookassa_webhook_handler: {e}", exc_info=True)
        return web.Response(status=500)

