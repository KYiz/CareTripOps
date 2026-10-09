# Codex — CareTrip Ops V3.2 Implementation Handoff

You have no conversation history. Read these project artifacts in this order:

1. `CARETRIP_FINAL_REVIEW_V3_2.md` (highest priority)
2. `FRONTEND_UX_API_SPEC_V3_2.md` (binding dashboard + embedded phone UI/API)
3. `diagrams/system_architecture_v3_2.mmd`, `workflow_v3_2.mmd`, `erd_v3_2.mmd`, `frontend_interaction_v3_2.mmd`, `frontend_api_sequence_v3_2.mmd`, `frontend_web_page_flow_v3_2.mmd`, `frontend_mobile_page_flow_v3_2.mmd`
4. `CARETRIP_FINAL_REVIEW_V3_1_SOURCE.md` (backend details only where consistent with V3.2)
5. `CARETRIP_POC_SPEC_V3_0_SOURCE.md` and `references/` (historical references, nonbinding)

## User instruction / language

**Speak with the user in Chinese. All created file content, UI text, tests, comments, docstrings, code, commits and documentation must be English.**

The target existing repository is `https://github.com/KYiz/CareTripOps.git` (branch `main`, private). Use that existing repository if authenticated and available. Do **not** initialize another nested Git repository. If pushing is not authorized, report the limitation rather than inventing a push result. Never commit keys or `.env`.

## Build

Use the page-flow diagrams as UX navigation references, not authorization to add uncontracted services. The iOS visual language is a design reference only, and the two multi-page image mockups are nonbinding. P0 is the minimal dual-view workflow defined in FRONTEND_UX_API_SPEC_V3_2.md.

Develop one **browser-based React SPA** with a desktop agent dashboard and an **embedded phone-shaped simulator**; the phone is not a native application. Both views share one Case ID and existing FastAPI APIs and render only PostgreSQL-backed state. Keep Python FastAPI, LangGraph, LangChain model adapter, PostgreSQL, AsyncPostgresSaver, Docker Compose and pytest. Implement constrained Manager + 5 hybrid worker responsibilities. Default deterministic mode labeled; enable real provider only with valid user-supplied credentials and honest token accounting.

### Essential workflow

Create Case -> extract requirements -> preliminary ranking -> synthetic source evidence -> Manager arbitration and exclusion -> at most one rerank and revalidation -> verified offer -> prepare pending approval -> interrupt -> phone approve/reject using existing REST approval contract -> resume -> idempotent mock booking -> audit trail and the same result on both views.

Use eight business tables, not seven. **Do not add a mobile-users table, phone-app database, separate mobile backend, extra auth, or fake live supplier API.**

## Execution constraints

- First present a plan of at most eight steps in Chinese; then implement without per-step confirmation.
- Code should be concise and readable, usually 100–300 lines per substantive file with 400 as a soft review threshold.
- P0: actual backend graph and PG, actual REST and Case synchronization, minimal dashboard + phone offer/approval/result. P1: visual polish, SSE, public hosting.
- Validate `docker compose config`, `docker compose up --build -d`, API readiness, pytest, cross-view approval and rejection, duplicate order protections, reload recovery. Report what was *actually* run and observed.
- Prepare clear English README, setup, and a short demo route. Preserve time for the required on-camera video and submission.

No fabricated status, model usage, tests, external hosting or payment. If blocked, explain in Chinese.
