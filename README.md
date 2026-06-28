# TraderOS API

FastAPI + PostgreSQL trading journal API.

## Current status

Project initialization.

## Local database

Start PostgreSQL:

```bash
docker compose up -d db
docker compose ps
docker compose exec db psql -U traderos -d traderos -c "SELECT 1;"
docker compose down
docker compose down -v

## Database migrations

TraderOS uses Alembic for database migrations.

Start PostgreSQL before running migrations:

```bash
docker compose up -d db
alembic upgrade head
alembic current
alembic revision --autogenerate -m "describe change"
docker compose down