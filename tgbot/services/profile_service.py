from dataclasses import dataclass
from typing import Optional, Dict, Any

from db import User
from database.repositories.user import UserRepository
from marzban.init_client import MarzClientCache
from loader import logger


@dataclass
class ProfileData:
    db_user: User | None
    marzban_user: Dict[str, Any] | None
    error: str | None = None


class ProfileService:
    def __init__(self, user_repo: UserRepository, marzban: MarzClientCache):
        self._user_repo = user_repo
        self._marzban = marzban

    async def get_profile(self, user_id: int) -> ProfileData:
        """Возвращает данные профиля без побочных эффектов."""
        user = await self._user_repo.get(user_id)

        if not user or not user.marzban_username:
            return ProfileData(
                db_user=user, marzban_user=None,
                error="У вас еще нет активной подписки. Пожалуйста, оплатите тариф, чтобы получить доступ."
            )

        try:
            marzban_user = await self._marzban.get_user(user.marzban_username)
            if not marzban_user:
                return ProfileData(
                    db_user=user, marzban_user=None,
                    error="Не удалось получить данные о вашей подписке. Пожалуйста, обратитесь в поддержку."
                )
            return ProfileData(db_user=user, marzban_user=marzban_user)
        except Exception as e:
            logger.error(f"Failed to get user {user.marzban_username} from Marzban: {e}", exc_info=True)
            return ProfileData(
                db_user=user, marzban_user=None,
                error="Не удалось получить данные о вашей подписке. Пожалуйста, обратитесь в поддержку."
            )
