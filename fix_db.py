# fix_db.py — миграция: приводит БД к текущей версии db.py
import asyncio
from sqlalchemy import text
from db import async_engine


async def fix_database():
    print("🔄 Подключение к базе данных...")
    async with async_engine.begin() as conn:

        # ── 1. Таблица users: старые колонки (могут уже существовать) ───────
        print("\n📋 Таблица users — старые поля...")
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255) UNIQUE;"
        ))
        print("  ✅ email")

        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);"
        ))
        print("  ✅ password_hash")

        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_code VARCHAR(10);"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_code_expire TIMESTAMP WITHOUT TIME ZONE;"
        ))
        print("  ✅ reset_code / reset_code_expire")

        # ── 2. Таблица users: новые колонки верификации email ────────────────
        print("\n📋 Таблица users — колонки верификации email...")
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_code VARCHAR(10);"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_code_expire TIMESTAMP WITHOUT TIME ZONE;"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN NOT NULL DEFAULT FALSE;"
        ))
        print("  ✅ verification_code / verification_code_expire / is_email_verified")

        # ── 3. Таблица payments ──────────────────────────────────────────────
        print("\n📋 Создаю таблицу payments...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payments (
                id                  BIGSERIAL PRIMARY KEY,
                yookassa_payment_id VARCHAR NOT NULL UNIQUE,
                user_id             BIGINT NOT NULL REFERENCES users(user_id),
                tariff_id           BIGINT NOT NULL REFERENCES tariffs(id),
                original_amount     FLOAT NOT NULL,
                final_amount        FLOAT NOT NULL,
                promo_code          VARCHAR,
                discount_percent    INTEGER NOT NULL DEFAULT 0,
                status              VARCHAR NOT NULL DEFAULT 'pending',
                source              VARCHAR NOT NULL DEFAULT 'bot',
                created_at          TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                completed_at        TIMESTAMP WITHOUT TIME ZONE
            );
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_payments_yookassa_payment_id ON payments(yookassa_payment_id);"
        ))
        print("  ✅ payments")

        # ── 4. Таблица external_subscriptions ────────────────────────────────
        print("\n📋 Создаю таблицу external_subscriptions...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS external_subscriptions (
                id          SERIAL PRIMARY KEY,
                name        VARCHAR NOT NULL,
                url         VARCHAR NOT NULL,
                added_at    TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                is_active   BOOLEAN NOT NULL DEFAULT TRUE
            );
        """))
        print("  ✅ external_subscriptions")

        # ── 5. Таблица external_configs ──────────────────────────────────────
        print("\n📋 Создаю таблицу external_configs...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS external_configs (
                id              SERIAL PRIMARY KEY,
                subscription_id INTEGER NOT NULL
                    REFERENCES external_subscriptions(id) ON DELETE CASCADE,
                name            VARCHAR NOT NULL,
                raw_link        VARCHAR NOT NULL,
                is_active       BOOLEAN NOT NULL DEFAULT TRUE,
                added_at        TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
            );
        """))
        print("  ✅ external_configs")

    print("\n🎉 Миграция завершена успешно!")


if __name__ == "__main__":
    asyncio.run(fix_database())
