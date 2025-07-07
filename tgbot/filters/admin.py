# tgbot/filters/admin.py
from aiogram.filters import BaseFilter
from aiogram.types import Message
from loader import config

class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        # Проверяем, есть ли ID пользователя в списке админов из конфига
        return message.from_user.id == config.tg_bot.admin_id