# CareTrip Ops V4 UI and interaction increment

## What changed

- Web and operations heroes use content-driven height. The planning action and photo attribution have separate space at narrow widths.
- The standalone Mobile route becomes a full-width, single-scroll companion page on small screens. The Demo route keeps its phone simulator.
- The Mobile voice entry is disabled until `/api/guide/capabilities` reports availability. Text planning remains available.
- The saved-trip list distinguishes loading, inaccessible trips, and an empty browser history. Switching cases clears the pending approval confirmation and clarification answers.
- The Dashboard execution path is derived from persisted audit events, approval, evidence, and order records. Missing events remain visibly pending.
- The primary navigation remains Home, Dashboard, Mobile, and Demo on every route. Selecting a primary route keeps the React shell mounted.
- Vite forwards WebSocket upgrades for `/api`. The live guide accepts an exact same-origin host in addition to configured demo origins, and records provider or stream failures without exposing credentials.

## Data boundaries

| Surface | Data source | Boundary |
| --- | --- | --- |
| Case status, approval, orders, audit trail | FastAPI backed by PostgreSQL | Current persisted case records |
| Initial requirements and itinerary | Gemini only when the case reports API success or `GEMINI_REVIEWED`; otherwise local rules | Illustrative planning content |
| Live voice | Gemini Live through the case WebSocket | Available only when the capability endpoint enables it |
| Destination imagery | Local licensed WebP library | Photo attribution and source link shown |
| Offers and evidence | Synthetic supplier catalog and local verification skills | No live supplier inventory, price, or confirmation |
| Booking | Idempotent simulated order skill | No payment or real reservation |
| Maps and routes | No integration | No live distance, route, or travel-time claim |

## Verification on 9 October 2026

- TypeScript type check: passed.
- Vite production build: passed.
- Frontend route, photo, and case-token tests: 9 passed.
- Backend skill, guide, graph-contract, itinerary-quality, and itinerary-evaluation tests: 39 passed.
- Browser inspection: Web, Dashboard, and Mobile rendered at a narrow viewport without document-level horizontal overflow. The Dashboard hero action and photo attribution had a 32 px gap after the spacing correction.
- End-to-end case creation, Gemini execution, supplier discovery, evidence arbitration, approval, booking, cross-view synchronization, and reload recovery: **not verified in this run**. FastAPI and PostgreSQL were not running on localhost. No Docker lifecycle action was taken.

## Remaining limitations

- Queenstown and other non-Auckland destinations have illustrative drafts, but the complete synthetic package flow is Auckland-only.
- The Guide's text responses use case rules; only explicitly marked itinerary generation and live voice use Gemini.
- The execution path reports persisted events. It does not infer worker completion when the matching event is absent.
- A real Gemini Live voice call was not exercised in this run because FastAPI and PostgreSQL were unavailable. The WebSocket origin checks and frontend build passed, but a deployed provider connection still needs runtime verification.
