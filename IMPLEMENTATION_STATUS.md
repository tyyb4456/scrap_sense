# ScrapSense — Implementation Status Audit

- **Audit date:** 2026-10-29
- **Spec source of truth:** `ScrapSense_Project_Overview.md` (supported by `README.md` and `PRODUCT.md`)
- **Scope:** entire repository, excluding `node_modules`, `.venv`, `__pycache__`, `.git`, build output, caches, and agent-tooling directories
- **Mode:** read-only code inspection plus verification runs. No application source was modified by this audit; this document was rewritten to replace the stale 2026-10-25 snapshot.

---

## 1. Executive Summary

### Overall completion estimate

**≈60–65% of the full overview.** The central product loop now exists end to end: a picker reports a sale through chat, the report is extracted, deterministically validated, compared against comparable reports, persisted, and then used by a deterministic local → city → seed price estimator exposed through an authenticated API and a frontend price-check dialog. A reviewer queue and approve/reject flow close the trust loop.

The remaining work is concentrated in the secondary/advanced scope: verified seed prices, the Tier 2 ML model, voice/camera capture, the material classifier, forecasting, and operational hardening (retention, rate limiting, CI, containers). The core loop is no longer the gap.

### Top strengths

1. **The core price chain is real.** `backend/app/services/prices.py`, `backend/app/services/price_aggregation.py`, `GET /api/v1/prices/estimate`, the `estimate_price` chat tool, and the frontend `PriceCheck` dialog all use the same deterministic rules. Reports are actually read back and aggregated.
2. **Trust precedes aggregation.** Deterministic validation (`app/services/report_validation.py`), a conservative median/MAD Tier 1 (`app/services/anomaly_detection.py`), persisted `flagged` reports, and a reviewer-only approve/reject flow all exist. Only accepted, non-anomalous reports influence prices.
3. **Authentication and per-picker isolation are tested.** Clerk bearer verification, the `sub` claim as picker id, server-owned threads, and ownership checks are implemented and covered by API tests.
4. **The test suite is substantial and green.** 134 backend tests pass, including 12 tests that use the real PostgreSQL database for price aggregation and report review. `ruff`, `mypy`, the frontend lint, and the production build all run.
5. **The documentation is unusually honest.** Missing seed data, the disabled ML tier, the default-off LLM tier, and privacy gaps are stated rather than hidden.

### Top gaps / risks

1. **No verified seed data.** `backend/app/data/seed_prices.json` exists and is intentionally empty. With too few reports, the API correctly returns `unavailable`; there is still no defensible cold-start reference.
2. **Tier 2 ML is an interface, not a model.** `app/services/ml_anomaly.py` defines the readiness gate and a disabled/unavailable verdict. There is no Isolation Forest, no trained artifact, and no training script.
3. **No voice, camera, classifier, or forecasting.** The product remains a text chat plus a structured price form. No audio capture/transcription, image upload, CNN, TFLite/ONNX export, or time-series model exists.
4. **Multi-turn clarification is not resolved.** Extraction reads only the last message and does not merge an earlier draft with a follow-up answer.
5. **Provenance is weaker than documented.** The isolated compiled subagent receives the coordinator's task description, so the persisted `raw_text` may be a paraphrase rather than the picker's verbatim message.
6. **Operational hardening is missing.** No retention policy, memory deletion, rate limiting, idempotency key, CI, or application Dockerfiles. The live LLM path is not exercised by the suite.
7. **Minor debt remains.** Some unused report schemas, a duplicate/misspelled `requirements.txt`, a stale `llm.py` docstring, and three non-blocking frontend lint warnings.

### Bottom line

This is now a credible **working price-transparency MVP**, not just a chat shell. The next milestone should turn the empty seed file into audited field data and make the trust layer robust; polishing the chat UI further will not close the remaining product gap.

---

## 2. Repo Structure

```text
D:\scrap_sense\
├── ScrapSense_Project_Overview.md   Problem framing, architecture, models, data strategy, stack, timeline, built/gap list.
├── README.md                        Setup, configuration, endpoints, trust policy, checks, known limitations.
├── PRODUCT.md                       Product brief: users, positioning, constraints, principles.
├── IMPLEMENTATION_STATUS.md         This audit.
├── docker-compose.yml               Local PostgreSQL 17 only. No backend/frontend app containers.
├── .env.example                     Postgres compose variables only.
├── .gitignore                       Ignores .env, .venv, node_modules, caches, logs, agent-tooling dirs.
├── skills-lock.json                 Agent-skill lock file (not product code).
│
├── backend\
│   ├── pyproject.toml               Python >=3.12, FastAPI, LangGraph, deepagents, SQLAlchemy, Clerk, xKiro, scikit-learn.
│   ├── requirements.txt             Unpinned duplicate dependency list; contains a typo (`sciket-learn`).
│   ├── uv.lock                      Resolved dependency lock.
│   ├── .env.example                 DB, xKiro, Clerk, CORS, admin IDs, anomaly/price settings.
│   ├── .env                         Local secrets, gitignored (not tracked).
│   ├── alembic.ini                  Alembic config; URL overridden in env.py from settings.
│   ├── alembic\versions\
│   │   ├── 0001_create_final_reports.py
│   │   ├── 0002_create_chat_threads.py
│   │   └── 0003_add_anomaly_review_fields.py   observed_at, reviewed_at, reviewed_by.
│   ├── app\
│   │   ├── main.py                  FastAPI app factory, CORS, lifespan closing agent pool/engine.
│   │   ├── llm.py                   xKiro-backed ChatOpenAI factory; stale "KapraOS" docstring.
│   │   ├── loops.py                 Selector event-loop factory used by the documented Windows dev command.
│   │   ├── agents\
│   │   │   ├── main_agent.py        Deep Agents coordinator, per-picker memory, price tool.
│   │   │   └── report_intaker.py    CompiledSubAgent wrapping the report pipeline.
│   │   ├── api\routes\
│   │   │   ├── chat.py              POST /chat + thread CRUD/history/delete; Clerk-protected.
│   │   │   ├── health.py            GET /health/live and /health/ready.
│   │   │   ├── prices.py            GET /prices/estimate; Clerk-protected.
│   │   │   └── reports.py           Reviewer queue, detail, and PATCH review; admin-only.
│   │   ├── auth\dependencies.py     Clerk bearer verification; require_auth and require_admin.
│   │   ├── core\config.py           Pydantic settings for DB, xKiro, Clerk, anomaly, price.
│   │   ├── data\seed_prices.json    Seed-price file, schema v1, intentionally empty.
│   │   ├── db\                       Declarative Base, async engine/session factory.
│   │   ├── models\                   Report and chat_thread ORM models.
│   │   ├── schemas\                  Chat, price, seed-file, report/review, anomaly schemas.
│   │   ├── services\
│   │   │   ├── anomaly_detection.py  Tier 1 median/MAD + DB-backed comparable-report query.
│   │   │   ├── ml_anomaly.py         Tier 2 readiness gate and disabled/unavailable verdict.
│   │   │   ├── report_validation.py  Deterministic intake validation and clarification text.
│   │   │   ├── materials.py          Explicit material aliases and normalization.
│   │   │   ├── price_aggregation.py  Pure aggregation, dedupe, eligibility, fallback chain.
│   │   │   ├── prices.py             DB-backed PriceService and seed-file loader.
│   │   │   ├── reports.py            Persist, read for pricing, queue, and review decisions.
│   │   │   ├── chat_threads.py       ChatThreadStore: create/list/get/touch/delete.
│   │   │   └── chat_history.py       Load human/assistant turns from graph state.
│   │   ├── tools\price_estimator.py  Chat tool backed by PriceService.
│   │   └── workflows\
│   │       ├── pipeline.py           Intake + validation + anomaly tiers + persistence graph.
│   │       └── state.py              PipelineState.
│   └── tests\                        194 tests across 20 files, including real PostgreSQL integration.
│
├── frontend\
│   ├── package.json                 React 19, TS, Vite 8, Clerk, Tailwind 4, oxlint. No test script.
│   ├── vite.config.ts               React + Tailwind plugins.
│   ├── .env.example                 API base URL + Clerk publishable key.
│   ├── .env                         Local frontend env, gitignored (not tracked).
│   ├── src\
│   │   ├── main.tsx                 ClerkProvider or setup screen; mounts App.
│   │   ├── App.tsx                  Landing, Clerk gate, demo/landing/review modes, sample ledger.
│   │   ├── components\
│   │   │   ├── Chat.tsx             Live chat state + demo chat with hardcoded synthetic history.
│   │   │   ├── ThemeToggle.tsx      Light/dark toggle.
│   │   │   ├── chat\                Chat shell, markdown, price-check dialog, format, icons, types.
│   │   │   └── review\ReviewQueue.tsx  Reviewer queue UI with pagination and confirmation dialog.
│   │   ├── lib\                     Typed API client, Clerk token helper, demo mode, theme.
│   │   └── index.css                Tailwind theme, claymorphism design tokens.
│   └── dev.log / dev.err.log        Local dev-server artifacts, gitignored.
│
└── MISSING (documented or expected but absent):
    ├── verified seed-price entries
    ├── backend/app/ml/ or classifier module
    ├── trained model artifacts (CNN / Isolation Forest / forecasting)
    ├── training, export, or demo-data seeding scripts
    ├── voice/audio capture and transcription
    ├── backend/frontend Dockerfiles
    └── CI configuration (.github/workflows or equivalent)
```

---

## 3. Architecture as Actually Built

### 3.1 Sale-report flow

1. **Browser (React + Clerk).** `frontend/src/lib/useAccessToken.ts` obtains a session token; `frontend/src/lib/api.ts` sends JSON to `VITE_API_BASE_URL`.
2. **FastAPI entry.** `backend/app/main.py` creates the app, applies CORS, and mounts `/api/v1`. Chat, price, and review routes depend on Clerk auth.
3. **Thread selection.** `POST /api/v1/chat` creates a server-owned `chat_threads` row or verifies ownership of the supplied thread (`app/api/routes/chat.py`).
4. **Agent invocation.** The route invokes the lazily built Deep Agents coordinator with `thread_id` and `picker_id` in config and `AgentContext(picker_id=...)`. The coordinator is built in `app/agents/main_agent.py` with an xKiro model, the `scrap_report_pipeline` compiled subagent, the `estimate_price` tool, `AsyncPostgresSaver` checkpoints, `AsyncPostgresStore` memory, and a per-picker `/memories/` namespace.
5. **Routing.** Routing is prompt-driven, not deterministic. The system prompt tells the LLM to delegate sale reports to the subagent and to call `estimate_price` for value questions.
6. **Report pipeline.** `app/workflows/pipeline.py` runs `report_draft` (LLM structured extraction) → `validate_and_build` (deterministic validation, clarification on failure) → `deterministic_check` (median/MAD Tier 1 against comparable PostgreSQL rows) → `ml_check` (explicitly disabled Tier 2) → optional `llm_check` (only when `USE_LLM_REASONING=true` and a lower tier already flagged the report) → `accept` → `finalize_report`.
7. **Persistence.** `save_report()` validates again and inserts a `reports` row with `picker_id`, extracted fields, the anomaly verdict, and status `accepted` or `flagged`.
8. **Response.** `POST /api/v1/chat` extracts the last non-empty assistant text and returns `{user_id, thread_id, reply}`. There is no streaming/SSE.

### 3.2 Price-check flow

1. The picker opens the price-check dialog from the chat empty state (`PriceCheck.tsx`) or asks the chat agent a value question.
2. The dialog calls `GET /api/v1/prices/estimate?material=&location=&area=` with a Clerk token; the chat path calls the `estimate_price` tool.
3. Both use `PriceService.estimate()` → `fetch_reports_for_pricing()` → `evaluate_price()`.
4. The estimator filters to accepted, non-anomalous, PKR/kg reports in the requested city, applies duplicate suppression, prefers area evidence when the threshold is met, then city evidence, then city seed prices, then national seed prices, then `unavailable`. Sources are never blended.
5. The response includes the median, observed range, counts, freshness, evidence quality, confidence, provenance, limitations, and an explanatory message. No evidence returns `200` with a null price, never `0`.

### 3.3 Reviewer flow

1. Flagged reports are persisted and excluded from aggregation.
2. A Clerk user whose `sub` is in `ADMIN_USER_IDS` opens `/review`.
3. The UI calls `GET /api/v1/reports?status=flagged&page=&page_size=` (oldest first, stable id tie-breaker).
4. `PATCH /api/v1/reports/{id}/review` with `accepted` or `rejected` applies a locked transition. Only a `flagged` report can be decided; repeats or already-decided reports return `409`.
5. Approval clears the active anomaly flag but does not bypass any other eligibility rule (currency, age, duplicate suppression, etc.). Rejection keeps the row for audit and excludes it permanently.

### 3.4 What is absent from the data flow

- **No voice path.** No audio capture, transcription, or voice endpoint.
- **No photo/classifier path.** The chat schema accepts text only; there is no image upload or classifier module.
- **No forecasting path.** No time-series model or trend logic.
- **No offline mode.** The app requires PostgreSQL, Clerk, and a live LLM provider for normal use.
- **No Tier 2 model.** The graph node and readiness gate exist, but no model is trained or loaded.
- **No retention/memory deletion.** Thread deletion removes checkpoints; long-term picker memory remains.

---

## 4. Checklist Against the Overview

Statuses are exactly one of **DONE**, **PARTIAL**, **NOT STARTED**, or **DIVERGED**.

### A. Product flow and agents

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| A1 | Free-text sale report → structured, validated data | **DONE** | `workflows/pipeline.py`; `services/report_validation.py`; `tests/test_pipeline.py`, `tests/test_report_validation.py` | Live LLM provider not exercised by the suite; tests use fake models. |
| A2 | Flag uncertainty instead of guessing | **DONE** | `validate_and_build`, `clarification_question`; tests | Missing/unsupported fields produce one clarification question and no persistence. |
| A3 | Resolve a flagged report across subsequent turns | **PARTIAL** | `report_draft` reads only `messages[-1]`; no draft merge | A follow-up that only supplies a missing field may fail validation again. Untested live. |
| A4 | Voice / transcribed voice input (Urdu) | **NOT STARTED** | No audio/transcription code; composer is a textarea | No provider or endpoint. |
| A5 | Material classifier agent from a photo | **NOT STARTED** | No classifier module, image schema, UI, or torch/onnx/tflite dependency | Matches the overview's own admission. |
| A6 | Orchestrator routes report vs. price requests | **PARTIAL** | `main_agent.py` prompt and wiring | Prompt-driven only; no deterministic router and no routing test. |
| A7 | Orchestrator offline data-gap reasoning loop | **NOT STARTED** | No scheduler or gap-analysis loop | Overview explicitly calls this future work. |
| A8 | Anomaly Tier 1: deterministic price vs. recent median | **DONE** | `services/anomaly_detection.py`; 16 tests in `test_anomaly_detection.py` | Median/MAD over accepted, comparable, recent reports; area preferred when sample allows. |
| A9 | Anomaly Tier 2: Isolation Forest price+quantity | **PARTIAL** | `services/ml_anomaly.py` readiness gate and disabled verdict | Interface only; no model, training script, or artifact. |
| A10 | Anomaly Tier 3: LLM judge only for flagged reports | **DONE** | `pipeline.py` `llm_check_node`, `route_after_ml`; tests | Reachable when `USE_LLM_REASONING=true` and a lower tier flagged; cannot clear the flag or override validation; failures retain it. |
| A11 | Trust verdict gates report/price influence | **DONE** | `services/reports.py`, `services/price_aggregation.py`, reviewer routes | `flagged`/`rejected` reports are excluded; approval restores eligibility only if other rules pass. |
| A12 | Price estimator fallback chain: local → city → seed → unavailable | **DONE** | `services/price_aggregation.py`; `tests/test_price_aggregation.py` | Sources are never blended. |
| A13 | Aggregate trustworthy reports into price references | **DONE** | `fetch_reports_for_pricing`, `PriceService`, price API/UI | Deterministic median with counts, range, freshness, and evidence quality. |
| A14 | Reporter-trust agent (considered future upgrade) | **NOT STARTED** | No code | Correctly out of scope for now. |
| A15 | Forecasting model (RNN/LSTM) | **NOT STARTED** | No model/dependency | No time-series data logic. |
| A16 | Shared data store for report and price paths | **DONE** | PostgreSQL reports read by `PriceService` | The two paths now converge functionally. |
| A17 | Two request types: "I sold this" vs. "what's this worth?" | **PARTIAL** | Prompt + `estimate_price` tool + price dialog | Text price questions work; photo price questions have no path. |

### B. Models and data strategy

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| B1 | CNN (MobileNetV2 / EfficientNet-Lite), fine-tune, export TFLite/ONNX | **NOT STARTED** | No classifier code, dataset, notebook, or model artifact; no torch dependency | Nothing to verify. |
| B2 | Trained Isolation Forest model (~50+ reports, dormant until meaningful) | **PARTIAL** | `services/ml_anomaly.py` readiness rule; `ANOMALY_ML_*` settings | The dormant interface exists; no model or artifact. |
| B3 | RNN/LSTM forecasting model | **NOT STARTED** | No model/dependency | Overview says not built. |
| B4 | `app/data/seed_prices.json` with source, date, collector, price | **PARTIAL** | File, schema, and loader exist; `entries` is empty | Correctly refuses to invent values. |
| B5 | Week-1 manual seed-price collection | **NOT STARTED** | No data or field notes in repo | Cannot verify externally. |
| B6 | Crowd-report dataset accumulation | **PARTIAL** | Reports persist with dedupe-at-read and review status | No ingestion volume or durable idempotency. |
| B7 | Cold-start/demo data seeding, clearly synthetic | **PARTIAL** | Frontend demo threads and sample ledger labeled "Illustration only" | Frontend-only fixtures; no backend seeder. |
| B8 | Location at neighborhood/city level only; never precise GPS | **PARTIAL** | `reports.city`/`reports.area`; no GPS fields | Raw text can still contain a precise address; `area` is free text with no granularity validation. |
| B9 | Reporter identity anonymized; no name/phone plaintext | **DONE** | `picker_id` from Clerk `sub`; no name/phone columns; auth tests | Raw message text may contain PII (separate gap). |
| B10 | Dealer-referencing data only as anonymized aggregates | **PARTIAL** | No dealer model or publication path; prices are aggregates only | Nothing named is published, but there is no dedicated protection mechanism. |
| B11 | Retention policy | **NOT STARTED** | No cleanup job/config | Acknowledged in overview and README. |
| B12 | Memory deletion | **NOT STARTED** | Thread deletion removes checkpoints only | `/memories/picker_notes.md` survives thread deletion. |
| B13 | Encryption at rest | **NOT STARTED** | No encryption config/policy | Acknowledged in overview. |

### C. Tech stack and platform

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| C1 | FastAPI backend, Python 3.11+ | **DONE** | `pyproject.toml`; `app/main.py` | Actually requires Python >=3.12; docs and code now agree on 3.12. |
| C2 | LangGraph orchestration | **DONE** | `workflows/pipeline.py`; Deep Agents on LangGraph | Uses `deepagents` as an extra layer not named in the overview. |
| C3 | PyTorch for CNN | **NOT STARTED** | Absent from dependencies | No ML training environment. |
| C4 | scikit-learn for Isolation Forest | **PARTIAL** | `scikit-learn` is a declared dependency | No model, training script, or artifact uses it yet. |
| C5 | React + TypeScript + Vite frontend | **DONE** | `frontend/package.json`; build passes | React 19, Vite 8, Tailwind 4. |
| C6 | Clerk-authenticated chat UI | **DONE** | `main.tsx`, `App.tsx`, `useAccessToken.ts`; backend auth tests | Live Clerk flow not exercised in this audit. |
| C7 | Voice-first UI | **NOT STARTED** | No mic/audio UI | Text composer only. |
| C8 | PostgreSQL-backed LangGraph checkpoints | **DONE** | `main_agent.py`; live DB tables | Created by the saver on first use. |
| C9 | PostgreSQL long-term store / memory | **DONE** | `main_agent.py`; live `store` table | No deletion path. |
| C10 | Finalized report rows in PostgreSQL | **DONE** | `models/report.py`; `services/reports.py`; migration `0001` | Integration tests cover real persistence. |
| C11 | Structured seed prices + market aggregation wired | **DONE** | Seed loader + `evaluate_price` + `PriceService` | The file is empty, so seed fallback is configured but unused. |
| C12 | Docker/deploy files | **PARTIAL** | `docker-compose.yml` (Postgres only) | No app Dockerfiles, CI, or production server config. |
| C13 | Seeder scripts | **NOT STARTED** | No scripts directory | Frontend demo fixtures are not a seeder. |

### D. Build timeline / milestones

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| D1 | Week 1: seed data + report intake + simple baseline estimator | **PARTIAL** | Intake and estimator done; seed data missing | 2 of 3 delivered. |
| D2 | Week 2: all three anomaly tiers + orchestrator reasoning loop + real estimator | **PARTIAL** | Tier 1 and Tier 3 done; Tier 2 interface; estimator real | No orchestrator offline reasoning loop; Tier 2 has no model. |
| D3 | Week 3: CNN + offline export + Urdu voice + field testing | **NOT STARTED** | No CNN, export, audio, or field-test evidence | No dataset or model. |
| D4 | Week 4: field feedback, polish, demo video, documentation | **PARTIAL** | Frontend polish and docs; no field feedback or demo video | Documentation is relatively good; field validation is absent. |

### E. API, schemas, and tables

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| E1 | `POST /api/v1/chat` | **DONE** | `chat.py`; 12 chat API tests | Agent is faked in tests; live agent path untested. |
| E2 | `POST /api/v1/chat/threads` | **DONE** | `chat.py`; test | Returns 201 with default title. |
| E3 | `GET /api/v1/chat/threads` | **DONE** | `chat.py`; test | No pagination. |
| E4 | `GET /api/v1/chat/threads/{thread_id}/messages` | **DONE** | `chat.py`; test | Uses `agent.aget_state()`; faked in tests. |
| E5 | `DELETE /api/v1/chat/threads/{thread_id}` | **DONE** | `chat.py`; test | Checkpointer faked in tests. |
| E6 | `GET /api/v1/health/live` | **DONE** | `health.py`; test | — |
| E7 | `GET /api/v1/health/ready` | **DONE** | `health.py`; tests | Checks DB only, not agent/LLM. |
| E8 | Report submission/list/review endpoints | **PARTIAL** | `api/routes/reports.py` | Reviewer list/detail/review exist; there is no separate picker-facing report submission endpoint (reports enter through chat). |
| E9 | SSE / streaming responses | **NOT STARTED** | No streaming code in backend/frontend | Not in the overview; noted for completeness. |
| E10 | `reports` table + migrations | **DONE** | `models/report.py`; migrations `0001`, `0003` | Includes `observed_at`, `reviewed_at`, `reviewed_by`. |
| E11 | `chat_threads` table + migration | **DONE** | `models/chat_thread.py`; migration `0002` | No foreign keys. |
| E12 | LangGraph checkpoint/store tables | **DONE** | `main_agent.py`; live DB | Created by savers on first use. |
| E13 | Report Pydantic schemas | **DONE** | `schemas/report.py` | Includes draft, verdict, final report, judgment, queue/review schemas. |
| E14 | Chat Pydantic schemas | **DONE** | `schemas/chat.py` | Length limits present. |
| E15 | Report read/status/submission schemas | **PARTIAL** | `ReportCreate`, `ReportStatusUpdate`, `ReportRead`, `ReportSubmissionResponse` | Dead code; no route uses them. `ReportRead` expects fields the model does not have. |
| E16 | Reviewer/role separation | **DONE** | `require_admin`, `ADMIN_USER_IDS`, `routes/reports.py` | Enforced server-side; frontend only renders 401/403 states. |
| E17 | Per-picker long-term memory namespace | **DONE** | `main_agent.py` | No deletion path. |
| E18 | Thread deletion removes checkpoints | **DONE** | `chat.py`; test | Does not delete reports (intended) or memory. |
| E19 | Honest documentation of gaps | **DONE** | Overview, README, PRODUCT, this audit | Docs now match the implemented price/anomaly/review scope. |
| E20 | `GET /api/v1/prices/estimate` | **DONE** | `routes/prices.py`; `tests/test_prices_api.py` | Auth required; 422 for invalid query; 503 on DB failure. |
| E21 | Reviewer queue UI at `/review` | **DONE** | `frontend/src/components/review/ReviewQueue.tsx`; `App.tsx` | Loading, empty, access-denied, error states; confirmation dialog; pagination. |

### F. Quality gates and verification

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| F1 | Backend test suite | **DONE** | `uv run pytest -o addopts="" --tb=short`: **134 passed** | See §8. |
| F2 | Backend lint | **DONE** | `uv run ruff check .`: all checks passed | Previously red; now green. |
| F3 | Backend typecheck | **DONE** | `uv run mypy app tests`: success, 62 source files | — |
| F4 | Frontend build | **DONE** | `npm run build`: `tsc -b && vite build` succeeded | 97 modules transformed. |
| F5 | Frontend lint | **PARTIAL** | `npm run lint`: 0 errors, 3 warnings (`react/set-state-in-effect`) | Non-blocking; worth cleaning before adding tests. |
| F6 | Frontend tests | **NOT STARTED** | No test script or test files | No component, hook, or e2e coverage. |
| F7 | Integration tests against real PostgreSQL | **DONE** | `tests/test_price_integration.py` (5), `tests/test_report_review_integration.py` (7) | Use the configured real database, skip if unavailable, roll back or delete their own rows. |
| F8 | CI pipeline | **NOT STARTED** | No `.github` or other CI config | Quality gates are manual. |
| F9 | README/setup accuracy | **DONE** | README documents the uvicorn `--loop app.loops:selector_loop_factory` command | The deleted `run.py` is no longer referenced; `loops.py` is used. |
| F10 | Live model/agent end-to-end verification | **PARTIAL** | Keys exist in ignored local `backend/.env`; no live LLM call made in this audit | Provider/auth behavior cannot be claimed without exercising it. |

---

## 5. Per-Component Deep Dive

### 5.1 Coordinator / main agent

- **Purpose:** Picker-facing conversational coordinator.
- **Inputs:** Chat message + `thread_id` + `picker_id`; Clerk-authenticated.
- **Outputs:** Assistant reply text; side effects in `reports`, checkpoints, and long-term memory.
- **Key code:** `SYSTEM_PROMPT`, `AgentContext`, `build_agent`, `aget_agent`, `aget_checkpointer`, `aclose_agent` in `app/agents/main_agent.py`.
- **Wiring:** `create_deep_agent` with `subagents=[scrap_pipeline_agent]`, `tools=[estimate_price]`, `context_schema=AgentContext`, Postgres checkpointer/store, and `CompositeBackend` routing `/memories/` to a per-picker namespace.
- **Status:** coordinator exists and is wired; routing is prompt-only and untested. No offline reasoning loop.

### 5.2 Report-intake subagent and pipeline

- **Purpose:** Turn one sale message into a validated report and anomaly verdict.
- **Inputs:** A single `HumanMessage` containing the coordinator's task description.
- **Outputs:** `ReportDraft`, validation result, anomaly verdicts, `FinalReport`, persisted `reports` row, clarification/acceptance message.
- **Key code:** `report_intaker.py`; `pipeline.py` extraction, validation routing, anomaly nodes, accept/finalize, graph wiring.
- **Validation:** `services/report_validation.py` rejects missing fields, unsupported materials/currencies/units, non-finite or non-positive values, inconsistent location fields, and implausible future timestamps before any anomaly tier.
- **Notable risk:** The isolated compiled subagent receives the parent's generated `description`, not necessarily the original user message. The pipeline saves the first HumanMessage as `raw_text`, so provenance is weaker than the documentation implies.
- **Notable risk:** Multi-turn clarification has no merge logic. `report_draft` reads only the last message.

### 5.3 Anomaly detection

- **Purpose:** Decide whether a report is trustworthy before it affects prices.
- **Tier 1 (deterministic):** `services/anomaly_detection.py` compares the candidate with trusted reports sharing normalized material, currency, kg unit, and city. It prefers area evidence when the sample allows, uses median/MAD, and returns explicit `pass`, `suspicious`, `insufficient_evidence`, or `unavailable` outcomes. Insufficient history persists the report as `pending_evidence` (excluded from pricing and baselines); `services/report_reevaluation.py` re-runs Tier 1 under a row lock on explicit request.
- **Tier 2 (ML):** `services/ml_anomaly.py` exposes the feature contract (`log1p(price_per_kg)`, `log1p(quantity_kg)`), a readiness gate (report count, distinct materials, distinct cities), and a disabled/unavailable verdict. No model exists.
- **Tier 3 (LLM):** `llm_check_node` is reached only for statistically suspicious reports and only when `USE_LLM_REASONING=true`. It uses schema-validated output and cannot clear the flag or override validation; timeouts and provider/malformed-output failures retain the statistical flag.
- **Status:** a functioning trust layer for Tier 1 plus an optional Tier 3; Tier 2 remains deliberately dormant.

### 5.4 Price aggregation and estimation

- **Purpose:** Return a defensible PKR/kg reference for a material and location.
- **Pure rules:** `services/price_aggregation.py` owns eligibility, duplicate suppression, median/range/freshness/quality, seed selection, and the fallback chain.
- **DB read:** `services/prices.py` loads comparable reports (accepted, non-anomalous, matching city, currency, material aliases, recent) and the configured seed file, then calls `evaluate_price`.
- **Fallback:** local (area) reports → city reports → city seed → national seed → `unavailable`. Sources are never blended.
- **Diagnostics:** only counts are logged; raw report text, picker ids, and contact details are not logged.
- **Status:** real and tested, including real-PostgreSQL integration. It is intentionally conservative: low evidence returns `unavailable`.

### 5.5 Price API, tool, and UI

- **API:** `GET /api/v1/prices/estimate` requires Clerk auth, validates query parameters, and maps database failures to `503`.
- **Tool:** `estimate_price` is the chat-facing wrapper over the same `PriceService`; database failures return an explicit unavailable estimate rather than a fabricated number.
- **UI:** `PriceCheck.tsx` shows the median, observed range, source/scope, counts, freshness, evidence quality, seed provenance, and limitations. It distinguishes report evidence from a labelled seed reference and never renders a null price as zero.
- **Status:** complete for text/structured price checks.

### 5.6 Reviewer flow

- **API:** `GET /api/v1/reports` (paginated, status-filtered, oldest first), `GET /api/v1/reports/{id}`, `PATCH /api/v1/reports/{id}/review`.
- **Authorization:** every route depends on `require_admin`; the Clerk `sub` must be listed in `ADMIN_USER_IDS`.
- **Projection:** omits picker identity, Clerk identifiers, raw picker text, and thread information; includes material, quantity, price, currency/unit, city/area, timestamps, status, anomaly method, anomaly reason, and extraction confidence.
- **Transitions:** only `flagged` → `accepted` or `flagged` → `rejected`; repeats or already-decided reports return `409`; approval clears `is_anomalous` but does not bypass other eligibility rules.
- **UI:** `/review` provides loading, empty, access-denied, and error states, a confirmation dialog, pagination, and refresh after decisions.
- **Status:** complete for human review.

### 5.7 Authentication

- **Purpose:** Verify Clerk session tokens and derive picker identity.
- **Behavior:** 401 without a bearer token; 503 when Clerk is unconfigured; rejects an unknown `azp` when present; accepts tokens without `azp`; uses `sub` as the picker id; `require_admin` enforces `ADMIN_USER_IDS`.
- **Tests:** 5 auth tests plus auth-failure coverage in chat/review tests.
- **Gap:** no rate limiting or abuse control.

### 5.8 Chat threads, history, and API

- **Purpose:** Server-owned per-picker conversations.
- **Data:** `chat_threads` row per conversation; checkpoints per `thread_id`; memory per `picker_id`.
- **Ownership:** `get_thread`/`list_threads` filter by user id; routes verify ownership before history/delete.
- **Gaps:** no pagination; thread creation before agent invocation can leave an empty thread; no idempotency for retries; no streaming; full graph state is loaded for history.

### 5.9 Reports persistence

- **Purpose:** Store finalized reports attributed to the authenticated picker.
- **Behavior:** validates again, inserts `status="flagged"` if anomalous else `"accepted"`, stores `observed_at`, `reviewed_at`, and `reviewed_by`.
- **Read paths:** price aggregation and reviewer queue use SQLAlchemy async sessions; integration tests exercise the real database.
- **Gap:** `save_report` opens its own `SessionLocal` rather than accepting an injected session, which limits transaction composition.

### 5.10 Frontend

- **Purpose:** Clerk-authenticated chat, price-check, and reviewer UI.
- **Features:** sign-in, thread list/search/grouping, new chat, history load, delete with confirmation, retry banner, copy message, markdown/table/code rendering, mobile drawer, dark/light theme, landing page, dev-only demo mode, price-check dialog, reviewer queue.
- **Gaps:** no voice, no camera, no offline/PWA, no tests, no e2e. Text-only capture.
- **Quality:** build passes; lint has 3 non-blocking React warnings.

### 5.11 Configuration and environment

- **Key code:** `core/config.py`.
- **Env vars:** `ENVIRONMENT`, `DEBUG`, `DATABASE_URL`, `DATABASE_ECHO`, `XKIRO_API_KEY`, `XKIRO_BASE_URL`, `XKIRO_MODEL`, `USE_LLM_REASONING`, `ANOMALY_*`, `PRICE_*`, `CORS_ORIGINS`, `CLERK_SECRET_KEY`, `CLERK_JWT_KEY`, `CLERK_AUTHORIZED_PARTIES`, `ADMIN_USER_IDS`.
- **Behavior:** `get_settings()` is `lru_cache`d; some modules call it at import time, so `.env` changes require a process restart and tests can inherit local values.
- **Docs:** `.env.example` and README now document the LLM and anomaly settings, including `USE_LLM_REASONING`.

### 5.12 Operations / deployment

- **Present:** `docker-compose.yml` for PostgreSQL 17; `.env.example`; Alembic migrations through `0004`; `uv.lock`.
- **Absent:** backend/frontend Dockerfiles, CI, production process config, reverse proxy, TLS, backup/retention jobs, observability/metrics, rate limiting.
- **Live local DB:** Docker Compose reports the DB healthy; Alembic is at `0004_add_report_anomaly_outcome (head)`.

### 5.13 Tests

- **Backend:** 194 tests; all pass. Coverage includes auth, validation, MAD behavior, cold-start pending evidence and re-evaluation, ML readiness, graph routing, price aggregation, price API, reviewer actions, and real PostgreSQL price/review integration.
- **Frontend:** none.
- **Not covered:** live model/provider calls, full agent → subagent → persistence routing, multi-turn clarification, retention, rate limiting, prompt injection, performance.
- **Consequence:** the highest-risk remaining wiring gaps are coordinator routing and live provider behavior.

---

## 6. Data Layer

### 6.1 Tables

| Table | Created by | Purpose | Key columns / constraints |
|---|---|---|---|
| `reports` | Alembic `0001`, extended by `0003` | Finalized sale reports | `id` UUID PK; `picker_id` String(128) indexed; `raw_text` Text; `material`; `price_per_kg` Numeric(12,2) > 0; `quantity_kg` Numeric(12,3) > 0; `currency` String(3) default PKR; `city`, `area`; `observed_at`; `confidence` Float; `is_anomalous` Bool; `anomaly_reason` Text; `anomaly_method` String(20); `status` String(20) indexed; `reviewed_at`, `reviewed_by`; `created_at`, `updated_at`. Indexes: `(picker_id, created_at)`, `picker_id`, `status`. |
| `chat_threads` | Alembic `0002` | Server-owned conversation threads | `id` UUID PK; `user_id` String(128) indexed; `title` String(200) default "New chat"; `created_at`, `updated_at`. Index `(user_id, updated_at)`. |
| `checkpoints` | LangGraph `AsyncPostgresSaver.setup()` | Graph checkpoints | Managed by LangGraph. |
| `checkpoint_blobs` | LangGraph setup | Checkpoint channel blobs | Managed by LangGraph. |
| `checkpoint_writes` | LangGraph setup | Pending checkpoint writes | Managed by LangGraph. |
| `checkpoint_migrations` | LangGraph setup | Checkpoint schema version | Managed by LangGraph. |
| `store` | LangGraph `AsyncPostgresStore.setup()` | Long-term memory/files | Managed by LangGraph; per-picker namespace. |
| `store_migrations` | LangGraph setup | Store schema version | Managed by LangGraph. |
| `alembic_version` | Alembic | Migration state | Currently `0003_add_anomaly_review_fields`. |

**Missing tables:** `users`/pickers, `seed_prices` (file-based today), `market_prices`/aggregates (computed on demand), `dealer_quotes`, separate `anomaly_flags`/`review_actions` audit tables, `report_revisions`, `voice_notes`, `classifier_predictions`, `forecasts`.

### 6.2 Relationships

- **No database foreign keys.** `reports.picker_id` and `chat_threads.user_id` are logical references to the Clerk `sub`.
- **No joins.** Reports are read for pricing/review; threads are read/write; checkpoints/store are addressed by `thread_id`/`picker_id` namespaces.
- **Attribution:** reports use the authenticated picker id, not the thread id. The fallback to `thread_id` when `picker_id` is absent remains a misattribution risk if config propagation fails.

### 6.3 Repositories / services

- `ChatThreadStore`: create/list/get/touch/delete. `list_threads` and `get_thread` are user-scoped; `touch_thread` and `delete_thread` are not.
- `save_report`: write path with re-validation; `fetch_reports_for_pricing` and `fetch_comparable_reports`: bounded read paths; `list_reports_for_review`, `get_report_for_review`, `review_report`: reviewer paths.
- `PriceService` + `evaluate_price`: deterministic price read model.
- `load_thread_messages`: reads graph state via `aget_state`.
- No retention service, no memory-deletion service, no seed import script.

### 6.4 Live database verification

- `docker compose ps`: `scrap_sense-db-1` running, healthy, port 5432.
- `uv run alembic current`: `0003_add_anomaly_review_fields (head)`.
- The integration tests insert rows, exercise the real service/API, then roll back or delete only their own rows. They do not rely on pre-existing development rows.

---

## 7. API Surface

All routes are mounted under `/api/v1`. Health routes are unauthenticated; chat and price routes require a Clerk bearer token; report-review routes additionally require the user id in `ADMIN_USER_IDS`.

| Method | Path | Auth | Request shape | Response shape | Tested? |
|---|---|---|---|---|---|
| `POST` | `/api/v1/chat` | Clerk bearer | `{message: str (1..4000), thread_id?: UUID}` | `{user_id, thread_id, reply}` | Yes: happy path, new/owned thread, foreign thread 404, empty message 422, missing auth 401, Clerk unconfigured 503, agent failure 503, empty reply 502. Agent faked. |
| `GET` | `/api/v1/chat/threads` | Clerk bearer | none | `[{id, title, created_at, updated_at}]` | Yes: scoped to authenticated user. |
| `POST` | `/api/v1/chat/threads` | Clerk bearer | optional `{title?: str (1..200)}` | `{id, title, created_at, updated_at}` (201) | Yes: empty body creates default "New chat". |
| `GET` | `/api/v1/chat/threads/{thread_id}/messages` | Clerk bearer | path UUID | `{thread_id, messages: [{role, content}]}` | Yes: owned/foreign 404, history shape. Checkpointer faked. |
| `DELETE` | `/api/v1/chat/threads/{thread_id}` | Clerk bearer | path UUID | 204 no content | Yes: owned deletion, foreign 404, checkpoint deletion recorded. |
| `GET` | `/api/v1/health/live` | none | none | `{status: "ok", version}` | Yes. |
| `GET` | `/api/v1/health/ready` | none | none | `{status, database, version}`; 503 when DB unavailable | Yes: both DB states. |
| `GET` | `/api/v1/prices/estimate` | Clerk bearer | query `material` (required), `location?`, `area?` | `PriceEstimate` (median or null, source, scope, counts, range, freshness, quality, confidence, provenance, limitations) | Yes: 8 API tests plus pure aggregation and real-DB integration tests. |
| `GET` | `/api/v1/reports` | Reviewer only | query `status?` (default flagged), `page`, `page_size` (1–100) | `{items, page, page_size, total, pages, has_more}` | Yes: auth, filtering, oldest-first pagination, real DB. |
| `GET` | `/api/v1/reports/{report_id}` | Reviewer only | path UUID | `ReportQueueItem` or 404 | Yes. |
| `PATCH` | `/api/v1/reports/{report_id}/review` | Reviewer only | `{status: "accepted" \| "rejected"}` | `{id, status, is_anomalous, reviewed_at, reviewed_by}` | Yes: approval, rejection, 404, 409 repeats, 403 picker, real DB. |

**Not present:** separate picker-facing report submission/list endpoints, classifier/image endpoint, voice/transcription endpoint, SSE/streaming endpoint, WebSocket, batch/import endpoint.

**Error handling:** consistent 401/403/404/409/422/502/503 across chat, price, and review; health returns 503 without leaking DB details. No rate-limit responses.

---

## 8. Test Report

### Commands and results

```powershell
# Backend test suite
cd D:\scrap_sense\backend
uv run pytest -o addopts="" --tb=short
# 134 collected, 134 passed, 0 failed, 0 skipped, 0 collection errors
# Completed in 30.05s

uv run ruff check .
# All checks passed!

uv run mypy app tests
# Success: no issues found in 62 source files

cd D:\scrap_sense\frontend
npm run lint
# 0 errors, 3 warnings (react/set-state-in-effect at Chat.tsx:176, Chat.tsx:205, ChatView.tsx:567)

npm run build
# Success: tsc -b && vite build; 97 modules transformed
```

Database/ops verification:

```powershell
docker compose ps
# db service running and healthy

cd D:\scrap_sense\backend
uv run alembic current
# 0003_add_anomaly_review_fields (head)
```

Per-file results:

| Test file | Tests | Result |
|---|---:|---|
| `tests/test_anomaly_detection.py` | 16 | Passed |
| `tests/test_auth.py` | 5 | Passed |
| `tests/test_chat_api.py` | 12 | Passed |
| `tests/test_cold_start_bootstrap.py` | 6 | Passed (real PostgreSQL) |
| `tests/test_config.py` | 4 | Passed |
| `tests/test_health.py` | 3 | Passed |
| `tests/test_main_agent.py` | 3 | Passed |
| `tests/test_ml_anomaly.py` | 3 | Passed |
| `tests/test_pipeline.py` | 22 | Passed |
| `tests/test_price_aggregation.py` | 23 | Passed |
| `tests/test_price_estimator.py` | 2 | Passed |
| `tests/test_price_integration.py` | 5 | Passed (real PostgreSQL) |
| `tests/test_prices_api.py` | 8 | Passed |
| `tests/test_report_review.py` | 6 | Passed |
| `tests/test_report_review_integration.py` | 7 | Passed (real PostgreSQL) |
| `tests/test_report_validation.py` | 9 | Passed |
| `tests/test_seed_prices.py` | 6 | Passed |

### What is tested well

- Auth token handling: missing bearer, unknown `azp`, authorized `azp`, missing `azp`, unconfigured Clerk.
- User ownership boundaries: foreign thread read/append/delete returns 404; thread list is scoped.
- Chat API failure modes: 422, 401, 503, 502.
- Intake extraction fallback, validation, clarification, routing, all three anomaly-tier behaviors, accept/flag summaries, finalize persistence, and picker-id preference.
- Median/MAD behavior, insufficient evidence, pending-evidence persistence and exclusion, controlled re-evaluation, zero-MAD handling, and ML readiness.
- Price eligibility, duplicate suppression, local → city → seed → unavailable fallback, seed-file parsing, price API validation/error handling, and real-PostgreSQL aggregation.
- Reviewer authorization, pagination, approval/rejection transitions, conflicts, and real-PostgreSQL eligibility effects.
- Health endpoints with healthy/unavailable DB fakes.
- Agent wiring (subagent list, tools, context schema, checkpointer/store/memory).

### Coverage gaps

- **No live LLM/provider test.** Provider/key/network behavior is unverified in this audit.
- **No agent-routing test.** Nothing proves a sale message reaches `scrap_report_pipeline` or a price question calls `estimate_price` end to end.
- **No multi-turn clarification test.**
- **No frontend tests** (no test script, no component/e2e tests).
- **No security tests** for rate limiting, PII redaction, retention, or prompt injection.
- **No performance/load tests.**
- **No classifier/voice/forecasting tests** because those components do not exist.

### Audit limitations

- Live LLM calls were intentionally not made. Keys are present in the ignored local `backend/.env`, but no external call was executed.
- GPU/model training cannot be verified because there is no ML code or artifact.
- Field data, picker testing, dealer visits, and demo-video evidence cannot be verified from the repository; none is present.

---

## 9. Tech Debt and Risks

### High

1. **No verified seed data.** The loader and empty file exist, but cold-start estimates remain `unavailable` until audited entries are added.
2. **Tier 2 has no model.** The interface is honest, but there is no Isolation Forest, training script, or artifact.
3. **Provenance is weaker than documented.** The isolated compiled subagent receives the coordinator's `description`, and the pipeline saves the first HumanMessage as `raw_text`; it may not be the picker's verbatim text.
4. **Multi-turn clarification is unresolved.** Extraction reads only the last message and does not merge an earlier draft.
5. **No live end-to-end verification.** Coordinator routing, subagent invocation, persistence, and provider behavior are not covered by an integration test.
6. **No retention, memory deletion, rate limiting, or idempotency.** Retried chat requests can create another thread and/or duplicate report; long-term memory cannot be erased.

### Medium

7. **Synchronous, non-streaming LLM requests.** `POST /chat` blocks for the whole agent run with no explicit timeout/retry policy. No SSE.
8. **PII handling is documented, not enforced.** Raw messages reach the provider and are stored in checkpoints/`raw_text`; no redaction, retention, or encryption.
9. **Location granularity is unenforced.** `city`/`area` are free text; nothing prevents a precise address in raw text or `area`.
10. **Weak repository contracts for threads.** `touch_thread`/`delete_thread` take only `thread_id` and rely on prior route authorization.
11. **Picker id fallback.** `_picker_id_from_config` falls back to `thread_id` if `picker_id` is absent, which could misattribute reports.
12. **Dead/mismatched schemas.** `ReportCreate`, `ReportStatusUpdate`, `ReportRead`, `ReportSubmissionResponse` are unused. `ReportRead` expects fields the model does not have.
13. **No thread pagination.** Thread list and full history are unbounded; `load_thread_messages` reads the entire graph state.
14. **Empty-thread leak on failure.** The thread row is created before agent invocation; a 503 leaves an empty thread.
15. **Persistence failure is swallowed into a user message.** `finalize_report_node` catches exceptions and returns text, with no retry/outbox/metric.
16. **No observability.** Logs only; no metrics, tracing, alerting, or request IDs. Readiness checks DB only.
17. **No CI or application Dockerfiles.** Quality gates are manual.

### Low

18. **`requirements.txt` is duplicate, unpinned, and misspelled** (`sciket-learn`); `pyproject.toml`/`uv.lock` are authoritative.
19. **Stale docstring:** `app/llm.py` says "KapraOS AI layer".
20. **Unused dependencies:** `numpy`, `pandas`, `plotly`, and `scikit-learn` are declared but no product code uses them yet.
21. **`pydantic[email]` dependency** with no email usage.
22. **Frontend lint warnings** (`set-state-in-effect`) are benign but should be cleaned before adding tests.
23. **Committed local artifacts** (`frontend/dev.log`, `dev.err.log`) are ignored by git but present in the working tree; harmless noise.
24. **Demo mode uses regex-generated replies** (`frontend/src/components/Chat.tsx`); it is clearly synthetic and must never be presented as market truth.

### Security notes

- **Good:** chat/price routes require Clerk auth; reviewer routes require `ADMIN_USER_IDS`; ownership checks prevent cross-user reads/deletes; CORS is an explicit allowlist; SQLAlchemy uses parameterized queries; `.env` files are gitignored and not tracked; reviewer projections omit identity and raw text.
- **Risk:** prompt injection via raw message into extraction/judge prompts; structured output limits fields but not malicious free-text content.
- **Risk:** no rate limiting or abuse control; no request size beyond 4000 characters; no durable idempotency.
- **Risk:** raw PII reaches the model provider and is stored unencrypted; no redaction, retention, or memory deletion.
- **Risk:** no encryption-at-rest policy, no backup/restore procedure.

---

## 10. Divergences and Extras vs. the Overview

### Divergences

1. **Coordinator built on Deep Agents, not plain LangGraph.** `deepagents` adds a `task` tool, isolated subagents, a filesystem/memory middleware, and prompt conventions not described in the spec.
2. **No explicit "Price-Estimator Agent."** The estimator is a plain tool (`estimate_price`) plus an HTTP service, not a separate agent.
3. **Text-only web chat vs. "picker app (camera + voice)."** The built product is a responsive web chat with a text composer and a structured price form. There is no camera capture, audio recording, Urdu voice interface, or mobile app.
4. **Tier 1 is implemented; Tier 2 is an honest placeholder; Tier 3 is implemented but default-off.** This is closer to the overview than the previous snapshot, but the ML layer is still absent.
5. **Reviewer flow is an extra.** The overview only mentions reviewer/role separation as future work; the repository now has `require_admin`, `ADMIN_USER_IDS`, a reviewer queue API, and a `/review` UI.
6. **No offline capability.** The overview motivates the architecture with unreliable connectivity and offline model export; the current app requires PostgreSQL, Clerk, and a live xKiro call for chat.
7. **Python version.** Overview says 3.11+; `pyproject.toml` requires >=3.12. Documentation now says 3.12+.
8. **scikit-learn is declared but unused.** It is in `pyproject.toml`, but no model code uses it.
9. **Price estimator now returns a real estimate or `unavailable`, never a fabricated `0.0`.** The old `tier_used="seed"` placeholder is gone.

### Extras (present in code, not planned in the overview)

- Full chat-thread CRUD with titles, ordering, search, grouping, and a delete confirmation dialog.
- Landing page with a sample ledger labeled "Illustration only."
- Dev-only demo mode with four synthetic conversations and regex-generated replies.
- Light/dark theme toggle with localStorage + system preference.
- A small markdown renderer supporting headings, lists, code fences, quotes, tables, and rules.
- Message copy-to-clipboard, retry banner, jump-to-latest, mobile drawer, responsive composer.
- Price-check dialog with evidence scope, counts, freshness, quality, seed provenance, and limitations.
- Reviewer queue UI with pagination and a confirmation dialog.
- `deepagents` as an orchestration library; xKiro as a specific OpenAI-compatible provider.
- Real-PostgreSQL integration tests for price aggregation and report review.
- Duplicate `requirements.txt` alongside `pyproject.toml`/`uv.lock`.
- Local dev logs (`frontend/dev.log`, `frontend/dev.err.log`), gitignored.
- No SSE/streaming, WebSocket, or push transport.

---

## 11. Recommended Next Milestones

These are batched by product outcome. Order is by priority: make the core reference trustworthy with real data, then harden the trust/operations layer, then add capture/ML.

### M1 — Audited seed data and field validation

**Why:** The price chain is real, but with an empty seed file it correctly returns `unavailable` in most cold-start cases.

**Scope:**
- Collect week-1 seed prices from real dealers/pickers with `material`, `price_per_kg`, `currency`, `unit`, `city` (or null), `source`, `collected_at`, and optional `collector`.
- Add only audited entries to `backend/app/data/seed_prices.json`; keep the provenance rules strict.
- Run a small field test with pickers and compare the estimator's output with actual sale outcomes.
- Document the collection method and freshness policy.

**Exit criteria:**
- Seed entries validate against `SeedPriceFile` and appear through the seed fallback with correct provenance.
- `uv run pytest`, `uv run ruff check .`, and `uv run mypy app tests` pass.
- Manual check: a material with seed data returns a nonzero, clearly labelled reference; a material without evidence still returns `unavailable`.

### M2 — Trust-layer depth: Tier 2, reputation, and multi-turn clarification

**Why:** Aggregating untrusted reports can make the price worse, not better; and current clarification is single-turn.

**Scope:**
- Implement the Tier 2 Isolation Forest only after the documented readiness gate is satisfied; commit a reproducible training script and artifact metadata.
- Add a reporter-trust/reputation signal (a genuine judgment call) or explicitly document why it remains out of scope.
- Merge follow-up clarification answers with the earlier draft so a picker can complete a report across turns.
- Consider a durable idempotency key for report submission.

**Exit criteria:**
- Tests cover the full graph path deterministic → ml → llm → finalize with a flagged report.
- A test proves a multi-turn clarification completes a report.
- A flagged report never influences estimates; an approved report does.
- Model artifact or training script is committed with a reproducible command.

### M3 — Integration, correctness, and operational hardening

**Why:** The suite is strong, but live routing, retention, and abuse controls are still missing.

**Scope:**
- Add an opt-in live-agent smoke test (or fake provider) that proves a sale message reaches the pipeline and a price question calls `estimate_price`.
- Add request timeouts/retries for LLM calls; add structured logs/request IDs; extend readiness to include provider configuration.
- Add retention/cleanup policy and a memory-deletion path.
- Add rate limiting and request-size limits.
- Add backend/frontend Dockerfiles and a CI workflow running pytest, ruff, mypy, frontend lint, and build.
- Remove dead schemas, fix `requirements.txt`, and clean the stale `llm.py` docstring.
- Clean the three frontend lint warnings.

**Exit criteria:**
- CI is green on the default branch.
- The documented setup works from a clean checkout on Windows and Linux.
- Retention and memory-deletion behavior is documented and tested.
- The live-agent smoke test passes against the configured provider or a fake provider.

### M4 — Voice and camera capture + material classifier

**Why:** These are the overview's secondary helper features and the field constraints it motivates.

**Scope:**
- Add audio recording/upload and transcription (or a documented provider), with Urdu/Roman Urdu handling and graceful failure.
- Add image upload and a classifier service wrapping a trained CNN (MobileNetV2/EfficientNet-Lite), with confidence thresholds and a "not sure" path.
- Train/fine-tune on a public dataset; export TFLite/ONNX for offline use; commit the training script, evaluation report, and model artifact location.
- Add frontend capture controls and a result card that clearly distinguishes classifier confidence from market price.
- Add tests using fixture images/audio and a mocked inference backend.

**Exit criteria:**
- Classifier inference endpoint/service tests pass with fixtures.
- Voice upload/transcription tests pass with a mocked provider.
- End-to-end UI test (or documented manual test) covers photo → classifier → price check.
- No fabricated material identification when confidence is low.

### M5 — Forecasting (only after real report volume)

**Why:** The overview correctly says an RNN on a handful of reports would memorize noise.

**Scope:**
- Build a time-series dataset from accepted reports; define evaluation/backtest splits.
- Implement a simple statistical baseline first, then an RNN/LSTM only if it beats the baseline.
- Add model versioning, offline evaluation, and a fallback to the deterministic estimator.
- Expose trend/price history only where sample size supports it.

**Exit criteria:**
- Backtest report shows the model does not underperform the deterministic baseline.
- Forecasting tests pass; estimator falls back safely on insufficient data.
- Documentation states the data-volume threshold and limitations.

---

*End of audit.*
