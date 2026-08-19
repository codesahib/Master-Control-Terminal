# Master Terminal v1

Finance-first personal console with FastAPI + React/TypeScript + Postgres.

## Features
- RRSP/TFSA/FHSA contribution room tracking
- Manual transaction logging with type-first flow
- One-click full-data JSON export for manual backups before resetting volumes
- Matching JSON backup restore to rebuild data after a reset
- Spreadsheet preview imports for contributions and holdings
- Analytics endpoints for sector/account/platform distributions and trend time series
- Dark-themed dashboard with charts and transaction table
- Docker Compose deployment (`web`, `api`, `db`)

## Run with Docker
### Hosted DB / Supabase
Create `.env` from `.env.example`, then set:
- `DATABASE_URL` for host tools and local backend runs.
- `DATABASE_POOLER_URL` for Docker. Use Supabase's session pooler connection string.

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs
- Hosted DB startup skips migrations; run `alembic upgrade head` explicitly when schema changes.
- Docker starts only `web` and `api`; it does not start local Postgres.

### Local DB
Use the local overlay when you want Docker to start Postgres too:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

- Starts `db`, `api`, and `web`.
- Forces the API to use `postgresql+psycopg://postgres:postgres@db:5432/master_terminal`.
- Runs migrations on startup.

## API Endpoints
- `POST /transactions`
- `GET /transactions`
- `GET /export`
- `POST /import-backup`
- `POST /imports/contributions`
- `POST /imports/holdings`
- `GET /limits/{year}`
- `GET /analytics/distribution?group_by=sector|account|platform`
- `GET /analytics/timeseries`

## Local Dev (optional)
### Backend
```bash
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
# Optional; .env also works.
export DATABASE_URL="postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres\
?sslmode=require"
alembic upgrade head
uvicorn app.main:app --reload
```

### Migrations
```bash
cd backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Tests
```bash
cd backend
pytest
```
