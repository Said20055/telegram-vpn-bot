import base64
import uuid
from urllib.parse import unquote

import httpx

from database.repositories.external_vpn import ExternalSubscriptionRepository, ExternalConfigRepository
from db import ExternalConfig, ExternalSubscription

VALID_PREFIXES = ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "hy2://", "tuic://")

# Фиксированный HWID для запросов к внешним подпискам (имитация устройства)
_HWID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "vpn-bot-fetcher"))

_FETCH_HEADERS = {
    "User-Agent": "HappProxy/2.1.6 (Linux; Bot)",
    "x-hwid": _HWID,
    "x-device-os": "Linux",
    "x-ver-os": "6.1",
    "x-device-model": "Server",
    "Accept": "*/*",
}


def _extract_links(text: str) -> list[dict]:
    """Извлекает VPN-ссылки из текста (по одной на строку)."""
    links = []
    for line in text.splitlines():
        line = line.strip()
        if any(line.startswith(p) for p in VALID_PREFIXES):
            if "#" in line:
                raw_link, fragment = line.rsplit("#", 1)
                name = unquote(fragment).strip() or raw_link[:40]
            else:
                raw_link = line
                name = line[:40]
            links.append({"name": name, "raw_link": line})
    return links


def parse_subscription(content: str) -> list[dict]:
    """
    Парсит V2Ray/Xray subscription: base64-строка или plain-текст → список {name, raw_link}.
    Сначала пробует plain-текст, потом base64 decode.
    """
    # Сначала проверяем plain-текст (прямая вставка конфигов)
    links = _extract_links(content)
    if links:
        return links

    # Пробуем base64 decode (стандартный формат подписки)
    try:
        decoded = base64.b64decode(content + "==").decode("utf-8", errors="ignore")
        return _extract_links(decoded)
    except Exception:
        return []


def parse_raw_configs(text: str) -> list[dict]:
    """
    Парсит raw-конфиги вставленные напрямую (по одной ссылке на строку).
    Принимает как plain-текст, так и base64.
    """
    return parse_subscription(text)


class ExternalVpnService:
    def __init__(
        self,
        sub_repo: ExternalSubscriptionRepository,
        config_repo: ExternalConfigRepository,
    ):
        self._sub_repo = sub_repo
        self._config_repo = config_repo

    async def fetch_and_parse(self, url: str) -> list[dict]:
        """Загружает URL подписки и возвращает список серверов [{name, raw_link}]."""
        async with httpx.AsyncClient(
            timeout=15, follow_redirects=True, verify=False
        ) as client:
            response = await client.get(url, headers=_FETCH_HEADERS)
            response.raise_for_status()
        return parse_subscription(response.text)

    async def save_configs(self, url: str, name: str, selected: list[dict]) -> tuple[ExternalSubscription, int]:
        """Создаёт ExternalSubscription и сохраняет выбранные конфиги."""
        sub = await self._sub_repo.create(name=name, url=url)
        count = await self._config_repo.create_many(sub.id, selected)
        return sub, count

    async def get_active_links(self) -> list[str]:
        """Возвращает список raw_link для всех активных внешних конфигов."""
        configs: list[ExternalConfig] = await self._config_repo.get_active()
        return [c.raw_link for c in configs]

    async def get_all_subscriptions(self) -> list[ExternalSubscription]:
        return await self._sub_repo.get_all()

    async def get_configs_by_subscription(self, sub_id: int) -> list[ExternalConfig]:
        return await self._config_repo.get_by_subscription(sub_id)

    async def toggle_config(self, config_id: int) -> tuple[bool, int | None]:
        """Возвращает (новое_значение_is_active, subscription_id)."""
        return await self._config_repo.toggle_active(config_id)

    async def delete_config(self, config_id: int):
        await self._config_repo.delete(config_id)

    async def delete_subscription(self, sub_id: int):
        await self._sub_repo.delete(sub_id)
