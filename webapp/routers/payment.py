# webapp/routers/payment.py
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

# Импортируем нашу "чистую" функцию
# Если файл лежит в tgbot/services, убедись, что Python видит эту папку
# Или скопируй payment.py в webapp/core/
from tgbot.services.payment import create_payment 
from db import async_session_maker, User, Tariff
from webapp.dependencies import get_current_user
from config import load_config

router = APIRouter(prefix="/payment")
config = load_config()
logger = logging.getLogger(__name__)

# Модель данных, которые придут из JS
class PaymentRequest(BaseModel):
    tariff_name: str
    price: float

async def get_db():
    async with async_session_maker() as session:
        yield session

@router.post("/create")
async def create_payment_route(
    payload: PaymentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 1. Находим тариф в БД по имени и цене (для безопасности)
    # В идеале лучше передавать tariff_id, но пока оставим как есть в JS
    from sqlalchemy import select
    result = await db.execute(
        select(Tariff).where(Tariff.name == payload.tariff_name, Tariff.price == payload.price)
    )
    tariff = result.scalar_one_or_none()
    
    if not tariff:
        raise HTTPException(status_code=404, detail="Тариф не найден")

    # 2. Формируем URL возврата (на профиль сайта)
    # config.webhook.domain должен быть без http/https, или используй жестко https://твой-домен
    return_url = f"https://{config.webhook.domain}/profile/" 

    try:
        # 3. Создаем платеж
        payment_url, payment_id = create_payment(
            amount=tariff.price,
            description=f"Подписка {tariff.name} (Web)",
            return_url=return_url,
            user_id=user.user_id,
            user_email=user.email,
            shop_id=config.yookassa.shop_id,       # Берем из конфига сайта
            secret_key=config.yookassa.secret_key, # Берем из конфига сайта
            metadata={
                "tariff_id": tariff.id,
                "source": "web"  # Метка, что оплата с сайта
            }
        )
        
        return {"payment_url": payment_url}

    except Exception as e:
        logger.error(f"Error creating payment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка платежного шлюза")