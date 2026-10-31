# ScrapSense Security and Privacy Audit

- **Audit date:** 2026-10-31
- **Scope:** backend, frontend, persistence configuration, and tracked documentation in this repository
- **Method:** code inspection, framework-internal inspection (`langgraph`, `deepagents`), dependency and secret-hygiene checks, and verification runs
- **Out of scope:** live provider data-handling terms, production infrastructure, database/backup encryption, and operational access control outside this repository

This report distinguishes **implemented behavior**, **documented limitations**, and **proposed policy**. Proposed retention periods are not implemented.

## 1. Executive summary

ScrapSense is a pseudonymous, account-linked data system, not an anonymous one. A report is stored against the Clerk `sub` claim, the raw picker message is stored in `reports.raw_text` and in LangGraph checkpoints, and chat messages are sent to the configured external model provider. The reviewer queue is identity-minimized, but the underlying rows still contain the picker id and raw text.

The audit found one clear user-control gap: deleting a chat thread removed its checkpoints but left the picker's long-term agent memory in place, and there was no erasure path. That gap is now fixed with `DELETE /api/v1/chat/memory`. The audit also removed a misleading "anonymous" claim from the UI and documentation, removed a picker id from an info-level log, and made thread repository writes user-scoped. Report rows still have no retention policy or user-facing erasure path; that remains open.

No changes were made to the price estimation algorithm, Tier 1/2/3 anomaly logic, original picker-message provenance, or Clerk attribution semantics.

## 2. Data inventory

| Data | Where it is stored | Identifier / linkage | Access path | Actual retention |
| --- | --- | --- | --- | --- |
| Clerk session token | Request `Authorization: Bearer` header; not persisted by this app | Clerk `sub`, `sid`, `azp` claims | Clerk SDK verification in `require_auth` | Provider/session policy |
| Picker id (Clerk `sub`) | `reports.picker_id`, `chat_threads.user_id`, memory store namespace, `reviewed_by` | Direct account link | Authenticated owner; admin review metadata | Until deleted or manually removed |
| Raw picker message | `reports.raw_text`; LangGraph checkpoints (`messages`, `original_message`); sent to xKiro | Linked to picker id and thread id | Owner, application code, model provider | Indefinite in reports; thread checkpoints until thread deletion |
| Extracted report fields | `reports` row (material, price/kg, quantity, currency, city, area, observed_at, confidence, anomaly fields) | `picker_id` | Owner indirectly; reviewer projection; price aggregation | Indefinite |
| Thread title | `chat_threads.title` (first 80 characters of the first message, or a default) | `user_id` | Owner's thread list | Until thread deletion |
| Chat history | LangGraph checkpoints keyed by server-generated thread UUID | Thread id; ownership checked against `chat_threads` | Owner via history endpoint; agent | Until thread deletion |
| Long-term agent notes | Postgres store namespace `(picker_id,)`, logical path `/memories/picker_notes.md` | Picker id | Agent at runtime; no read endpoint | Until `DELETE /api/v1/chat/memory`; no automatic expiry |
| Reviewer decision | `reports.status`, `reviewed_at`, `reviewed_by` | Picker id and admin id | Admin-only review API | With the report row |
| Reviewer queue projection | API response only | None (omits picker id and raw text) | `ADMIN_USER_IDS` | Not persisted separately |
| Application logs | Deployment log sink | Report ids; picker id removed from the reviewed info log | Operators | Deployment-dependent |

## 3. Data flows and trust boundaries

1. **Authentication.** The frontend sends a Clerk bearer token. `require_auth` verifies it with the Clerk SDK and derives `ClerkUser.user_id` from `sub`. Admin routes additionally require the id to be in `ADMIN_USER_IDS`.
2. **Chat.** `POST /api/v1/chat` creates or loads an owned thread, passes the verbatim message to the deep agent, and persists LangGraph checkpoints under the thread UUID. The picker id is passed separately as `AgentContext.picker_id`.
3. **Report intake.** The subagent extracts structured fields, validates them deterministically, compares them with historical reports, and persists `raw_text` plus `picker_id` in `reports`.
4. **Long-term memory.** The agent may write notes through `StoreBackend` under namespace `(picker_id,)`. The logical path is `/memories/picker_notes.md`; after the composite backend strips the route prefix, the store key is `/picker_notes.md`.
5. **External model.** The raw message and extraction/review prompts are sent to the configured OpenAI-compatible xKiro endpoint. Provider-side retention and training use were not verified in this audit.
6. **Review.** Admins can read a projection that omits picker identity, Clerk identifiers, raw text, and thread information. The database row still contains those fields.
7. **Deletion.** Thread deletion removes checkpoints and the thread row. Memory deletion removes only the picker's memory namespace. Report rows are separate and are not deleted by either action.

## 4. Findings

### F1. No long-term memory erasure path (High) — fixed

**Before:** `DELETE /api/v1/chat/threads/{thread_id}` called `checkpointer.adelete_thread(...)` and deleted the `chat_threads` row, but the per-picker namespace in `AsyncPostgresStore` was untouched. A picker could delete every conversation and still have `/memories/picker_notes.md` injected into the next chat.

**Now:** `DELETE /api/v1/chat/memory` erases every store item in the authenticated picker's namespace. The implementation is idempotent and does not touch other pickers or report rows.

- `backend/app/api/routes/chat.py:244` — authenticated memory-erasure route
- `backend/app/services/chat_memory.py:13` — namespace-scoped deletion
- `backend/app/agents/main_agent.py:48` — shared namespace helper
- Tests: `backend/tests/test_chat_memory.py`, `backend/tests/test_chat_api.py`

**Residual:** the store deletion is tested with fakes, not against a live `AsyncPostgresStore`.

### F2. Misleading "anonymous" claims (High) — fixed

**Before:** the UI said "Reports are anonymous" and "Your name is never attached." That is inaccurate: `reports.picker_id` is the Clerk `sub` (a stable account identifier), and the raw message can contain a name, phone number, or precise address.

**Now:** the UI and documentation call the identifier **pseudonymous** and warn that raw messages may contain personal details.

- `frontend/src/components/chat/ChatView.tsx:211`
- `frontend/src/App.tsx:123`
- `PRODUCT.md`, `ScrapSense_Project_Overview.md`, `README.md`

### F3. Reports have no retention or self-service erasure (High) — open

`reports.raw_text` and `reports.picker_id` are retained indefinitely. There is no expiry job, no user-facing report-deletion endpoint, and no anonymization-on-request path. Deleting a thread or memory does not remove reports. The reviewer projection is identity-minimized, but the stored row is not.

This is a policy and product decision, not a bug that can be fixed without deciding how deletion affects price history. A proposed policy is in Section 6; it is **not implemented**.

### F4. Raw messages go to an external model provider (Medium) — disclosed, not mitigated

`POST /api/v1/chat` sends the picker's message verbatim to xKiro, and suspicious reports may send extraction/review prompts. No redaction, local-only mode, or provider-side data-processing agreement is configured or verified in this repository.

**Mitigation now:** UI and README warn users not to include names or phone numbers. **Open:** optional PII redaction, provider due diligence, and a documented retention/data-use agreement.

### F5. No rate limiting or durable abuse controls (Medium) — open

There is no rate limit, per-user quota, idempotency key, or LLM timeout/retry policy on the chat route. A retried request can create another thread or duplicate a report. Request body size is bounded by the chat schema, but repeated LLM calls can still be abused. This is an availability/cost risk and an indirect privacy risk through excessive data collection.

### F6. Picker id in an info-level log (Low) — fixed

`finalize_report_node` logged the picker id at info level. That is an account identifier in the operational log stream. The log now records only the report id.

- `backend/app/workflows/pipeline.py:614`

Other reviewed logs do not include raw message text: extraction logs the message length, not its content. Authentication logs the Clerk failure reason and the `azp` value, not the token. Deployment access logs and provider logs are outside this repository and were not audited.

### F7. Weak thread repository contracts (Low) — fixed

`touch_thread` and `delete_thread` previously accepted only a thread id and relied on the route's prior ownership check. They now require `user_id` and filter on it, so an internal caller cannot mutate another user's thread by id alone.

- `backend/app/services/chat_threads.py:57` and `:77`
- `backend/app/api/routes/chat.py:168` and `:239`

### F8. Secret hygiene (Informational) — verified

- Only `.env.example` files are tracked by git; local `.env` files are ignored.
- `XKIRO_API_KEY`, `CLERK_SECRET_KEY`, and `CLERK_JWT_KEY` are represented as `SecretStr` in settings.
- The local `backend/.env` has `CLERK_JWT_KEY` empty and `CLERK_SECRET_KEY` set; Clerk can verify with the secret key. No secret values were printed during this audit.
- `docker-compose.yml` contains development database credentials. Those are not production secrets but must not be reused in deployment.

### F9. Authentication, CORS, and ownership (Informational) — verified

- Chat, price, and memory routes require a Clerk bearer token.
- Reviewer routes require both authentication and membership in `ADMIN_USER_IDS`.
- Thread list/get/history/delete are ownership-scoped; foreign access returns `404`.
- CORS uses an explicit origin allowlist, `allow_credentials=False`, and only `Authorization`/`Content-Type` request headers.
- SQLAlchemy queries are parameterized.
- No public report endpoint exists.

### F10. Encryption at rest and backups (Medium) — open

Application-level storage is unencrypted: report text, checkpoints, and memory are plaintext in PostgreSQL. Database encryption, volume encryption, backup encryption, and backup retention are deployment responsibilities and are not configured here. A database or backup compromise exposes chat history, notes, and raw report text.

### F11. No in-app memory-erasure control (Low) — open

The backend endpoint exists and is documented, but the frontend has no button or settings screen for it. Users can erase notes only through the API or an operator. The UI copy now avoids claiming anonymity, but a visible control would make the privacy story complete.

### F12. Thread titles can contain message content (Low) — accepted

The first 80 characters of the first message are stored as the thread title. Titles are visible only to the owner's thread list, but they can contain PII. This is a UX trade-off, not a cross-user leak. A future change could use a material/neutral title or a shorter summary.

## 5. Implemented changes

| Change | Files | Tests |
| --- | --- | --- |
| Added `DELETE /api/v1/chat/memory` | `backend/app/api/routes/chat.py` | `test_chat_api.py` |
| Added namespace-scoped memory deletion service | `backend/app/services/chat_memory.py` | `test_chat_memory.py` |
| Exposed shared memory store and namespace helper | `backend/app/agents/main_agent.py` | `test_main_agent.py`, `test_chat_memory.py` |
| Made thread touch/delete user-scoped | `backend/app/services/chat_threads.py`, `chat.py` | `test_chat_api.py` |
| Removed picker id from info log | `backend/app/workflows/pipeline.py` | Existing pipeline tests |
| Corrected pseudonymity and PII wording | `frontend/src/App.tsx`, `ChatView.tsx`, `README.md`, `PRODUCT.md`, `ScrapSense_Project_Overview.md`, `IMPLEMENTATION_STATUS.md` | Frontend build/lint |

## 6. Proposed retention and deletion policy (not implemented)

These are recommendations. No scheduled job, TTL, or automatic expiry exists in the codebase.

| Data | Proposed retention | Proposed trigger / action |
| --- | --- | --- |
| Chat checkpoints | 30 days after last thread activity | Delete checkpoints and thread row |
| Long-term memory | Until user deletes, or 180 days after last activity | Delete the picker namespace |
| Raw report text | 90 days, or immediately after review when no longer needed | Clear `raw_text`; keep numeric fields for aggregates |
| Picker id on reports | Keep while needed for anomaly/trust; unlink on verified account erasure | Replace with a non-reversible pseudonym or delete the row |
| Application logs | 30 days | No raw text, tokens, or picker ids |
| Backups | 30 days, encrypted | Document restore and deletion limits |

Open policy questions: whether deleting a report should change historical price estimates; whether rejected/flagged raw text should have a shorter retention period; and how an account-erasure request should treat reports that already contributed to aggregates.

## 7. Verification

Run from `backend/`:

```text
uv run pytest          -> 202 passed in 55.73s
uv run ruff check .    -> All checks passed
uv run mypy app tests  -> Success: no issues found in 69 source files
```

Run from `frontend/`:

```text
npm run lint           -> 0 errors; 3 pre-existing react(set-state-in-effect) warnings
npm run build          -> success (tsc -b && vite build)
```

The PostgreSQL container was healthy and the integration tests ran. However, memory deletion was exercised with fake stores, and thread/checkpoint deletion is still faked in the chat API tests. No live `AsyncPostgresStore` deletion or live provider call was executed in this audit.

## 8. Recommended next steps

1. Add a visible "Forget saved notes" control, or fold memory erasure into an account-data settings screen.
2. Implement and test a retention job for checkpoints, memory, and raw report text.
3. Decide and document report-erasure semantics for aggregates, then add an authenticated erasure request path.
4. Add PII redaction or a local-only mode before sending messages to the provider.
5. Add per-user rate limits, LLM timeouts/retries, and an idempotency key.
6. Configure encrypted backups and document the backup retention/deletion boundary.
7. Add a live-store integration test for memory deletion and a live-provider smoke test behind an explicit opt-in flag.
