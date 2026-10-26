# ScrapSense — Implementation Status Audit

> **Post-audit update (2026-10-25):** This document is the read-only pre-implementation snapshot.
> The price-intelligence gap described below has since been implemented: deterministic report
> aggregation, seed fallback, the price API, the frontend price check, and real PostgreSQL
> integration tests now exist. The anomaly routing gap has also been fixed: deterministic
> intake validation, a median/MAD Tier 1, a disabled-with-readiness-gate Tier 2, a reachable
> LLM Tier 3 that cannot clear flags, persisted `flagged` reports, and a reviewer-only approval
> endpoint now exist. See `PRODUCT.md`, `README.md`, and `ScrapSense_Project_Overview.md` for
> the current state. The sections below remain the original audit snapshot.

### Current anomaly status (2026-10-26)

- Deterministic validation runs before every anomaly tier and blocks invalid input with a
  clarification question instead of persisting it.
- Anomaly Tier 1 is implemented as a conservative median/MAD comparison over accepted,
  non-anomalous reports with matching material, currency, unit, and city. Area-level evidence is
  preferred when available.
- Suspicious reports are persisted as `flagged` and excluded from price aggregation. They are not
  labelled fraud or automatically rejected.
- Anomaly Tier 2 is deliberately disabled. The interface and readiness gate live in
  `backend/app/services/ml_anomaly.py`; the current database is far below the documented threshold.
- Anomaly Tier 3 is reachable only for suspicious reports when `USE_LLM_REASONING=true`. It can
  annotate or strengthen a flag but cannot clear it; timeouts and provider failures retain the flag.
- `PATCH /api/v1/reports/{report_id}/review` lets an `ADMIN_USER_IDS` reviewer approve or reject a
  flagged report. Approval clears the active flag and restores price eligibility.
- Migration `0003_add_anomaly_review_fields` adds `observed_at`, `reviewed_at`, and `reviewed_by`.
- The backend suite covers graph routing, validation, MAD behavior, ML readiness, review actions,
  and real PostgreSQL price-eligibility integration.

- **Audit date:** 2026-10-25
- **Spec source of truth:** `ScrapSense_Project_Overview.md` (supported by `README.md` and `PRODUCT.md`)
- **Scope:** entire repository, excluding `node_modules`, `.venv`, `__pycache__`, `.git`, build output, caches, and agent-tooling directories
- **Mode:** read-only. The only file created by this audit is this document. No source file was modified, refactored, or deleted. `frontend/dist` produced by the verification build was removed afterward.

---

## 1. Executive Summary

### Overall completion estimate

**≈30% of the full overview.** The repository is a working authenticated chat + report-intake + persistence demo, but the product's central value chain — trustworthy aggregation of picker reports into a usable fair-price reference — is **not built**. If the score is limited to the currently implemented "authenticated text chat with persisted intake" slice, that slice is roughly 70–75% complete.

The overview itself is unusually honest about what is missing (§9–§11). This audit confirms those admissions and finds a few additional gaps: the LLM anomaly tier is unreachable in the compiled graph, the stored `raw_text` is not guaranteed to be the picker's verbatim message, the documented dev runner `run.py` no longer exists, and the lint gate fails.

### Top 5 strengths

1. **Authentication and per-user thread isolation are real and tested.** Clerk verification, bearer-token requirements, authorized-party checks, and ownership checks are implemented in `backend/app/auth/dependencies.py` and `backend/app/api/routes/chat.py`; 12 API tests cover cross-user rejection, history scoping, and deletion scoping.
2. **Report intake is a real LangGraph pipeline with structured extraction and deterministic validation.** `backend/app/workflows/pipeline.py` implements extract → validate → route → anomaly stub → finalize, including a clarification fallback instead of guessing.
3. **PostgreSQL persistence is genuinely wired.** `reports`, `chat_threads`, and the LangGraph checkpoint/store tables exist in the live local database; Alembic is at `0002_create_chat_threads`; one report row and 120 checkpoints are present.
4. **The placeholder behavior is honest rather than fabricated.** The price tool returns `0.0` at zero confidence and the anomaly tiers return neutral verdicts, matching the "honest gaps over false confidence" principle.
5. **The frontend chat experience is complete for text chat.** Clerk sign-in, server-backed threads, history restoration, deletion, search, responsive drawer, markdown rendering, theme toggle, and build success are all present.

### Top 5 gaps / risks

1. **No real price intelligence.** `estimate_price()` is a hardcoded `0.0`; reports are never read back or aggregated; there is no seed-price file, no local/city/seed fallback chain, and no price API or UI. The core user outcome — walking into a negotiation with a number — does not exist.
2. **Anomaly detection is placeholders only.** Tier 1 has no median check, Tier 2 has no Isolation Forest, and Tier 3's LLM judge is **unreachable in the compiled graph** because both lower tiers always return `is_anomalous=False`. The tests exercise the LLM node directly, masking the wiring gap.
3. **The ML layer is absent.** No PyTorch, no scikit-learn, no classifier module, no trained artifacts, no TFLite/ONNX export, no forecasting model. The "secondary" photo feature and the future forecasting model are both not started.
4. **Integration confidence is low.** All persistence and API tests use fakes; no test touches PostgreSQL, Alembic, the real checkpointer, or a live LLM. The stored `raw_text` is the coordinator's task description, not necessarily the picker's original message. Live provider behavior was not exercised in this audit.
5. **Operational and privacy hardening is missing.** No retention policy, no memory deletion, no encryption-at-rest policy, no rate limiting, no idempotency, no CI, no app Dockerfiles, and documentation tells users to run a deleted `run.py`. `ruff check` currently fails.

### Bottom line

This is a credible **foundation and demo shell**, not yet a price-transparency product. The next milestone must make reports produce a real, defensible price estimate; polishing the chat UI further will not close the product gap.

---

## 2. Repo Structure

```text
D:\scrap_sense\
├── ScrapSense_Project_Overview.md   Spec: problem, agents, models, data strategy, stack, timeline, honest gap list.
├── README.md                        Setup/run docs. Mostly accurate, but references deleted backend/run.py.
├── PRODUCT.md                       Product brief: users, positioning, constraints, privacy principles.
├── docker-compose.yml               Local PostgreSQL 17 only. No backend/frontend app containers.
├── .env.example                     Postgres compose variables only.
├── .gitignore                       Ignores .env, .venv, node_modules, caches, logs, agent-tooling dirs.
├── skills-lock.json                 Agent-skill lock file (not product code).
│
├── backend\
│   ├── pyproject.toml               Python >=3.12, FastAPI, LangGraph, deepagents, SQLAlchemy, Clerk, xKiro/OpenAI.
│   ├── requirements.txt             Unpinned duplicate dependency list; no torch/sklearn.
│   ├── uv.lock                      Resolved dependency lock.
│   ├── .env.example                 Backend template: DB, xKiro, Clerk, CORS, admin IDs.
│   ├── .env                         Local secrets, gitignored (verified not tracked).
│   ├── alembic.ini                  Alembic config; URL is overridden in env.py from settings.
│   ├── alembic\
│   │   ├── env.py                   Async Alembic environment; imports app models for metadata.
│   │   └── versions\
│   │       ├── 0001_create_final_reports.py   Creates reports table + indexes/checks.
│   │       └── 0002_create_chat_threads.py    Creates chat_threads table + indexes.
│   ├── app\
│   │   ├── main.py                  FastAPI app factory, CORS, lifespan closing agent pool/engine.
│   │   ├── llm.py                   xKiro-backed ChatOpenAI factory; raises if key missing.
│   │   ├── loops.py                 Unused selector event-loop factory (run.py was deleted).
│   │   ├── agents\
│   │   │   ├── main_agent.py        Deep Agents coordinator, per-picker memory backend, lazy Postgres pool.
│   │   │   └── report_intaker.py    CompiledSubAgent wrapping the report pipeline.
│   │   ├── api\
│   │   │   ├── router.py            Mounts health + chat routers under /api/v1.
│   │   │   ├── deps.py              Session dependency alias.
│   │   │   └── routes\
│   │   │       ├── chat.py          POST /chat + thread CRUD/history/delete; Clerk-protected.
│   │   │       └── health.py        GET /health/live and /health/ready.
│   │   ├── auth\
│   │   │   └── dependencies.py      Clerk bearer verification; require_auth and unused require_admin.
│   │   ├── core\
│   │   │   └── config.py            Pydantic settings; DB, xKiro, Clerk, CORS, use_llm_reasoning.
│   │   ├── db\
│   │   │   ├── base.py              Declarative Base + naming convention.
│   │   │   └── session.py           Async engine/session factory; module-level settings.
│   │   ├── models\
│   │   │   ├── report.py            finalized reports table ORM model.
│   │   │   └── chat_thread.py       chat_threads ORM model.
│   │   ├── schemas\
│   │   │   ├── report.py            ReportDraft, AnomalyVerdict, FinalReport, LLMJudgment + unused report schemas.
│   │   │   ├── price.py             PriceEstimate + unused request/response wrappers.
│   │   │   └── chat.py              Chat request/response/thread/history schemas.
│   │   ├── services\
│   │   │   ├── reports.py           save_report(): validate + insert Report.
│   │   │   ├── chat_threads.py      ChatThreadStore: create/list/get/touch/delete.
│   │   │   └── chat_history.py      Load human/assistant turns from graph state.
│   │   ├── tools\
│   │   │   └── price_estimator.py   estimate_price(): hardcoded zero-price placeholder.
│   │   └── workflows\
│   │       ├── pipeline.py          Intake + placeholder anomaly + finalize LangGraph.
│   │       └── state.py             PipelineState (MessagesState + report/verdict fields).
│   └── tests\                       38 tests: auth, chat API, config, health, main agent wiring, pipeline, price placeholder.
│
├── frontend\
│   ├── package.json                 React 19, TS, Vite 8, Clerk, Tailwind 4, oxlint. No test script.
│   ├── vite.config.ts               React + Tailwind plugins.
│   ├── .env.example                 API base URL + Clerk publishable key.
│   ├── .env                         Local frontend env, gitignored (verified not tracked).
│   ├── src\
│   │   ├── main.tsx                 ClerkProvider or setup screen; mounts App.
│   │   ├── App.tsx                  Landing, Clerk gate, demo/landing modes, sample ledger.
│   │   ├── components\
│   │   │   ├── Chat.tsx             Live chat state + demo chat with hardcoded synthetic history.
│   │   │   ├── ThemeToggle.tsx      Light/dark toggle.
│   │   │   └── chat\
│   │   │       ├── ChatView.tsx     Full chat shell: sidebar, messages, composer, delete dialog.
│   │   │       ├── MarkdownMessage.tsx  Small markdown renderer (headings, lists, code, tables).
│   │   │       ├── MessageText.tsx  Inline markdown/links/number highlighting.
│   │   │       ├── format.ts        Relative time + thread grouping.
│   │   │       ├── icons.tsx        Inline icon set.
│   │   │       └── types.ts         Chat UI types.
│   │   ├── lib\
│   │   │   ├── api.ts               Typed fetch client for the five chat endpoints.
│   │   │   ├── useAccessToken.ts    Clerk getToken wrapper.
│   │   │   ├── demoMode.ts          Dev-only ?demo/?landing mode flags.
│   │   │   └── theme.ts             localStorage/system theme store.
│   │   └── index.css                Tailwind theme, claymorphism design tokens.
│   └── dev.log / dev.err.log        Local dev-server artifacts, gitignored.
│
└── MISSING (documented or expected but absent):
    ├── backend/run.py               README still instructs users to run it; removed in commit 868fb96.
    ├── backend/app/data/seed_prices.json
    ├── backend/app/ml/ or classifier module
    ├── trained model artifacts (CNN / Isolation Forest / forecasting)
    ├── seed/demo-data scripts
    ├── backend/frontend Dockerfiles
    └── CI configuration (.github/workflows or equivalent)
```

---

## 3. Architecture as Actually Built

### End-to-end text flow

1. **Browser (React + Clerk).** The user signs in through Clerk. `frontend/src/lib/useAccessToken.ts` obtains a session token for each API call. `frontend/src/lib/api.ts` sends JSON to `VITE_API_BASE_URL` (default `http://localhost:8000/api/v1`).
2. **FastAPI entry.** `backend/app/main.py` creates the app, applies CORS, and mounts `/api/v1`. All chat routes depend on `require_auth`, which verifies the Clerk bearer token and derives `user_id` from the `sub` claim (`backend/app/auth/dependencies.py:49`).
3. **Thread selection.** `POST /api/v1/chat` either creates a server-owned `chat_threads` row for the picker or verifies that the supplied `thread_id` belongs to that picker (`backend/app/api/routes/chat.py:98-115`). A thread is created **before** the agent runs, so an agent failure can leave an empty thread.
4. **Agent invocation.** The route calls the lazily built Deep Agents coordinator with `thread_id` and `picker_id` in the config and `AgentContext(picker_id=...)` (`backend/app/api/routes/chat.py:120-129`). The coordinator is built in `backend/app/agents/main_agent.py:53-81` with:
   - xKiro `ChatOpenAI` model,
   - a `scrap_report_pipeline` compiled subagent,
   - the `estimate_price` tool,
   - `AsyncPostgresSaver` checkpoints,
   - `AsyncPostgresStore` long-term memory,
   - a `/memories/` route stored under the picker's namespace.
5. **Routing.** Routing is **prompt-driven, not deterministic**. The system prompt tells the LLM to delegate sale reports to `scrap_report_pipeline` and to call `estimate_price` for "what is this worth" questions (`backend/app/agents/main_agent.py:29-43`). There is no explicit router class, no classifier, and no photo/voice branch.
6. **Report intake subagent.** Deep Agents invokes the compiled pipeline in isolated mode, meaning the subagent receives a single `HumanMessage` containing the parent agent's task `description`, not the original conversation (`deepagents/middleware/subagents.py:835` in the installed dependency). The pipeline:
   - `report_draft` reads the last message and asks the LLM for structured `ReportDraft` (`backend/app/workflows/pipeline.py:110-142`).
   - `validate_and_build` checks for material, positive price, and positive quantity; if anything is missing or flagged, it returns one clarification question and ends (`pipeline.py:145-174`).
   - `deterministic_check_node` returns a neutral verdict (`pipeline.py:177-180`).
   - `ml_check_node` returns a neutral verdict (`pipeline.py:183-186`).
   - `route_after_ml` only sends flagged reports to the LLM judge, and only when `USE_LLM_REASONING` is true (`pipeline.py:330-339`). Because both lower tiers always return `False`, **the LLM judge is never reached in normal execution**.
   - `accept_node` summarizes the verdict (`pipeline.py:248-263`).
   - `finalize_report_node` persists the report and exposes it as `structured_response` (`pipeline.py:266-323`).
7. **Persistence.** `save_report()` inserts a `reports` row with `picker_id` (the Clerk `sub`), extracted fields, the anomaly verdict, and status `accepted` or `flagged` (`backend/app/services/reports.py:10-41`). LangGraph checkpoints and the long-term store are also in PostgreSQL.
8. **Response.** `POST /api/v1/chat` extracts the last non-empty assistant text and returns `{user_id, thread_id, reply}` (`backend/app/api/routes/chat.py:137-148`). There is no streaming/SSE.
9. **History.** `GET /api/v1/chat/threads/{id}/messages` verifies ownership, then reads graph state through `agent.aget_state()` and returns only human/assistant turns (`backend/app/services/chat_history.py:28-56`).
10. **Deletion.** `DELETE /api/v1/chat/threads/{id}` verifies ownership, deletes checkpoints via the checkpointer, then deletes the thread row (`backend/app/api/routes/chat.py:191-214`). Reports already submitted are intentionally retained.

### What is absent from the data flow

- **No price read path.** The estimator never reads `reports`, `chat_threads`, or any seed file. It returns a hardcoded zero (`backend/app/tools/price_estimator.py:10-23`).
- **No aggregation.** There is no query that computes a median/mean/range by material and region, and no market-price table.
- **No photo/classifier path.** The chat schema only accepts text; there is no image upload or classifier module.
- **No voice path.** There is no audio capture, transcription, or voice endpoint.
- **No forecasting path.** There is no time-series model or trend logic.
- **No offline mode.** The app requires PostgreSQL, Clerk, and a live LLM provider for normal use, despite the overview's field-connectivity motivation.
- **No reviewer flow.** `require_admin` exists but no route uses it; report review/status schemas are unused.

---

## 4. Checklist Against the Overview

Statuses are exactly one of **DONE**, **PARTIAL**, **NOT STARTED**, or **DIVERGED**. Evidence points to the implementation and, where available, the test name.

### A. Product flow and agents

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| A1 | Free-text sale report → structured, validated data | **DONE** | `pipeline.py:110-164` (`report_draft`, `validate_and_build`); tests `test_pipeline.py::test_report_draft_extracts_structured_details`, `test_validate_and_build_asks_for_missing_fields` | Live LLM provider not exercised in this audit; tests use fake models. |
| A2 | Flag uncertainty instead of guessing | **DONE** | `pipeline.py:145-174`; `ReportDraft.needs_clarification`; tests `test_extraction_failure_falls_back_to_clarification`, `test_pipeline_asks_for_clarification` | One clarification question is returned; no guessing fallback. |
| A3 | Resolve a flagged report across subsequent turns | **PARTIAL** | `pipeline.py:112-113` reads only `messages[-1]`; no merge of earlier draft; no follow-up-turn test | A second message that only supplies the missing field will fail validation again unless the parent agent packs earlier context into the subagent description. Not verified live. |
| A4 | Voice / transcribed voice input (Urdu) | **NOT STARTED** | No audio/transcription code; frontend composer is a textarea (`ChatView.tsx:784-799`); no `MediaRecorder`/speech code in `frontend/src` | No model/provider or endpoint. |
| A5 | Material classifier agent from a photo | **NOT STARTED** | No classifier module, no image upload schema, no image UI; no torch/onnx/tflite dependency | Not even a stub module, matching the overview's own admission. |
| A6 | Orchestrator routes report vs. price requests | **PARTIAL** | `main_agent.py:29-43` prompt; `main_agent.py:71-81` subagent + tool wiring; `report_intaker.py:11-19` | Prompt-driven only; no routing test; no deterministic router; no test that a sale message actually reaches the pipeline. |
| A7 | Orchestrator offline data-gap reasoning loop | **NOT STARTED** | `app/loops.py:8` is an event-loop factory, not gap analysis; no scheduler/agent loop | Overview §4/§10 explicitly calls this future work. |
| A8 | Anomaly Tier 1: deterministic price vs. recent median | **PARTIAL** | `pipeline.py:177-180` returns `_neutral_verdict("deterministic")`; test `test_deterministic_and_ml_checks_are_neutral` asserts neutrality | No median query, no baseline, no thresholds. |
| A9 | Anomaly Tier 2: Isolation Forest price+quantity | **PARTIAL** | `pipeline.py:183-186` returns `_neutral_verdict("ml")`; no sklearn/torch dependency; no model artifact | Only the graph slot exists; the model is not started. |
| A10 | Anomaly Tier 3: LLM judge only for flagged reports | **PARTIAL** | `pipeline.py:189-216` (`llm_check_node`), `pipeline.py:330-339` (gate); test `test_llm_check_uses_judgment` | Unit-tested directly, but unreachable in the compiled graph because both lower tiers always return `False`. `USE_LLM_REASONING` defaults to `False` (`config.py:32`). |
| A11 | Trust verdict gates report/price influence | **PARTIAL** | `services/reports.py:34` sets status flagged/accepted; `pipeline.py:256-258`; tests `test_accept_reports_a_flagged_verdict`, `test_finalize_report_persists_the_report` | Reports can be flagged, but tier nodes never flag, and no price path consumes reports at all. |
| A12 | Price estimator fallback chain: local → city → seed, blended | **PARTIAL** | `tools/price_estimator.py:10-23` returns `0.0`, `confidence=0.0`, `tier_used="seed"`, zero counts; test `test_price_estimator.py::test_estimate_price_returns_the_seed_placeholder_contract` | Contract fields exist; all logic/data are missing. The `"seed"` tier label is misleading because no seed data exists. |
| A13 | Aggregate trustworthy reports into price references | **NOT STARTED** | No read/aggregate query over `Report`; grep finds only `save_report`; no market table | `reports` rows accumulate but are never used. |
| A14 | Reporter-trust agent (considered future upgrade) | **NOT STARTED** | No code; overview §4:94 explicitly calls it future | Correctly out of scope for now. |
| A15 | Forecasting model (RNN/LSTM) | **NOT STARTED** | No model/dependency; overview §5 marks it not built | No time-series data logic. |
| A16 | Shared data store for report and price paths | **PARTIAL** | PostgreSQL holds `reports` and LangGraph state; `estimate_price` is hardcoded and does not read `reports` | The store is shared physically, but the two paths do not converge functionally. |
| A17 | Two request types: "I sold this" vs. "what's this worth?" | **PARTIAL** | `main_agent.py:32-38` prompt; `estimate_price` tool | Text price questions are routed to a zero-returning tool; photo price questions have no path. |

### B. Models and data strategy

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| B1 | CNN (MobileNetV2 / EfficientNet-Lite), fine-tune, export TFLite/ONNX | **NOT STARTED** | No classifier code, dataset, notebook, or model artifact; no torch dependency (`pyproject.toml:5-22`) | GPU/training cannot be verified because nothing exists. |
| B2 | Trained Isolation Forest model (~50+ reports, dormant until meaningful) | **NOT STARTED** | No sklearn dependency/model artifact; only the neutral node exists | No count threshold or dormant-model logic. |
| B3 | RNN/LSTM forecasting model | **NOT STARTED** | No model/dependency | Overview says not built. |
| B4 | `app/data/seed_prices.json` with source, date, collector, range/price | **NOT STARTED** | `backend/app/data` does not exist; no seed file anywhere | Overview §6 TODO. |
| B5 | Week-1 manual seed-price collection | **NOT STARTED** | No data, import script, or field notes in repo | Cannot verify externally; no evidence on hand. |
| B6 | Crowd-report dataset accumulation | **PARTIAL** | `models/report.py:22-63`; `services/reports.py:10-41`; live DB has 1 report row | Persistence exists; no ingestion volume, deduplication, or operational data strategy. |
| B7 | Cold-start/demo data seeding, clearly synthetic | **PARTIAL** | `frontend/src/components/Chat.tsx:23-125` hardcoded demo threads; `App.tsx:13-17` sample ledger; labels "Demo workspace" / "Illustration only" | Frontend-only fixtures; no backend seeder; complies with "do not present as market truth" but not a data-loading solution. |
| B8 | Location at neighborhood/city level only; never precise GPS | **PARTIAL** | `models/report.py:42-43` has `city`/`area`; no GPS fields; no granularity validation | Raw text can still contain a precise address, and `area` is free text. No enforcement. |
| B9 | Reporter identity anonymized; no name/phone plaintext | **DONE** | `reports.picker_id` from Clerk `sub` (`auth/dependencies.py:90-103`); no name/phone columns; tests `test_chat_api.py` ownership tests | Raw message text may contain PII; that is a separate acknowledged gap. |
| B10 | Dealer-referencing data only as anonymized aggregates | **NOT STARTED** | No dealer model, no aggregation, no publication path | Nothing to anonymize yet; the protection mechanism is not implemented. |
| B11 | Retention policy | **NOT STARTED** | No cleanup job/config; live DB has 120 checkpoints | Acknowledged in overview §11 and README. |
| B12 | Memory deletion | **NOT STARTED** | `chat.py:205` deletes thread checkpoints only; no store deletion; `main_agent.py:63-67` memory is per-picker | `/memories/picker_notes.md` survives thread deletion, as documented. |
| B13 | Encryption at rest | **NOT STARTED** | No encryption config/policy in `db/session.py` or docs | Acknowledged in overview §11. |

### C. Tech stack and platform

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| C1 | FastAPI backend, Python 3.11+ | **DONE** | `pyproject.toml:4-22`; `app/main.py:20-36` | Actually requires Python >=3.12, not 3.11. Minor docs/version divergence. |
| C2 | LangGraph orchestration | **DONE** | `workflows/pipeline.py:342-378` (`StateGraph`); `agents/main_agent.py` (Deep Agents on LangGraph) | Uses `deepagents` as an extra layer not named in the overview. |
| C3 | PyTorch for CNN | **NOT STARTED** | Absent from `pyproject.toml` and `requirements.txt` | No ML environment. |
| C4 | scikit-learn for Isolation Forest | **NOT STARTED** | Absent from dependencies | No ML environment. |
| C5 | React + TypeScript + Vite frontend | **DONE** | `frontend/package.json`; `vite.config.ts`; `npm run build` passes | React 19, Vite 8, Tailwind 4. |
| C6 | Clerk-authenticated chat UI | **DONE** | `main.tsx:8-18`; `App.tsx:1-9, 152-160`; `useAccessToken.ts`; backend `require_auth` | Backend auth is tested; live Clerk flow not exercised. |
| C7 | Voice-first UI | **NOT STARTED** | No mic/audio UI in `frontend/src` | Text composer only. |
| C8 | PostgreSQL-backed LangGraph checkpoints | **DONE** | `main_agent.py:117-122`; live DB tables `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`; 120 checkpoints | Live DB verified. |
| C9 | PostgreSQL long-term store / memory | **DONE** | `main_agent.py:63-67, 121`; live `store` table with 1 picker namespace | Live DB verified. |
| C10 | Finalized report rows in PostgreSQL | **DONE** | `models/report.py`; `services/reports.py`; migration `0001`; live `reports` table with 1 row | Persistence in a real DB is not covered by tests; verified manually. |
| C11 | Structured seed prices + market aggregation wired | **NOT STARTED** | No seed table/file; no aggregation query | Overview §7 says still to be wired. |
| C12 | Docker/deploy files | **PARTIAL** | `docker-compose.yml` (Postgres only); no `Dockerfile`, no CI, no production server config | Local dev DB only. |
| C13 | Seeder scripts | **NOT STARTED** | No scripts directory; no seed script | Frontend demo fixtures are not a seeder. |

### D. Build timeline / milestones

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| D1 | Week 1: seed data + report intake + simple baseline estimator | **PARTIAL** | Intake done (`pipeline.py`); no seed file; no baseline estimator | 2 of 3 missing. |
| D2 | Week 2: all three anomaly tiers + orchestrator reasoning loop + real estimator | **PARTIAL** | Pipeline skeleton and LLM judge code; tiers are neutral; no reasoning loop; estimator hardcoded | The structure exists; the substance does not. |
| D3 | Week 3: CNN + offline export + Urdu voice + field testing | **NOT STARTED** | No CNN, export, audio, or field-test evidence | No dataset or model. |
| D4 | Week 4: field feedback, polish, demo video, documentation | **PARTIAL** | Frontend polish and docs (`README.md`, `PRODUCT.md`, overview); no field feedback or demo video in repo | Documentation is relatively good; field validation is absent. |

### E. API, schemas, and tables

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| E1 | `POST /api/v1/chat` | **DONE** | `chat.py:98-148`; tests `test_chat_returns_the_main_agent_reply`, `test_chat_continues_an_owned_thread`, `test_chat_rejects_another_users_thread`, `test_chat_rejects_empty_message`, `test_chat_requires_authentication`, `test_chat_returns_503_when_clerk_is_not_configured`, `test_chat_returns_503_when_agent_fails`, `test_chat_returns_502_when_agent_has_no_text` | Agent is faked in tests; live agent path untested. |
| E2 | `POST /api/v1/chat/threads` | **DONE** | `chat.py:160-172`; test `test_create_thread_accepts_an_empty_body` | Returns 201 with default title. |
| E3 | `GET /api/v1/chat/threads` | **DONE** | `chat.py:151-157`; test `test_thread_list_is_scoped_to_the_authenticated_user` | No pagination. |
| E4 | `GET /api/v1/chat/threads/{thread_id}/messages` | **DONE** | `chat.py:175-188`; test `test_thread_history_is_scoped_to_the_authenticated_user` | Uses `agent.aget_state()`; faked in tests. |
| E5 | `DELETE /api/v1/chat/threads/{thread_id}` | **DONE** | `chat.py:191-214`; test `test_delete_thread_removes_only_owned_history` | Checkpointer faked in tests. |
| E6 | `GET /api/v1/health/live` | **DONE** | `health.py:29-33`; test `test_liveness` | No version pin issues. |
| E7 | `GET /api/v1/health/ready` | **DONE** | `health.py:36-61`; tests `test_readiness_when_database_is_available`, `test_readiness_when_database_is_unavailable` | Checks DB only, not agent/LLM. |
| E8 | Report submit/list/review endpoints | **NOT STARTED** | Only chat routes exist (`api/router.py`); no report router | Reports are only created via chat. |
| E9 | SSE / streaming responses | **NOT STARTED** | No `StreamingResponse`, `EventSource`, or event-stream code in backend/frontend | Not in the overview; noted because the audit brief asked about SSE/streaming. |
| E10 | `reports` table + migration | **DONE** | `models/report.py:22-63`; `alembic/versions/0001_create_final_reports.py`; live DB table | No foreign keys. |
| E11 | `chat_threads` table + migration | **DONE** | `models/chat_thread.py:16-41`; `alembic/versions/0002_create_chat_threads.py`; live DB table | No foreign keys. |
| E12 | LangGraph checkpoint/store tables | **DONE** | `main_agent.py:117-122`; live DB tables `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`, `store`, `store_migrations` | Created by savers on first use, matching docs. |
| E13 | Report Pydantic schemas (`ReportDraft`, `AnomalyVerdict`, `FinalReport`, `LLMJudgment`) | **DONE** | `schemas/report.py:15-28, 68-104`; used by pipeline/tests | Good validation bounds and literals. |
| E14 | Chat Pydantic schemas | **DONE** | `schemas/chat.py:12-47`; used by routes/tests | Length limits present. |
| E15 | Report read/status/submission schemas | **PARTIAL** | `ReportCreate`, `ReportStatusUpdate`, `ReportRead`, `ReportSubmissionResponse` at `schemas/report.py:30-63` | Dead code: no route uses them. `ReportRead` expects `reporter_id`/`reported_at`/`reviewed_at`, which do not exist on `Report` (`models/report.py`), so it would fail if used as-is. |
| E16 | Reviewer/role separation | **PARTIAL** | `require_admin` (`auth/dependencies.py:106-120`), `admin_user_ids` (`config.py:39`) | No route uses `require_admin`; no reviewer workflow. |
| E17 | Per-picker long-term memory namespace | **DONE** | `main_agent.py:63-67`; live store has one picker namespace | No deletion path. |
| E18 | Thread deletion removes checkpoints | **DONE** | `chat.py:204-213`; test `test_delete_thread_removes_only_owned_history` | Does not delete reports (intended) or memory. |
| E19 | Honest documentation of gaps | **DONE** | Overview §9–§11; `README.md` "Known limitations"; `PRODUCT.md` "Explicitly not built yet" | This is a genuine strength, though one doc claim (`run.py`) is stale. |

### F. Quality gates and verification

| # | Item | Status | Evidence | Notes |
|---|---|---|---|---|
| F1 | Backend test suite | **DONE** | `uv run pytest -o addopts="" --tb=short`: **38 passed** | See §8. |
| F2 | Backend lint | **PARTIAL** | `uv run ruff check .`: 1 error, `I001` unsorted imports in `app/agents/main_agent.py:5` | Fixable, but currently red. |
| F3 | Backend typecheck | **DONE** | `uv run mypy app tests`: success, 44 source files | — |
| F4 | Frontend build | **DONE** | `npm run build`: `tsc -b && vite build` succeeded | Build output was removed after verification. |
| F5 | Frontend lint | **PARTIAL** | `npm run lint`: 0 errors, 3 warnings (`Chat.tsx:176`, `Chat.tsx:205`, `ChatView.tsx:531`, `react/set-state-in-effect`) | Non-blocking but worth cleaning. |
| F6 | Frontend tests | **NOT STARTED** | No test script in `package.json`; no test files under `frontend/src` | No component, hook, or e2e coverage. |
| F7 | Integration tests against real PostgreSQL | **NOT STARTED** | `test_chat_api.py` uses `FakeThreadStore`/`FakeCheckpointer`; `test_pipeline.py` patches `save_report` | No test runs Alembic, SQLAlchemy sessions, or real checkpointer/store. |
| F8 | CI pipeline | **NOT STARTED** | No `.github` or other CI config; only `docker-compose.yml` | Quality gates are manual and currently inconsistent. |
| F9 | README/setup accuracy | **DIVERGED** | README references `backend/run.py` at lines 48, 68, 82; the file is absent and was deleted in commit `868fb96`; `loops.py` is correspondingly unused | Following the Windows setup instructions will fail at `uv run python run.py`. |
| F10 | Live model/agent end-to-end verification | **PARTIAL** | Keys exist in ignored local `backend/.env`; live DB has 1 report, 5 threads, 120 checkpoints from prior use; this audit did not make live LLM calls | Cannot claim current provider/auth correctness without exercising it. No GPU/model verification possible. |

---

## 5. Per-Component Deep Dive

### 5.1 Coordinator / main agent

- **Purpose:** Picker-facing conversational coordinator.
- **Inputs:** Chat message + `thread_id` + `picker_id`; Clerk-authenticated.
- **Outputs:** Assistant reply text; side effects in `reports`, checkpoints, and long-term memory.
- **Key code:** `SYSTEM_PROMPT` (`main_agent.py:29-43`), `AgentContext` (`:46-50`), `build_agent` (`:53-81`), `aget_agent` lazy singleton/pool (`:90-137`), `aget_checkpointer` (`:140-146`), `aclose_agent` (`:149-158`).
- **Wiring:** `create_deep_agent` with `subagents=[scrap_pipeline_agent]`, `tools=[estimate_price]`, `context_schema=AgentContext`, Postgres checkpointer/store, `CompositeBackend` routing `/memories/` to a per-picker namespace.
- **Config/env:** `XKIRO_API_KEY`, `XKIRO_BASE_URL`, `XKIRO_MODEL`, `DATABASE_URL`/`POSTGRES_URI`.
- **Status:** coordinator exists and is wired; routing behavior is prompt-only and untested. No offline reasoning loop.

### 5.2 Report-intake subagent and pipeline

- **Purpose:** Turn one sale message into a validated report and anomaly verdict.
- **Inputs:** A single `HumanMessage` containing the coordinator's task description.
- **Outputs:** `ReportDraft`, anomaly verdicts, `FinalReport` in state, persisted `reports` row, clarification/acceptance message.
- **Key code:** `report_intaker.py:11-19`; `pipeline.py:110-142` extraction, `:145-174` validation/routing, `:177-216` anomaly nodes, `:248-323` accept/finalize, `:342-378` graph.
- **Config/env:** `XKIRO_*`; `USE_LLM_REASONING`; `DATABASE_URL`.
- **Notable risk:** The isolated compiled subagent receives the parent's generated `description`, not the original user message (`deepagents/middleware/subagents.py:835`). The pipeline saves the first HumanMessage as `raw_text` (`pipeline.py:279-286`), so `reports.raw_text` is the coordinator's paraphrase, not necessarily verbatim picker text. The system prompt asks the coordinator not to rewrite details, but nothing enforces it.
- **Notable risk:** Multi-turn clarification has no merge logic. `report_draft` reads only the last message. The parent may or may not include prior context in the next subagent description; this is untested.

### 5.3 Anomaly detection

- **Purpose:** Decide whether a report is trustworthy.
- **Inputs:** `ReportDraft`.
- **Outputs:** `AnomalyVerdict` with `is_anomalous`, `reason`, `method`, `confidence`.
- **Key code:** `pipeline.py:177-216`, `:230-245` (`_resolve_verdict`), `:326-339` (routing).
- **Tier 1:** Neutral stub only. No median/baseline query.
- **Tier 2:** Neutral stub only. No Isolation Forest, no model, no sklearn.
- **Tier 3:** LLM judge implemented via `with_structured_output(LLMJudgment)`, but unreachable because Tier 1/2 never flag; also gated by `USE_LLM_REASONING=False` by default.
- **Tests:** The placeholder tests assert neutrality; the LLM test calls `llm_check_node` directly. No test proves the graph ever reaches `llm_check`.
- **Status:** graph scaffold + judge code, no functioning trust layer.

### 5.4 Price estimator

- **Purpose:** Return a fair price per kg for a material/location.
- **Inputs:** `material_str`, `location` (tool signature).
- **Outputs:** `PriceEstimate` dict: material, location, `estimated_price_per_kg=0.0`, `confidence=0.0`, `tier_used="seed"`, zero local/city counts.
- **Key code:** `tools/price_estimator.py:10-23`; schema `schemas/price.py:10-17`.
- **Config/env:** None; no DB access.
- **Status:** typed placeholder only. The `"seed"` label is inconsistent with the absence of seed data. No fallback chain, aggregation, API, or UI.

### 5.5 Classifier agent (material from photo)

- **Purpose:** Secondary helper when a picker is unsure what a material is.
- **Inputs/outputs:** Would need image upload + material prediction.
- **Key code:** None.
- **Status:** **NOT STARTED.** No module, no dependency, no dataset, no export.

### 5.6 Forecasting

- **Purpose:** Learn price trends over time.
- **Inputs/outputs:** Would need time-series report data.
- **Key code:** None.
- **Status:** **NOT STARTED**, consistent with the overview.

### 5.7 Authentication

- **Purpose:** Verify Clerk session tokens and derive picker identity.
- **Inputs:** `Authorization: Bearer <token>`.
- **Outputs:** `ClerkUser(user_id, session_id, claims)` or 401/503.
- **Key code:** `auth/dependencies.py:23-46` options/authorized-party logic, `:49-103` `require_auth`, `:106-120` `require_admin`.
- **Behavior:** 401 without bearer; 503 when Clerk is unconfigured; rejects unknown `azp`; accepts tokens without `azp`; uses `sub` as picker id.
- **Tests:** 5 tests in `test_auth.py`; 12 chat API tests include auth failures.
- **Config/env:** `CLERK_SECRET_KEY`, optional `CLERK_JWT_KEY`, `CLERK_AUTHORIZED_PARTIES`, `ADMIN_USER_IDS`.
- **Gap:** `require_admin` is unused; reviewer separation is not implemented.

### 5.8 Chat threads, history, and API

- **Purpose:** Server-owned per-picker conversations.
- **Key code:** `services/chat_threads.py:16-79`; `services/chat_history.py:28-56`; `api/routes/chat.py`.
- **Data:** `chat_threads` row per conversation; checkpoints per `thread_id`; memory per `picker_id`.
- **Ownership:** `get_thread`/`list_threads` filter by `user_id`; routes verify ownership before history/delete. `touch_thread` and `delete_thread` take only `thread_id` and rely on the route's prior ownership check — a weaker repository contract than the docstring claims.
- **Gaps:** no pagination; thread creation before agent invocation can leave empty threads; no idempotency for retries; no streaming; full graph state is loaded for history.

### 5.9 Reports persistence

- **Purpose:** Store finalized reports attributed to the authenticated picker.
- **Inputs:** `picker_id`, `raw_text`, `ReportDraft`, `AnomalyVerdict`.
- **Outputs:** `FinalReport` + inserted `reports` row.
- **Key code:** `services/reports.py:10-41`; `models/report.py:22-63`.
- **Behavior:** Rejects incomplete drafts; inserts `status="flagged"` if anomalous else `"accepted"`; uses `SessionLocal` directly (not an injected session).
- **Tests:** Persistence is always monkeypatched (`test_pipeline.py:63-83`), so the SQL path is untested.
- **Live DB evidence:** one `reports` row exists (`plastic`, 150.00/kg, 2 kg, PKR, accepted, method `deterministic`), showing the pipeline has run against a real DB at least once. This is not proof that the current code path is correct under all inputs.

### 5.10 Frontend

- **Purpose:** Clerk-authenticated chat UI with persisted threads.
- **Key code:** `main.tsx` (ClerkProvider), `App.tsx` (landing/Clerk gate), `Chat.tsx` (live/demo state), `ChatView.tsx` (layout/composer/delete dialog), `lib/api.ts` (fetch client), `lib/useAccessToken.ts`, `lib/theme.ts`.
- **Features:** sign-in, thread list/search/grouping, new chat, history load, delete with confirmation, retry banner, copy message, markdown/table/code rendering, mobile drawer, dark/light theme, landing page, dev-only demo mode.
- **Gaps:** no voice, no camera, no price/market view, no offline/PWA, no tests, no e2e. Text-only.
- **Config/env:** `VITE_API_BASE_URL`, `VITE_CLERK_PUBLISHABLE_KEY`, optional `VITE_DEMO_MODE`.
- **Quality:** build passes; lint has 3 non-blocking React warnings.

### 5.11 Configuration and environment

- **Key code:** `core/config.py:11-44`.
- **Env vars:** `ENVIRONMENT`, `DEBUG`, `DATABASE_URL`, `DATABASE_ECHO`, `XKIRO_API_KEY`, `XKIRO_BASE_URL`, `XKIRO_MODEL`, `USE_LLM_REASONING`, `CORS_ORIGINS`, `CLERK_SECRET_KEY`, `CLERK_JWT_KEY`, `CLERK_AUTHORIZED_PARTIES`, `ADMIN_USER_IDS`.
- **Behavior:** `get_settings()` is `lru_cache`d; some modules (`db/session.py`, `workflows/pipeline.py`) call it at import time, so `.env`/environment changes require a process restart and tests can inherit local values.
- **Gap:** `USE_LLM_REASONING` is not documented in `README.md` or `.env.example`.

### 5.12 Operations / deployment

- **Present:** `docker-compose.yml` for PostgreSQL 17; `.env.example`; Alembic migrations; `uv.lock`.
- **Absent:** backend/frontend Dockerfiles, CI, production process config, reverse proxy, TLS, backup/retention jobs, observability/metrics, rate limiting.
- **Docs drift:** `README.md` still documents `run.py`, removed in commit `868fb96`; `app/loops.py` is consequently dead code. Following the documented Windows setup will fail.
- **Live local DB:** Docker Compose reports the DB healthy; Alembic is at `0002_create_chat_threads`.

### 5.13 Tests

- **Backend:** 38 tests; all pass. Unit-level coverage is decent for auth, validation, routing, and fake-agent API behavior.
- **Frontend:** none.
- **Integration:** none against real PostgreSQL, Alembic, LangGraph checkpointer/store, or a live model.
- **Consequence:** the most important wiring risks (agent → subagent, subagent → persistence, checkpointer → history, estimator → reports) are not covered.

---

## 6. Data Layer

### 6.1 Tables

| Table | Created by | Purpose | Key columns / constraints |
|---|---|---|---|
| `reports` | Alembic `0001_create_final_reports` | Finalized sale reports | `id` UUID PK; `picker_id` String(128) indexed; `raw_text` Text; `material`; `price_per_kg` Numeric(12,2) > 0; `quantity_kg` Numeric(12,3) > 0; `currency` String(3) default PKR; `city`, `area`; `confidence` Float; `is_anomalous` Bool; `anomaly_reason` Text; `anomaly_method` String(20); `status` String(20) indexed; `created_at`, `updated_at` timestamptz. Indexes: `(picker_id, created_at)`, `picker_id`, `status`. |
| `chat_threads` | Alembic `0002_create_chat_threads` | Server-owned conversation threads | `id` UUID PK; `user_id` String(128) indexed; `title` String(200) default "New chat"; `created_at`, `updated_at`. Index `(user_id, updated_at)`. |
| `checkpoints` | LangGraph `AsyncPostgresSaver.setup()` | Graph checkpoints | Managed by LangGraph. |
| `checkpoint_blobs` | LangGraph setup | Checkpoint channel blobs | Managed by LangGraph. |
| `checkpoint_writes` | LangGraph setup | Pending checkpoint writes | Managed by LangGraph. |
| `checkpoint_migrations` | LangGraph setup | Checkpoint schema version | Managed by LangGraph. |
| `store` | LangGraph `AsyncPostgresStore.setup()` | Long-term memory/files | Managed by LangGraph; per-picker namespace. |
| `store_migrations` | LangGraph setup | Store schema version | Managed by LangGraph. |
| `alembic_version` | Alembic | Migration state | Currently `0002_create_chat_threads`. |

**Missing tables:** `users`/pickers, `seed_prices`, `market_prices`/aggregates, `dealer_quotes`, `anomaly_flags` (separate audit trail), `review_actions`, `report_revisions`, `voice_notes`, `classifier_predictions`, `forecasts`.

### 6.2 Relationships

- **No database foreign keys.** `reports.picker_id` and `chat_threads.user_id` are logical references to the Clerk `sub`, not FK-constrained rows.
- **No joins anywhere.** Reports are write-only; threads are read/write; checkpoints/store are addressed by `thread_id`/`picker_id` namespaces.
- **Attribution:** reports use the authenticated picker id, not the thread id (`pipeline.py:219-227`). Tests cover the preference for `picker_id` (`test_finalize_report_prefers_authenticated_picker_id`), but the fallback to `thread_id` when `picker_id` is absent is a misattribution risk if config propagation ever fails.

### 6.3 Repositories / services

- `ChatThreadStore` (`services/chat_threads.py:16`): create/list/get/touch/delete. `list_threads` and `get_thread` are user-scoped; `touch_thread` and `delete_thread` are not.
- `save_report` (`services/reports.py:10`): write-only insert; no read/update/list/aggregate repository for reports.
- `load_thread_messages` (`services/chat_history.py:28`): reads graph state via `aget_state`.
- No seed-price loader, no market aggregation service, no review service, no retention service.

### 6.4 Live database verification

- `docker compose ps`: `scrap_sense-db-1` running, healthy, port 5432.
- `uv run alembic current`: `0002_create_chat_threads (head)`.
- Tables present: `alembic_version`, `chat_threads`, `checkpoint_blobs`, `checkpoint_migrations`, `checkpoint_writes`, `checkpoints`, `reports`, `store`, `store_migrations`.
- Row counts: `reports` = 1, `chat_threads` = 5, `checkpoints` = 120, `store` = 1.
- Sample report fields: `plastic`, 150.00 PKR/kg, 2.000 kg, `anomaly_method=deterministic`, `status=accepted`, empty `city`/`area`.
- These are local development rows; they are not production data and were not created by this audit.

---

## 7. API Surface

All routes are mounted under `/api/v1` (`app/api/router.py`). Chat routes require `Authorization: Bearer <Clerk session token>`. Health routes are unauthenticated. Interactive docs are at `/docs`.

| Method | Path | Auth | Request shape | Response shape | Tested? |
|---|---|---|---|---|---|
| `POST` | `/api/v1/chat` | Clerk bearer | `{message: str (1..4000), thread_id?: UUID}` | `{user_id: str, thread_id: UUID, reply: str}` | Yes: happy path, new/owned thread, foreign thread 404, empty message 422, missing auth 401, Clerk unconfigured 503, agent failure 503, empty reply 502. Agent faked. |
| `GET` | `/api/v1/chat/threads` | Clerk bearer | none | `[{id, title, created_at, updated_at}]` | Yes: scoped to authenticated user. |
| `POST` | `/api/v1/chat/threads` | Clerk bearer | optional `{title?: str (1..200)}` | `{id, title, created_at, updated_at}` (201) | Yes: empty body creates default "New chat". |
| `GET` | `/api/v1/chat/threads/{thread_id}/messages` | Clerk bearer | path UUID | `{thread_id, messages: [{role: "user"\|"assistant", content: str}]}` | Yes: owned/foreign 404, history shape. Checkpointer faked. |
| `DELETE` | `/api/v1/chat/threads/{thread_id}` | Clerk bearer | path UUID | 204 no content | Yes: owned deletion, foreign 404, checkpoint deletion recorded. |
| `GET` | `/api/v1/health/live` | none | none | `{status: "ok", version: str}` | Yes. |
| `GET` | `/api/v1/health/ready` | none | none | `{status: "ok"\|"degraded", database: "ok"\|"unavailable", version: str}`; 503 when DB unavailable | Yes: both DB states. |

**Not present:** report submission/list/review endpoints, price-estimate endpoint, classifier/image endpoint, voice/transcription endpoint, admin/reviewer endpoints, SSE/streaming endpoint, WebSocket, batch/import endpoint.

**Error handling:** consistent 401/404/422/502/503 on chat; health returns 503 without leaking DB details. No rate-limit responses.

---

## 8. Test Report

### Commands and results

```powershell
# Backend test suite
cd D:\scrap_sense\backend
uv run pytest -o addopts="" --tb=short
# 38 collected, 38 passed, 0 failed, 0 skipped, 0 collection errors
# Completed in 22.98s
```

Per-file results:

| Test file | Tests | Result |
|---|---:|---|
| `tests/test_auth.py` | 5 | Passed |
| `tests/test_chat_api.py` | 12 | Passed |
| `tests/test_config.py` | 2 | Passed |
| `tests/test_health.py` | 3 | Passed |
| `tests/test_main_agent.py` | 3 | Passed |
| `tests/test_pipeline.py` | 12 | Passed |
| `tests/test_price_estimator.py` | 1 | Passed |

Other verification:

```powershell
cd D:\scrap_sense\backend
uv run ruff check .
# 1 error: I001 unsorted import block in app/agents/main_agent.py:5

uv run mypy app tests
# Success: no issues found in 44 source files

cd D:\scrap_sense\frontend
npm run lint
# 0 errors, 3 warnings (react/set-state-in-effect at Chat.tsx:176, Chat.tsx:205, ChatView.tsx:531)

npm run build
# Success: tsc -b && vite build; 95 modules transformed
```

Database/ops verification:

```powershell
docker compose ps
# db service running and healthy

cd D:\scrap_sense\backend
uv run alembic current
# 0002_create_chat_threads (head)
```

### What is tested well

- Auth token handling: missing bearer, unknown `azp`, authorized `azp`, missing `azp`, unconfigured Clerk.
- User ownership boundaries: foreign thread read/append/delete returns 404; thread list is scoped.
- Chat API failure modes: 422, 401, 503, 502.
- Pipeline extraction success/failure fallback; missing-field clarification; routing; neutral tiers; direct LLM judge; accept/flag summary; finalize persistence call and picker-id preference.
- Health endpoints with healthy/unavailable DB fakes.
- Agent wiring (subagent list, tools, context schema, checkpointer/store/memory).
- Price placeholder contract.

### Coverage gaps

- **No real PostgreSQL test.** `test_chat_api.py` uses `FakeThreadStore` and `FakeCheckpointer`; `test_pipeline.py` monkeypatches `save_report`.
- **No Alembic migration test.**
- **No real LangGraph checkpointer/store test.**
- **No live LLM/provider test.** Provider/key/network behavior unverified in this audit.
- **No agent-routing test.** Nothing proves a sale message reaches `scrap_report_pipeline` or a price question calls `estimate_price`.
- **No multi-turn clarification test.**
- **No report read/aggregation tests** because no such code exists.
- **No frontend tests** (no test script, no component/e2e tests).
- **No security tests** for rate limiting, PII redaction, retention, or prompt injection.
- **No performance/load tests.**
- **No classifier/forecasting tests** because those components do not exist.

### Audit limitations

- Live LLM calls were intentionally not made. Both `XKIRO_API_KEY` and `CLERK_SECRET_KEY` are present in the ignored local `backend/.env`, but no external call was executed.
- GPU/model training cannot be verified because there is no ML code or artifact.
- Field data, picker testing, dealer visits, and demo-video evidence cannot be verified from the repository; none is present.
- The live DB contains prior development rows; their presence proves the persistence path has been exercised manually, not that the current test suite covers it.

---

## 9. Tech Debt and Risks

### High

1. **Core product value is absent.** No aggregation, no seed prices, no real estimate. `estimate_price()` always returns `0.0` (`tools/price_estimator.py:10-23`). A picker cannot get a defensible number.
2. **Anomaly trust layer is non-functional.** Tier 1/2 are neutral stubs (`pipeline.py:177-186`); Tier 3 is unreachable (`pipeline.py:330-339`). Every valid report is accepted.
3. **The LLM judge is effectively dead code in the graph.** Tests call `llm_check_node` directly (`test_pipeline.py::test_llm_check_uses_judgment`), which hides the fact that no graph path reaches it.
4. **`reports.raw_text` may not be the picker's text.** The isolated compiled subagent receives the coordinator's `description` (`deepagents/middleware/subagents.py:835`), and the pipeline saves the first HumanMessage as `raw_text` (`pipeline.py:279-286`). This weakens provenance/audit claims.
5. **No integration coverage.** All DB/agent boundaries are faked; the real wiring could regress without any failing test.
6. **Docs/dev runner drift.** README instructs `uv run python run.py` (lines 48, 68, 82), but `backend/run.py` was deleted in commit `868fb96`. Setup fails on the documented path; `app/loops.py` is dead code.
7. **Lint gate is red.** `ruff check .` fails `I001` in `main_agent.py:5`. No CI catches this.

### Medium

8. **No idempotency.** A client retry (`Chat.tsx` retry path) can create another thread and/or duplicate report, because the API has no idempotency key or deduplication.
9. **Synchronous, non-streaming LLM requests.** `POST /chat` blocks for the whole agent run (possibly extraction + judge), with no explicit timeout/retry policy. No SSE. Poor UX on weak connections.
10. **PII handling is only documented, not enforced.** Raw messages go to the provider and are stored in checkpoints/`raw_text`; no redaction, retention, encryption, or memory deletion. `area` can contain a precise address.
11. **Location granularity is unenforced.** `city`/`area` are free text; no validation that location is neighborhood/city level.
12. **Weak repository contracts for threads.** `ChatThreadStore.touch_thread`/`delete_thread` take only `thread_id` and rely on prior route authorization; future callers could bypass ownership.
13. **Picker id fallback.** `_picker_id_from_config` falls back to `thread_id` if `picker_id` is absent (`pipeline.py:219-227`), which could misattribute reports if config propagation breaks.
14. **Clarification is single-turn.** No merge of a follow-up reply with an earlier draft; extraction reads only the last message (`pipeline.py:112-113`).
15. **Dead/mismatched schemas.** `ReportCreate`, `ReportStatusUpdate`, `ReportRead`, `ReportSubmissionResponse`, `PriceEstimateRequest`, `PriceEstimateResponse` are unused. `ReportRead` expects fields the model does not have.
16. **Reviewer scaffolding is incomplete.** `require_admin` and `ADMIN_USER_IDS` exist but no route uses them.
17. **No pagination.** Thread list and full history are unbounded; `load_thread_messages` reads the entire graph state.
18. **Empty-thread leak on failure.** The thread row is created before agent invocation; a 503 leaves an empty thread.
19. **Persistence failure is swallowed into a user message.** `finalize_report_node` catches exceptions and returns text (`pipeline.py:289-307`), with no retry/outbox/metric.
20. **No observability.** Logs only; no metrics, tracing, alerting, or request IDs. Health readiness checks DB only, not the LLM/agent.

### Low

21. **Misleading `tier_used="seed"` while no seed data exists** (`tools/price_estimator.py:19`).
22. **Stale docstring:** `app/llm.py:1` says "KapraOS AI layer" — unrelated copy-paste.
23. **Mojibake character** in the numeric regex in `frontend/src/components/chat/MessageText.tsx` (`String.raw` contains `�`), which may break some currency matching.
24. **Duplicate/unpinned `requirements.txt`** alongside `pyproject.toml` and `uv.lock`.
25. **`USE_LLM_REASONING` undocumented** in README and `.env.example`.
26. **Python version drift:** overview says 3.11+, project requires 3.12.
27. **`pydantic[email]` dependency** with no email usage.
28. **Committed local artifacts** (`frontend/dev.log`, `dev.err.log`) are ignored by git but present in the working tree; harmless, but noise.
29. **No `dist`/build reproducibility check in CI** because there is no CI.
30. **Frontend lint warnings** (`set-state-in-effect`) are benign but should be cleaned before adding tests.

### Security notes

- **Good:** all chat routes require Clerk auth; ownership checks prevent cross-user reads/deletes; CORS is an explicit allowlist; SQLAlchemy uses parameterized queries; `.env` files are gitignored and not tracked.
- **Risk:** prompt injection via raw message into extraction/judge prompts; structured output limits fields but not malicious free-text content.
- **Risk:** no rate limiting or abuse control; no request size beyond 4000 characters; no idempotency.
- **Risk:** raw PII reaches the model provider and is stored unencrypted; no redaction or retention.
- **Risk:** no encryption-at-rest policy, no backup/restore procedure.

---

## 10. Divergences and Extras vs. the Overview

### Divergences

1. **Coordinator built on Deep Agents, not plain LangGraph.** The overview names LangGraph only. `deepagents` adds a `task` tool, isolated subagents, a filesystem/memory middleware, and prompt conventions not described in the spec. This is a reasonable implementation choice, but it changes routing and memory semantics.
2. **No explicit "Price-Estimator Agent."** The overview's architecture shows a price-estimator agent on the "what's this worth?" path. In code it is a plain function tool (`estimate_price`) called by the coordinator, returning a hardcoded zero.
3. **Text-only web chat vs. "picker app (camera + voice)."** The built product is a responsive web chat with a text composer. There is no camera capture, no audio recording, no Urdu voice interface, and no mobile app.
4. **Anomaly tiers are stubs, not implementations.** The overview describes Tier 1 arithmetic and Tier 2 Isolation Forest; code has neutral placeholder nodes. Tier 3 exists but is unreachable. The overview's §9 admits the stubs, so this is an honest gap rather than hidden overclaiming.
5. **No convergence of report and price paths.** The overview shows trusted reports feeding the estimator through a shared data store. Reports are stored, but the estimator never reads them.
6. **No offline capability.** The overview motivates the architecture with unreliable connectivity and offline model export; the current app requires PostgreSQL, Clerk, and a live xKiro call for chat.
7. **`run.py` removed but still documented.** README's layout and setup commands are stale. The commit `868fb96` removed `backend/run.py`; `app/loops.py` remains as unused residue.
8. **`tier_used="seed"` without seed data.** The overview says the estimator returns `0.0` with zero confidence and no seed file exists; the tool labels the result as the `"seed"` tier anyway. That is a small but misleading divergence.
9. **Reviewer scaffolding not in the overview.** `require_admin`, `ADMIN_USER_IDS`, and `ReportStatusUpdate` suggest a review workflow; the overview only mentions reviewer/role separation as future work.
10. **Python version.** Overview says 3.11+; `pyproject.toml` requires >=3.12.
11. **Chat thread model is more built out than the overview's brief mention.** Server-owned UUID threads, list/search/delete, per-picker memory, and deletion of checkpoints match the overview's §9 claims and are a strength.

### Extras (present in code, not planned in the overview)

- Full chat-thread CRUD with titles, ordering, search, grouping, and a delete confirmation dialog.
- Landing page with a sample ledger labeled "Illustration only."
- Dev-only demo mode with four synthetic conversations and regex-generated replies (`frontend/src/components/Chat.tsx:23-152`).
- Light/dark theme toggle with localStorage + system preference.
- A small markdown renderer supporting headings, lists, code fences, quotes, tables, and rules.
- Message copy-to-clipboard, retry banner, jump-to-latest, mobile drawer, responsive composer.
- `deepagents` as an orchestration library; xKiro as a specific OpenAI-compatible provider.
- `require_admin` + `ADMIN_USER_IDS` (unused) and unused report-review/status schemas.
- Duplicate `requirements.txt` alongside `pyproject.toml`/`uv.lock`.
- Local dev logs (`frontend/dev.log`, `frontend/dev.err.log`), gitignored.
- No SSE/streaming, WebSocket, or push transport (not in the overview; noted for completeness).

---

## 11. Recommended Next Milestones

These are intentionally batched. Each has a product outcome and a test-based exit criterion. Order is by priority: make the product do its core job, then make it trustworthy, then make it operable, then add capture/ML.

### M1 — Real price intelligence: seed data + aggregation + estimator + API/UI

**Why:** Without this, ScrapSense does not solve the user's problem.

**Scope:**
- Define `app/data/seed_prices.json` with material, region, `price_per_kg`/`range`, `source`, `collection_date`, `collector`; add a typed loader and validation.
- Add aggregation queries over `reports` (local area → city → seed fallback) with minimum-sample thresholds and confidence based on sample size/recency.
- Replace `estimate_price()` with the real fallback chain; remove the misleading `"seed"` label when no seed exists.
- Add a `GET /api/v1/prices/estimate?material=&location=` endpoint (and/or a dedicated price response in chat) plus a minimal price display in the UI.
- Add a market/aggregation read model or service; document that only accepted reports count.
- Add seed data provenance and a `seed_prices` table or file-based loader. Do not invent prices; if no seed data exists, keep returning zero/unknown with a clear reason.

**Exit criteria:**
- New tests cover: seed-only estimate, local-report estimate, city fallback, blended estimate, insufficient-data behavior, flagged reports excluded, provenance fields present.
- An integration test against real PostgreSQL inserts reports and verifies the estimate.
- `uv run pytest`, `uv run ruff check .`, `uv run mypy app tests` all pass; frontend build passes.
- Manual check: a picker asking for a material with seed data gets a nonzero estimate with confidence and sample counts.

### M2 — Trust layer: deterministic median + Isolation Forest + LLM tier + review status

**Why:** Aggregating untrusted reports can make the price worse, not better.

**Scope:**
- Implement Tier 1: recent median/robust range per material+region with minimum sample count; return a real verdict and reason.
- Implement Tier 2: train/save an Isolation Forest on price+quantity; ship a model artifact or a documented training script; skip/dormant until the threshold is met, exactly as the overview describes.
- Wire Tier 3 so `route_after_ml` actually reaches `llm_check_node` for flagged reports; add a timeout/fallback and cost guard.
- Persist reviewable flags; implement the existing `ReportStatusUpdate` schema and an admin/reviewer route using `require_admin` (or delete the dead scaffolding).
- Ensure flagged reports never influence estimates.

**Exit criteria:**
- Tests cover each tier independently and the full graph path deterministic → ml → llm → finalize with a flagged report.
- A test proves an accepted report enters aggregation and a flagged report does not.
- Model artifact or training script is committed with a reproducible command.
- All backend gates and type checks pass.

### M3 — Integration, correctness, and operational hardening

**Why:** The current suite passes while the real wiring is untested; the product needs a trustworthy base before field use.

**Scope:**
- Add a real PostgreSQL test fixture (test database/transaction rollback) covering migrations, `ChatThreadStore`, `save_report`, and history.
- Add a live-agent smoke test behind an opt-in flag (or a fake provider) that proves a sale message reaches the pipeline and a price question calls `estimate_price`.
- Add idempotency/deduplication for chat retries; decide whether thread creation happens after a successful agent call.
- Add request timeouts/retries for LLM calls; add structured logs/request IDs; extend readiness to include agent/provider configuration.
- Fix `run.py` docs (either restore a corrected runner or remove the instructions); delete or use `loops.py`.
- Fix the ruff `I001` error and the 3 frontend lint warnings.
- Add backend/frontend Dockerfiles and a CI workflow running pytest, ruff, mypy, frontend lint, and build.

**Exit criteria:**
- CI is green on the default branch.
- At least one integration test touches real PostgreSQL and Alembic.
- The documented setup works from a clean checkout on Windows and Linux.
- No dead `run.py` reference remains.

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

**Why:** The overview correctly says an RNN on a handful of reports would memorize noise. This is a later upgrade, not an MVP.

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
