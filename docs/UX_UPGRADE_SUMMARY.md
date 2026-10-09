# CareTrip Ops V3.3 UX Upgrade Summary

## Scope and implementation

- The project remains one React SPA, one FastAPI backend, one LangGraph workflow, one PostgreSQL business database, and the existing Docker Compose services.
- The homepage now has a natural-language intake that calls the existing Case creation API before navigating to `/mobile?caseId=...`. Its date and request inputs use the same React state as the other views.
- Six New Zealand destination cards use attributed local photography. Their buttons prefill an editable request and focus the planner; they do not invent a supplier offer. Travel-style buttons filter those cards. Four featured experiences are explicitly illustrative and feed the same planner input.
- The phone simulator adds working Explore and Help tabs alongside Home and My Trip. Explore pre-fills an editable destination request. Help explains the sample workflow and does not imply live support.
- The dashboard and `/demo` retain their backend-fed offer, evidence, approval, order, and audit views. No synthetic event animation or hard-coded success result was added.
- The homepage and phone keep sample offers, illustrative itineraries, and simulated bookings visibly distinct. Photo metadata and assets remain local; photos never enter evidence evaluation.

## Backend and AI status

The existing Auckland A/C/B synthetic workflow remains unchanged. `mock_llm` performs deterministic extraction. The optional OpenAI adapter has no current real-provider smoke test; Gemini and generated itinerary text are not implemented. The daily outline remains an explicitly illustrative derivative of stored requirements, with no verified schedule, inventory, transport duration, or price claim. Non-Auckland destinations can supply requirements and imagery but not an approvable sample package.

## Test evidence

- Frontend route and photo tests: 6 passed.
- TypeScript type check: passed after the V3.3 homepage changes.
- Vite production build: passed after the V3.3 homepage changes.
- Python source compilation and a destination scope smoke check: passed.
- Backend Pytest, current Docker build, API contract, browser rendering, responsive behavior, approval/rejection, cross-view synchronization, and PostgreSQL read-back: not run for the V3.3 source. Docker lifecycle is reserved for the operator; the audit shell had no Docker CLI and port 8080 was closed.

## Deferred features

Preference reruns, voice input/readout, travel-card export, maps, sponsored partner content, Gemini, online photo search, real supplier APIs, payment, and commercial partnerships remain unimplemented. They are not prerequisites for the fixed P0 Auckland demonstration.

## Demo readiness

Source compilation is successful, but **the current build is not yet accepted as a live Hackathon demo**. The operator must rebuild and start Compose, then the current API, database, browser, recovery, and synchronized approval journey must pass. Earlier container/browser pass records describe a previous bundle and do not certify this UX upgrade.
