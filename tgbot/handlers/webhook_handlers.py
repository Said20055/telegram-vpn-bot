# tgbot/handlers/webhook_handlers.py

from datetime import datetime
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiohttp import web
from aiogram import Bot, Dispatcher

from tgbot.services import payment_service
from tgbot.services.payment import parse_webhook_notification
from database import user_repo
from loader import logger, config
from tgbot.handlers.user.profile import show_profile_logic


async def _notify_tg_user(user_id: int, tariff, marzban, bot: Bot, request: web.Request):
    """Уведомление ТОЛЬКО для Telegram пользователей."""
    if user_id < 0:
        return

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

    try:
        await bot.send_message(user_id, f"✅ Оплата успешна! Тариф '<b>{tariff.name}</b>' активирован.")

        from aiogram.types import User, Chat, Message
        fake_msg = Message(
            message_id=0, date=datetime.now(),
            chat=Chat(id=user_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="User")
        )
        await show_profile_logic(fake_msg, marzban, bot)
    except Exception as e:
        logger.error(f"Failed to notify TG user {user_id}: {e}")


async def _log_transaction(bot: Bot, user_id: int, tariff_name: str, price: float,
                           is_new: bool, payment=None):
    """Логирование в админ-чат с информацией о скидке."""
    user = await user_repo.get(user_id)
    if not user:
        return

    source_icon = "🌐 WEB" if user_id < 0 else "🤖 BOT"
    action = "💎 Новая подписка" if is_new else "🔄 Продление"
    username_text = f"@{user.username}" if user.username else "Нет"

    # Формируем строку суммы с учётом скидки
    if payment and payment.discount_percent > 0:
        amount_text = (
            f"{payment.final_amount:.2f} RUB "
            f"(скидка {payment.discount_percent}%, промокод {payment.promo_code}, "
        )
    else:
        amount_text = f"{price:.2f} RUB"

    text = (
        f"{source_icon} | {action}\n\n"
        f"👤 <b>User:</b> {user.full_name} (ID: <code>{user.user_id}</code>)\n"
        f"🏷 <b>Username:</b> {username_text}\n\n"
        f"💳 <b>Тариф:</b> {tariff_name}\n"
        f"💰 <b>Сумма:</b> {amount_text}"
    )

    try:
        await bot.send_message(
            chat_id=config.tg_bot.support_chat_id,
            message_thread_id=config.tg_bot.transaction_log_topic_id,
            text=text
        )
    except Exception as e:
        logger.error(f"Failed to send transaction log: {e}")


async def _log_refund(bot: Bot, payment):
    """Логирование возврата в админ-чат."""
    user = await user_repo.get(payment.user_id)
    if not user:
        return

    username_text = f"@{user.username}" if user.username else "Нет"

    text = (
        f"💸 <b>ВОЗВРАТ</b>\n\n"
        f"👤 <b>User:</b> {user.full_name} (ID: <code>{user.user_id}</code>)\n"
        f"🏷 <b>Username:</b> {username_text}\n\n"
        f"💰 <b>Сумма возврата:</b> {payment.final_amount:.2f} RUB\n"
        f"🆔 <b>YooKassa ID:</b> <code>{payment.yookassa_payment_id}</code>"
    )

    try:
        await bot.send_message(
            chat_id=config.tg_bot.support_chat_id,
            message_thread_id=config.tg_bot.transaction_log_topic_id,
            text=text
        )
    except Exception as e:
        logger.error(f"Failed to send refund log: {e}")


# --- ГЛАВНЫЙ ХЕНДЛЕР ---
async def yookassa_webhook_handler(request: web.Request):
    try:
        request_body = await request.json()
        notification = parse_webhook_notification(request_body)

        if not notification:
            return web.Response(status=400)

        event_type = notification.event
        payment_obj = notification.object
        yookassa_payment_id = payment_obj.id

        bot: Bot = request.app['bot']
        marzban = request.app['marzban']

        # === УСПЕШНАЯ ОПЛАТА ===
        if event_type == 'payment.succeeded':
            paid_amount = float(payment_obj.amount.value)

            result = await payment_service.process_successful_payment(
                yookassa_payment_id, paid_amount
            )
            if not result:
                return web.Response(status=200)

            # Уведомление реферера (Telegram-специфично)
            if result.referrer_id and result.referrer_id > 0:
                try:
                    await bot.send_message(
                        result.referrer_id,
                        f"🎉 Ваш реферал совершил первую оплату! Вам начислено <b>14 бонусных дней</b>."
                    )
                except Exception as e:
                    logger.error(f"Failed to notify referrer {result.referrer_id}: {e}")

            # Лог транзакции
            await _log_transaction(
                bot, result.payment.user_id, result.tariff.name,
                result.payment.final_amount, result.extension.is_new_marzban_user,
                payment=result.payment
            )

            # Уведомление пользователя (только TG)
            if result.payment.user_id > 0:
                await _notify_tg_user(result.payment.user_id, result.tariff, marzban, bot, request)

            return web.Response(status=200)

        # === ВОЗВРАТ ===
        elif event_type == 'refund.succeeded':
            refunded_payment = await payment_service.process_refund(yookassa_payment_id)
            if refunded_payment:
                await _log_refund(bot, refunded_payment)
                # Уведомляем пользователя
                if refunded_payment.user_id > 0:
                    try:
                        await bot.send_message(
                            refunded_payment.user_id,
                            f"💸 Произведён возврат средств: <b>{refunded_payment.final_amount:.2f} RUB</b>.\n"
                            "Дни подписки были скорректированы."
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify user about refund: {e}")

            return web.Response(status=200)

        # === ОТМЕНА ===
        elif event_type == 'payment.canceled':
            from database import payment_repo
            payment = await payment_repo.get_by_yookassa_id(yookassa_payment_id)
            await payment_repo.update_status(yookassa_payment_id, 'cancelled')
            logger.info(f"Payment {yookassa_payment_id} cancelled by YooKassa")
            if payment and payment.user_id > 0:
                try:
                    await bot.send_message(
                        payment.user_id,
                        "⏰ Ваш счёт на оплату был автоматически отменён, так как не был оплачен в течение 10 минут.\n\n"
                        "Вы можете создать новый платёж в любое время."
                    )
                except Exception:
                    pass
            return web.Response(status=200)

        else:
            logger.warning(f"Unknown webhook event: {event_type}")
            return web.Response(status=200)

    except Exception as e:
        logger.error(f"FATAL Webhook Error: {e}", exc_info=True)
        return web.Response(status=500)
