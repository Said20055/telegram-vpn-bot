from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from cachetools import TTLCache

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, time_limit: float = 1.0):
        """
        :param time_limit: Лимит времени в секундах. 
                           Сообщения от одного пользователя чаще этого лимита будут игнорироваться.
        """
        # Создаем кэш, где ключ - это ID пользователя, а значение хранится time_limit секунд.
        self.cache = TTLCache(maxsize=10_000, ttl=time_limit)

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        
        # Проверяем, есть ли ID пользователя в нашем кэше
        if event.from_user.id in self.cache:
            # Если пользователь уже отправлял запрос недавно, игнорируем это обновление
            # и не передаем его дальше.
            return

        # Если пользователя в кэше нет, добавляем его туда
        self.cache[event.from_user.id] = None
        
        # И спокойно передаем управление дальше, следующему мидлварю или хендлеру
        return await handler(event, data)