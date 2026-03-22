from datetime import datetime, timedelta

from sqlalchemy import select, update, func

from db import Payment


class PaymentRepository:
    def __init__(self, session_maker):
        self._session_maker = session_maker

    async def create(self, yookassa_payment_id: str, user_id: int, tariff_id: int,
                     original_amount: float, final_amount: float, source: str = 'bot',
                     promo_code: str = None, discount_percent: int = 0) -> Payment:
        async with self._session_maker() as session:
            payment = Payment(
                yookassa_payment_id=yookassa_payment_id,
                user_id=user_id,
                tariff_id=tariff_id,
                original_amount=original_amount,
                final_amount=final_amount,
                source=source,
                promo_code=promo_code,
                discount_percent=discount_percent,
            )
            session.add(payment)
            await session.commit()
            await session.refresh(payment)
            return payment

    async def get_by_yookassa_id(self, yookassa_payment_id: str) -> Payment | None:
        async with self._session_maker() as session:
            stmt = select(Payment).where(Payment.yookassa_payment_id == yookassa_payment_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_status(self, yookassa_payment_id: str, status: str) -> bool:
        async with self._session_maker() as session:
            completed_at = datetime.now() if status in ('succeeded', 'failed', 'refunded') else None
            stmt = (
                update(Payment)
                .where(Payment.yookassa_payment_id == yookassa_payment_id)
                .values(status=status, completed_at=completed_at)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def get_user_payments(self, user_id: int, limit: int = 20) -> list[Payment]:
        async with self._session_maker() as session:
            stmt = (
                select(Payment)
                .where(Payment.user_id == user_id)
                .order_by(Payment.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_user_pending(self, user_id: int) -> Payment | None:
        async with self._session_maker() as session:
            stmt = select(Payment).where(
                Payment.user_id == user_id,
                Payment.status == 'pending'
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_pending_older_than(self, minutes: int) -> list[Payment]:
        async with self._session_maker() as session:
            cutoff = datetime.now() - timedelta(minutes=minutes)
            stmt = select(Payment).where(
                Payment.status == 'pending',
                Payment.created_at < cutoff
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def cancel_stale(self, minutes: int = 30) -> list[Payment]:
        """Cancel pending payments older than N minutes. Returns cancelled payments."""
        stale = await self.get_pending_older_than(minutes)
        for p in stale:
            await self.update_status(p.yookassa_payment_id, 'cancelled')
        return stale

    async def get_revenue_stats(self, days: int) -> dict:
        async with self._session_maker() as session:
            since = datetime.now() - timedelta(days=days)
            stmt = select(
                func.count(Payment.id),
                func.coalesce(func.sum(Payment.final_amount), 0)
            ).where(
                Payment.status == 'succeeded',
                Payment.completed_at >= since
            )
            result = await session.execute(stmt)
            row = result.one()
            return {"count": row[0], "revenue": float(row[1])}

    async def get_total_revenue(self) -> dict:
        async with self._session_maker() as session:
            stmt = select(
                func.count(Payment.id),
                func.coalesce(func.sum(Payment.final_amount), 0)
            ).where(Payment.status == 'succeeded')
            result = await session.execute(stmt)
            row = result.one()
            return {"count": row[0], "revenue": float(row[1])}
