"""
Скрипт для массового обновления пользователей Marzban:
 - Устанавливает лимит трафика 1000 ГБ с ежемесячным сбросом
 - Обновляет proxies/inbounds до актуальных (из текущей конфигурации Marzban)

Запуск внутри контейнера:
    docker exec vpn_bot python3 scripts/migrate_users.py

Опционально — задержка между запросами (по умолчанию 0.3 сек):
    docker exec vpn_bot python3 scripts/migrate_users.py --delay 0.5
"""

import asyncio
import sys
import argparse

sys.path.insert(0, ".")

from loader import marzban_client
from marzban.init_client import DATA_LIMIT_BYTES, DATA_LIMIT_RESET_STRATEGY


async def build_proxies_and_inbounds():
    """Строит актуальные proxies и inbounds из конфигурации Marzban."""
    inbounds_raw = await marzban_client.get_inbounds()
    proxies = {}
    inbounds_map = {}
    for protocol, items in inbounds_raw.items():
        if items:
            tags = [item["tag"] if isinstance(item, dict) else item for item in items]
            inbounds_map[protocol] = tags
            proxies[protocol] = {"flow": "xtls-rprx-vision"} if protocol == "vless" else {}
    return proxies, inbounds_map


async def migrate(delay: float):
    print(f"Запуск миграции (задержка между запросами: {delay}с)...")

    # Получаем актуальные inbounds один раз
    proxies, inbounds_map = await build_proxies_and_inbounds()
    if not proxies:
        print("ОШИБКА: нет доступных inbounds в Marzban. Прерываем.")
        return

    print(f"Актуальные протоколы: {list(proxies.keys())}")
    print(f"Inbounds: {inbounds_map}")

    # Получаем список всех пользователей
    data = await marzban_client.get_users(limit=4096)
    users = data.get("users", [])
    total = len(users)
    print(f"Найдено пользователей: {total}")

    updated = skipped = failed = 0

    client = await marzban_client.get_http_client()

    for i, user in enumerate(users, 1):
        username = user.get("username", "")
        current_limit = user.get("data_limit") or 0
        current_strategy = user.get("data_limit_reset_strategy", "")
        current_proxies = set(user.get("proxies", {}).keys())
        target_proxies = set(proxies.keys())

        needs_limit = current_limit == 0 or current_strategy != DATA_LIMIT_RESET_STRATEGY
        needs_proxies = current_proxies != target_proxies

        if not needs_limit and not needs_proxies:
            print(f"[{i}/{total}] {username} — пропущен (всё актуально)")
            skipped += 1
            continue

        body = {}
        if needs_limit:
            body["data_limit"] = DATA_LIMIT_BYTES
            body["data_limit_reset_strategy"] = DATA_LIMIT_RESET_STRATEGY
        if needs_proxies:
            body["proxies"] = proxies
            body["inbounds"] = inbounds_map

        try:
            response = await client.put(f"/api/user/{username.lower()}", json=body)
            response.raise_for_status()
            reasons = []
            if needs_limit:
                reasons.append("лимит")
            if needs_proxies:
                reasons.append("proxies")
            print(f"[{i}/{total}] {username} — обновлён ({', '.join(reasons)})")
            updated += 1
        except Exception as e:
            print(f"[{i}/{total}] {username} — ОШИБКА: {e}")
            failed += 1

        await asyncio.sleep(delay)

    print(f"\nГотово: обновлено={updated}, пропущено={skipped}, ошибок={failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.3, help="Задержка между запросами в секундах")
    args = parser.parse_args()

    asyncio.run(migrate(args.delay))
