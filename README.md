# Master Terminal

Personal finance console for RRSP, TFSA and FHSA accounts. FastAPI + SQLAlchemy + Postgres backend, React + TypeScript + Vite frontend.

## Features
- Contribution room per account and tax year: RRSP 60-day deadline, FHSA $8,000 carry-forward cap and $40,000 lifetime limit, TFSA withdrawals added back the next year.
- Transactions: contributions, buys, sells, dividends, reinvestments, transfers, currency exchanges, unit adjustments and withdrawals. Edit and delete, with funding checks and a check that no sale exceeds the units held.
- Holdings and P/L derived from transactions, with live prices (Yahoo Finance) and manual values for GICs and funds.
- Overview: portfolio value history, allocation in CAD, needs-attention list, money in vs invested.
- Light, dark and system themes. Works from 360px phones to wide desktops: sidebar, icon rail or bottom tabs.
- JSON export and restore. The app downloads a fresh export before every restore.

## Run with Docker
Create `.env` from `.env.example`.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Direct Postgres URL, for host tools and local backend runs |
| `DATABASE_POOLER_URL` | Supabase session pooler URL, used by Docker when set |
| `API_TOKEN` | Shared secret. When set, every request except `/health` must send `X-API-Token`. The web container gets it as `VITE_API_TOKEN` |
| `CORS_ORIGINS` | Allowed browser origins, comma separated (default `http://localhost:5173`) |
| `ALLOWED_HOSTS` | Host headers the API accepts, comma separated (default `localhost,127.0.0.1`). Blocks DNS-rebinding pages |
| `API_PORT`, `WEB_PORT`, `DB_PORT` | Host ports (defaults 8000, 5173, 5433). All bind to 127.0.0.1 only |

Without `API_TOKEN`, requests must send `X-Requested-With: master-terminal`. That forces a CORS preflight, so other websites cannot call the API. Set a token anyway.

### Hosted DB (Supabase)
```bash
docker compose up --build -d
```
- Frontend: http://localhost:5173. API docs: http://localhost:8000/docs.
- Startup does not run migrations against a hosted DB. Back up first (`scripts/backup.sh`), then run `alembic upgrade head` yourself.
- Row-level security is enabled on every app table. The `postgres` role owns the tables and bypasses it; the Supabase anon role sees nothing.

### Local DB
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```
Starts `db`, `api` and `web`, points the API at the local Postgres and runs migrations on startup.

### Running the frontend outside Docker
```bash
cd frontend && npm ci && npm run dev
```
If `API_TOKEN` is set, put the same value in `frontend/.env` as `VITE_API_TOKEN`.

## Backups
`scripts/backup.sh` runs `pg_dump` (public schema) in Docker. It writes to `~/Backups/master-control-terminal/<UTC timestamp>/`, keeps the newest 14, and never prints the database URL. The header has a cron line for nightly runs and the restore command.

## Database migrations
```bash
cd backend
alembic upgrade head        # apply
alembic check               # models and migrations must match
```
Tables that exist only in the database (not in the app models) are ignored by `alembic check` and autogenerate.

## API overview
- Reference data: `GET /years`, `GET /platforms`, `GET /symbols/search`, `POST /symbols`
- Contributions: `GET/POST /contributions`, `PUT/DELETE /contributions/{id}`, `GET /available-contributions`
- Account transactions: `GET/POST /account-transactions`, `PUT/DELETE /account-transactions/{id}`, `GET /transactions` (all activity; `page_size` 1-100)
- Room: `GET /limits/{year}`, `GET /limits`, `GET /contribution-limits`, `PUT /contribution-limits/{account}/{tax_year}`
- Portfolio: `GET /holdings`, `GET /portfolio/pl` (`sort_by`), `GET /portfolio/summary`, `GET /portfolio/overview`, `GET /portfolio/health`, `GET /portfolio/history`
- Analytics: `GET /analytics/distribution`, `GET /analytics/timeseries` (CAD)
- Prices and values: `POST /market-prices/refresh` (also stores USD/CAD and today's portfolio snapshot), `POST /manual-valuations`
- Backup: `GET /export`, `POST /import-backup`

## Tests and audits
```bash
cd backend && pip install -r requirements-dev.txt && pytest
```
- CI (`.github/workflows/ci.yml`): pytest, migrations plus `alembic check` on Postgres, frontend build.
- `scripts/audit/smoke_endpoints.py --api URL --token TOKEN [--disposable]`: calls every endpoint. Use `--disposable` only on a throwaway database; it writes.
- `scripts/audit/run_screens.sh WEB_URL`: screenshots and layout checks at 8 widths in light and dark (Playwright in Docker).
- `psql "$DATABASE_URL" -f scripts/audit/db_checks.sql`: integrity checks.
