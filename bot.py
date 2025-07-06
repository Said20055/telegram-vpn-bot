import asyncio

from aiogram import Dispatcher, F
from aiogram.enums import ChatType
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# --- ШАГ 1: Импортируем готовые объекты из loader ---
# Мы импортируем уже настроенные: bot, config, logger и КЛИЕНТ MARZBAN
from loader import bot, config, logger, marzban_client

# --- ШАГ 2: Импортируем наши новые модули и хендлеры ---
from db import setup_database
from tgbot.handlers import routers_list
from tgbot.middlewares.flood import ThrottlingMiddleware
from tgbot.handlers.webhook_handlers import yookassa_webhook_handler
from utils import broadcaster


async def on_startup(bot, marzban): # Добавили marzban в аргументы
    """Выполняется при запуске бота."""
    # 1. Инициализируем базу данных
    setup_database()
    logger.info("Database initialized.")

    # Можно добавить проверку соединения с Marzban
    # if await marzban.is_online():
    #     logger.info("Marzban panel is online.")
    # else:
    #     logger.error("Could not connect to Marzban panel!")

    # 2. Отправляем сообщение админу о запуске
    await broadcaster.broadcast(bot, [config.tg_bot.admin_id], "Бот запущен")
    logger.info("Startup message sent to admin.")

    # 3. Устанавливаем команды меню
    await register_commands(bot)
    logger.info("Bot commands registered.")

    # 4. Установка вебхука
    if config.webhook.use_webhook:
        webhook_url = f"https://{config.webhook.domain}{config.webhook.url}"
        await bot.set_webhook(webhook_url, drop_pending_updates=True) # Добавлено drop_pending_updates
        logger.info(f"Webhook set to: {webhook_url}")
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Polling mode: Webhook deleted and pending updates dropped.")


async def register_commands(bot):
    """Регистрирует команды в меню Telegram."""
    commands = [
        BotCommand(command='start', description='🏠 Главное меню'),
        # ... другие команды
    ]
    await bot.set_my_commands(commands, BotCommandScopeDefault())


def register_global_middlewares(dp: Dispatcher):
    """Регистрирует глобальные мидлвари."""
    middleware_types = [
        ThrottlingMiddleware(),
    ]
    for middleware_type in middleware_types:
        dp.message.outer_middleware(middleware_type)
        dp.callback_query.outer_middleware(middleware_type)
    dp.callback_query.outer_middleware(CallbackAnswerMiddleware())
    dp.message.filter(F.chat.type == ChatType.PRIVATE)
    logger.info("Global middlewares registered.")


def main_webhook():
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage, marzban=marzban_client)
    dp.include_routers(*routers_list)
    register_global_middlewares(dp)
    dp.startup.register(on_startup)

    app = web.Application()
    app['bot'] = bot

    app['marzban'] = marzban_client # Это у вас уже должно быть
    app['config'] = config # <--- ДОБАВЬТЕ ЭТУ СТРОКУ
    
    
    # --- НАШИ ИЗМЕНЕНИЯ ---
    # 1. Регистрируем обработчик для вебхуков Telegram
    telegram_webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    telegram_webhook_handler.register(app, path=config.webhook.url)
    
    # 2. Регистрируем обработчик для вебхуков YooKassa на отдельный путь
    app.router.add_post('/yookassa', yookassa_webhook_handler)

    setup_application(app, dp, bot=bot, marzban=marzban_client)
    
    logger.info("Starting bot in webhook mode...")
    web.run_app(app, host='0.0.0.0', port=8080)


async def main_polling():
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage, marzban=marzban_client)
    dp.include_routers(*routers_list)
    register_global_middlewares(dp)
    
    # Вызываем on_startup до запуска основных процессов
    await on_startup(bot, marzban_client)
    
    logger.info("Starting bot in polling mode...")

    # Создаем задачу для запуска веб-сервера YooKassa в фоне
    yookassa_server_task = asyncio.create_task(start_yookassa_webhook_server())

    # Создаем задачу для запуска поллинга Telegram в фоне
    polling_task = asyncio.create_task(dp.start_polling(bot))

    # Запускаем обе задачи и ждем их завершения (что в норме не произойдет)
    await asyncio.gather(
        polling_task,
        yookassa_server_task
    )


async def start_yookassa_webhook_server():
    app = web.Application()
    
    # "Внедряем" в приложение все нужные нам объекты
    app['bot'] = bot
    app['marzban'] = marzban_client # <--- ВОТ ЭТА СТРОКА РЕШАЕТ ПРОБЛЕМУ
    app['config'] = config         # <--- ЭТА СТРОКА НУЖНА ДЛЯ ОПОВЕЩЕНИЙ АДМИНА
    
    app.router.add_post('/yookassa', yookassa_webhook_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=8081)
    await site.start()
    logger.info("YooKassa webhook server started on port 8081")
    while True:
        await asyncio.sleep(3600)


if __name__ == '__main__':
    # Логирование уже настроено в loader.py
    logger.info("Initializing bot...")
    
    if config.webhook.use_webhook:
        main_webhook()
    else:
        try:
            asyncio.run(main_polling())
        except (KeyboardInterrupt, SystemExit):
            logger.warning("Bot stopped!")