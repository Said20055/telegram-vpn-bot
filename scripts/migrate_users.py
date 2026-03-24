"""
Скрипт для массового обновления пользователей Marzban:
 - Устанавливает лимит трафика 1000 ГБ с ежемесячным сбросом
 - Обновляет proxies/inbounds до актуальных (из текущей конфигурации Marzban)

Функции:
 - Пагинация: запрашивает пользователей батчами (--batch), не грузит Marzban целиком
 - Сохранение прогресса: при прерывании продолжает с места остановки
 - Возобновление: повторный запуск автоматически пропускает уже обработанных

Запуск внутри контейнера:
    docker exec vpn_bot python3 scripts/migrate_users.py

Параметры:
    --delay   задержка между PUT запросами (сек, default=0.5)
    --batch   размер батча при получении пользователей (default=100)
    --reset   сбросить прогресс и начать заново
"""

import asyncio
import sys
import argparse
import json
import os

sys.path.insert(0, ".")

from loader import marzban_client
from marzban.init_client import DATA_LIMIT_BYTES, DATA_LIMIT_RESET_STRATEGY

PROGRESS_FILE = "/tmp/migrate_users_progress.json"


def load_progress() -> set:
    """Загружает список уже обработанных пользователей."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE) as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_progress(done: set):
    """Сохраняет прогресс на диск."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(list(done), f)


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


async def fetch_all_users(batch_size: int, delay: float) -> list:
    """Получает всех пользователей постранично, чтобы не перегружать Marzban."""
    all_users = []
    offset = 0
    while True:
        print(f"  Загрузка пользователей: offset={offset}...", flush=True)
        data = await marzban_client.get_users(offset=offset, limit=batch_size)
        users = data.get("users", [])
        if not users:
            break
        all_users.extend(users)
        total = data.get("total", 0)
        print(f"  Загружено {len(all_users)}/{total}", flush=True)
        if len(all_users) >= total:
            break
        offset += batch_size
        await asyncio.sleep(delay)
    return all_users


async def migrate(delay: float, batch_size: int, reset: bool):
    if reset and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("Прогресс сброшен.")

    done = load_progress()
    if done:
        print(f"Найден прогресс: уже обработано {len(done)} пользователей. Продолжаем...")

    print(f"Запуск миграции (задержка={delay}с, батч={batch_size})...")

    # Получаем актуальные inbounds один раз
    proxies, inbounds_map = await build_proxies_and_inbounds()
    if not proxies:
        print("ОШИБКА: нет доступных inbounds в Marzban. Прерываем.")
        return

    print(f"Протоколы: {list(proxies.keys())}")
    print(f"Inbounds: {inbounds_map}")

    # Загружаем всех пользователей батчами
    print("Получение списка пользователей...")
    users = await fetch_all_users(batch_size=batch_size, delay=delay)
    total = len(users)
    print(f"Всего пользователей: {total}")

    updated = skipped = failed = already_done = 0
    client = await marzban_client.get_http_client()

    for i, user in enumerate(users, 1):
        username = user.get("username", "")
        if not username:
            continue

        # Пропускаем уже обработанных (resume после разрыва)
        if username in done:
            already_done += 1
            continue

        current_limit = user.get("data_limit") or 0
        current_strategy = user.get("data_limit_reset_strategy", "")
        current_proxies = set(user.get("proxies", {}).keys())
        target_proxies = set(proxies.keys())

        needs_limit = current_limit == 0 or current_strategy != DATA_LIMIT_RESET_STRATEGY
        needs_proxies = current_proxies != target_proxies

        if not needs_limit and not needs_proxies:
            print(f"[{i}/{total}] {username} — пропущен (всё актуально)", flush=True)
            skipped += 1
            done.add(username)
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
            print(f"[{i}/{total}] {username} — обновлён ({', '.join(reasons)})", flush=True)
            updated += 1
            done.add(username)
        except Exception as e:
            print(f"[{i}/{total}] {username} — ОШИБКА: {e}", flush=True)
            failed += 1

        # Сохраняем прогресс каждые 10 пользователей
        if len(done) % 10 == 0:
            save_progress(done)

        await asyncio.sleep(delay)

    save_progress(done)
    print(f"\nГотово: обновлено={updated}, пропущено={skipped}, уже было={already_done}, ошибок={failed}")

    # Если всё успешно — удаляем файл прогресса
    if failed == 0 and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("Файл прогресса удалён.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.5, help="Задержка между запросами в секундах")
    parser.add_argument("--batch", type=int, default=100, help="Размер батча при получении пользователей")
    parser.add_argument("--reset", action="store_true", help="Сбросить прогресс и начать заново")
    args = parser.parse_args()

    asyncio.run(migrate(delay=args.delay, batch_size=args.batch, reset=args.reset))
