# tgbot/services/payment.py (или webapp/core/payment.py)
import uuid
from yookassa import Configuration, Payment
from yookassa.domain.notification import WebhookNotification

def create_payment(
    amount: float,
    description: str,
    return_url: str,
    user_id: int,
    user_email: str = None,
    metadata: dict = None,
    shop_id: str = None,     # Передаем явно
    secret_key: str = None   # Передаем явно
):
    """
    Универсальная функция создания платежа.
    """
    # Настраиваем SDK перед запросом
    if shop_id and secret_key:
        Configuration.account_id = shop_id
        Configuration.secret_key = secret_key

    idempotence_key = str(uuid.uuid4())
    
    # Если email не передан, генерируем заглушку (для бота)
    # Для сайта мы будем передавать реальный email
    receipt_email = user_email if user_email else f"user_{abs(user_id)}@telegram.user"

    receipt_data = {
        "customer": {"email": receipt_email},
        "items": [{
            "description": description,
            "quantity": "1.00",
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "vat_code": "1",
            "payment_mode": "full_prepayment",
            "payment_subject": "service"
        }]
    }

    # Базовые метаданные + то, что передали сверху
    final_metadata = {'user_id': str(user_id)}
    if metadata:
        final_metadata.update(metadata)

    payment_obj = Payment.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "return_url": return_url
        },
        "capture": True,
        "description": description,
        "metadata": final_metadata,
        "receipt": receipt_data
    }, idempotence_key)

    return payment_obj.confirmation.confirmation_url, payment_obj.id

def parse_webhook_notification(request_body: dict):
    try:
        return WebhookNotification(request_body)
    except Exception:
        return None