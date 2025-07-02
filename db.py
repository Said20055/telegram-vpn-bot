import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()  # Загрузим переменные из .env

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def get_user(telegram_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
            return cur.fetchone()


def create_user(telegram_id: int, referred_by: int = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (telegram_id, referral_code, referred_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id) DO NOTHING
            """, (telegram_id, f"ref_{telegram_id}", referred_by))
            conn.commit()


def mark_user_paid(telegram_id: int, days: int = 30):
    paid_until = datetime.utcnow() + timedelta(days=days)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET is_paid = TRUE,
                    paid_until = %s
                WHERE telegram_id = %s
            """, (paid_until, telegram_id))
            conn.commit()


def is_user_paid(telegram_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT is_paid, paid_until
                FROM users
                WHERE telegram_id = %s
            """, (telegram_id,))
            row = cur.fetchone()
            if row and row["is_paid"] and row["paid_until"] > datetime.utcnow():
                return True
            return False


def save_payment(telegram_id: int, yookassa_id: str, amount: float, status: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO payments (telegram_id, yookassa_id, amount, status)
                VALUES (%s, %s, %s, %s)
            """, (telegram_id, yookassa_id, amount, status))
            conn.commit()
