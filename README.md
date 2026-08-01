# TraderOS API

TraderOS is a backend-first trading journal API built with FastAPI and PostgreSQL. The current MVP focuses on authentication, ownership-safe trade management, trade filtering, pagination, summary stats, and a clean backend architecture that is easy to inspect and run locally.

## Project Overview

TraderOS is designed as a portfolio-ready backend for recording and reviewing trades through an HTTP API. The implemented scope is intentionally narrow: secure user auth, user-owned trade CRUD, list filtering, paginated trade history, and a summary stats endpoint for reviewing performance.

## Tech Stack

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Pydantic
- Pytest
- Ruff
- Docker Compose
- GitHub Actions

## MVP Features

- JWT authentication with register, login, and current-user endpoints
- Ownership-safe trade CRUD for authenticated users
- Trade listing with symbol, side, and opened date-range filters
- Pagination for trade listing with `limit` and `offset`
- Trade summary stats for the authenticated user
- PostgreSQL persistence with SQLAlchemy models and Alembic migrations
- Host-based and containerized local development workflows
- Docker Compose for local PostgreSQL and API container orchestration
- Ruff, Pytest, and GitHub Actions for code quality and CI

## Architecture Overview

TraderOS uses a straightforward backend layering approach:

- API routes handle HTTP orchestration and response codes.
- Dependencies inject the database session and authenticated user.
- Repositories isolate database queries and persistence logic.
- Services hold business logic where it makes sense, such as trade stats aggregation.
- Schemas define request and response contracts.
- Models define database tables and ORM mappings.
- Alembic manages schema migrations over time.

At a high level, requests enter FastAPI routes, auth and DB dependencies are resolved, repositories interact with PostgreSQL through SQLAlchemy, and schemas shape the JSON returned to clients.

## Host-Based Development Setup

Create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

The project currently defines these environment variables in `.env.example`:

- `APP_NAME`
- `APP_ENV`
- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `UPLOAD_DIR`
- `MAX_UPLOAD_SIZE_MB`

Notes:

- Host-based API development uses `localhost` in `DATABASE_URL`, because PostgreSQL is exposed from Docker Compose to the host on `localhost:5432`.
- `JWT_SECRET_KEY` should be changed from the example value for local development.
- `UPLOAD_DIR` and `MAX_UPLOAD_SIZE_MB` exist in the example file, but screenshot upload endpoints are not part of the currently implemented API surface.
- `.env` must not be copied into the Docker image. Container configuration is supplied at runtime through Docker Compose.

## Host-Based Development Workflow

Start PostgreSQL locally with Docker Compose:

```bash
docker compose up -d db
docker compose ps
```

The database container runs locally through Docker and exposes PostgreSQL on `localhost:5432`.

Run migrations from the host after the database is healthy:

```bash
alembic upgrade head
```

Start the FastAPI development server from the host:

```bash
fastapi dev app/main.py
```

Once the app is running locally, the main URLs are:

- API base: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI schema: `http://127.0.0.1:8000/openapi.json`

Stop the local database container when needed:

```bash
docker compose down
```

## Containerized Development Workflow

Build the API image:

```bash
docker compose build api
```

Start PostgreSQL:

```bash
docker compose up -d db
```

Run migrations explicitly through the API image:

```bash
docker compose run --rm api alembic upgrade head
```

Start the full stack:

```bash
docker compose up -d
```

Check service status:

```bash
docker compose ps
```

Inspect logs:

```bash
docker compose logs api
docker compose logs db
```

Check API liveness:

```bash
curl http://localhost:8000/health
```

Access Swagger:

```text
http://localhost:8000/docs
```

Stop containers:

```bash
docker compose down
```

Remove containers and the PostgreSQL volume:

```bash
docker compose down -v
```

Container workflow notes:

- The API container uses `db` as the PostgreSQL hostname through `DATABASE_URL=postgresql+psycopg://traderos:traderos@db:5432/traderos`.
- Configuration is injected at container runtime by Docker Compose rather than baked into the image.
- `JWT_SECRET_KEY` is passed as a runtime environment value. The Compose fallback is only for local convenience and is not a production-safe secret strategy.
- The `/health` endpoint is used as a process liveness check only. It does not validate PostgreSQL readiness.
- Alembic migrations remain intentionally explicit. The API container does not run migrations automatically on startup.

## Running Linting and Tests

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

## API Overview

Base URL in local development:

```text
http://127.0.0.1:8000
```

Implemented endpoints:

### Health

- `GET /health`

### Auth

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`

### Trades

- `POST /trades`
- `GET /trades`
- `GET /trades/{trade_id}`
- `PATCH /trades/{trade_id}`
- `DELETE /trades/{trade_id}`

### Trade Stats

- `GET /trades/stats/summary`

Protected endpoints require:

```text
Authorization: Bearer <access_token>
```

## Auth Flow Examples

Register a user:

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "trader@example.com",
    "password": "strongpass123"
  }'
```

Log in and receive an access token:

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "trader@example.com",
    "password": "strongpass123"
  }'
```

Get the current authenticated user:

```bash
curl http://127.0.0.1:8000/auth/me \
  -H "Authorization: Bearer <access_token>"
```

## Trades API Examples

Create a trade:

```bash
curl -X POST http://127.0.0.1:8000/trades \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "symbol": "AAPL",
    "side": "long",
    "entry_price": 210.50,
    "exit_price": 214.10,
    "quantity": 10,
    "opened_at": "2026-07-18T09:30:00Z",
    "closed_at": "2026-07-18T11:00:00Z",
    "pnl": 36.00,
    "notes": "Breakout trade during the morning session."
  }'
```

Get a single trade:

```bash
curl http://127.0.0.1:8000/trades/1 \
  -H "Authorization: Bearer <access_token>"
```

Update a trade:

```bash
curl -X PATCH http://127.0.0.1:8000/trades/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "notes": "Updated after post-trade review.",
    "pnl": 40.00
  }'
```

Delete a trade:

```bash
curl -X DELETE http://127.0.0.1:8000/trades/1 \
  -H "Authorization: Bearer <access_token>"
```

## Trade Filters and Pagination Examples

`GET /trades` supports these query parameters:

- `symbol`
- `side`
- `opened_from`
- `opened_to`
- `limit`
- `offset`

List trades with filters and pagination:

```bash
curl "http://127.0.0.1:8000/trades?symbol=AAPL&side=long&opened_from=2026-07-01T00:00:00Z&opened_to=2026-07-31T23:59:59Z&limit=10&offset=0" \
  -H "Authorization: Bearer <access_token>"
```

Examples:

- `symbol=AAPL` filters by exact symbol.
- `side=long` or `side=short` filters by trade direction.
- `opened_from` and `opened_to` filter by `opened_at`.
- `limit` defaults to `20` and is capped at `100`.
- `offset` defaults to `0`.

## Trade Stats Examples

`GET /trades/stats/summary` supports these query parameters:

- `symbol`
- `side`
- `opened_from`
- `opened_to`

Get a stats summary:

```bash
curl "http://127.0.0.1:8000/trades/stats/summary?symbol=AAPL&side=long&opened_from=2026-07-01T00:00:00Z&opened_to=2026-07-31T23:59:59Z" \
  -H "Authorization: Bearer <access_token>"
```

The summary response includes:

- `total_trades`
- `closed_trades`
- `winning_trades`
- `losing_trades`
- `breakeven_trades`
- `total_pnl`
- `average_pnl`
- `win_rate`

## Project Status / MVP Scope

TraderOS is currently an MVP backend. The implemented scope covers:

- user registration, login, and current-user retrieval
- JWT-protected endpoints
- user-owned trade CRUD
- trade filtering by symbol, side, and opened date range
- trade list pagination
- summary stats for the authenticated user
- local PostgreSQL, explicit migrations, linting, tests, CI, and API containerization

This repository does not currently implement a frontend, production-complete deployment, screenshot endpoints, metadata resources, or advanced analytics.

## Future Improvements

Possible next steps after the MVP:

- production deployment and environment hardening
- screenshot upload and file management endpoints
- tags, setups, and richer trade classification
- advanced analytics and richer performance stats
- CSV export and import workflows
- frontend dashboard or client app
- stronger production observability and operational safeguards
