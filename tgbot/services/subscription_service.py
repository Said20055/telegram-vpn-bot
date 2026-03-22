from dataclasses import dataclass

from database.repositories.user import UserRepository
from marzban.init_client import MarzClientCache
from loader import logger


@dataclass
class ExtensionResult:
    is_new_marzban_user: bool
    marzban_username: str


class SubscriptionService:
    def __init__(self, user_repo: UserRepository, marzban: MarzClientCache):
        self._user_repo = user_repo
        self._marzban = marzban

    async def extend(self, user_id: int, days: int) -> ExtensionResult:
        """
        Продлевает подписку в БД и Marzban. Создает Marzban-пользователя если нужно.
        """
        user = await self._user_repo.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found in DB")

        marzban_username = self._resolve_marzban_username(user)
        is_new = await self._ensure_marzban_user(marzban_username, days)

        if not user.marzban_username:
            await self._user_repo.update_marzban_username(user_id, marzban_username)

        await self._user_repo.extend_subscription(user_id, days)

        logger.info(f"Subscription for user {user_id} extended by {days} days (marzban: {marzban_username}, new={is_new})")
        return ExtensionResult(is_new_marzban_user=is_new, marzban_username=marzban_username)

    async def activate_trial(self, user_id: int, days: int = 7) -> ExtensionResult:
        """Активирует пробный период: extend + пометить trial_received."""
        result = await self.extend(user_id, days)
        await self._user_repo.set_trial_received(user_id)
        return result

    def _resolve_marzban_username(self, user) -> str:
        if user.marzban_username:
            return user.marzban_username.lower()
        if user.user_id > 0:
            return f"user_{user.user_id}"
        return f"web_{abs(user.user_id)}"

    async def _ensure_marzban_user(self, username: str, days: int) -> bool:
        """Создает или продлевает пользователя в Marzban. Возвращает True если создан новый."""
        existing = await self._marzban.get_user(username)
        if existing:
            await self._marzban.modify_user(username=username, expire_days=days)
            return False
        else:
            await self._marzban.add_user(username=username, expire_days=days)
            return True
