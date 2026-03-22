from urllib.parse import quote_plus

REDIRECT_PAGE_URL = "https://vac-service.ru:8443/import"


def build_import_url(subscription_url: str) -> str:
    """Генерирует URL для импорта подписки в Happ через редирект-страницу."""
    deep_link = build_deeplink(subscription_url)
    return f"{REDIRECT_PAGE_URL}?deeplink={quote_plus(deep_link)}"

def build_deeplink(subscription_url: str) -> str:
    """Преобразует deeplink в URL для импорта."""
    return f"happ://add/{quote_plus(subscription_url)}"
