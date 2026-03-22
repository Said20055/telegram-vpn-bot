from dataclasses import dataclass
from datetime import datetime

from db import Tariff, Payment
from database.repositories.user import UserRepository
from database.repositories.tariff import TariffRepository
from database.repositories.payment import PaymentRepository
from tgbot.services.subscription_service import SubscriptionService, ExtensionResult
from tgbot.services.referral_service import ReferralService
from loader import logger


@dataclass
class PaymentResult:
    tariff: Tariff
    extension: ExtensionResult
    referrer_id: int | None
    is_first_payment: bool
    payment: Payment | None = None


class PaymentService:
    def __init__(self, subscription_service: SubscriptionService,
                 referral_service: ReferralService,
                 user_repo: UserRepository,
                 tariff_repo: TariffRepository,
                 payment_repo: PaymentRepository):
        self._subscription_service = subscription_service
        self._referral_service = referral_service
        self._user_repo = user_repo
        self._tariff_repo = tariff_repo
        self._payment_repo = payment_repo

    async def create_payment_record(self, yookassa_payment_id: str, user_id: int,
                                    tariff_id: int, original_amount: float,
                                    final_amount: float, source: str = 'bot',
                                    promo_code: str = None, discount_percent: int = 0) -> Payment:
        """Create a payment record in DB when payment is initiated."""
        return await self._payment_repo.create(
            yookassa_payment_id=yookassa_payment_id,
            user_id=user_id,
            tariff_id=tariff_id,
            original_amount=original_amount,
            final_amount=final_amount,
            source=source,
            promo_code=promo_code,
            discount_percent=discount_percent,
        )

    async def has_pending_payment(self, user_id: int) -> bool:
        """Check if user already has a pending payment."""
        pending = await self._payment_repo.get_user_pending(user_id)
        return pending is not None

    async def get_pending_payment(self, user_id: int) -> Payment | None:
        """Return the pending payment for a user, if any."""
        return await self._payment_repo.get_user_pending(user_id)

    async def process_successful_payment(self, yookassa_payment_id: str,
                                         paid_amount: float) -> PaymentResult | None:
        """
        Process a successful payment webhook:
        1. Verify payment exists in DB
        2. Check idempotency (status must be pending)
        3. Verify amount matches
        4. Extend subscription (DB + Marzban)
        5. Award referral bonus if first payment
        6. Mark first payment done
        7. Update payment status to succeeded
        """
        # 1. Verify payment exists in our DB
        payment = await self._payment_repo.get_by_yookassa_id(yookassa_payment_id)
        if not payment:
            logger.error(f"Payment {yookassa_payment_id} not found in local DB — possible forged webhook")
            return None

        # 2. Idempotency: skip if already processed
        if payment.status != 'pending':
            logger.warning(f"Payment {yookassa_payment_id} already processed (status={payment.status}), skipping")
            return None

        # 3. Verify amount
        if abs(paid_amount - payment.final_amount) > 0.01:
            logger.error(
                f"Payment {yookassa_payment_id} amount mismatch: "
                f"expected {payment.final_amount}, got {paid_amount}"
            )
            await self._payment_repo.update_status(yookassa_payment_id, 'failed')
            return None

        tariff = await self._tariff_repo.get_by_id(payment.tariff_id)
        if not tariff:
            logger.error(f"Tariff {payment.tariff_id} not found during payment processing")
            return None

        user = await self._user_repo.get(payment.user_id)
        if not user:
            logger.error(f"User {payment.user_id} not found during payment processing")
            return None

        is_first_payment = not user.is_first_payment_made

        # 4. Extend subscription
        extension = await self._subscription_service.extend(payment.user_id, tariff.duration_days)

        # 5. Referral bonus
        referrer_id = await self._referral_service.process_first_payment_bonus(payment.user_id)

        # 6. Mark first payment
        if is_first_payment:
            await self._user_repo.set_first_payment_done(payment.user_id)

        # 7. Update payment status
        await self._payment_repo.update_status(yookassa_payment_id, 'succeeded')

        logger.info(
            f"Payment processed: user={payment.user_id}, tariff={tariff.name}, "
            f"amount={payment.final_amount}, discount={payment.discount_percent}%, "
            f"promo={payment.promo_code or 'none'}, first={is_first_payment}"
        )
        return PaymentResult(
            tariff=tariff,
            extension=extension,
            referrer_id=referrer_id,
            is_first_payment=is_first_payment,
            payment=payment,
        )

    async def process_refund(self, yookassa_payment_id: str) -> Payment | None:
        """
        Process a refund: mark payment as refunded, deduct days or disable subscription.
        """
        payment = await self._payment_repo.get_by_yookassa_id(yookassa_payment_id)
        if not payment:
            logger.error(f"Refund: Payment {yookassa_payment_id} not found in DB")
            return None

        if payment.status != 'succeeded':
            logger.warning(f"Refund: Payment {yookassa_payment_id} is not succeeded (status={payment.status})")
            return None

        tariff = await self._tariff_repo.get_by_id(payment.tariff_id)
        days_to_deduct = tariff.duration_days if tariff else 0

        if days_to_deduct > 0:
            user = await self._user_repo.get(payment.user_id)
            if user and user.subscription_end_date:
                from datetime import timedelta
                new_end = user.subscription_end_date - timedelta(days=days_to_deduct)
                now = datetime.now()
                if new_end <= now:
                    # Subscription expired after deduction — disable in Marzban
                    await self._user_repo.extend_subscription(payment.user_id, -days_to_deduct)
                    if user.marzban_username:
                        try:
                            await self._subscription_service._marzban.modify_user(
                                username=user.marzban_username, expire_days=-days_to_deduct
                            )
                        except Exception as e:
                            logger.error(f"Refund: Failed to update Marzban for {user.marzban_username}: {e}")
                else:
                    await self._user_repo.extend_subscription(payment.user_id, -days_to_deduct)
                    if user.marzban_username:
                        try:
                            await self._subscription_service._marzban.modify_user(
                                username=user.marzban_username, expire_days=-days_to_deduct
                            )
                        except Exception as e:
                            logger.error(f"Refund: Failed to update Marzban for {user.marzban_username}: {e}")

        await self._payment_repo.update_status(yookassa_payment_id, 'refunded')
        logger.info(f"Refund processed: payment={yookassa_payment_id}, user={payment.user_id}, days_deducted={days_to_deduct}")
        return payment

    async def get_user_payments(self, user_id: int, limit: int = 20) -> list[Payment]:
        return await self._payment_repo.get_user_payments(user_id, limit)
