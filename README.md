# ScrapSense

ScrapSense is a price-transparency tool for waste pickers. This repository currently
contains the Phase 1 backend foundation: configuration, async PostgreSQL access, an
Alembic migration, health endpoints, and a report-intake workflow skeleton built with
LangGraph and Deep Agents.

## Phase 1 scope

Included:

- FastAPI application with liveness and database-readiness endpoints
- Async SQLAlchemy 2.x engine, session factory, and a `reports` model
- Alembic migration for the initial schema
- A LangGraph report-intake graph with deterministic normalization and validation
- A lazily built Deep Agent extractor that returns a structured `ReportDraft`
- Unit tests with test doubles; no real LLM or database is needed for tests

Not included yet:

- Report submission, review, pricing, or anomaly-detection endpoints
- Authentication or reporter identity verification
- Seed data, forecasting, and material classification
- Frontend integration

## Layout

```
backend/
  app/
    api/                 FastAPI router and health routes
    agents/              Deep Agent construction and structured extraction
    core/                Environment-driven settings
    db/                  SQLAlchemy base and async session factory
    models/              ORM models
    schemas/             Shared Pydantic schemas
    workflows/report_intake/
                         LangGraph state, nodes, and graph
  alembic/               Migration environment and versions
  tests/                 Unit tests
docker-compose.yml       Local PostgreSQL
```

## Setup

Prerequisites: Python 3.12+, uv, and Docker.

```powershell
Copy-Item .env.example .env
docker compose up -d db

Set-Location backend
Copy-Item .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The API is served at `http://127.0.0.1:8000`.

## Configuration

Settings are loaded from `backend/.env` and environment variables. Provider API keys
are not stored in application settings; the LangChain model provider reads its standard
environment variable, such as `OPENAI_API_KEY`.

`AI_MODEL` must use the `provider:model` format, for example
`openai:gpt-4.1-mini` or `anthropic:claude-sonnet-4-6`.

The Docker defaults are development-only. Change `POSTGRES_PASSWORD` and keep
`backend/.env` in sync.

## Endpoints

- `GET /api/v1/health/live` returns process liveness.
- `GET /api/v1/health/ready` runs `SELECT 1` and returns `200` when PostgreSQL is
  reachable or `503` without exposing connection details.

Interactive docs are available at `http://127.0.0.1:8000/docs`.

## Checks

```powershell
Set-Location backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

## Agent safety

The Deep Agent is constructed lazily, so importing the application does not require an
API key. Its harness profile removes filesystem and shell tools and disables the
general-purpose subagent. The graph accepts an injected extractor, which keeps LLM calls
out of unit tests and allows the extraction boundary to be replaced later.
