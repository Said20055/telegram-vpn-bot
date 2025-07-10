# marzban/init_client.py (оптимизированная версия + метод delete)

import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from marzban_api_client.api.admin import admin_token
from marzban_api_client.models.body_admin_token_api_admin_token_post import (
    BodyAdminTokenApiAdminTokenPost,
)
from marzban_api_client.client import Client

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
            
            self._http_client = httpx.AsyncClient(base_url=self._base_url, headers=headers, verify=False)
            self._logger.info('New Marzban http client created.')
        return self._http_client

    async def add_user(self, username: str, expire_days: int) -> Dict[str, Any]:
        """Создает нового пользователя в Marzban."""
        client = await self.get_http_client()
        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp())

        json_body = {
            "username": username.lower(),
            "expire": expire_timestamp,
            "proxies": {"vless": {}},
            "inbounds": {"vless": ["VLESS-Reality"]}
        }

        response = await client.post("/api/user", json=json_body)
        response.raise_for_status()  # Вызовет исключение для кодов 4xx/5xx
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
        """Корректно продлевает подписку пользователя."""
        client = await self.get_http_client()
        
        user_dict = await self.get_user(username)
        if not user_dict:
            raise ValueError(f"User '{username}' not found in Marzban, can't modify.")
        
        current_expire = user_dict.get('expire') or int(datetime.now().timestamp())
            
        if current_expire > int(datetime.now().timestamp()):
            new_expire_date = datetime.fromtimestamp(current_expire) + timedelta(days=expire_days)
        else:
            new_expire_date = datetime.now() + timedelta(days=expire_days)
        
        json_body = {"expire": int(new_expire_date.timestamp())}
        
        response = await client.put(f"/api/user/{username.lower()}", json=json_body)
        response.raise_for_status()
        return response.json()

    # --- НОВЫЙ МЕТОД ---
        
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