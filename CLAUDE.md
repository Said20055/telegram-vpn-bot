# CLAUDE.md
ОБЩАЙСЯ СО МНОЙ НА РУССКОМ
Speek russian!

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Submodule Docs
- **`webapp/CLAUDE.md`** — детальная документация web-dashboard: все маршруты, JWT, шаблоны, CSS/JS паттерны, деплой

## Project Overview

Telegram VPN subscription bot with web dashboard and payment processing. Integrates:
- **Telegram Bot** (aiogram 3.x) — user registration, subscriptions, payments
- **Web Dashboard** (FastAPI) — user portal with email auth
- **Marzban** (v0.8.4) — VPN backend (X-Ray proxy, Shadowsocks/VLESS)
- **YooKassa** — Russian payment gateway
- **PostgreSQL** (16) — user, tariff, promo code, channel data

## Running the Project

```bash
# One-time setup
cp env.dist .env
cp env.marzban.dist .env.marzban
openssl req -x509 -newkey rsa:2048 -nodes -keyout privkey.pem -out fullchain.pem -days 365 -subj "/CN=localhost"

# Build and start all services (Docker)
./refresh.sh    # builds image `vpn_bot`, runs docker compose up

# Development (polling mode, no Docker)
# Set USE_WEBHOOK=False in .env
python3 -m bot

# Web dashboard only
uvicorn webapp.main:app --reload
```

## Environment Variables (`.env`)

Key variables from `env.dist`:

| Variable | Description |
|---|---|
| `BOT_TOKEN` | From @BotFather |
| `ADMIN` | Telegram ID(s) of admins, comma-separated |
| `USE_WEBHOOK` | `False` for dev (polling), `True` for prod |
| `DOMAIN` | Bot webhook domain (must be non-empty, use `localhost` for dev) |
| `SERVER_URL` | Webhook path, e.g. `/webhook` |
| `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY` | Payment credentials |
| `DB_NAME/USER/PASSWORD/HOST/PORT` | PostgreSQL connection (`DB_HOST=postgres` in Docker) |
| `MARZ_HAS_CERTIFICATE` | Enable SSL for Marzban connection |
| `CERT_FULLCHAIN_PATH` / `CERT_KEY_PATH` | Absolute paths to SSL certs (required for Docker volume mounts) |

## Architecture

```
nginx (host: 80 → HTTP, 8443 → HTTPS)
  ├── /yookassa        → vpn_bot (8081)     — Telegram bot + YooKassa webhooks
  ├── /dashboard,/api  → marzban (8002)     — Marzban admin panel (internal)
  ├── /import          → static HTML        — deeplink redirect page
  └── /                → vpn_site (8000)    — FastAPI web dashboard

marzban also binds host:443 directly (bypasses nginx).
All services share PostgreSQL on Docker network.
```

### Data flow

1. User sends Telegram command → `bot.py` dispatcher → `tgbot/handlers/` → `database/requests.py` (SQLAlchemy) → PostgreSQL
2. Payment: bot creates YooKassa payment → YooKassa POSTs webhook to bot port 8081 → `webhook_handlers.py` → subscription extended in Marzban
3. Marzban calls go through `marzban/init_client.py` (`MarzClientCache` — cached httpx client with auto token refresh)
4. Marzban inbounds are detected dynamically via `GET /api/inbounds` — no hardcoded protocol names

### Key files

| File | Role |
|---|---|
| `bot.py` | Entry point — polling vs webhook mode, scheduler start |
| `loader.py` | Initializes bot instance, config, logger, Marzban client (`marzban_client`) |
| `config.py` | Typed config dataclasses loaded from `.env` |
| `db.py` | SQLAlchemy models: `User`, `Tariff`, `PromoCode`, `Channel` |
| `database/requests.py` | All async DB CRUD operations |
| `marzban/init_client.py` | `MarzClientCache` — wraps Marzban API (add/modify/delete users, get inbounds/nodes/stats) |
| `tgbot/handlers/` | Routers split into `user/`, `admin/`, `support.py`, `webhook_handlers.py` |
| `tgbot/services/` | Service layer (subscription, payment, referral, promo, profile, support, user, admin stats) |
| `tgbot/services/scheduler.py` | APScheduler jobs — subscription expiry checks |
| `utils/url.py` | `build_import_url()`, `build_deeplink()` — VPN import link generation (Happ deeplinks via redirect page) |
| `webapp/main.py` | FastAPI app with Jinja2 templates |
| `webapp/routers/` | `auth.py` (JWT login/register), `dashboard.py`, `payment.py` |

### Bot modes

- **Polling** (`USE_WEBHOOK=False`): for local dev, no external domain needed
- **Webhook** (`USE_WEBHOOK=True`): for production, requires `DOMAIN` + SSL

### Admin vs regular users

Admin Telegram IDs are set via `ADMIN` env var. Admins get access to:
- Broadcast to all users
- Manage tariffs, promo codes, channels
- View user statistics

Web dashboard users register separately with email (stored with negative user IDs to avoid collision with Telegram IDs).

## Docker Services

Defined in `docker-compose.yml` (all prefixed `vpn_`):
- `vpn_bot` — main bot container (image: `vpn_bot`, port 8081)
- `vpn_site` — web dashboard container (image: `vpn_bot`, port 8000)
- `marzban` — VPN management panel (container: `vpn_marzban`, ports 443 + 8002 localhost-only)
- `nginx` — reverse proxy (container: `vpn_nginx`, ports 80 + 8443)
- `postgres` — database (container: `vpn_postgres`, port 5432 localhost-only, healthcheck with `pg_isready`)

Logs: `docker logs vpn_bot` / `docker logs vpn_site` / `docker logs vpn_marzban`

### Marzban connectivity

In Docker, bot connects to Marzban at `https://marzban:8002` (service name, not container name). With `USE_WEBHOOK=True`, uses `https://{DOMAIN}/` instead. Marzban API returns inbound objects with `{tag, protocol, network, tls, port}` — extract `tag` strings for user creation requests.

## Refactoring Plan

There is an active refactoring plan at `.claude/plans/shimmying-whistling-mist.md` to restructure the codebase from flat handlers into a layered architecture: Handler → Service → Repository → Database. Service files in `tgbot/services/` are being built out but handlers have not yet been migrated to use them.
