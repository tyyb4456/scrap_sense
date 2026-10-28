# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Waste pickers who sell recovered scrap to local dealers (kabaris). They use ScrapSense on a modern
smartphone in two moments of the same loop:

- **Before a sale** — checking what their material is plausibly worth, so they negotiate with a
  number instead of accepting whatever the dealer offers.
- **After a sale** — reporting what they sold and what they were paid, which is the data that
  makes the price reference exist for everyone else.

Dealers are not users. They already hold the pricing knowledge and information advantage the
product exists to offset.

## Product Purpose

ScrapSense closes the price-information gap between waste pickers and the dealers they sell to.
Pickers report sales; the system turns raw reports into clean data, checks each report before
trusting it, aggregates trustworthy reports into a fair-price estimate, and lets any picker check
that estimate before their next sale. Success means a picker walks into a negotiation knowing a
defensible price rather than guessing.

## Positioning

The price reference comes from pooled reports by pickers themselves, not from dealer quotes or a
single middleman's word. That is the mechanism a dealer-facing tool or a market-data vendor cannot
truthfully copy: the pickers being protected are the source of the data. Material identification
from a photo is a secondary helper for when a picker is unsure what something is, not the core
product.

## Operating Context

- Sales happen in person at local scrap collection points; the phone is the only tool in hand.
- Reports arrive as informal, messy language — often Roman Urdu or Urdu, e.g. "aaj maine 2 kilo
  plastic becha, 300 rupay mila" — not structured forms.
- Reported region is the Multan area per project documentation; the specific dealers and
  neighborhoods for seed data remain an open decision.
- Urdu voice input is the stated long-term ambition; the current release is an English UI carrying
  local-language content in conversation. Voice is not launch-critical.
- The product must work without spending the picker's money on model calls; LLM reasoning is
  reserved for parsing ambiguous input and adjudicating flagged reports.

## Capabilities and Constraints

Built today:

- Clerk-authenticated chat on the frontend and backend; the Clerk `sub` claim is the picker id.
- `POST /api/v1/chat` with server-owned, per-picker threads, persisted history, and deletion.
- A coordinator agent that delegates sale reports to a report-intake subagent.
- LLM structured extraction plus deterministic validation of intake reports, with uncertain fields
  flagged rather than guessed.
- Final reports persisted to PostgreSQL, attributed to the picker id (never the thread id).
- Deterministic price estimates from eligible reports with local -> city -> seed fallback, an
  authenticated `GET /api/v1/prices/estimate` endpoint, and a frontend price-check dialog.
- Deterministic intake validation plus a conservative median/MAD anomaly tier over comparable
  reports. Suspicious reports are persisted as `flagged`, excluded from estimates, and can only
  return to the eligible pool through a reviewer-only approval endpoint.
- An optional LLM review of statistically suspicious reports that cannot clear a statistical flag.
- A reviewer-only queue at `/review` with pagination, confirmation before approval or rejection,
  and explicit empty/access-denied/error states.
- Deterministic duplicate suppression for identical reports from one picker inside a short window.

Explicitly not built yet: verified seeded field prices (the loader and empty file exist), a trained
anomaly model (Tier 2 is disabled until real data satisfies the documented readiness threshold), the
material classifier CNN, image/camera capture, Urdu voice capture or transcription, forecasting,
reporter reputation, and the coordinator's offline gap-analysis loop.

Constraints and terminology:

- Chat checkpoints and per-picker long-term memory live in PostgreSQL; deleting a thread does not
  delete `/memories/picker_notes.md`.
- Raw report text is sent verbatim to the configured model provider.
- Identity is an anonymized picker id; location is stored at neighborhood/city level only, never
  precise GPS.
- The database is required; there is no offline mode.
- Device assumption confirmed by the user: a modern smartphone browser. Low-end hardware, weak
  connectivity, and shared devices are not treated as binding design constraints at this stage.
- Interface language: English UI; conversation content in the picker's own language (Roman Urdu or
  Urdu) is expected.

## Brand Commitments

Product name: ScrapSense. The existing greeting opens with "Assalam-o-alaikum", establishing a
respectful, locally grounded voice rather than a neutral assistant tone.

## Evidence on Hand

- `ScrapSense_Project_Overview.md` records the problem framing and informal-recycling-market
  research figures (picker vs. dealer earnings, sub-value payouts, rigged weighing). Those figures
  are cited in prose without source links; treat them as project context, not audited data.
- The seed price file exists but is intentionally empty. The estimator returns `unavailable`
  rather than inventing prices until audited entries are added.
- No testimonials, customers, benchmark results, demo dataset, or field data exist. None may be
  fabricated.
- Material classifier training data is planned from a public dataset; nothing is collected yet.

## Product Principles

1. An independent number beats the dealer's word: any price shown must trace to pooled picker
   reports or audited seed data, never to invention.
2. Arithmetic and trained models do the math; LLM reasoning is reserved for genuine judgment on
   messy input and flagged reports.
3. Trust precedes aggregation: a report may influence a price only after it survives validation.
4. Honest gaps over false confidence: a placeholder reports zero/neutral rather than a plausible
   guess.
5. Protecting the picker constrains what can be published: anonymized aggregates only, never a
   named dealer callout.
