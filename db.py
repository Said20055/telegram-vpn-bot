# db.py (ФИНАЛЬНАЯ ВЕРСИЯ НА SQLAlchemy)

import datetime
from sqlalchemy import (
    create_engine, BigInteger, String, DateTime, Boolean, ForeignKey,
    Integer, Float, select, func
)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from config import load_config

# --- 1. Настройка ---
config = load_config()
db_config = config.dataBase
DSN = f"postgresql+asyncpg://{db_config.user}:{db_config.password}@{db_config.host}:{db_config.port}/{db_config.db_name}"
SYNC_DSN = f"postgresql://{db_config.user}:{db_config.password}@{db_config.host}:{db_config.port}/{db_config.db_name}"

# Создаем асинхронный "движок" и фабрику сессий
async_engine = create_async_engine(DSN)
async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False)

# --- 2. Базовая модель ---
class Base(DeclarativeBase):
    pass

# --- 3. Определяем все ваши модели на новом синтаксисе ---
class User(Base):
    __tablename__ = 'users'
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=True)
    full_name: Mapped[str] = mapped_column(String)
    reg_date: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    subscription_end_date: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    marzban_username: Mapped[str] = mapped_column(String, unique=True, nullable=True)
    
    # --- НОВОЕ ПОЛЕ ДЛЯ ОТСЛЕЖИВАНИЯ ТРИАЛА ---
    has_received_trial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    referrer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id', ondelete='SET NULL'), nullable=True)
    referral_bonus_days: Mapped[int] = mapped_column(Integer, default=0)
    is_first_payment_made: Mapped[bool] = mapped_column(Boolean, default=False)
    support_topic_id: Mapped[int] = mapped_column(Integer, nullable=True)
    
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=True)
    
    reset_code: Mapped[str] = mapped_column(String(10), nullable=True)
    reset_code_expire: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)

    verification_code: Mapped[str] = mapped_column(String(10), nullable=True)
    verification_code_expire: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')

class Tariff(Base):
    __tablename__ = 'tariffs'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    price: Mapped[float] = mapped_column(Float)
    duration_days: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class PromoCode(Base):
    __tablename__ = 'promo_codes'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True)
    bonus_days: Mapped[int] = mapped_column(Integer, default=0)
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    expire_date: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    uses_left: Mapped[int] = mapped_column(Integer, default=1)

class UsedPromoCode(Base):
    __tablename__ = 'used_promo_codes'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'))
    promo_code_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('promo_codes.id'))
    used_date: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)

class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    yookassa_payment_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'))
    tariff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('tariffs.id'))
    original_amount: Mapped[float] = mapped_column(Float)
    final_amount: Mapped[float] = mapped_column(Float)
    promo_code: Mapped[str] = mapped_column(String, nullable=True)
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default='pending')  # pending / succeeded / failed / refunded / cancelled
    source: Mapped[str] = mapped_column(String, default='bot')  # bot / web
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    completed_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)

class Channel(Base):
    __tablename__ = 'channels'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    title: Mapped[str] = mapped_column(String)
    invite_link: Mapped[str] = mapped_column(String)


class ExternalSubscription(Base):
    """Источник внешних VPN-конфигов (URL подписки стороннего провайдера)."""
    __tablename__ = 'external_subscriptions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    added_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExternalConfig(Base):
    """Отдельный сервер из внешней подписки, выбранный админом."""
    __tablename__ = 'external_configs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(Integer, ForeignKey('external_subscriptions.id', ondelete='CASCADE'))
    name: Mapped[str] = mapped_column(String)
    raw_link: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


# --- 4. Функция для создания таблиц ---
def setup_database_sync():
    """Создает таблицы синхронно при старте бота."""
    engine = create_engine(SYNC_DSN)
    Base.metadata.create_all(engine)
    print("INFO: Database tables created or already exist via SQLAlchemy.")