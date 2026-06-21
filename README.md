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