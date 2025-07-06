# marzban/init_client.py (финальная универсальная версия)

import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from marzban_api_client import models
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

    async def _get_token(self):
        try:
            login_data = BodyAdminTokenApiAdminTokenPost(username=self._config.marzban.username, password=self._config.marzban.password)
            async with Client(base_url=self._base_url, verify_ssl=False) as temp_client:
                token_response = await admin_token.asyncio(client=temp_client, body=login_data)
                return token_response.access_token
        except Exception as e:
            self._logger.error(f"Error getting Marzban token: {e}", exc_info=True)
            raise

    async def get_http_client(self) -> httpx.AsyncClient:
        if not self._http_client or self._exp_at < datetime.now():
            self._logger.info('Getting new Marzban token...')
            token = await self._get_token()
            self._exp_at = datetime.now() + timedelta(minutes=self._config.marzban.token_expire - 1)
            
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
            self._http_client = httpx.AsyncClient(base_url=self._base_url, headers=headers, verify=False)
            self._logger.info('New Marzban http client created.')
        return self._http_client

    async def add_user(self, username: str, expire_days: int) -> Dict[str, Any]:
        client = await self.get_http_client()
        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp())
        
        json_body = {
            "username": username.lower(),
            "expire": expire_timestamp,
            "proxies": {"shadowsocks": {}},
            "inbounds": {}
        }
        
        response = await client.post("/api/user", json=json_body)
        response.raise_for_status()
        return response.json()

    async def get_user(self, username: str) -> Optional[Any]:
        """Универсальный get_user, который пытается распарсить ответ всеми способами."""
        self._logger.info(f"--- Attempting to GET user: {username.lower()} ---")
        client = await self.get_http_client()
        try:
            response = await client.get(f"/api/user/{username.lower()}")
            self._logger.info(f"GET user response status: {response.status_code}")
            
            if response.status_code == 200:
                json_response = response.json()
                self._logger.info(f"GET user JSON response: {json_response}")
                
                # --- УНИВЕРСАЛЬНЫЙ ПАРСЕР ---
                if hasattr(models.UserResponse, 'model_validate'):
                    self._logger.info("Parsing with model_validate (pydantic v2)")
                    return models.UserResponse.model_validate(json_response)
                elif hasattr(models.UserResponse, 'parse_obj'):
                    self._logger.info("Parsing with parse_obj (pydantic v1)")
                    return models.UserResponse.parse_obj(json_response)
                else:
                    self._logger.warning("UserResponse object has no parse methods. Returning raw dict.")
                    return json_response
            return None
        except Exception as e:
            self._logger.error(f"Error in get_user: {e}", exc_info=True)
            return None

    async def modify_user(self, username: str, expire_days: int) -> Dict[str, Any]:
        """Корректно продлевает подписку пользователя."""
        await asyncio.sleep(0.2) # Небольшая пауза
        client = await self.get_http_client()
        
        user_object = await self.get_user(username)
        if not user_object:
            raise ValueError(f"User {username} not found in Marzban, can't modify.")
        
        # --- УНИВЕРСАЛЬНЫЙ ДОСТУП К ПОЛЯМ ---
        current_expire = getattr(user_object, 'expire', user_object.get('expire')) if user_object else int(datetime.now().timestamp())
        if not current_expire:
            current_expire = int(datetime.now().timestamp())
            
        if current_expire > int(datetime.now().timestamp()):
            new_expire_date = datetime.fromtimestamp(current_expire) + timedelta(days=expire_days)
        else:
            new_expire_date = datetime.now() + timedelta(days=expire_days)
        
        new_expire_timestamp = int(new_expire_date.timestamp())
        json_body = {"expire": new_expire_timestamp}
        
        response = await client.put(f"/api/user/{username.lower()}", json=json_body)
        response.raise_for_status()
        return response.json()