"""
webapp/routers/subscription.py

Агрегирующий прокси для Marzban subscription URL.
Перехватывает запросы на /sub/{marzban_username}, добавляет внешние VPN-конфиги
если у пользователя активная подписка, и возвращает объединённый base64-список.
"""

import base64

import httpx
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from database import external_config_repo
from loader import logger

router = APIRouter()

# Marzban subscription endpoint внутри Docker-сети (без SSL verify)
_MARZBAN_BASE = "https://marzban:8002"


@router.get("/sub/{marzban_username}", response_class=PlainTextResponse)
async def subscription_proxy(marzban_username: str):
    """
    1. Запрашивает подписку из Marzban напрямую по внутреннему адресу
    2. Добавляет все активные внешние конфиги из БД
    3. Возвращает объединённый base64-список
    """
    marz_url = f"{_MARZBAN_BASE}/sub/{marzban_username}"

    # Получаем оригинальную подписку из Marzban
    marz_content = ""
    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            resp = await client.get(marz_url)
            resp.raise_for_status()
            marz_content = resp.text.strip()
    except httpx.HTTPError as e:
        logger.warning(f"[sub_proxy] Marzban request failed for {marzban_username}: {e}")
        return PlainTextResponse("", media_type="text/plain; charset=utf-8")

    # Получаем активные внешние конфиги
    ext_configs = await external_config_repo.get_active()
    if not ext_configs:
        return PlainTextResponse(marz_content, media_type="text/plain; charset=utf-8")

    # Декодируем Marzban base64 → список ссылок + добавляем внешние
    marz_links = _decode_links(marz_content)
    ext_links = [c.raw_link for c in ext_configs]

    combined = marz_links + ext_links
    encoded = base64.b64encode("\n".join(combined).encode("utf-8")).decode("utf-8")

    return PlainTextResponse(encoded, media_type="text/plain; charset=utf-8")


def _decode_links(content: str) -> list[str]:
    """Декодирует base64-подписку в список ссылок."""
    try:
        decoded = base64.b64decode(content + "==").decode("utf-8", errors="ignore")
        return [line.strip() for line in decoded.splitlines() if line.strip()]
    except Exception:
        # Если уже plain-текст (некоторые провайдеры отдают без base64)
        return [line.strip() for line in content.splitlines() if line.strip()]


