import asyncio

from database.repositories.user import UserRepository
from database.repositories.stats import StatsRepository
from marzban.init_client import MarzClientCache
from loader import logger


class UserService:
    def __init__(self, user_repo: UserRepository, stats_repo: StatsRepository):
        self._user_repo = user_repo
        self._stats_repo = stats_repo

    async def register_or_get(self, user_id: int, full_name: str, username: str | None = None):
        return await self._user_repo.get_or_create(user_id, full_name, username)

    async def get_user(self, user_id: int):
        return await self._user_repo.get(user_id)

    async def find_user(self, query: str):
        """Ищет пользователя по ID или username."""
        if query.isdigit():
            return await self._user_repo.get(int(query))
        return await self._user_repo.get_by_username(query.replace("@", ""))

    async def delete_user(self, user_id: int, marzban: MarzClientCache) -> bool:
        """Удаляет пользователя из Marzban и БД."""
        user = await self._user_repo.get(user_id)
        if not user:
            return False

        if user.marzban_username:
            success = await marzban.delete_user(user.marzban_username)
            if not success:
                await asyncio.sleep(1)
                success = await marzban.delete_user(user.marzban_username)
            if not success:
                logger.error(f"Failed to delete marzban user {user.marzban_username} after 2 attempts")
                return False

        return await self._user_repo.delete(user_id)

    async def get_referral_info(self, user_id: int) -> dict:
        """Возвращает данные рефералки для отображения."""
        user = await self._user_repo.get(user_id)
        count = await self._stats_repo.count_user_referrals(user_id)
        return {
            "referral_count": count,
            "bonus_days": user.referral_bonus_days if user else 0
        }
