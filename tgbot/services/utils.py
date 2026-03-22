# tgbot/services/utils.py

from urllib.parse import urlparse


def format_traffic(byte_count: int | None) -> str:
    """Красиво форматирует байты в Кб, Мб, Гб."""
    if byte_count is None:
        return "Неизвестно"
    if byte_count == 0:
        return "0 Гб"

    power = 1024
    n = 0
    power_labels = {0: 'Б', 1: 'Кб', 2: 'Мб', 3: 'Гб'}
    while byte_count >= power and n < len(power_labels) - 1:
        byte_count /= power
        n += 1
    return f"{byte_count:.2f} {power_labels.get(n, 'Тб')}"

def decline_word(number: int, titles: list[str]) -> str:
    """
    Правильно склоняет слово после числа.
    Пример: decline_word(5, ['день', 'дня', 'дней']) -> 'дней'
    :param number: Число.
    :param titles: Список из трех вариантов слова (для 1, 2, 5).
    """
    if (number % 10 == 1) and (number % 100 != 11):
        return titles[0]
    elif (number % 10 in [2, 3, 4]) and (number % 100 not in [12, 13, 14]):
        return titles[1]
    else:
        return titles[2]


def get_user_attribute(user_obj, key, default=None):
    """Безопасно получает атрибут из объекта Marzban (словаря или объекта)."""
    if isinstance(user_obj, dict):
        return user_obj.get(key, default)
    return getattr(user_obj, key, default)

def _parse_link(link: str):
    try:
        parsed = urlparse(link)
        host = parsed.hostname or parsed.netloc.split("@")[-1].split(":")[0]
        port = str(parsed.port or parsed.netloc.split(":")[-1])
        return host, port
    except Exception:
        return "unknown", "unknown"
