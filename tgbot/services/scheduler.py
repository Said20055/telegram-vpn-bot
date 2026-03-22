# tgbot/services/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from datetime import datetime, timedelta

from database import user_repo, tariff_repo, payment_repo
from tgbot.keyboards.inline import tariffs_keyboard
from utils import broadcaster
from .utils import decline_word
from loader import logger, config

# --- 1. Основная функция, которую будет вызывать планировщик ---

async def send_reminder(bot: Bot, user, text: str):
    """Универсальная функция для отправки напоминания с клавиатурой тарифов."""
    try:
        active_tariffs = await tariff_repo.get_active()
        tariffs_list = list(active_tariffs) if active_tariffs else []

        await bot.send_message(
            chat_id=user.user_id,
            text=text,
            reply_markup=tariffs_keyboard(tariffs_list) if tariffs_list else None
        )
        logger.info(f"Sent reminder to user {user.user_id}")
    except Exception as e:
        logger.warning(f"Failed to send reminder to user {user.user_id}. Error: {e}")


# --- 2. Основная функция, которую вызывает планировщик ---

async def check_subscriptions(bot: Bot):
    """Проверяет подписки пользователей и отправляет гибкие напоминания."""
    logger.info("Scheduler job: Running subscription check...")

    count = 0
    # --- Проверка по дням (7 и 3 дня) ---
    for days_left in [7, 3]:
        users_to_remind = await user_repo.get_with_expiring_subscription(days_left)
        if not users_to_remind:
            continue

        logger.info(f"Found {len(users_to_remind)} users with {days_left} days left.")
        day_word = decline_word(days_left, ['день', 'дня', 'дней'])
        text = (
            f"👋 Привет, {{user_full_name}}!\n\n"
            f"Напоминаем, что ваша подписка истекает через <b>{days_left} {day_word}</b>.\n\n"
            "Чтобы не потерять доступ, пожалуйста, продлите ее."
        )
        for user in users_to_remind:
            ok = await send_reminder(bot, user, text.format(user_full_name=user.full_name))
            if ok:
                count += 1

    # --- Проверка по часам (менее 24 часов) ---
    users_less_than_day = await user_repo.get_with_expiring_subscription_in_hours(24)
    if not users_less_than_day:
        return # Завершаем, если таких пользователей нет

    logger.info(f"Found {len(users_less_than_day)} users with less than 24 hours left.")
    for user in users_less_than_day:
        hours_left = int((user.subscription_end_date - datetime.now()).total_seconds() / 3600)
        if hours_left <= 0: continue

        hour_word = decline_word(hours_left, ['час', 'часа', 'часов'])
        text = (
            f"👋 Привет, {user.full_name}!\n\n"
            f"❗️ Ваша подписка истекает уже сегодня, осталось менее <b>{hours_left} {hour_word}</b>.\n\n"
            "Чтобы не потерять доступ, продлите ее прямо сейчас."
        )
        ok = await send_reminder(bot, user, text)
        if ok:
            count += 1

    if count > 0:
        await broadcaster.broadcast(bot, config.tg_bot.admin_ids, "✅ Рассылка завершена. Сообщение доставлено {count} пользователям.")


# --- 3. Автоотмена зависших платежей ---

async def cancel_stale_payments(bot: Bot):
    """Отменяет платежи в статусе pending старше 30 минут."""
    try:
        cancelled = await payment_repo.cancel_stale(minutes=30)
        if cancelled:
            logger.info(f"Auto-cancelled {len(cancelled)} stale payments")
            for p in cancelled:
                if p.user_id > 0:
                    try:
                        await bot.send_message(
                            p.user_id,
                            "⏰ Ваш счёт на оплату был автоматически отменён, так как не был оплачен в течение 30 минут.\n\n"
                            "Вы можете создать новый платёж в любое время."
                        )
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"Error in cancel_stale_payments: {e}", exc_info=True)


# --- 4. Функция для добавления всех задач в планировщик ---

def schedule_jobs(scheduler: AsyncIOScheduler, bot: Bot):
    """
    Добавляет все фоновые задачи в планировщик.
    Вызывается один раз при старте бота.
    """
    # Запускать проверку подписок каждый день в 10:00 по МСК
    scheduler.add_job(
        check_subscriptions,
        trigger='cron',
        hour=12,
        minute=49,
        kwargs={'bot': bot}
    )

    # Автоотмена зависших платежей каждые 10 минут
    scheduler.add_job(
        cancel_stale_payments,
        trigger='interval',
        minutes=10,
        kwargs={'bot': bot}
    )

    logger.info("Scheduler jobs added.")
