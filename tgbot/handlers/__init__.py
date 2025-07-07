
from tgbot.handlers.user import user_router
from .admin.main import admin_main_router
from .admin.users import admin_users_router

# Собираем все роутеры в один список
routers_list = [
    user_router,
    admin_main_router,
    admin_users_router,
]

__all__ = [
    "routers_list",
]
