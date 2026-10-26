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
- Deterministic price estimates from eligible reports, with local -> city -> seed fallback
- A `GET /api/v1/prices/estimate` endpoint and a frontend price-check dialog
- A React chat UI with sign-in and persisted history
- Liveness and database-readiness endpoints

Not included yet:

- Verified seed-price entries (the loader and empty configuration file exist)
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

Price estimation is configured with conservative, deliberately unvalidated defaults:

- `PRICE_MIN_OBSERVATIONS` (default `3`) — minimum eligible observations for a report-based level.
- `PRICE_MAX_OBSERVATION_AGE_DAYS` (default `90`) — older reports and seed entries are excluded.
- `PRICE_MAX_OBSERVATIONS` (default `2000`) — bound on reports read per estimate.
- `PRICE_DUPLICATE_WINDOW_MINUTES` (default `15`) — identical reports from one picker inside this
  window count once. Set to `0` to disable the guard.
- `PRICE_SEED_PRICES_PATH` (default `app/data/seed_prices.json`, resolved from `backend/`) — seed
  reference file. It ships empty on purpose. Only add audited entries with `material`,
  `price_per_kg`, `currency`, `unit`, `city` (or null for national), `source`, `collected_at`, and
  optionally `collector`; never use illustrative values as live market data.

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

Prices (requires `Authorization: Bearer <Clerk session token>`):

- `GET /api/v1/prices/estimate?material=plastic&location=Multan&area=Shah%20Rizwan`
  returns a median estimate from eligible reports. `location` is the city and is required for
  report-based evidence; `area` is optional and is used to prefer neighbourhood evidence. The
  service falls back in this order: local (area) reports -> city reports -> city seed prices ->
  national seed prices -> `unavailable`. It never blends two levels. A city-specific seed entry
  is preferred over a national one, and the response's `geographic_scope` says which was used.

The response is stable and includes `estimated_price_per_kg` (or `null`), `currency`, `unit`,
`source` (`local_reports`, `city_reports`, `seed_data`, or `unavailable`), `geographic_scope`,
eligible observation counts, the observed minimum/maximum, freshness, an evidence-quality label,
and explanatory limitations. A request with no trustworthy evidence returns `200` with
`source="unavailable"` and a null price, not `0`.

Example shape:

```json
{
  "material": "plastic",
  "material_label": "Plastic",
  "location": "Multan",
  "area": "Shah Rizwan",
  "currency": "PKR",
  "unit": "kg",
  "estimated_price_per_kg": 150.0,
  "source": "local_reports",
  "geographic_scope": "area",
  "observation_count": 3,
  "local_observation_count": 3,
  "city_observation_count": 3,
  "observed_min_price_per_kg": 130.0,
  "observed_max_price_per_kg": 170.0,
  "oldest_observation_at": "2026-10-23T10:00:00Z",
  "newest_observation_at": "2026-10-24T09:00:00Z",
  "freshness_days": 1.0,
  "evidence_quality": "medium",
  "confidence": 0.65,
  "seed_source": null,
  "seed_collected_at": null,
  "message": "Based on 3 checked picker reports from Shah Rizwan, Multan.",
  "limitations": [
    "The observed range is the range of eligible reports, not a guaranteed market boundary.",
    "Estimates use the median of checked picker reports; flagged or rejected reports are excluded.",
    "This is a picker-reported reference, not a dealer quote or an exchange price.",
    "Identical reports from the same picker within 15 minutes are counted once."
  ],
  "generated_at": "2026-10-25T12:00:00Z"
}
```

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
- Price evidence is thin until enough pickers report. The published seed file is empty, so with
  fewer than the configured minimum observations the API returns `unavailable`, not a guess.
- The anomaly tier checks are neutral placeholders, so every valid report is accepted. Price
  aggregation therefore excludes flagged reports but cannot detect new anomalies.
- Report freshness uses the row's `created_at` (the save time), because the schema has no separate
  market-observation timestamp. The report schema is PKR/kg only; other currencies are excluded
  rather than converted.
- Identical reports are collapsed only inside the configurable short window. The schema has no
  durable idempotency key, so unrelated duplicate submissions outside that window are still
  counted separately.
- Seed `source` strings are returned to clients as provenance. Keep them free of personal
  contact details; the optional `collector` field is internal and is not returned.
