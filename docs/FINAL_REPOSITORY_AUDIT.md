# CareTrip Ops V3.2 Final Repository Audit

> V3.3 addendum (2026-10-09): The homepage now submits a real Case request, destination/style controls are interactive, and the phone has Explore and Help tabs. TypeScript, Vite build (38 modules), and six Node photo/route tests passed on the current source; all current browser/API/database checks remain pending. The source-level changes do not alter the Manager, evidence, approval, or booking graph. The operator has not started the current containers, and port 8080 was closed during this audit. See `docs/UX_UPGRADE_SUMMARY.md` and `docs/FINAL_ACCEPTANCE_REPORT.md` for the current acceptance boundary.

> The 2026-10-09 frontend redesign has passed TypeScript and Vite builds, but its browser appearance and interactions remain **NOT TESTED** until the operator rebuilds the Docker web service. The historical browser PASS entries below apply to the earlier UI bundle.

> Historical baseline audit: the pass results below describe the earlier fixed Auckland build. The 2026-10-09 New Zealand destination and photo extension has not been deployed to Docker yet. Current extension statuses are recorded below and in `docs/IMPLEMENTATION_PROGRESS.md`.

## 2026-10-09 Extension Audit

| Area | Status | Current evidence / remaining check |
|---|---|---|
| Architecture alignment | PASS | Source review: same React SPA, FastAPI, LangGraph graph, PostgreSQL database, and three unchanged Compose services. |
| Requirement traceability | PASS | `docs/DESTINATION_IMAGE_TRACEABILITY.md` maps all seven V3.2 diagrams to the scope and image extension. |
| Skills coverage | PASS | 17 pure Skill/graph tests passed; destination and attraction normalization is called from the Requirements Worker. |
| Agent workflow | NOT TESTED | New foreign-scope branch has unit coverage but no PostgreSQL graph execution yet. |
| API / schema consistency | PASS | Static review of `RequirementOutput`, SQLAlchemy columns, case JSON, and TypeScript `Requirements`; `alembic heads` returned `0002_destination_media`. Live migration and API response remain NOT TESTED. |
| Database integrity | NOT TESTED | The additive migration and old-row backfill were reviewed but not executed against PostgreSQL this turn. |
| Frontend integration | NOT TESTED | TypeScript and Vite builds passed; four local photo mapping/integrity tests passed. Browser rendering, failed-image UI, and cross-view behavior await the rebuilt deployment. |
| Error and recovery handling | NOT TESTED | Known foreign destinations stop before discovery in source and pure tests; durable case/audit read-back, restart, and image load failure need integration checks. |
| Docker verification | NOT TESTED | Compose YAML parses and the F-drive VHDX exists. `docker compose config` was unavailable because no Docker CLI/plugin is present in the current shell. Per current operator instruction, no container lifecycle command was run. |
| P0 extension completion assessment | FAIL | Source and local tests are ready; deployment, migration, browser, and full business-flow regression remain required. |

The image library is offline and attributed. Photos have no path into evidence verification or booking. The unchanged synthetic catalog supports the fixed Auckland demo only. No token usage occurred in `mock_llm` mode during this extension.

## Scope and evidence

This audit covers the entire local project at the end of the four implementation phases. It traces the actual path `React → typed API client → FastAPI → LangGraph workers/Skills → PostgreSQL → API response → React`. Status values are **PASS / FAIL / NOT TESTED / NOT IMPLEMENTED**. A PASS below names its test or code-review evidence. The default mode is deterministic with synthetic suppliers and evidence; no live inventory, real booking, payment, or production authorization is claimed.

## Architecture Alignment

| Area | Status | Evidence |
|---|---|---|
| One React SPA, FastAPI, LangGraph, PostgreSQL, Nginx | PASS | `docker-compose.yml` config parsed; three services built and started; web and readiness returned HTTP 200. |
| Manager, five worker responsibilities, nine Skills | PASS | `backend/app/graph.py`, executable Skills, graph compile test, PostgreSQL integration tests. |
| PostgreSQL checkpoint and business fact separation | PASS | `AsyncPostgresSaver.setup()` on healthy API startup; checkpoint tables and eight Alembic business tables queried in PostgreSQL. |
| Real supplier/payment/auth integration | NOT IMPLEMENTED | Deliberately outside P0; synthetic demo actor and catalog are labeled in UI and README. |

## Requirement Traceability

| V3.2 diagram | Implementation | Validation | Status |
|---|---|---|---|
| System Architecture | `docker-compose.yml`, `backend/app/main.py`, `backend/app/graph.py`, React SPA | Compose build/start, readiness, integration suite | PASS |
| Workflow | Conditional graph nodes, clarification/approval interrupts, Manager rerank | Graph compile, integration T01–T08, API restart at pending checkpoint | PASS |
| ERD | Eight SQLAlchemy models and `0001_initial` Alembic revision | Database table/revision inspection, approval/order integration | PASS |
| Frontend Interaction | Dashboard, phone, one API client and case ID | Browser creation, approval, rejection, reload | PASS |
| Frontend API Sequence | FastAPI routes and durable decision before graph resume | API integration and browser journey | PASS |
| Web Page Flow | Case intake, status, offers, evidence, audit, order | Browser rendering and interaction | PASS |
| Mobile Page Flow | P0 embedded verified plan, approval, result | Browser rendering and interaction | PASS |

The V3.2 ERD was updated to match implemented fields. Other V3.2 diagrams remain valid at their specified P0 abstraction level; the extra illustrated pages are P1 navigation references rather than implemented screens. V3.1 details were applied only where V3.2 did not supersede them. Historical images were used only as visual references.

## Skills Coverage

| Skill | Call site | Validation | Status |
|---|---|---|---|
| `extract_requirements` | Requirements Worker | Schema/parser unit tests; complete and incomplete integration | PASS |
| `validate_requirements` | Requirements Worker and supplier guard | Missing field and currency tests | PASS |
| `search_suppliers` | Discovery Worker | A/C/B catalog and snapshot integration | PASS |
| `compare_offers` | Comparison Worker | Budget/order unit tests | PASS |
| `verify_evidence` | Evidence Worker; C preassessment | A BLOCK/C REVIEW/B PASS unit and integration tests | PASS |
| `rerank_offers` | Comparison Worker after Manager arbitration | Ranking unit test and conflict integration | PASS |
| `prepare_approval` | Approval Worker | Pending persisted before interrupt; integration decision test | PASS |
| `execute_mock_booking` | Booking Worker | No order before approval, duplicate decision and replay tests | PASS |
| `generate_review` | Review Worker | Unit summary test and completed audit event integration | PASS |

Inputs, outputs, preconditions, side effects, errors, and idempotency rules are recorded in `backend/app/skills/SKILLS.md`. The side-effect Skills are business transaction functions, not separate LLM agents.

## Agent Workflow

**PASS:** `StateGraph` compilation, conditional routing, A exclusion, one rerank, B re-verification, pending approval interrupt, durable decision, `Command(resume=...)`, booking, and Review were exercised against PostgreSQL. The fixed browser case showed A `BLOCK`, C `REVIEW`, B `PASS`, one approval, one committed order, and 13 ordered audit events. The safe no-conflict A path, incomplete requirements, no-PASS manual review, and rejection also passed integration tests. The graph did not present preliminary A as verified.

**PASS:** Controlled provider timeout and invalid-output injections led to `HUMAN_REVIEW`, one counted attempted call, a `MODEL_ERROR` audit event, and zero orders. The clarification cap stopped before a third question. **NOT TESTED:** An actual live provider call and provider quota exhaustion were not exercised. `MODEL_MODE=api` is implemented with one bounded LangChain/OpenAI Requirements call and no automatic fallback; no provider key was supplied, and no token usage was fabricated.

## API / Schema Consistency

**PASS:** The contracted REST routes are present in FastAPI and the shared TypeScript client. `/api/openapi.json` returned HTTP 200. Money is serialized as strings, IDs as UUID strings, and errors use a structured envelope. React shows backend status, sources, assessments, approval, order, and events. Browser approval called the same FastAPI endpoint as integration tests. The extra `/api/cases/{id}/resume` route is limited to explicit recovery.

**PASS:** `GET /api/cases/{id}/offers` labels preliminary, blocked, review, and final verified snapshots separately. The phone selects only a final PASS offer tied to the approval. The UI contains no microphone, native mobile dependency, second database, real hotel claim, or browser API key.

## Database Integrity

**PASS:** Alembic revision `0001_initial` applied; PostgreSQL inspection found `cases`, `requirements`, `offers`, `evidence`, `offer_assessments`, `approvals`, `orders`, and `audit_events`, plus four LangGraph checkpoint tables. An integration test confirmed the PostgreSQL trigger rejects offer snapshot price updates. Source evidence and aggregate assessments are separate. Pending approval has a per-case partial unique index. Orders have a unique idempotency key and unique approval relation. Services recheck case ownership, PASS assessment, version, amount, currency, and expiry; integration tests covered cross-case rejection, stale amount, duplicate approval, and booking replay.

**PASS:** After all three containers restarted, the previously completed case still had status `DEMO_COMPLETED`, exactly one order with the original ID, and 13 audit events. The PostgreSQL named volume was retained.

## Frontend Integration

**PASS:** TypeScript and Vite production builds completed locally and in the web image. At a 1440 × 900 browser viewport, dashboard and phone were visible together. The phone frame's inner CSS viewport is approximately 392 × 846 pixels. In browser checks, desktop Case creation supplied the same case ID to the phone; before verification the phone showed a waiting state; after verification it displayed only B. Phone approval caused backend-confirmed completion on both views. A separate browser Case was rejected and both views displayed rejection with no order. Reload at `?caseId=<uuid>` reconstructed the completed Case and order from API data.

| Frontend acceptance | Status | Evidence |
|---|---|---|
| F01 shared Case ID | PASS | Browser create and same ID in desktop/phone. |
| F02 no early verified phone offer | PASS | Browser waiting state immediately after create. |
| F03 A BLOCK/C REVIEW/B PASS | PASS | Browser API-backed offer/evidence and audit display. |
| F04 phone approval/one order/sync | PASS | Browser completion plus API/integration read-back. |
| F05 phone rejection/zero order | PASS | Separate browser rejection and integration test. |
| F06 duplicate action protection | PASS | Disabled UI buttons during mutation; duplicate API decision and order replay integration tests. |
| F07 refresh recovery | PASS | Browser reload restored same completed Case and order. |
| F08 distinct error/stale/manual/mode states | PASS | Source inspection of status rendering; stale transition integration test. Not all states were visually exercised. |
| F09 no unsupported native/API-key claims | PASS | Frontend dependency and source inspection. |

## Error and Recovery Handling

**PASS:** Missing requirements interrupt and resume, no PASS candidate to `HUMAN_REVIEW`, rejection to `REJECTED`, and stale approval to `HUMAN_REVIEW` were tested. Each observed terminal path has database audit events. Restarting the API while a case was awaiting approval retained the pending checkpoint; the decision resumed it and produced one order. A committed order is reused by the booking Skill when its key is replayed.

**NOT TESTED:** Forced PostgreSQL outage during a transaction, forced checkpoint-write failure after business commit, and multi-process concurrency were not injected. The design remains a single-process demo; it does not claim distributed exactly-once execution.

## Docker Verification

| Check | Status | Evidence |
|---|---|---|
| `docker compose config` equivalent | PASS | Installed `docker-compose.exe config` produced valid `web`, `api`, `db` configuration. |
| `docker compose up --build -d` equivalent | PASS | Installed plugin built and started all three services; API and DB healthy. |
| `docker compose ps` / logs equivalent | PASS | Installed plugin showed running services and HTTP 200 API logs. |
| Exact `docker version` command | NOT TESTED | Windows `docker.exe` was absent from PATH; the Compose plugin accessed the existing Docker Desktop Linux Engine. |
| F-drive Docker storage | PASS | Docker Desktop `CustomWslDistroDir` is `F:\Docker\DockerDesktopWSL`; `disk/docker_data.vhdx` exists there and grew during image builds. No Docker/WSL configuration or other project resources were changed. |
| Named-volume persistence | PASS | Completed Case/order/events survived all-container restart. |

## Test Evidence

- Container `pytest -q --tb=short`: **17 passed, 1 external-library deprecation warning**, final run after rebuild.
- Frontend `tsc -b` and Vite build: **PASS**, locally and in the web image.
- `GET /`, `/api/readyz`, and `/api/openapi.json`: HTTP 200.
- Fixed demo browser Case: `1d0c3058-a338-46ba-b986-8fa9eb744e2e`; completed mock order `958ce8e5-01d8-4651-acab-86c68fffc806`, one order and 13 audit events after restart.
- API restart at pending approval: Case `2be45b68-9304-48b6-ab92-af5251077868` resumed to `DEMO_COMPLETED` with one order.
- Browser rejection Case: `6d518be1-bf83-4ef5-858f-8c48ed1b3973`; both views showed rejection and no order.

| Backend scenario | Status | Evidence |
|---|---|---|
| T01 safe no-conflict A | PASS | PostgreSQL integration test. |
| T02 A conflict and B recheck | PASS | PostgreSQL integration and browser trace. |
| T03 clarification limit/resume | PASS | Missing-field interrupt/resume and two-answer limit exhaustion integration tests. |
| T04 rejection | PASS | Integration and browser. |
| T05 no PASS | PASS | NZD 900 integration case to HUMAN_REVIEW. |
| T06 duplicate approval/order | PASS | Duplicate API decision and booking replay. |
| T07 stale approval | PASS | Tampered approved amount returned 409, no order, audit/manual review. |
| T08 rerank cap | PASS | No-PASS test observed exactly one `MANAGER_RERANK`. |
| T09 invalid/timeout/quota model | PASS | Timeout and invalid-output injections reached HUMAN_REVIEW with no fallback/order; quota exhaustion and a real provider call remain NOT TESTED. |
| T10 forced checkpoint/DB failure | NOT TESTED | Booking idempotent replay tested, but fault injection was not. |
| T11 browser refresh | PASS | Browser reload of completed case. |
| T12 container restart | PASS | All-container restart and same order read-back. |
| T13 cross-case approval | PASS | Integration rejected wrong Case/approval pair. |
| T14 terminal audit | PASS | Rejection, manual review, and completion audit asserted; failed runner audit code inspected. |
| T15 demo date/currency | PASS | Explicit date and NZD input, catalog/amount tests, browser display. |

## Remaining Issues

1. Live model mode and provider token accounting need a real server-side key and separate smoke test; actual token usage in this run is **none**.
2. Forced database/checkpoint failures and concurrent API replicas were not tested. This is a single-process local PoC.
3. The Windows Docker CLI executable was absent, so exact `docker version` was not run. The installed Compose plugin and Engine were functional.
4. Expanded desktop/mobile page navigation, automated browser scripting, SSE, RBAC, genuine supplier APIs, payment, and public hosting remain outside P0.

## P0 Completion Assessment

**PASS for the local deterministic Hackathon PoC.** The real FastAPI/LangGraph/PostgreSQL path, nine executable Skills, evidence arbitration, one rerank with B re-verification, durable human approval, one idempotent simulated order, backend audit, dual-view browser interaction, Compose deployment, and restart recovery have test evidence above. This assessment does not extend to live-model reliability, real travel booking, production authorization, fault-tolerant distributed execution, or public hosting.

## Current Change Audit — Four Paths and New Zealand Photos (2026-10-09)

The evidence above records the previous container build. It does not verify the current source changes until the operator rebuilds the containers.

| Area | Status | Current evidence |
|---|---|---|
| Architecture alignment | PASS | One SPA, one FastAPI backend, one PostgreSQL database, and the existing three-service Compose configuration remain in source. |
| Requirement traceability | PASS | Four paths match the current URL request; image matching follows persisted destination and attraction fields. |
| Skills coverage and agent workflow | PASS | Source review shows no new agent or booking bypass; existing Manager and Skills remain the business path. |
| API/schema consistency | PASS | `draft_itinerary` is derived in the case GET response and is optional in the shared TypeScript case type. Python source compilation and TypeScript check passed. |
| Database integrity | NOT TESTED | The new response reads existing requirement columns; live migration and read-back await the operator's rebuild. |
| Frontend integration | NOT TESTED | Photo and route unit checks passed (6/6), and Vite built successfully; the current browser bundle has not been served or inspected in a browser. |
| Error and recovery handling | NOT TESTED | Local photo fallback is covered by mapping tests; current browser load-failure, page refresh, and container recovery still need live checks. |
| Docker verification | NOT TESTED | `docker-compose.yml` and Nginx fallback were reviewed; Docker and Compose executables were unavailable for a current config/build check. No container lifecycle command was run. |
| P0 completion assessment for current build | NOT TESTED | Prior core workflow passed, but the route/photo extension requires a rebuilt deployment and end-to-end verification. |

Remaining issue: the daily outline is intentionally illustrative and does not claim a confirmed schedule or supplier availability. Only the fixed Auckland synthetic catalog yields a verified sample offer. The current host Python lacks Pytest and backend packages, so the new Python tests could not run outside the API container.

