# ScrapSense

ScrapSense is a price-transparency tool for waste pickers. The backend exposes an authenticated
chat endpoint backed by a LangGraph/Deep Agents coordinator, a report-intake subagent, a
price-estimator tool, and PostgreSQL-backed conversation persistence. The frontend is a Clerk
protected React chat UI.

## Current scope

Included:

- Clerk session authentication on the frontend and backend
- A `POST /api/v1/chat` endpoint that talks to the main ScrapSense agent
- Per-Clerk-user conversation checkpoints and agent memory stored in PostgreSQL
- A coordinator agent that delegates sale reports to the report-intake subagent
- An LLM extraction step plus deterministic validation in the intake pipeline
- Placeholder anomaly checks (deterministic and ML tiers return neutral verdicts)
- Final reports persisted to the PostgreSQL `reports` table
- A placeholder price-estimator tool
- A React chat UI with sign-in and persisted history
- Liveness and database-readiness endpoints

Not included yet:

- Market-price aggregation from stored reports or a real market data store
- Trained anomaly models, the LLM anomaly tier being enabled by default, or forecasting
- The material classifier CNN
- Reporter reputation or contributor programs

## Layout

```
backend/
  app/
    agents/              Main coordinator agent and intake subagent
    api/routes/          Chat and health routes
    auth/                Clerk request verification and dependencies
    core/                Environment-driven settings
    db/                  SQLAlchemy engine and session factory
    models/              SQLAlchemy models, including finalized reports
    schemas/             Chat, price, and report schemas
    services/            Report persistence
    tools/               Price-estimator tool used by the main agent
    workflows/           Intake/anomaly LangGraph pipeline and state
  alembic/               Migration environment for application tables
  tests/                 Unit and API tests
  run.py                 Dev server runner with a psycopg-compatible event loop
frontend/
  src/
    components/          Chat UI
    lib/                 Typed chat API client and Clerk token helper
docker-compose.yml       Local PostgreSQL
```

## Setup

Prerequisites: Python 3.12+, uv, Node.js 20+, Docker, and a Clerk application.

```powershell
Copy-Item .env.example .env
docker compose up -d db

Set-Location backend
Copy-Item .env.example .env
uv sync
uv run alembic upgrade head
uv run python run.py
```

In a second terminal:

```powershell
Set-Location frontend
Copy-Item .env.example .env
npm install
npm run dev
```

The API is served at `http://127.0.0.1:8000` and the UI at `http://localhost:5173`.

Use `run.py` rather than calling `uvicorn` directly. On Windows, uvicorn's default Proactor
event loop is incompatible with async psycopg, which the Postgres checkpointer uses; `run.py`
selects a compatible loop for every platform.

## Clerk setup

1. Create a Clerk application and enable the sign-in methods you want.
2. Put the publishable key in `frontend/.env` as `VITE_CLERK_PUBLISHABLE_KEY`.
3. Put the secret key in `backend/.env` as `CLERK_SECRET_KEY`.
4. Set `CLERK_AUTHORIZED_PARTIES` and `CORS_ORIGINS` to your frontend origins.
5. Add reviewer Clerk user IDs to `ADMIN_USER_IDS` (JSON array) when reviewer features return.

`CLERK_JWT_KEY` is optional. Set it instead of relying on network calls for JWT verification; if
either a secret key or JWT key is configured, Clerk verification is enabled. Chat returns `401`
without a valid bearer token and `503` when no Clerk credential is configured.

## Configuration

Settings are loaded from `backend/.env` and environment variables. Provider API keys are not
stored in application settings; the LangChain model provider reads its standard environment
variable, such as `OPENAI_API_KEY`.

`AI_MODEL` must use the `provider:model` format, for example `openai:gpt-4.1-mini` or
`anthropic:claude-sonnet-4-6`.

The Docker defaults are development-only. Change `POSTGRES_PASSWORD` and keep `backend/.env` in
sync. The database is required: run `uv run alembic upgrade head` to create the application
tables, and LangGraph creates its checkpoint and store tables on first chat request.

## Endpoints

Health:

- `GET /api/v1/health/live` returns process liveness.
- `GET /api/v1/health/ready` runs `SELECT 1` and returns `200` when PostgreSQL is reachable,
  otherwise `503` without exposing connection details.

Chat (requires `Authorization: Bearer <Clerk session token>`):

- `POST /api/v1/chat` sends one picker message to the main agent.

```json
{
  "message": "aaj maine 2 kilo plastic becha, 300 rupay mila"
}
```

```json
{
  "user_id": "user_...",
  "reply": "..."
}
```

The Clerk `sub` claim is the agent's picker id and conversation thread id, so each signed-in user
has isolated history and memory. The client cannot choose another user's identity.

Interactive docs are available at `http://127.0.0.1:8000/docs`.

## Checks

```powershell
Set-Location backend
uv run pytest
uv run ruff check .
uv run mypy app tests

Set-Location ../frontend
npm run lint
npm run build
```

## Known limitations

- Submitted raw text is sent to the configured model provider.
- Chat checkpoints and agent memory are persisted in PostgreSQL, but there is no user-facing
  deletion endpoint yet.
- The price estimator always returns `0.0` with zero confidence until real seed data exists.
- The anomaly tier checks are neutral placeholders, so every valid report is accepted.
- Reports are stored in PostgreSQL, but price estimation does not use them until market
  aggregation is built.
