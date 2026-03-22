from datetime import datetime, timedelta

from sqlalchemy import select, func

from db import User


class StatsRepository:
    def __init__(self, session_maker):
        self._session_maker = session_maker

    async def count_all_users(self) -> int:
        async with self._session_maker() as session:
            stmt = select(func.count()).select_from(User)
            result = await session.execute(stmt)
            return result.scalar_one()

    async def count_new_users_for_period(self, days: int) -> int:
        async with self._session_maker() as session:
            start_date = datetime.now() - timedelta(days=days)
            stmt = select(func.count()).select_from(User).where(User.reg_date >= start_date)
            result = await session.execute(stmt)
            return result.scalar_one()

    async def count_active_subscriptions(self) -> int:
        async with self._session_maker() as session:
            stmt = select(func.count()).select_from(User).where(
                User.subscription_end_date.is_not(None),
                User.subscription_end_date > datetime.now()
            )
            result = await session.execute(stmt)
            return result.scalar_one()

    async def count_user_referrals(self, user_id: int) -> int:
        async with self._session_maker() as session:
            stmt = select(func.count()).select_from(User).where(User.referrer_id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one()

    async def get_user_referrals(self, user_id: int) -> list[User]:
        async with self._session_maker() as session:
            stmt = select(User).where(User.referrer_id == user_id)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def count_users_with_first_payment(self) -> int:
        async with self._session_maker() as session:
            stmt = select(func.count()).select_from(User).where(User.is_first_payment_made == True)
            result = await session.execute(stmt)
            return result.scalar_one()
