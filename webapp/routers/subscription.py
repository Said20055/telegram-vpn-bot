"""
webapp/routers/subscription.py

Агрегирующий прокси для Marzban subscription URL.
Перехватывает запросы на /sub/{marzban_username}, добавляет внешние VPN-конфиги
если у пользователя активная подписка, и возвращает объединённый base64-список.
"""

import base64
import time

import httpx
from fastapi import APIRouter
from fastapi.responses import Response

from database import external_config_repo
from loader import logger

router = APIRouter()

# Marzban subscription endpoint внутри Docker-сети (без SSL verify)
_MARZBAN_BASE = "https://marzban:8002"

# Заголовки Marzban которые пробрасываем клиенту
_PASSTHROUGH_HEADERS = (
    "subscription-userinfo",
    "profile-update-interval",
    "profile-title",
    "profile-web-page-url",
    "support-url",
    "content-disposition",
)

_ANNOUNCE_EXPIRED = "Ваша подписка истекла. Продлите подписку для доступа ко всем серверам."
_ANNOUNCE_ACTIVE = "Не работает VPN? Нажми на кнопку 🔄 и проверь каждый вариант"


def _b64_header(text: str) -> str:
    """Кодирует текст в формат base64: для HTTP-заголовков Happ (кириллица)."""
    return "base64:" + base64.b64encode(text.encode("utf-8")).decode("ascii")


@router.get("/sub/{marzban_username}")
async def subscription_proxy(marzban_username: str):
    """
    1. Запрашивает подписку из Marzban напрямую по внутреннему адресу
    2. Пробрасывает оригинальные заголовки Marzban (subscription-userinfo и др.)
    3. Проверяет статус подписки по subscription-userinfo
    4. Если подписка активна — добавляет внешние VPN-конфиги + announce
    5. Если истекла — возвращает только Marzban + announce об истечении
    """
    marz_url = f"{_MARZBAN_BASE}/sub/{marzban_username}"

    # Получаем оригинальную подписку из Marzban
    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            resp = await client.get(marz_url)
            resp.raise_for_status()
            marz_content = resp.text.strip()
            marz_headers = resp.headers
    except httpx.HTTPError as e:
        logger.warning(f"[sub_proxy] Marzban request failed for {marzban_username}: {e}")
        return Response("", media_type="text/plain; charset=utf-8")

    # Собираем заголовки для ответа (проброс из Marzban)
    response_headers = {}
    for hdr in _PASSTHROUGH_HEADERS:
        if hdr in marz_headers:
            response_headers[hdr] = marz_headers[hdr]

    # Проверяем статус подписки
    sub_active = _is_subscription_active(marz_headers.get("subscription-userinfo", ""))

    if not sub_active:
        response_headers["announce"] = _b64_header(_ANNOUNCE_EXPIRED)
        return Response(
            marz_content,
            media_type="text/plain; charset=utf-8",
            headers=response_headers,
        )

    # Announce для активных пользователей
    response_headers["announce"] = _b64_header(_ANNOUNCE_ACTIVE)

    # Получаем активные внешние конфиги
    ext_configs = await external_config_repo.get_active()
    if not ext_configs:
        return Response(
            marz_content,
            media_type="text/plain; charset=utf-8",
            headers=response_headers,
        )

    # Декодируем Marzban base64 → список ссылок + добавляем внешние
    marz_links = _decode_links(marz_content)
    ext_links = [c.raw_link for c in ext_configs]

    combined = marz_links + ext_links
    encoded = base64.b64encode("\n".join(combined).encode("utf-8")).decode("utf-8")

    return Response(
        encoded,
        media_type="text/plain; charset=utf-8",
        headers=response_headers,
    )


def _is_subscription_active(userinfo_header: str) -> bool:
    """Проверяет активность подписки по заголовку subscription-userinfo.

    Формат: upload=123; download=456; total=10737418240; expire=1711234567
    - expire > 0 и expire < now() → истекла по времени
    - total > 0 и upload + download >= total → исчерпан трафик
    - Если заголовок пуст или не парсится → считаем активной (safe fallback)
    """
    if not userinfo_header:
        return True

    parts = {}
    for part in userinfo_header.split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            try:
                parts[key.strip()] = int(value.strip())
            except ValueError:
                continue

    expire = parts.get("expire", 0)
    if expire > 0 and expire < time.time():
        return False

    total = parts.get("total", 0)
    if total > 0:
        used = parts.get("upload", 0) + parts.get("download", 0)
        if used >= total:
            return False

    return True


_VPN_PREFIXES = ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "hy2://", "tuic://")


def _decode_links(content: str) -> list[str]:
    """Декодирует подписку в список ссылок.

    Сначала проверяет plain-text (b64decode молча декодирует любую строку без исключения),
    затем пробует base64.
    """
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if any(line.startswith(_VPN_PREFIXES) for line in lines):
        return lines
    try:
        decoded = base64.b64decode(content + "==").decode("utf-8", errors="ignore")
        return [line.strip() for line in decoded.splitlines() if line.strip()]
    except Exception:
        return lines
