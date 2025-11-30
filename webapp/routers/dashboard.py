# webapp/routers/dashboard.py
import logging
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlparse  # <--- Добавили urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db import async_session_maker, User
from marzban.init_client import MarzClientCache
from webapp.dependencies import get_current_user
from loader import config, logger
from database.requests import get_active_tariffs

router = APIRouter(prefix="/profile")
templates = Jinja2Templates(directory="webapp/templates")

# Фильтр даты
def timestamp_to_date(value):
    if value:
        try:
            return datetime.fromtimestamp(float(value)).strftime('%Y-%m-%d %H:%M')
        except Exception:
            return "Неизвестно"
    return "Неограниченно"

templates.env.filters['timestamp_to_date'] = timestamp_to_date

# --- Зависимости ---

def get_marz_client(request: Request) -> MarzClientCache:
    return request.app.state.marz_client

async def get_db():
    async with async_session_maker() as session:
        yield session

# --- Роуты ---

@router.get("/", response_class=HTMLResponse)
async def dashboard_page(
    request: Request, 
    user: User = Depends(get_current_user),
    marz_client: MarzClientCache = Depends(get_marz_client)
):
    if not user:
        return RedirectResponse(url="/login")

    # Получаем тарифы для модального окна
    tariffs_list = await get_active_tariffs()

    marzban_user_data = None
    subscription_link = None
    import_link = None
    error_message = None

    if user.marzban_username:
        try:
            marzban_user_data = await marz_client.get_user(user.marzban_username)
            if marzban_user_data:
                # 1. Получаем сырую ссылку от Marzban
                raw_link = marzban_user_data.get("subscription_url", "")
                if not raw_link and marzban_user_data.get('links'):
                    raw_link = marzban_user_data['links'][0]

                # 2. ФОРМИРУЕМ ПРАВИЛЬНУЮ ССЫЛКУ (Домен + 8443)
                if raw_link:
                    # Вытаскиваем только путь (например, /sub/long_uuid)
                    path = urlparse(raw_link).path
                    
                    # Берем домен из конфига (ENV: DOMAIN)
                    # Если домена нет в конфиге, fallback на localhost, но он должен быть в .env
                    domain = config.webhook.domain or "localhost"
                    
                    # Собираем новую ссылку: https://DOMAIN:8443/sub/...
                    subscription_link = f"https://{domain}:8443{path}"

                # 3. Генерируем Deeplink для кнопки (на базе уже новой ссылки)
                if subscription_link:
                    encoded_url = quote_plus(subscription_link)
                    import_link = f"v2raytun://import/{encoded_url}"
                     

            else:
                error_message = "Аккаунт не найден на сервере VPN."
        except Exception as e:
            logger.error(f"Ошибка получения данных из Marzban: {e}")
            error_message = "Не удалось загрузить статус VPN."

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "vpn_data": marzban_user_data,
        "sub_link": subscription_link,
        "import_link": import_link,
        "error": error_message,
        "tariffs": tariffs_list,
        "title": "Личный кабинет"
    })


@router.post("/activate_trial")
async def activate_trial(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    marz_client: MarzClientCache = Depends(get_marz_client)
):
    if not user:
        return RedirectResponse(url="/login")
    
    if user.has_received_trial:
         return templates.TemplateResponse("dashboard.html", {
            "request": request, 
            "user": user, 
            "error": "Вы уже использовали пробный период!",
            "title": "Личный кабинет",
            "tariffs": await get_active_tariffs() # Не забываем тарифы при ошибке
        })

    marz_username = f"web_{abs(user.user_id)}"
    trial_days = 3 # Твой срок триала
    
    try:
        logger.info(f"Создание триала для {user.email} -> {marz_username}")
        await marz_client.add_user(username=marz_username, expire_days=trial_days)

        user = await db.merge(user)
        user.marzban_username = marz_username
        user.has_received_trial = True
        user.subscription_end_date = datetime.now() + timedelta(days=trial_days)
        
        await db.commit()
        logger.info(f"Триал успешно выдан: {user.email}")

    except Exception as e:
        logger.error(f"Ошибка при выдаче триала: {e}")
        await db.rollback()
        return templates.TemplateResponse("dashboard.html", {
            "request": request, 
            "user": user, 
            "error": f"Ошибка создания VPN: {str(e)}",
            "title": "Личный кабинет",
            "tariffs": await get_active_tariffs()
        })

    return RedirectResponse(url="/profile/", status_code=303)