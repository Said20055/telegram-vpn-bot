# webapp/core/mail.py
import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr

# Читаем настройки прямо из ENV для простоты
conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
    MAIL_FROM=os.getenv("MAIL_FROM", "noreply@vacvpn.com"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

async def send_reset_code(email: EmailStr, code: str):
    """Отправляет код восстановления на почту"""
    
    html = f"""
    <div style="background-color: #121212; color: #ffffff; padding: 20px; font-family: Arial;">
        <h2 style="color: #ff6600;">VacVPN</h2>
        <p>Вы запросили сброс пароля.</p>
        <p>Ваш код подтверждения:</p>
        <h1 style="background: #2c2c2c; padding: 10px; display: inline-block; border-radius: 8px; border: 1px solid #ff6600;">{code}</h1>
        <p style="color: #888; font-size: 12px; margin-top: 20px;">Если это были не вы, просто проигнорируйте письмо.</p>
    </div>
    """

    message = MessageSchema(
        subject="Сброс пароля | VacVPN",
        recipients=[email],
        body=html,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    await fm.send_message(message)