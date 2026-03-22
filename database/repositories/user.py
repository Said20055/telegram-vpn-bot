from datetime import datetime, timedelta

from sqlalchemy import select, update, delete, func

from db import User, UsedPromoCode


class UserRepository:
    def __init__(self, session_maker):
        self._session_maker = session_maker

    async def get_or_create(self, user_id: int, full_name: str, username: str | None = None) -> tuple[User, bool]:
        async with self._session_maker() as session:
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                return user, False

            user = User(user_id=user_id, full_name=full_name, username=username)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user, True

    async def get(self, user_id: int) -> User | None:
        async with self._session_maker() as session:
            return await session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        async with self._session_maker() as session:
            stmt = select(User).where(func.lower(User.username) == username.lower())
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_all_ids(self) -> list[int]:
        async with self._session_maker() as session:
            stmt = select(User.user_id)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def update_marzban_username(self, user_id: int, marzban_username: str):
        async with self._session_maker() as session:
            stmt = update(User).where(User.user_id == user_id).values(marzban_username=marzban_username)
            await session.execute(stmt)
            await session.commit()

    async def extend_subscription(self, user_id: int, days: int):
        async with self._session_maker() as session:
            user = await session.get(User, user_id)
            if not user:
                return
            now = datetime.now()
            new_date = (user.subscription_end_date if user.subscription_end_date and user.subscription_end_date > now else now) + timedelta(days=days)
            user.subscription_end_date = new_date
            await session.commit()

    async def set_referrer(self, user_id: int, referrer_id: int):
        async with self._session_maker() as session:
            stmt = update(User).where(User.user_id == user_id).values(referrer_id=referrer_id)
            await session.execute(stmt)
            await session.commit()

    async def add_bonus_days(self, user_id: int, days: int):
        async with self._session_maker() as session:
            user = await session.get(User, user_id)
            if user:
                user.referral_bonus_days = (user.referral_bonus_days or 0) + days
                await session.commit()

    async def set_first_payment_done(self, user_id: int):
        async with self._session_maker() as session:
            stmt = update(User).where(User.user_id == user_id).values(is_first_payment_made=True)
            await session.execute(stmt)
            await session.commit()

    async def delete(self, user_id: int) -> bool:
        async with self._session_maker() as session:
            user = await session.get(User, user_id)
            if not user:
                return False
            await session.execute(
                delete(UsedPromoCode).where(UsedPromoCode.user_id == user_id)
            )
            await session.delete(user)
            await session.commit()
            return True

    async def get_with_expiring_subscription(self, days_left: int) -> list[User]:
        async with self._session_maker() as session:
            target_date_start = datetime.now().date() + timedelta(days=days_left)
            target_date_end = target_date_start + timedelta(days=1)
            stmt = select(User).where(
                User.subscription_end_date >= target_date_start,
                User.subscription_end_date < target_date_end
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_with_expiring_subscription_in_hours(self, hours: int) -> list[User]:
        async with self._session_maker() as session:
            now = datetime.now()
            expiration_limit = now + timedelta(hours=hours)
            stmt = select(User).where(
                User.subscription_end_date > now,
                User.subscription_end_date <= expiration_limit
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def set_trial_received(self, user_id: int):
        async with self._session_maker() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(has_received_trial=True)
            )
            await session.execute(stmt)
            await session.commit()

    async def set_support_topic(self, user_id: int, topic_id: int):
        async with self._session_maker() as session:
            stmt = update(User).where(User.user_id == user_id).values(support_topic_id=topic_id)
            await session.execute(stmt)
            await session.commit()

    async def clear_support_topic(self, user_id: int):
        async with self._session_maker() as session:
            stmt = update(User).where(User.user_id == user_id).values(support_topic_id=None)
            await session.execute(stmt)
            await session.commit()

    async def get_by_support_topic(self, topic_id: int) -> User | None:
        async with self._session_maker() as session:
            stmt = select(User).where(User.support_topic_id == topic_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_without_first_payment(self) -> list[int]:
        async with self._session_maker() as session:
            stmt = select(User.user_id).where(User.is_first_payment_made == False)
            result = await session.execute(stmt)
            return [user_id for (user_id,) in result.all()]

    async def get_by_email(self, email: str) -> User | None:
        async with self._session_maker() as session:
            stmt = select(User).where(User.email == email)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def set_email_and_password(self, user_id: int, email: str, password_hash: str):
        async with self._session_maker() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(email=email, password_hash=password_hash, is_email_verified=True)
            )
            await session.execute(stmt)
            await session.commit()

    async def set_verification_code(self, user_id: int, code: str, expire: datetime):
        async with self._session_maker() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(verification_code=code, verification_code_expire=expire)
            )
            await session.execute(stmt)
            await session.commit()

    async def clear_verification_code(self, user_id: int):
        async with self._session_maker() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(verification_code=None, verification_code_expire=None)
            )
            await session.execute(stmt)
            await session.commit()

    async def mark_email_verified(self, user_id: int):
        async with self._session_maker() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(is_email_verified=True, verification_code=None, verification_code_expire=None)
            )
            await session.execute(stmt)
            await session.commit()
