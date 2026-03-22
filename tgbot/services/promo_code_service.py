from dataclasses import dataclass
from datetime import datetime

from db import PromoCode
from database.repositories.promo_code import PromoCodeRepository
from database.repositories.user import UserRepository


@dataclass
class PromoValidationResult:
    is_valid: bool
    error_message: str | None = None
    promo: PromoCode | None = None


class PromoCodeService:
    def __init__(self, promo_repo: PromoCodeRepository, user_repo: UserRepository):
        self._promo_repo = promo_repo
        self._user_repo = user_repo

    async def validate(self, code: str, user_id: int, require_discount: bool = False) -> PromoValidationResult:
        """
        Единая валидация промокода.
        require_discount: если True, отклоняет промокоды без скидки (только бонусные дни).
        """
        promo = await self._promo_repo.get_by_code(code)
        if not promo:
            return PromoValidationResult(False, "Промокод не найден.")

        if await self._promo_repo.has_user_used(user_id, promo.id):
            return PromoValidationResult(False, "Вы уже использовали этот промокод.")

        if require_discount and promo.discount_percent == 0:
            return PromoValidationResult(
                False,
                "Этот промокод дает бонусные дни, а не скидку. Введите его вручную в разделе «Промокод»."
            )

        if promo.uses_left <= 0:
            return PromoValidationResult(False, "К сожалению, этот промокод уже закончился.")

        if promo.expire_date and datetime.now() > promo.expire_date:
            return PromoValidationResult(False, "Срок действия этого промокода истек.")

        return PromoValidationResult(True, promo=promo)

    async def apply(self, user_id: int, promo: PromoCode):
        """Пометить промокод как использованный."""
        await self._promo_repo.use(user_id, promo)

    async def apply_bonus_days(self, user_id: int, promo: PromoCode, subscription_service):
        """Применить промокод с бонусными днями: use + extend."""
        await self.apply(user_id, promo)
        return await subscription_service.extend(user_id, promo.bonus_days)

    # --- Admin methods ---

    async def create(self, code: str, bonus_days: int = 0, discount_percent: int = 0,
                     max_uses: int = 1, expire_date=None):
        return await self._promo_repo.create(code, bonus_days, discount_percent, max_uses, expire_date)

    async def delete(self, promo_id: int):
        return await self._promo_repo.delete_by_id(promo_id)

    async def get_all(self):
        return await self._promo_repo.get_all()

    async def get_by_code(self, code: str):
        return await self._promo_repo.get_by_code(code)
