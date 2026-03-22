# webapp/routers/payment.py
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tgbot.services.payment import create_payment
from tgbot.services import payment_service, promo_service, subscription_service
from db import User, Tariff
from database import tariff_repo
from webapp.dependencies import get_current_user
from config import load_config

router = APIRouter(prefix="/payment")
config = load_config()
logger = logging.getLogger(__name__)


class PaymentRequest(BaseModel):
    tariff_name: str
    price: float
    promo_code: str | None = None
    discount_percent: int = 0


@router.post("/create")
async def create_payment_route(
    payload: PaymentRequest,
    user: User = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Проверка на дубликат pending-платежа
    if await payment_service.has_pending_payment(user.user_id):
        raise HTTPException(
            status_code=409,
            detail="У вас уже есть неоплаченный счёт. Дождитесь его отмены (30 мин) или завершите оплату."
        )

    # Находим тариф в БД по имени и цене
    tariff = await tariff_repo.get_by_name_and_price(payload.tariff_name, payload.price)
    if not tariff:
        raise HTTPException(status_code=404, detail="Тариф не найден")

    # Рассчитываем финальную цену
    original_price = tariff.price
    final_price = original_price
    if payload.discount_percent > 0:
        final_price = round(original_price * (1 - payload.discount_percent / 100), 2)

    return_url = f"https://{config.webhook.domain}:8443/profile/"

    try:
        payment_url, yookassa_payment_id = create_payment(
            amount=final_price,
            description=f"Подписка {tariff.name} (Web)" + (f" (скидка {payload.discount_percent}%)" if payload.discount_percent else ""),
            return_url=return_url,
            user_id=user.user_id,
            user_email=user.email,
            shop_id=config.yookassa.shop_id,
            secret_key=config.yookassa.secret_key,
            metadata={
                "tariff_id": tariff.id,
                "source": "web"
            }
        )

        # Сохраняем платёж в БД
        await payment_service.create_payment_record(
            yookassa_payment_id=yookassa_payment_id,
            user_id=user.user_id,
            tariff_id=tariff.id,
            original_amount=original_price,
            final_amount=final_price,
            source='web',
            promo_code=payload.promo_code,
            discount_percent=payload.discount_percent,
        )

        logger.info(
            f"Web payment created: user={user.user_id}, tariff={tariff.name}, "
            f"amount={final_price}, discount={payload.discount_percent}%, "
            f"promo={payload.promo_code or 'none'}"
        )

        return {"payment_url": payment_url}

    except Exception as e:
        logger.error(f"Error creating payment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка платежного шлюза")


class PromoValidateRequest(BaseModel):
    code: str


@router.post("/validate-promo")
async def validate_promo_route(
    payload: PromoValidateRequest,
    user: User = Depends(get_current_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = await promo_service.validate(payload.code.upper(), user.user_id)
    if not result.is_valid:
        return {"valid": False, "error": result.error_message}

    promo = result.promo
    response = {"valid": True, "code": promo.code}

    if promo.discount_percent > 0:
        response["type"] = "discount"
        response["discount_percent"] = promo.discount_percent
    elif promo.bonus_days > 0:
        response["type"] = "bonus_days"
        response["bonus_days"] = promo.bonus_days

    return response


@router.post("/apply-bonus-promo")
async def apply_bonus_promo_route(
    payload: PromoValidateRequest,
    user: User = Depends(get_current_user),
):
    """Apply a bonus-days promo code (no payment needed)."""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = await promo_service.validate(payload.code.upper(), user.user_id)
    if not result.is_valid:
        raise HTTPException(status_code=400, detail=result.error_message)

    promo = result.promo
    if promo.bonus_days <= 0:
        raise HTTPException(status_code=400, detail="Этот промокод даёт скидку, а не бонусные дни")

    await promo_service.apply(user.user_id, promo)
    await subscription_service.extend(user.user_id, promo.bonus_days)

    return {"success": True, "bonus_days": promo.bonus_days}
