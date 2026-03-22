from sqlalchemy import select, delete, func

from db import PromoCode, UsedPromoCode


class PromoCodeRepository:
    def __init__(self, session_maker):
        self._session_maker = session_maker

    async def create(self, code: str, bonus_days=0, discount_percent=0, max_uses=1, expire_date=None) -> PromoCode:
        async with self._session_maker() as session:
            new_promo = PromoCode(
                code=code.upper(), bonus_days=bonus_days, discount_percent=discount_percent,
                max_uses=max_uses, uses_left=max_uses, expire_date=expire_date
            )
            session.add(new_promo)
            await session.commit()
            return new_promo

    async def get_all(self) -> list[PromoCode]:
        async with self._session_maker() as session:
            result = await session.execute(select(PromoCode))
            return result.scalars().all()

    async def get_by_code(self, code: str) -> PromoCode | None:
        async with self._session_maker() as session:
            stmt = select(PromoCode).where(func.lower(PromoCode.code) == code.lower())
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def has_user_used(self, user_id: int, promo_id: int) -> bool:
        async with self._session_maker() as session:
            stmt = select(UsedPromoCode).where(
                UsedPromoCode.user_id == user_id,
                UsedPromoCode.promo_code_id == promo_id
            )
            result = await session.execute(select(stmt.exists()))
            return result.scalar()

    async def use(self, user_id: int, promo: PromoCode):
        async with self._session_maker() as session:
            promo.uses_left -= 1
            new_usage = UsedPromoCode(user_id=user_id, promo_code_id=promo.id)
            session.add(promo)
            session.add(new_usage)
            await session.commit()

    async def delete_by_id(self, promo_id: int) -> bool:
        async with self._session_maker() as session:
            promo = await session.get(PromoCode, promo_id)
            if promo:
                stmt = delete(UsedPromoCode).where(UsedPromoCode.promo_code_id == promo_id)
                await session.execute(stmt)
                await session.delete(promo)
                await session.commit()
                return True
            return False
