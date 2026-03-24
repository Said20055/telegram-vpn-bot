from database.repositories.user import UserRepository
from tgbot.services.subscription_service import SubscriptionService
from loader import logger


class ReferralService:
    def __init__(self, user_repo: UserRepository, subscription_service: SubscriptionService):
        self._user_repo = user_repo
        self._subscription_service = subscription_service

    async def activate_new_user_referral(self, user_id: int, referrer_id: int, bonus_days: int = 7):
        """
        Регистрация нового реферала: установить реферера + выдать пробную подписку.
        """
        await self._user_repo.set_referrer(user_id, referrer_id)
        result = await self._subscription_service.extend(user_id, bonus_days)
        logger.info(f"Referral bonus: user {user_id} got {bonus_days} days via referrer {referrer_id}")
        return result

    async def process_first_payment_bonus(self, user_who_paid_id: int, bonus_days: int = 14) -> int | None:
        """
        Бонус рефереру при первой оплате.
        Возвращает referrer_id если бонус начислен, None иначе.
        """
        user = await self._user_repo.get(user_who_paid_id)
        if not (user and user.referrer_id and not user.is_first_payment_made):
            return None

        referrer = await self._user_repo.get(user.referrer_id)
        if not referrer:
            return None

        referrer_id = user.referrer_id

        try:
            if referrer.marzban_username:
                try:
                    await self._subscription_service._marzban.modify_user(
                        username=referrer.marzban_username, expire_days=bonus_days
                    )
                except Exception as e:
                    logger.error(f"Failed to extend marzban for referrer {referrer_id}: {e}")

            await self._user_repo.extend_subscription(referrer_id, days=bonus_days)
            await self._user_repo.add_bonus_days(referrer_id, days=bonus_days)

            logger.info(f"Referral bonus: Granted {bonus_days} days to referrer {referrer_id}")
            return referrer_id
        except Exception as e:
            logger.error(f"Error handling referral bonus for {referrer_id}: {e}")
            return None
