import datetime
from peewee import (Model, PostgresqlDatabase, BigIntegerField, CharField, DateTimeField,
                    BooleanField, ForeignKeyField, IntegerField, FloatField)

# Исправляем путь импорта в соответствии с вашей структурой проекта
from config import load_config 

# Загружаем конфигурацию
config = load_config()
db_config = config.dataBase

# Подключаемся к PostgreSQL, используя ваши данные из config
db = PostgresqlDatabase(
    db_config.db_name,
    user=db_config.user,
    password=db_config.password,
    host=db_config.host,
    port=db_config.port
)


class BaseModel(Model):
    class Meta:
        database = db

class Tariff(BaseModel):
    id = IntegerField(primary_key=True)
    name = CharField()                     # Например, "1 месяц"
    price = FloatField()                   # Цена в рублях, например, 100.00
    duration_days = IntegerField()         # Срок подписки в днях, например, 30
    is_active = BooleanField(default=True) # Флаг, чтобы можно было временно отключать тариф

    class Meta:
        table_name = "tariffs"
class User(BaseModel):
    user_id = BigIntegerField(primary_key=True)  # Используем BigIntegerField для Telegram ID
    username = CharField(null=True)
    full_name = CharField()
    reg_date = DateTimeField(default=datetime.datetime.now)
    
    # Поля для подписки
    subscription_end_date = DateTimeField(null=True)
    marzban_username = CharField(unique=True, null=True)  # Имя пользователя в Marzban

    # Поля для реферальной системы
    # --- ИСПРАВЛЕНО: Убран backref='referrals' для предотвращения RecursionError ---
    referrer_id = ForeignKeyField('self', null=True, on_delete='SET NULL') 
    
    referral_bonus_days = IntegerField(default=0)
    is_first_payment_made = BooleanField(default=False)

    class Meta:
        # Указываем имя таблицы в нижнем регистре, как принято в PostgreSQL
        table_name = "users" 


def setup_database():
    """Инициализирует базу данных: подключается и создает таблицы, если их нет."""
    try:
        db.connect()
        # Добавляем Tariff в список создаваемых таблиц
        db.create_tables([User, Tariff])
        print("INFO: Database connection successful. Tables User, Tariff created or already exist.")
        
        # --- Первоначальное заполнение тарифов ---
        # Эта функция сработает один раз, если таблица пуста
        if Tariff.select().count() == 0:
            initial_fill_tariffs()

    except Exception as e:
        print(f"ERROR: Database connection failed: {e}")
    finally:
        if not db.is_closed():
            db.close()

def initial_fill_tariffs():
    """Заполняет таблицу тарифов начальными значениями."""
    tariffs_data = [
        {'name': '1 месяц', 'price': 100.0, 'duration_days': 30},
        {'name': '3 месяца', 'price': 250.0, 'duration_days': 90},
        {'name': '1 год', 'price': 900.0, 'duration_days': 365}
    ]
    with db.atomic():
        Tariff.insert(tariffs_data).execute()
    print("INFO: Initial tariffs have been added to the database.")