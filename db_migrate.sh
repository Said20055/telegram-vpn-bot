#!/usr/bin/env bash
# db_migrate.sh — переносит данные с удалённого DB-сервера в локальный Docker postgres
#
# Запускать НА СЕРВЕРЕ С БОТОМ, из корня проекта:
#   ./db_migrate.sh

set -euo pipefail

# ══════════════════════════════════════════════════════════════
#  КОНФИГУРАЦИЯ
# ══════════════════════════════════════════════════════════════

# Удалённая БД (Timeweb)
REMOTE_HOST="256ea584f2a977882757fbe7.twc1.net"
REMOTE_PORT="5432"
REMOTE_USER="gen_user"
REMOTE_PASS='WO.gH<qNI3F170'
REMOTE_DB="default_db"

# Локальная БД (Docker vpn_postgres)
LOCAL_USER="vpn_bot"
LOCAL_PASS="vpn_bot_secret"
LOCAL_DB="vpn_bot"

# ══════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════════"
echo "  DB Migrate: $REMOTE_HOST/$REMOTE_DB → vpn_postgres/$LOCAL_DB"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Проверяем что локальный postgres запущен ─────────────────
if ! docker ps --format '{{.Names}}' | grep -q "^vpn_postgres$"; then
  echo "❌ Контейнер vpn_postgres не запущен."
  echo "   Сначала запустите: docker compose up -d postgres"
  exit 1
fi
echo "✅ Контейнер vpn_postgres найден"

# ── Шаг 1: Дамп с удалённого сервера (postgres:17 клиент) ────
echo ""
echo "1️⃣  Дампирую удалённую БД ($REMOTE_HOST)..."
echo "    postgres:17-alpine клиент (сервер PG17)..."

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

DUMP_SIZE=$(du -sh "$DUMP_FILE" | cut -f1)
DUMP_LINES=$(wc -l < "$DUMP_FILE")
echo "    ✅ Дамп: $DUMP_FILE ($DUMP_SIZE, $DUMP_LINES строк)"

# ── Шаг 2: Пересоздаём локальную БД ─────────────────────────
echo ""
echo "2️⃣  Пересоздаю локальную БД '$LOCAL_DB'..."

# Закрываем активные соединения
docker exec vpn_postgres psql -U "$LOCAL_USER" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$LOCAL_DB' AND pid <> pg_backend_pid();" \
  > /dev/null 2>&1 || true

docker exec vpn_postgres psql -U "$LOCAL_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS \"$LOCAL_DB\";" \
  -c "CREATE DATABASE \"$LOCAL_DB\" OWNER \"$LOCAL_USER\";" \
  > /dev/null

echo "    ✅ БД '$LOCAL_DB' пересоздана"

# ── Шаг 3: Восстановление дампа ──────────────────────────────
echo ""
echo "3️⃣  Восстанавливаю данные..."

docker exec -i vpn_postgres psql -U "$LOCAL_USER" -d "$LOCAL_DB" -q < "$DUMP_FILE"

echo "    ✅ Данные восстановлены"

# ── Шаг 4: Применяем миграции схемы ──────────────────────────
echo ""
echo "4️⃣  Применяю миграции (fix_db.py)..."

docker exec vpn_bot python3 fix_db.py

# ── Шаг 5: Перезапуск сервисов ───────────────────────────────
echo ""
echo "5️⃣  Перезапускаю бот и сайт..."

docker compose restart vpn_bot vpn_site

# ── Итог ──────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ Миграция завершена!"
echo ""
echo "  Дамп сохранён: $DUMP_FILE"
echo ""
echo "  Проверьте логи:"
echo "    docker logs vpn_bot --tail=30"
echo "    docker logs vpn_site --tail=30"
echo "═══════════════════════════════════════════════════════════════"
