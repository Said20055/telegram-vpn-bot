
import uuid
from yookassa import Configuration, Payment
from yookassa.domain.notification import WebhookNotification


# Импортируем наш объект конфига из loader
from loader import config

# Настраиваем SDK YooKassa
Configuration.account_id = config.yookassa.shop_id
Configuration.secret_key = config.yookassa.secret_key


def create_payment(user_id: int, amount: int, description: str, bot_username: str, metadata: dict = None):
    """
    Создает платеж в YooKassa и возвращает ссылку на оплату.
    """
    # Создаем уникальный ключ идемпотентности для каждого платежа
    idempotence_key = str(uuid.uuid4())
    
    payment = Payment.create({
        "amount": {
            "value": str(amount),
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            # Ссылка, куда вернется пользователь после оплаты
            "return_url": f"https://t.me/{bot_username}" 
        },
        "capture": True,
        "description": description,
        "metadata": metadata or {'user_id': str(user_id)}
    }, idempotence_key)
    
    # Возвращаем URL для оплаты и ID платежа
    return payment.confirmation.confirmation_url, payment.id


def parse_webhook_notification(request_body: dict) -> WebhookNotification | None:
    """
    Парсит тело запроса от YooKassa, чтобы убедиться, что это валидное уведомление.
    """
    try:
        notification_object = WebhookNotification(request_body)
        return notification_object
    except Exception:
        # Если тело запроса невалидно, вернется None
        return None