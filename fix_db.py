# fix_db.py
import asyncio
from sqlalchemy import text
from db import async_engine

async def fix_database():
    print("🔄 Подключение к базе данных...")
    async with async_engine.begin() as conn:
        print("🛠 Добавляю колонки...")
        
        # 1. Добавляем колонку email
        # Используем IF NOT EXISTS, чтобы скрипт не падал, если колонка вдруг уже есть
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255) UNIQUE;"))
        print("✅ Колонка 'email' добавлена.")

        # 2. Добавляем колонку password_hash
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);"))
        print("✅ Колонка 'password_hash' добавлена.")
        
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_code VARCHAR(10);"))
        # Добавляем колонку для времени жизни кода
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_code_expire TIMESTAMP WITHOUT TIME ZONE;"))
        
    print("🎉 Успешно! База данных обновлена.")

if __name__ == "__main__":
    asyncio.run(fix_database())