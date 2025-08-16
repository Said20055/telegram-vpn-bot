# tgbot/handlers/user/instruction.py (Полная, обновленная версия)

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InputFile, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Импортируем клавиатуру для кнопки "Назад"
from tgbot.keyboards.inline import back_to_main_menu_keyboard
from loader import config, logger # Импортируем конфиг, чтобы взять оттуда ID видео

instruction_router = Router(name="instruction")

# --- 1. Клавиатура со ссылками на клиенты ---
def os_client_keyboard():
    """Создает клавиатуру со ссылками на рекомендованные клиенты для VLESS."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🤖 Android (V2RayTun)", url="https://play.google.com/store/apps/details?id=com.v2raytun.android")
    builder.button(text="🍏 iOS (V2RayTun)", url="https://apps.apple.com/ru/app/v2raytun/id6476628951")
    builder.button(text="💻 Windows (NekoBox)", url="https://github.com/MatsuriDayo/nekobox/releases/latest")
    builder.button(text="🍎 macOS (V2rayU)", url="https://github.com/yanue/V2rayU/releases/latest")
    builder.button(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu")
    builder.adjust(1) # Располагаем кнопки по одной в ряд
    return builder.as_markup()


# --- 2. Универсальная функция для показа инструкции ---
async def show_instruction_message(event: types.Message | types.CallbackQuery):
    """
    Показывает пользователю видео и текстовую инструкцию по подключению.
    """
    # ID вашего видео-файла, который вы предварительно загрузили
    # Лучше хранить его в .env и загружать через config
    VIDEO_FILE_ID = config.tg_bot.instruction_video_id # <-- Нужно будет добавить в config.py
    
    # Новый, упрощенный текст инструкции
    text = (
        "📲 <b>Инструкция по подключению (Авто-импорт)</b>\n\n"
        "1️⃣ <b>Перейдите в профиль</b>\n"
        "Откройте раздел «👤 Мой профиль» в главном меню.\n\n"
        "2️⃣ <b>Нажмите на кнопку</b>\n"
        "Под QR-кодом и ссылкой найдите и нажмите кнопку <b>«📲 Импортировать подписку»</b>.\n\n"
        "3️⃣ <b>Разрешите открытие</b>\n"
        "Вас перенаправит на веб-страницу, которая предложит открыть приложение (V2RayTUN или другое). Согласитесь.\n\n"
        "4️⃣ <b>Подключитесь</b>\n"
        "Подписка будет добавлена автоматически! Осталось только обновить список серверов и нажать кнопку подключения.\n\n"
    )
    
    chat_id = event.from_user.id
    
    # --- Логика отправки ---
    if isinstance(event, types.CallbackQuery):
        # Если это колбэк, сначала нужно ответить на него
        await event.answer()
        # И удаляем старое сообщение, чтобы отправить новое с видео
        try: await event.message.delete()
        except: pass
    
    # Отправляем видео по его file_id, а текст - в подписи (caption)
    try:
        if VIDEO_FILE_ID:
            await event.bot.send_video(
                chat_id=chat_id,
                video=VIDEO_FILE_ID,
                caption=text,
                reply_markup=os_client_keyboard()
            )
        else: # Если видео не задано, отправляем только текст
            await event.bot.send_message(
                chat_id=chat_id,
                text=text + "\n\n<i>Видео-инструкция скоро появится.</i>",
                reply_markup=os_client_keyboard()
            )
    except Exception as e:
        logger.error(f"Failed to send instruction video: {e}")
        # Если не удалось отправить видео (например, ID неверный), шлем только текст
        await event.bot.send_message(chat_id=chat_id, text=text, reply_markup=os_client_keyboard())


# --- 3. Хендлеры для команды и кнопки ---
@instruction_router.message(Command("instruction"))
async def instruction_command_handler(message: types.Message):
    await show_instruction_message(message)

@instruction_router.callback_query(F.data == "instruction_info")
async def instruction_callback_handler(call: types.CallbackQuery):
    await show_instruction_message(call)