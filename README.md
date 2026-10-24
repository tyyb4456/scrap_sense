# ScrapSense

ScrapSense is a price-transparency tool for waste pickers. The backend exposes an authenticated
chat endpoint backed by a LangGraph/Deep Agents coordinator, a report-intake subagent, a
price-estimator tool, and PostgreSQL-backed conversation persistence. The frontend is a Clerk
protected React chat UI.

## Current scope

Included:

- Clerk session authentication on the frontend and backend
- A `POST /api/v1/chat` endpoint that talks to the main ScrapSense agent
- Server-owned, per-user chat threads with persisted checkpoints and agent memory in PostgreSQL
- Chat thread creation, listing, history loading, and deletion scoped to the signed-in user
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
    models/              SQLAlchemy models for reports and user-owned chat threads
    schemas/             Chat, price, and report schemas
    services/            Report, chat-thread, and chat-history persistence
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

Settings are loaded from `backend/.env` and environment variables. All LLM calls go through
xKiro, an OpenAI-compatible gateway. Configure it with:

- `XKIRO_API_KEY` — your xKiro key (required; never commit it).
- `XKIRO_BASE_URL` — defaults to `https://api.xkiro.com/v1`.
- `XKIRO_MODEL` — the xKiro model id, for example `mistralai/mistral-large-2512`.

The Docker defaults are development-only. Change `POSTGRES_PASSWORD` and keep `backend/.env` in
sync. The database is required: run `uv run alembic upgrade head` to create the application
tables, and LangGraph creates its checkpoint and store tables on first chat request.

## Endpoints

Health:

- `GET /api/v1/health/live` returns process liveness.
- `GET /api/v1/health/ready` runs `SELECT 1` and returns `200` when PostgreSQL is reachable,
  otherwise `503` without exposing connection details.

Chat (requires `Authorization: Bearer <Clerk session token>`):

- `POST /api/v1/chat` sends one picker message to the main agent. `thread_id` is optional; when it
  is omitted the server creates a new thread and returns its id.
- `GET /api/v1/chat/threads` lists the signed-in user's threads.
- `POST /api/v1/chat/threads` creates a new thread.
- `GET /api/v1/chat/threads/{thread_id}/messages` returns the stored conversation history.
- `DELETE /api/v1/chat/threads/{thread_id}` deletes the thread and its checkpoints.

```json
{
  "message": "aaj maine 2 kilo plastic becha, 300 rupay mila",
  "thread_id": "6f1d0b0e-7d4c-4a71-9d92-0f4f4c2f6a11"
}
```

```json
{
  "user_id": "user_...",
  "thread_id": "6f1d0b0e-7d4c-4a71-9d92-0f4f4c2f6a11",
  "reply": "..."
}
```

The Clerk `sub` claim is the picker id for reports and the namespace for long-term agent memory.
Threads are server-created UUIDs stored against that picker id; every thread endpoint verifies
ownership before reading, appending, or deleting. A client cannot choose another user's identity
or use another user's thread id. The pipeline receives the picker id separately from the thread id,
so a conversation id can never be mistaken for a reporter id.

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
- Chat checkpoints and agent memory are persisted in PostgreSQL. Deleting a thread removes its
  checkpoints, but the user's long-term `/memories/picker_notes.md` memory is shared across that
  user's threads and is not deleted with a single thread.
- The price estimator always returns `0.0` with zero confidence until real seed data exists.
- The anomaly tier checks are neutral placeholders, so every valid report is accepted.
- Reports are stored in PostgreSQL, but price estimation does not use them until market
  aggregation is built.
