# ScrapSense — Project Overview

A price-transparency tool for waste pickers, built as an agentic AI system with a deliberate mix of LLM reasoning and deterministic code.

---

## 1. The Problem

### 1.1 Original framing (v1) — and why it didn't hold up

The first version of this idea was: point a phone camera at a piece of scrap, a CNN identifies the material, and the app returns what it's worth.

That idea broke down on one question: **who is this for?** A scrap dealer already knows exactly what materials are worth — that knowledge is literally their job and their income advantage. Building a material-identification tool for someone who's already the expert doesn't solve anything.

### 1.2 The real problem (v2)

The person genuinely at an information disadvantage isn't the dealer — it's the **picker** selling *to* the dealer. Experience teaches a picker to recognize plastic vs. metal, but it doesn't tell them what the price *should be right now*, and their only usual price reference is the same dealer they're negotiating with. That's not independent knowledge — it's just whatever that dealer has been willing to pay.

**This is a documented, real problem, not a hypothetical one.** Research on informal recycling markets found:
- Waste pickers earn a small fraction of what dealers and collection-center managers earn (roughly $745–750/month for pickers vs. $1,550–2,300/month for dealers/managers)
- In exploitative cases, pickers have been paid as little as **59.5% of their materials' true value**
- Middlemen have controlled both pricing and information, sometimes rigging weighing systems on top of underpricing

The closest historical parallel: fishermen and farmers in various developing regions using simple phone-based price-checking to stop being lowballed by isolated middlemen — once they could see what others were being paid nearby, the price gap closed. Same mechanism, applied here.

---

## 2. The Solution

Pickers report what they sold and for how much, after each sale. The system:
1. Turns that raw report into clean data
2. Checks the report isn't fake or manipulated before trusting it
3. Aggregates trustworthy reports into a fair-price estimate
4. Lets any picker check that estimate *before* their next sale, so they walk in with a number instead of walking in blind

Material identification (the original v1 idea) survives only as a **secondary helper feature** — useful when a picker isn't sure what something is, but not the core product.

---

## 3. System Architecture

```
Picker app (camera + voice, simple UI)
        |
        v
   Orchestrator  ── decides which path to take
        |
   ┌────┴────┐
   |         |
"I sold   "what's this
 this"      worth?"
   |         |
   v         v
Report-    Classifier agent (secondary)
Intake       |
Agent        v
   |     Price-Estimator Agent
   v         ^
Anomaly       |
Agent         |
   |          |
   v          |
Data Store ───┘
   |
   v
Forecasting Model (future — not built yet, see §5)
```

Two request types, two paths, converging on a shared data store.

---

## 4. The Agents

| Agent | Job | Uses an LLM? |
|---|---|---|
| **Orchestrator** | Routes requests; periodically reasons about data gaps offline | Yes, for offline gap analysis |
| **Report-intake agent** | Turns a picker's raw message (text or transcribed voice) into structured, validated data. Flags anything it's unsure about instead of guessing. | Yes — one structured-extraction call per report |
| **Anomaly agent** | Decides whether a report is trustworthy before it affects any price estimate. Three tiers: | Only Tier 3 |
| — Tier 1: Deterministic | Is the price wildly off the recent median? Free, instant. | No |
| — Tier 2: ML | Does price + quantity *together* look weird, even if price alone seems fine? (Isolation Forest) Free once trained. | No |
| — Tier 3: LLM | Only for reports Tier 1 or 2 already flagged — legitimate outlier or bad data? | Yes |
| **Price-estimator agent** | Fallback chain: local reports → city-wide reports → manually-collected seed price, blended by how much real data exists. Pure math. | No |
| **Classifier agent (secondary)** | Identifies material from a photo when a picker is unsure. Wraps a trained CNN. | No |

### Why not full LLM autonomy?

Considered and deliberately rejected. Every deterministic step above (anomaly Tiers 1–2, the price estimator, the classifier) is either arithmetic or a trained model doing a forward pass — asking an LLM to do that instead makes it slower, costlier, and dependent on a live connection, for zero accuracy benefit. Given the target user has unreliable connectivity and no money to spend on API calls on their behalf, an "LLM does everything" architecture doesn't just cost more — it stops working in the field for the exact person it's meant to help.

LLM reasoning is reserved for genuine judgment calls: parsing messy/ambiguous input, and adjudicating the ambiguous minority of flagged reports.

**A considered future upgrade, not yet built:** a reporter-trust agent that reasons about how much weight to give a report based on that picker's track record — a real judgment call, unlike the current "treat every report equally."

---

## 5. Models To Train

| Model | Purpose | Status |
|---|---|---|
| **CNN** (MobileNetV2 / EfficientNet-Lite) | Material classification from a photo (secondary feature) | Fine-tune on a public dataset (e.g. Kaggle garbage classification); export to TFLite/ONNX for offline use |
| **Isolation Forest** | Multivariate anomaly detection — catches price+quantity combinations that look wrong together even when price alone looks fine | Needs ~50+ real pooled reports before it's meaningful; sits dormant (skipped, not guessed) until then |
| **RNN/LSTM** (forecasting) | Would eventually replace the simple statistical price-estimator with real trend learning across time | **Not built.** With only a handful of early reports, an RNN would just memorize noise. The deterministic fallback chain is the correct MVP; this is a week 3–4 upgrade once there's real report volume |

---

## 6. Data Strategy

There's no existing dataset for "fair scrap prices by material and region" — it has to be built:
- **Week 1:** manually collect seed prices by visiting real scrap dealers/kabari points and photographing/interviewing — this seeds the price-estimator's fallback before any crowd reports exist
- **Ongoing:** picker-submitted reports accumulate the real dataset the anomaly ML tier and eventual forecasting model depend on
- **Cold-start problem to design around:** the app is only useful once enough pickers are reporting. Worth seeding the hackathon demo with a small set of realistic hardcoded reports rather than relying on live adoption during the build window

> **TODO (week-1 field data):** `app/data/seed_prices.json` currently records only a
> `source` string per material (and `range`/`price_per_kg`). It has **no
> collected-on date and no collector field**, so freshness and provenance cannot
> be audited. When real week-1 field data replaces it, every entry must carry an
> explicit **source**, **collection date**, and **collector** — do not invent
> values for the placeholder data in the meantime.

### Privacy notes
- Location stored at neighborhood/city level only — never precise GPS
- Reporter identity is an anonymized ID, never a real name or phone number in plaintext
- Any dealer-referencing data stays as anonymized aggregate signals only, never a named public callout — this protects the picker from retaliation risk, not just a legal formality

---

## 7. Tech Stack

- **Backend:** FastAPI, Python 3.11+
- **Orchestration:** LangGraph
- **ML:** PyTorch (CNN), scikit-learn (Isolation Forest)
- **Frontend:** plain HTML/JS, voice-first given the literacy/connectivity constraints
- **Data:** structured JSON/DB — seed prices, accumulated reports

---

## 8. Build Timeline (1-month hackathon)

- **Week 1:** Manual seed-data collection (real pickers/dealers) + report-intake pipeline + simple baseline estimator
- **Week 2:** Anomaly agent (all three tiers) + orchestrator reasoning loop + first real price-estimator wired to real data
- **Week 3:** Secondary CNN classifier + offline export (TFLite/ONNX) + voice interface (Urdu) + begin real field testing with pickers
- **Week 4:** Iterate on field feedback, polish, demo video, documentation

---

## 9. What's Already Built (as of this document)

- ✅ `report_intake_agent.py` — LLM extraction + deterministic validation, tested
- ✅ `anomaly_agent.py` — three-tier detection (deterministic / ML / LLM), toggleable, tested
- ✅ `ml_anomaly_model.py` — Isolation Forest training + scoring, tested
- ✅ `price_estimator_agent.py` — fallback chain + data-driven price range, tested
- ⬜ Classifier agent — only a stub exists (mock backend, no real CNN trained yet)
- ⬜ Orchestrator — not yet built
- ⬜ Real data store / repository backend — currently an in-memory mock for testing
- ⬜ Frontend

---

## 10. Open Questions / Next Steps

- Who specifically will provide week-1 seed data — which dealers/pickers, in what area of Multan?
- Cold-start: how will the demo simulate report volume that wouldn't realistically exist yet in a live app?
- **Demo data is synthetic.** `backend/scripts/seed_demo_reports.py` writes
  scoring-demo intake rows under `demo-seed-*` reporter ids and prints a
  **SYNTHETIC DEMO DATA** banner. It is for exercising the estimator tiers and
  the review queue only — never market truth, and never a substitute for week-1
  field data.
- Decide, based on real comparison data from `compare_modes()`, whether the LLM anomaly tier is worth its cost once enough reports exist to judge it fairly
- Orchestrator's offline gap-analysis loop still needs to be designed and built

---

## 11. Known Privacy Gaps (v2 intake reports)

The v2 intake-report path hashes reporter identifiers and transaction ids before
storage. The following gaps remain and are tracked honestly rather than hidden:

- **No authentication.** `reporter_identifier` on `POST /transactions` is
  client-supplied and spoofable; chat's `user_id` is an anonymous installation
  scope, not a verified identity. Real binding arrives with channel/auth work.
- **Raw source text is still stored.** `transactions.source_text` keeps the
  original message verbatim, which may itself contain a name, phone number or
  precise address. The v2 intake table does not remove it.
- **Delete-by-reporter is partial.** `delete_by_reporter(reporter_id)` erases
  matching `intake_reports` rows only. Matching `transactions` and `reviews`
  (and checkpoints) are not erased by it.
- **Known-area table is a placeholder.** `app/data/known_areas.json` is seeded
  for development; unknown text stays in `location`/`area_raw` only when it
  passes the short/non-address/non-coordinate rule.
- **No key management.** The HMAC secret comes from a single environment
  variable with no rotation, versioning or per-tenant key support. Generate it
  once with `python -c "import secrets; print(secrets.token_hex(32))"`, back it
  up, and **never rotate it**: rotating changes every `reporter_id` and
  submission hash, so existing records stop matching new ones. The app now fails
  fast at startup when the variable is unset.
- **Rejecting an auto-accepted report is a no-op.** The review→intake sync only
  moves `pending`/`flagged` intake rows. A report the pipeline auto-accepted
  (`needs_review=False`) stays `accepted` even if a human later rejects the
  transaction, so a human-rejected report can keep feeding price references. A
  later phase must let a reviewer override an auto-accepted report and remove it
  from the qualifying set.
