# marzban/init_client.py (оптимизированная версия + метод delete)

import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from marzban_api_client.api.admin import admin_token
from marzban_api_client.models.body_admin_token_api_admin_token_post import (
    BodyAdminTokenApiAdminTokenPost,
)
from marzban_api_client.client import Client

DATA_LIMIT_BYTES = 1_000 * 1024 ** 3  # 1000 ГБ в байтах
DATA_LIMIT_RESET_STRATEGY = "month"   # сброс лимита каждый месяц


class MarzClientCache:
    def __init__(self, base_url: str, config, logger):
        self._http_client: Optional[httpx.AsyncClient] = None
        self._exp_at: Optional[datetime] = None
        self._base_url: str = base_url
        self._config = config
        self._logger = logger
        self._token: str = ''

    async def _get_token(self) -> str:
        """Получает токен доступа для API Marzban."""
        try:
            login_data = BodyAdminTokenApiAdminTokenPost(
                username=self._config.marzban.username, 
                password=self._config.marzban.password
            )
            async with Client(base_url=self._base_url, verify_ssl=False) as temp_client:
                token_response = await admin_token.asyncio(client=temp_client, body=login_data)
                return token_response.access_token
        except Exception as e:
            self._logger.error(f"Error getting Marzban token: {e}", exc_info=True)
            raise

    async def get_http_client(self) -> httpx.AsyncClient:
        """Возвращает аутентифицированный httpx клиент, обновляя токен при необходимости."""
        if not self._http_client or self._exp_at < datetime.now():
            self._logger.info('Getting new Marzban token...')
            token = await self._get_token()
            self._exp_at = datetime.now() + timedelta(minutes=self._config.marzban.token_expire - 1)
            
            headers = {
                "Authorization": f"Bearer {token}", 
                "Content-Type": "application/json", 
                "Accept": "application/json"
            }
            # Закрываем старый клиент, если он был, чтобы освободить ресурсы
            if self._http_client:
                await self._http_client.aclose()
            
            self._http_client = httpx.AsyncClient(base_url=self._base_url, headers=headers, verify=False, timeout=30.0)
            self._logger.info('New Marzban http client created.')
        return self._http_client

        
    async def get_system_stats(self) -> Dict[str, Any]:
        """Получает системную статистику из Marzban (включая онлайн)."""
        client = await self.get_http_client()
        try:
            response = await client.get("/api/system")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self._logger.error(f"Failed to get system stats from Marzban: {e}")
            # Возвращаем пустой словарь с дефолтными значениями
            return {"online_clients": 0, "cpu_usage": 0, "mem_usage": 0}
    
    async def get_nodes(self) -> list:
        """Получает список всех узлов (серверов) из Marzban."""
        client = await self.get_http_client()
        try:
            response = await client.get("/api/nodes")
            response.raise_for_status()
            nodes_list = response.json()
            return nodes_list if isinstance(nodes_list, list) else []
        except Exception as e:
            self._logger.error(f"Failed to get nodes from Marzban: {e}")
            return []
    async def get_inbounds(self) -> Dict[str, list]:
        """Получает доступные inbounds из Marzban."""
        client = await self.get_http_client()
        try:
            response = await client.get("/api/inbounds")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self._logger.error(f"Failed to get inbounds from Marzban: {e}")
            return {}

    async def add_user(self, username: str, expire_days: int) -> Dict[str, Any]:
        """Создает нового пользователя в Marzban, автоматически определяя доступные inbounds."""
        client = await self.get_http_client()
        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp())

        # Запрашиваем доступные inbounds у Marzban
        inbounds = await self.get_inbounds()
        self._logger.info(f"Available Marzban inbounds: {inbounds}")

        # Строим proxies и inbounds на основе доступных
        proxies = {}
        inbounds_map = {}
        for protocol, items in inbounds.items():
            if items:
                # items может быть списком объектов [{tag, protocol, ...}] или строк
                tags = []
                for item in items:
                    if isinstance(item, dict):
                        tags.append(item["tag"])
                    else:
                        tags.append(item)
                inbounds_map[protocol] = tags
                if protocol == "vless":
                    proxies[protocol] = {"flow": "xtls-rprx-vision"}
                else:
                    proxies[protocol] = {}

        if not proxies:
            raise ValueError(f"No inbounds available in Marzban. Configure at least one inbound in Marzban dashboard.")

        json_body = {
            "username": username.lower(),
            "expire": expire_timestamp,
            "data_limit": DATA_LIMIT_BYTES,
            "data_limit_reset_strategy": DATA_LIMIT_RESET_STRATEGY,
            "proxies": proxies,
            "inbounds": inbounds_map,
        }

        self._logger.info(f"Creating Marzban user '{username}' with inbounds: {inbounds_map}")
        response = await client.post("/api/user", json=json_body)
        if response.status_code != 200:
            self._logger.error(f"Marzban add_user failed: {response.status_code} {response.text}")
            response.raise_for_status()
        return response.json()

    async def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о пользователе из Marzban."""
        client = await self.get_http_client()
        try:
            response = await client.get(f"/api/user/{username.lower()}")
            if response.status_code == 200:
                return response.json()
            # Если юзер не найден, Marzban вернет 404, что будет поймано в except
            return None
        except httpx.HTTPStatusError as e:
            # Логируем только если это не 404 (юзер не найден)
            if e.response.status_code != 404:
                self._logger.error(f"Error getting user {username}: {e}", exc_info=True)
            return None
        except Exception as e:
            self._logger.error(f"An unexpected error occurred in get_user for {username}: {e}", exc_info=True)
            return None

    async def modify_user(self, username: str, expire_days: int) -> Dict[str, Any]:
        """
        Продлевает подписку существующего пользователя.
        Если пользователь не найден в Marzban - создает его с указанным сроком.
        """
        self._logger.info(f"Modifying/Ensuring subscription for user '{username}' for {expire_days} days.")
        
        # 1. Проверяем, существует ли пользователь
        user_exists = await self.get_user(username)
        
        # 2. Сценарий: Пользователь существует -> Продлеваем
        if user_exists:
            self._logger.info(f"User '{username}' exists. Extending subscription.")
            
            # Получаем текущую дату истечения из словаря
            current_expire_ts = user_exists.get('expire') or int(datetime.now().timestamp())
            
            # Рассчитываем новую дату
            if current_expire_ts > int(datetime.now().timestamp()):
                # Если подписка еще активна, добавляем дни к дате окончания
                new_expire_date = datetime.fromtimestamp(current_expire_ts) + timedelta(days=expire_days)
            else:
                # Если подписка истекла, добавляем дни к сегодняшней дате
                new_expire_date = datetime.now() + timedelta(days=expire_days)
            
            # Формируем тело запроса для изменения
            json_body = {
                "expire": int(new_expire_date.timestamp()),
                "data_limit": DATA_LIMIT_BYTES,
                "data_limit_reset_strategy": DATA_LIMIT_RESET_STRATEGY,
            }
            
            # Отправляем PUT запрос на изменение
            client = await self.get_http_client()
            response = await client.put(f"/api/user/{username.lower()}", json=json_body)
            response.raise_for_status()
            return response.json()

        # 3. Сценарий: Пользователя нет -> Создаем
        else:
            self._logger.warning(f"User '{username}' not found in Marzban. Creating a new user instead.")
            # Если пользователя нет, мы не можем его "изменить". Вместо этого мы вызываем
            # наш же метод add_user, чтобы создать его с нужным сроком.
            # Это избавляет от дублирования кода.
            return await self.add_user(username=username, expire_days=expire_days)

    async def get_users(self, offset: int = 0, limit: int = 1000) -> Dict[str, Any]:
        """Получает список всех пользователей из Marzban."""
        client = await self.get_http_client()
        try:
            response = await client.get("/api/users", params={"offset": offset, "limit": limit})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self._logger.error(f"Failed to get users list from Marzban: {e}")
            return {"users": [], "total": 0}

    async def set_data_limit(self, username: str, limit_bytes: int = DATA_LIMIT_BYTES) -> bool:
        """Устанавливает лимит трафика для существующего пользователя."""
        client = await self.get_http_client()
        try:
            response = await client.put(
                f"/api/user/{username.lower()}",
                json={
                    "data_limit": limit_bytes,
                    "data_limit_reset_strategy": DATA_LIMIT_RESET_STRATEGY,
                },
            )
            response.raise_for_status()
            self._logger.info(f"Set data_limit={limit_bytes} for user '{username}'.")
            return True
        except Exception as e:
            self._logger.error(f"Failed to set data_limit for user '{username}': {e}")
            return False

    async def apply_data_limit_to_all(self, limit_bytes: int = DATA_LIMIT_BYTES) -> Dict[str, int]:
        """
        Устанавливает лимит трафика всем пользователям, у которых он не задан (data_limit == 0 или None).
        Возвращает {'updated': N, 'skipped': M, 'failed': K}.
        """
        result = {"updated": 0, "skipped": 0, "failed": 0}
        data = await self.get_users(limit=4096)
        users = data.get("users", [])
        self._logger.info(f"apply_data_limit_to_all: found {len(users)} users in Marzban.")
        for user in users:
            username = user.get("username", "")
            current_limit = user.get("data_limit") or 0
            if current_limit == 0:
                ok = await self.set_data_limit(username, limit_bytes)
                if ok:
                    result["updated"] += 1
                else:
                    result["failed"] += 1
            else:
                result["skipped"] += 1
        self._logger.info(f"apply_data_limit_to_all done: {result}")
        return result

    async def delete_user(self, username: str) -> bool:
        """Удаляет пользователя из Marzban."""
        client = await self.get_http_client()
        try:
            response = await client.delete(f"/api/user/{username.lower()}")
            response.raise_for_status()
            self._logger.info(f"Successfully deleted user '{username}' from Marzban.")
            return True
        except httpx.HTTPStatusError as e:
            # Если юзер уже удален (404), считаем это успехом
            if e.response.status_code == 404:
                self._logger.warning(f"Attempted to delete user '{username}', but they were not found (already deleted?).")
                return True
            self._logger.error(f"Failed to delete user '{username}': {e}", exc_info=True)
            return False
        except Exception as e:
            self._logger.error(f"An unexpected error occurred in delete_user for '{username}': {e}", exc_info=True)
            return False