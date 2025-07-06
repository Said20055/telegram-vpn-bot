from db import db, User, Tariff
from peewee import DoesNotExist
import datetime

# Важно: используем менеджер контекста для безопасной работы с соединением
def db_connection(func):
    def wrapper(*args, **kwargs):
        db.connect(reuse_if_open=True)
        result = func(*args, **kwargs)
        db.close()
        return result
    return wrapper

@db_connection
def get_or_create_user(user_id: int, full_name: str, username: str | None = None):
    user, created = User.get_or_create(
        user_id=user_id,
        defaults={'full_name': full_name, 'username': username}
    )
    return user, created

@db_connection
def get_user(user_id: int):
    try:
        return User.get(User.user_id == user_id)
    except DoesNotExist:
        return None

@db_connection
def update_user_marzban_username(user_id: int, marzban_username: str):
    query = User.update(marzban_username=marzban_username).where(User.user_id == user_id)
    query.execute()

@db_connection
def extend_user_subscription(user_id: int, days: int):
    user = get_user(user_id)
    if not user:
        return
    
    if user.subscription_end_date and user.subscription_end_date > datetime.datetime.now():
        new_date = user.subscription_end_date + datetime.timedelta(days=days)
    else:
        new_date = datetime.datetime.now() + datetime.timedelta(days=days)

    query = User.update(subscription_end_date=new_date).where(User.user_id == user_id)
    query.execute()
@db_connection
def get_user_referrals(user_id: int):
    """Возвращает список пользователей, приглашенных указанным юзером."""
    return User.select().where(User.referrer_id == user_id)

@db_connection
def count_user_referrals(user_id: int):
    """Считает количество пользователей, приглашенных указанным юзером."""
    return User.select().where(User.referrer_id == user_id).count()
@db_connection
def set_user_referrer(user_id: int, referrer_id: int):
    """Устанавливает реферера для нового пользователя."""
    query = User.update(referrer_id=referrer_id).where(User.user_id == user_id)
    query.execute()

@db_connection
def add_bonus_days(user_id: int, days: int):
    """Добавляет пользователю бонусные дни."""
    user = get_user(user_id)
    if user:
        # Просто увеличиваем счетчик бонусных дней
        new_bonus_days = user.referral_bonus_days + days
        query = User.update(referral_bonus_days=new_bonus_days).where(User.user_id == user_id)
        query.execute()
@db_connection
def extend_user_subscription(user_id: int, days: int):
    user = get_user(user_id)
    if not user:
        return
    
    # Если подписка активна - продлеваем. Если нет - даем со дня оплаты.
    now = datetime.datetime.now()
    if user.subscription_end_date and user.subscription_end_date > now:
        new_date = user.subscription_end_date + datetime.timedelta(days=days)
    else:
        new_date = now + datetime.timedelta(days=days)
    
    query = User.update(subscription_end_date=new_date).where(User.user_id == user_id)
    query.execute()

@db_connection
def get_active_tariffs():
    """Возвращает список всех активных тарифов."""
    return Tariff.select().where(Tariff.is_active == True)

@db_connection
def get_tariff_by_id(tariff_id: int):
    """Возвращает тариф по его ID."""
    try:
        return Tariff.get(Tariff.id == tariff_id)
    except Tariff.DoesNotExist:
        return None

@db_connection
def set_first_payment_done(user_id: int):
    """Отмечает, что пользователь совершил первую оплату."""
    query = User.update(is_first_payment_made=True).where(User.user_id == user_id)
    query.execute()
@db_connection
def update_user_marzban_username(user_id: int, marzban_username: str):
    """Сохраняет имя пользователя Marzban в нашей базе данных."""
    query = User.update(marzban_username=marzban_username).where(User.user_id == user_id)
    query.execute()