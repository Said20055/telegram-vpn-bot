from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from marzban_api_client import AuthenticatedClient, Client
from marzban_api_client.api.admin import admin_token
from marzban_api_client.api.user import add_user as api_add_user, get_user as api_get_user, modify_user as api_modify_user
from marzban_api_client.models import (
    BodyAdminTokenApiAdminTokenPost,
    UserCreate,
    UserModify,
    UserResponse,
)


class MarzClientCache:
    def __init__(self, base_url: str, config, logger):
        self._client: Optional[AuthenticatedClient] = None
        self._exp_at: Optional[datetime] = None
        self._base_url: str = base_url
        self._config = config
        self._logger = logger
        self._token: str = ''

    async def get_client(self) -> AuthenticatedClient:
        # Если нет клиента или токен просрочен — получаем новый
        if not self._client or (self._exp_at and self._exp_at < datetime.now()):
            self._logger.info('Getting new Marzban token...')
            token = await self._get_token()
            self._token = token
            # Устанавливаем время истечения чуть раньше, чем в конфиге
            self._exp_at = datetime.now() + timedelta(minutes=self._config.marzban.token_expire - 1)
            self._client = AuthenticatedClient(
                base_url=self._base_url,
                token=self._token,
                verify_ssl=False
            )
            self._logger.info('New Marzban client object created.')
        return self._client

    async def _get_token(self) -> str:
        try:
            login_data = BodyAdminTokenApiAdminTokenPost(
                username=self._config.marzban.username,
                password=self._config.marzban.password,
            )
            async with Client(base_url=self._base_url, verify_ssl=False) as client:
                token_response = await admin_token.asyncio(
                    client=client,
                    body=login_data,
                )
                return token_response.access_token
        except Exception as e:
            self._logger.error(f"Error getting Marzban token: {e}", exc_info=True)
            raise

    async def add_user(self, username: str, expire_days: int) -> UserResponse:
        """
        Создает нового пользователя в Marzban и возвращает Pydantic-модель UserResponse
        """
        client = await self.get_client()
        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp())

        user_data = UserCreate(
            username=username,
            expire=expire_timestamp,
            proxies={"vless": {}}
        )
        raw = await api_add_user.asyncio(client=client, body=user_data)
        # Оборачиваем dict в Pydantic-модель
        user = UserResponse.parse_obj(raw)
        return user

    async def modify_user(self, username: str, expire_days: int) -> UserResponse:
        """
        Изменяет срок действия существующего пользователя в Marzban и возвращает обновленную модель
        """
        client = await self.get_client()
        current_raw = await self.get_user(username)
        if not current_raw:
            raise ValueError(f"User {username} not found in Marzban")

        current_expire = current_raw.get('expire', int(datetime.now().timestamp()))
        if current_expire > int(datetime.now().timestamp()):
            new_date = datetime.fromtimestamp(current_expire) + timedelta(days=expire_days)
        else:
            new_date = datetime.now() + timedelta(days=expire_days)

        new_ts = int(new_date.timestamp())
        user_modify = UserModify(expire=new_ts)
        raw = await api_modify_user.asyncio(client=client, username=username, body=user_modify)
        user = UserResponse.parse_obj(raw)
        return user

    async def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает "сырую" dict-информацию о пользователе или None, если не найден.
        """
        client = await self.get_client()
        try:
            response = await api_get_user.asyncio(client=client, username=username)
            return response
        except Exception:
            return None