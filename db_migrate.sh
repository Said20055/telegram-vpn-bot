#!/usr/bin/env bash
# db_migrate.sh — переносит данные с удалённого DB-сервера в локальный Docker postgres
#
# Запускать НА СЕРВЕРЕ С БОТОМ (Сервер Б), где лежит проект.
# Скрипт сам читает реквизиты удалённой БД из .env
#
# Использование:
#   ./db_migrate.sh

set -euo pipefail

# ── Читаем .env ──────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  echo "❌ Файл .env не найден. Запустите скрипт из корня проекта."
  exit 1
fi

_parse_env() { grep -E "^${1}=" .env | head -1 | cut -d= -f2- | tr -d "'" | tr -d '"'; }

REMOTE_HOST=$(_parse_env DB_HOST)
REMOTE_PORT=$(_parse_env DB_PORT)
REMOTE_USER=$(_parse_env DB_USER)
REMOTE_PASS=$(_parse_env DB_PASSWORD)
REMOTE_DB=$(_parse_env DB_NAME)
REMOTE_PORT=${REMOTE_PORT:-5432}

if [ -z "$REMOTE_HOST" ] || [ -z "$REMOTE_USER" ] || [ -z "$REMOTE_DB" ]; then
  echo "❌ Не удалось прочитать DB_HOST / DB_USER / DB_NAME из .env"
  exit 1
fi

if [ "$REMOTE_HOST" = "postgres" ] || [ "$REMOTE_HOST" = "localhost" ] || [ "$REMOTE_HOST" = "127.0.0.1" ]; then
  echo "⚠️  DB_HOST в .env уже указывает на локальный сервер ('$REMOTE_HOST')."
  echo "   Миграция не нужна — данные уже здесь."
  exit 0
fi

echo "═══════════════════════════════════════════════════════════════"
echo "  DB Migrate: $REMOTE_HOST:$REMOTE_PORT/$REMOTE_DB → vpn_postgres"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Проверяем что локальный postgres запущен ─────────────────────────────────
if ! docker ps --format '{{.Names}}' | grep -q "^vpn_postgres$"; then
  echo "❌ Контейнер vpn_postgres не запущен."
  echo "   Сначала запустите: docker compose up -d postgres"
  exit 1
fi

echo "✅ Контейнер vpn_postgres найден"

# ── Шаг 1: Дамп с удалённого сервера (через временный postgres:17 контейнер) ──
echo ""
echo "1️⃣  Дампирую удалённую БД ($REMOTE_HOST)..."
echo "    Используем postgres:17 клиент (удалённый сервер — PG17)..."
echo "    Это может занять время..."

DUMP_FILE="/tmp/db_migration_$(date +%Y%m%d_%H%M%S).sql"

docker run --rm \
  -e PGPASSWORD="$REMOTE_PASS" \
  postgres:17-alpine \
  pg_dump \
    -h "$REMOTE_HOST" \
    -p "$REMOTE_PORT" \
    -U "$REMOTE_USER" \
    -d "$REMOTE_DB" \
    --no-owner --no-acl --no-privileges \
  > "$DUMP_FILE"

DUMP_LINES=$(wc -l < "$DUMP_FILE")
DUMP_SIZE=$(du -sh "$DUMP_FILE" | cut -f1)
echo "    ✅ Дамп сохранён: $DUMP_FILE ($DUMP_SIZE, $DUMP_LINES строк)"

# ── Шаг 2: Закрываем соединения и пересоздаём локальную БД ───────────────────
echo ""
echo "2️⃣  Пересоздаю локальную БД..."

docker exec vpn_postgres psql -U "$REMOTE_USER" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$REMOTE_DB' AND pid <> pg_backend_pid();" \
  > /dev/null 2>&1 || true

docker exec vpn_postgres psql -U "$REMOTE_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS \"$REMOTE_DB\";" \
  -c "CREATE DATABASE \"$REMOTE_DB\";" \
  > /dev/null

echo "    ✅ БД '$REMOTE_DB' пересоздана"

# ── Шаг 3: Восстановление ────────────────────────────────────────────────────
echo ""
echo "3️⃣  Восстанавливаю данные в локальный vpn_postgres..."

docker exec -i vpn_postgres psql -U "$REMOTE_USER" -d "$REMOTE_DB" -q < "$DUMP_FILE"

echo "    ✅ Данные восстановлены"

# ── Шаг 4: Обновляем DB_HOST в .env ─────────────────────────────────────────
echo ""
echo "4️⃣  Обновляю DB_HOST в .env: '$REMOTE_HOST' → 'postgres'..."

# Бекап .env
cp .env .env.backup_$(date +%Y%m%d_%H%M%S)

sed -i "s/^DB_HOST=.*/DB_HOST=postgres/" .env

echo "    ✅ DB_HOST=postgres (бекап .env сохранён)"

# ── Шаг 5: Применяем миграции (новые таблицы/колонки) ────────────────────────
echo ""
echo "5️⃣  Применяю миграции схемы (fix_db.py)..."

docker exec vpn_bot python3 fix_db.py

# ── Шаг 6: Перезапуск сервисов с новым .env ──────────────────────────────────
echo ""
echo "6️⃣  Перезапускаю бот и сайт с новым DB_HOST..."

docker compose restart vpn_bot vpn_site

# ── Итог ──────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ Миграция завершена!"
echo ""
echo "  Дамп сохранён в: $DUMP_FILE"
echo "  Бекап .env:      .env.backup_*"
echo ""
echo "  Проверьте логи:"
echo "    docker logs vpn_bot --tail=30"
echo "    docker logs vpn_site --tail=30"
echo "═══════════════════════════════════════════════════════════════"
