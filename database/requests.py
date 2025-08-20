# database/requests.py (Полностью исправленная и отрефакторенная версия)

from db import Channel, db, User, Tariff, PromoCode, UsedPromoCode, async_session_maker

from sqlalchemy import select, update, delete, func

from datetime import datetime, timedelta

# --- Декоратор для безопасной работы с БД ---


# =============================================================================
# --- Функции для работы с пользователями (User) ---
# =============================================================================



async def get_or_create_user(user_id: int, full_name: str, username: str | None = None) -> tuple[User, bool]:
    async with async_session_maker() as session:
        # Пытаемся найти пользователя
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            return user, False  # уже существует

        # Если не найден — создаём
        user = User(user_id=user_id, full_name=full_name, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)  # чтобы получить id и актуальные данные из БД

        return user, True  # создан новый


async def get_user(user_id: int) -> User | None:
    """Асинхронно получает пользователя по его ID."""
    async with async_session_maker() as session:
        return await session.get(User, user_id)

async def get_user_by_username(username: str) -> User | None:
    """Асинхронно получает пользователя по его username (регистронезависимо)."""
    async with async_session_maker() as session:
        stmt = select(User).where(func.lower(User.username) == username.lower())
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
        
async def get_all_users_ids() -> list[int]:
    """Асинхронно получает список ID всех пользователей."""
    async with async_session_maker() as session:
        stmt = select(User.user_id)
        result = await session.execute(stmt)
        return result.scalars().all()

async def update_user_marzban_username(user_id: int, xui_username: str):
    """Асинхронно обновляет имя пользователя для панели 3x-ui."""
    async with async_session_maker() as session:
        stmt = update(User).where(User.user_id == user_id).values(xui_username=xui_username)
        await session.execute(stmt)
        await session.commit()

async def extend_user_subscription(user_id: int, days: int):
    """Асинхронно продлевает подписку пользователя."""
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if not user: return
        now = datetime.now()
        new_date = (user.subscription_end_date if user.subscription_end_date and user.subscription_end_date > now else now) + timedelta(days=days)
        user.subscription_end_date = new_date
        await session.commit()

async def set_user_referrer(user_id: int, referrer_id: int):
    """Асинхронно устанавливает реферера для пользователя."""
    async with async_session_maker() as session:
        stmt = update(User).where(User.user_id == user_id).values(referrer_id=referrer_id)
        await session.execute(stmt)
        await session.commit()

async def add_bonus_days(user_id: int, days: int):
    """Асинхронно добавляет бонусные дни пользователю."""
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if user:
            user.referral_bonus_days = (user.referral_bonus_days or 0) + days
            await session.commit()

async def set_first_payment_done(user_id: int):
    """Асинхронно отмечает, что пользователь совершил первую оплату."""
    async with async_session_maker() as session:
        stmt = update(User).where(User.user_id == user_id).values(is_first_payment_made=True)
        await session.execute(stmt)
        await session.commit()

async def delete_user(user_id: int) -> bool:
    """Асинхронно удаляет пользователя."""
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if user:
            await session.delete(user)
            await session.commit()
            return True
        return False

async def get_users_with_expiring_subscription(days_left: int) -> list[User]:
    """Асинхронно получает пользователей с подпиской, истекающей через X дней."""
    async with async_session_maker() as session:
        target_date_start = datetime.now().date() + timedelta(days=days_left)
        target_date_end = target_date_start + timedelta(days=1)
        stmt = select(User).where(
            User.subscription_end_date >= target_date_start,
            User.subscription_end_date < target_date_end
        )
        result = await session.execute(stmt)
        return result.scalars().all()

async def get_users_with_expiring_subscription_in_hours(hours: int) -> list[User]:
    """Асинхронно получает пользователей с подпиской, истекающей в ближайшие X часов."""
    async with async_session_maker() as session:
        now = datetime.now()
        expiration_limit = now + timedelta(hours=hours)
        stmt = select(User).where(
            User.subscription_end_date > now,
            User.subscription_end_date <= expiration_limit
        )
        result = await session.execute(stmt)
        return result.scalars().all()

async def set_user_trial_received(user_id: int):
    """
    Отмечает в базе данных, что пользователь получил пробный период.
    """
    async with async_session_maker() as session:
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(has_received_trial=True)
        )
        await session.execute(stmt)
        await session.commit()

# =============================================================================
# --- Функции для работы с тарифами (Tariff) ---
# =============================================================================

async def get_active_tariffs() -> list[Tariff]:
    """Асинхронно получает активные тарифы."""
    async with async_session_maker() as session:
        stmt = select(Tariff).where(Tariff.is_active == True).order_by(Tariff.price.asc())
        result = await session.execute(stmt)
        return result.scalars().all()

async def get_all_tariffs() -> list[Tariff]:
    """Асинхронно получает все тарифы."""
    async with async_session_maker() as session:
        result = await session.execute(select(Tariff))
        return result.scalars().all()

async def get_tariff_by_id(tariff_id: int) -> Tariff | None:
    """Асинхронно получает тариф по ID."""
    async with async_session_maker() as session:
        return await session.get(Tariff, tariff_id)

async def add_new_tariff(name: str, price: float, duration_days: int) -> Tariff:
    """Асинхронно добавляет новый тариф."""
    async with async_session_maker() as session:
        new_tariff = Tariff(name=name, price=price, duration_days=duration_days, is_active=True)
        session.add(new_tariff)
        await session.commit()
        return new_tariff

async def update_tariff_field(tariff_id: int, field: str, value):
    """Асинхронно обновляет поле тарифа."""
    async with async_session_maker() as session:
        stmt = update(Tariff).where(Tariff.id == tariff_id).values({field: value})
        await session.execute(stmt)
        await session.commit()

async def delete_tariff_by_id(tariff_id: int):
    """Асинхронно удаляет тариф."""
    async with async_session_maker() as session:
        stmt = delete(Tariff).where(Tariff.id == tariff_id)
        await session.execute(stmt)
        await session.commit()


# =============================================================================
# --- Функции для сбора статистики ---
# =============================================================================

# Подсчет всех пользователей
async def count_all_users() -> int:
    async with async_session_maker() as session:
        stmt = select(func.count()).select_from(User)
        result = await session.execute(stmt)
        return result.scalar_one()

# Подсчет новых пользователей за период
async def count_new_users_for_period(days: int) -> int:
    async with async_session_maker() as session:
        start_date = datetime.now() - timedelta(days=days)
        stmt = select(func.count()).select_from(User).where(User.reg_date >= start_date)
        result = await session.execute(stmt)
        return result.scalar_one()

# Подсчет активных подписок
async def count_active_subscriptions() -> int:
    async with async_session_maker() as session:
        stmt = select(func.count()).select_from(User).where(
            User.subscription_end_date.is_not(None),
            User.subscription_end_date > datetime.now()
        )
        result = await session.execute(stmt)
        return result.scalar_one()

# Подсчет рефералов пользователя
async def count_user_referrals(user_id: int) -> int:
    async with async_session_maker() as session:
        stmt = select(func.count()).select_from(User).where(User.referrer_id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one()

# Получение списка рефералов пользователя
async def get_user_referrals(user_id: int) -> list[User]:
    async with async_session_maker() as session:
        stmt = select(User).where(User.referrer_id == user_id)
        result = await session.execute(stmt)
        return result.scalars().all()

# Подсчет пользователей, совершивших первую оплату
async def count_users_with_first_payment() -> int:
    async with async_session_maker() as session:
        stmt = select(func.count()).select_from(User).where(User.is_first_payment_made == True)
        result = await session.execute(stmt)
        return result.scalar_one()

async def get_users_without_first_payment() -> list[int]:
    """
    Возвращает ID пользователей, которые ни разу не платили.
    """
    async with async_session_maker() as session:
        stmt = (
            select(User.user_id)
            .where(User.is_first_payment_made == False)  # условие как в синхронной версии
        )
        result = await session.execute(stmt)
        return [user_id for (user_id,) in result.all()]

# =============================================================================
# --- Функции для поддержки ---
# =============================================================================

async def set_user_support_topic(user_id: int, topic_id: int):
    """Асинхронно устанавливает ID топика поддержки для пользователя."""
    async with async_session_maker() as session:
        stmt = update(User).where(User.user_id == user_id).values(support_topic_id=topic_id)
        await session.execute(stmt)
        await session.commit()

async def clear_user_support_topic(user_id: int):
    """Асинхронно очищает ID топика поддержки для пользователя."""
    async with async_session_maker() as session:
        stmt = update(User).where(User.user_id == user_id).values(support_topic_id=None)
        await session.execute(stmt)
        await session.commit()
    
async def get_user_by_support_topic(topic_id: int) -> User | None:
    """Асинхронно получает пользователя по ID топика поддержки."""
    async with async_session_maker() as session:
        stmt = select(User).where(User.support_topic_id == topic_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

# =============================================================================
# --- Функции для системы промокодов ---
# =============================================================================

async def create_promo_code(code: str, bonus_days=0, discount_percent=0, max_uses=1, expire_date=None) -> PromoCode:
    """Асинхронно создает промокод."""
    async with async_session_maker() as session:
        new_promo = PromoCode(
            code=code.upper(), bonus_days=bonus_days, discount_percent=discount_percent,
            max_uses=max_uses, uses_left=max_uses, expire_date=expire_date
        )
        session.add(new_promo)
        await session.commit()
        return new_promo

async def get_all_promo_codes() -> list[PromoCode]:
    """Асинхронно получает все промокоды."""
    async with async_session_maker() as session:
        result = await session.execute(select(PromoCode))
        return result.scalars().all()

async def get_promo_code(code: str) -> PromoCode | None:
    """Асинхронно получает промокод по его коду (регистронезависимо)."""
    async with async_session_maker() as session:
        stmt = select(PromoCode).where(func.lower(PromoCode.code) == code.lower())
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

async def has_user_used_promo(user_id: int, promo_id: int) -> bool:
    """Асинхронно проверяет, использовал ли пользователь промокод."""
    async with async_session_maker() as session:
        stmt = select(UsedPromoCode).where(
            UsedPromoCode.user_id == user_id,
            UsedPromoCode.promo_code_id == promo_id
        )
        result = await session.execute(select(stmt.exists()))
        return result.scalar()

async def use_promo_code(user_id: int, promo: PromoCode):
    """Асинхронно отмечает использование промокода."""
    async with async_session_maker() as session:
        # Уменьшаем счетчик
        promo.uses_left -= 1
        # Создаем запись об использовании
        new_usage = UsedPromoCode(user_id=user_id, promo_code_id=promo.id)
        session.add(promo)
        session.add(new_usage)
        await session.commit()

async def delete_promo_code(promo_id: int) -> bool:
    """Асинхронно удаляет промокод."""
    async with async_session_maker() as session:
        promo = await session.get(PromoCode, promo_id)
        if promo:
            # SQLAlchemy сам обработает каскадное удаление, если оно настроено в БД,
            # но для безопасности можно сначала удалить связанные записи.
            stmt = delete(UsedPromoCode).where(UsedPromoCode.promo_code_id == promo_id)
            await session.execute(stmt)
            await session.delete(promo)
            await session.commit()
            return True
        return False
    
    
# =============================================================================
# --- Функции для системы каналов ---
# =============================================================================
    
# Добавление канала
async def add_channel(channel_id: int, title: str, invite_link: str) -> Channel:
    async with async_session_maker() as session:
        channel = Channel(channel_id=channel_id, title=title, invite_link=invite_link)
        session.add(channel)
        await session.commit()
        await session.refresh(channel)  # получаем актуальные данные
        return channel

# Получение всех каналов
async def get_all_channels() -> list[Channel]:
    async with async_session_maker() as session:
        stmt = select(Channel)
        result = await session.execute(stmt)
        return result.scalars().all()

# Удаление канала
async def delete_channel(channel_id: int) -> None:
    async with async_session_maker() as session:
        stmt = delete(Channel).where(Channel.channel_id == channel_id)
        await session.execute(stmt)
        await session.commit()
