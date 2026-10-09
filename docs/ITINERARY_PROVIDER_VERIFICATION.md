# Itinerary and Gemini verification — 2026-10-09

## Root cause and change

Previously, `build_draft_itinerary()` produced the initial daily outline from a generic fixed pattern. The optional Gemini Planner/Reviewer loop ran only when the guide revision endpoint was used. The running API image reported `model_mode=mock_llm`, so its Requirements Worker did not call Gemini.

The current source routes a complete requirement through the LangGraph `itinerary` node before supplier discovery. That node builds a local place-based outline, then calls Gemini Travel Planner and Travel Reviewer separately when `MODEL_MODE=api` and `GEMINI_PLANNING_ENABLED=true`. Reviewer concerns can trigger at most one more Planner call. All model output is validated by Pydantic and deterministic guards for day count, allowed and repeated places, repeated or empty activities, and unsupported price, distance, duration, or booking claims. A provider or validation failure is audited and shown as `GEMINI_FAILED` with a clearly labeled local illustrative outline.

The local place catalog covers Auckland, Queenstown, Rotorua, and Taupō with official Tourism New Zealand place pages as name and theme references. These pages do not verify current opening hours, accessibility, travel time, price, or inventory. Every generated day is labeled `ILLUSTRATIVE_DRAFT`.

Text and voice guide turns now share the same Case and `cases.guide_state` conversation. Voice clarification saves fields into the existing Requirement row and can make one Gemini requirements call after essential details are collected. A revised itinerary is versioned in Case state and requires traveler acceptance. A hotel, price, transport, package, or booking change still requires a new Case and fresh business verification; the itinerary revision path cannot alter an offer, approval, or order.

## Before and after evidence

| Scenario | Earlier initial outline | Current local fallback output verified by Pytest | Gemini application outcome |
|---|---|---|---|
| Queenstown, three easy lake days | Generic repeated text | Distinct Lake Wakatipu and Skyline Queenstown ideas, then an open day with rest and checks | Not tested in rebuilt graph |
| Rotorua, two hot spring days | Generic repeated text | Polynesian Spa and another distinct local stop | Not tested in rebuilt graph |
| Auckland, three city/culture days | Generic repeated text | Museum first, distinct subsequent stops | Not tested in rebuilt graph |
| Taupō, two nature days | Generic repeated text | Lake Taupō and Huka Falls | Not tested in rebuilt graph |

The fallback is a local illustrative outline, not a verified route. Direct Gemini smoke tests did not use these four full Cases or a database-backed graph.

## Tests actually executed

- Local backend unit and graph contract suite excluding database integration: **41 passed**.
- TypeScript project check and Vite production build: **passed**; 41 modules transformed.
- `gemini-3.8-flash` direct Requirements adapter call: **passed**. It returned Queenstown, three travelers, three days, budget 1000, NZD; provider usage reported 99 input and 39 output tokens.
- Separate direct Gemini Planner and Reviewer structured calls: **passed** after tightening the prompt and moving unsupported Pydantic JSON Schema constraints to backend validators. Planner produced two distinct Queenstown days with two activities each; Reviewer returned no concern. Provider usage reported 80 input/187 output and 331 input/45 output tokens respectively.
- One earlier direct Planner smoke call failed backend validation due to an invalid intensity and too many verification notes. The failure was surfaced; it did not become a successful plan. The schema/prompt was corrected and the bounded rerun passed.
- Full host Pytest collection: **not completed** because the database integration module probes a PostgreSQL address unavailable from the host. The 10 PostgreSQL tests previously passed in the older API image and must be rerun after the operator rebuilds.
- Current-source database, checkpoint, approval, booking, Live audio, microphone, cross-view browser, and restart recovery: **not tested**. The existing containers still serve the older image.

## Operator rebuild and acceptance

The operator controls container lifecycle. After manually running `docker compose up --build -d`, verify `/api/readyz` reports `model_mode=api` and `llm_provider=gemini`, then run `docker compose exec api pytest -q`. Create the four destination Cases and inspect `itinerary_source`, `draft_itinerary`, and audit events. Exercise Auckland approval and duplicate booking prevention, one voice clarification, a reviewed revision, page refresh, and both views. Treat `GEMINI_FAILED` as a provider or validation failure requiring investigation, not as Gemini success.

No API key value is included in this report.
