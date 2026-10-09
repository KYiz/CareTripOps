# CareTrip Ops Implementation Progress

## 2026-10-09 — V4.0 Companion Upgrade

### Completed
- Audited the existing V3.2/V3.3 planning graph, database, React routes, local image library, and prior acceptance limits.
- Added a persistent `cases.guide_state` JSONB column and Alembic revision `0003_guide_state` without changing the eight business tables or booking path.
- Added case-bound guide context, manual attraction selection, deterministic text responses, and a separate LangGraph itinerary revision graph. Revisions remain illustrative and cannot change a verified offer, approval, price, or order.
- Added an optional server-side Gemini Live WebSocket bridge with PCM audio, transcription, a read-only `get_current_trip` function tool, and voice-triggered revision routing. The browser keeps no permanent key.
- Added an optional Gemini Planner → Reviewer → Planner structured-output loop with a three-call case cap, schema validation, audit records, and a hard failure path.
- Added an opt-in ten-case Gemini evaluation harness with before/after scoring. It was not run against the provider.
- Added a phone AI Guide with a 2D avatar, journey stops, text questions, revision decisions, and a conditional voice control. Added homepage companion and clearly labeled demo partner sections.
- Updated backend dependencies, Compose environment wiring, English README, and guide unit tests.

### In Progress
- No active runtime work: operator-managed Docker startup is required before container and browser acceptance.

### Pending
- Run Alembic `0003` against PostgreSQL, all database integration tests, current four-route browser tests, and a full approval/booking regression after the operator starts Compose.
- Verify a real Gemini Live connection, microphone input, audio output, tool call, interruption/retry, and voice-triggered revision with the provided API key in the API container.
- Verify real Planner/Reviewer model calls and structured outputs before claiming Two Brains or Strict Shapes.
- Run the ten-case AI evaluation harness against the provider and inspect measured before/after results before claiming Prove It Works.

### Tests Executed
- Backend Pytest: 28 passed, 10 skipped because PostgreSQL was unavailable.
- Frontend route/photo tests: 6 passed.
- TypeScript project check: passed.
- Vite production build: passed, 41 modules transformed. The audit shell required a process-local workaround for `fs.realpathSync.native` permissions.
- Google Gen AI SDK 2.29.0 import and local Live/structured configuration validation: passed without a provider call.
- Browser preview attempt: failed with `ERR_CONNECTION_TIMED_OUT` from the in-app browser.

### Test Results
- Source compilation, unit contracts, and frontend production build: PASS.
- Current PostgreSQL, Docker, browser UI, Gemini provider, audio, and end-to-end workflow: NOT TESTED.

### Known Issues
- The audit shell lacks Docker CLI access; container lifecycle is reserved for the operator.
- The browser could not reach the local Vite preview port. Visual QA remains pending.
- Voice uses a configured Gemini Live model and depends on model availability for the account; a key's presence alone is not proof of service availability.
- The verified synthetic offer catalog remains limited to the Auckland fixture.

### Next Steps
- Operator: run `docker compose config` and `docker compose up --build -d` from the project root, then confirm services are healthy.
- After confirmation: run migrations, Pytest integration, browser flow, restart recovery, and bounded provider smoke tests without displaying credentials.

## 2026-10-09 — V3.3 P0 UX and Documentation Update

### Completed
- Audited the current route, API, graph, Skill, database, and front-end source before extending the UI.
- Added a homepage Case-creation form, six actionable destination cards, functional style filters, illustrative experience links, and in-page help.
- Added working Explore and Help tabs in the phone simulator while preserving the existing Case, clarification, approval, and order path.
- Updated the root README and converted the latest acceptance report to English. Added `docs/UX_UPGRADE_SUMMARY.md`.

### In Progress
- Live browser and backend acceptance after operator startup.

### Pending
- Operator-managed Docker rebuild/start, current backend Pytest and migration, browser visual and responsive checks, four-route navigation, and complete Auckland approval/rejection/replay checks.

### Tests Executed
- Node route/photo tests: 6 passed. TypeScript type check and Vite production build passed on the final V3.3 source (38 modules). A source scan found no Chinese text in 35 Markdown, Mermaid, and frontend TS/TSX files.

### Test Results
- Source-level P0 UX actions are implemented; the current V3.3 browser and PostgreSQL path remains NOT TESTED.

### Known Issues
- The host audit shell has no Docker CLI and port 8080 is closed. Host Python lacks backend Pytest dependencies.
- Other New Zealand destinations provide imagery and illustrative drafts only; verified synthetic offers remain limited to fixed Auckland.

### Next Steps
- Finish local checks, then wait for the operator to start the current Compose build before live end-to-end acceptance.

## 2026-10-09 — Frontend Visual Redesign

### Completed
- Revisited the V3.2 frontend specification and the package's web/mobile reference images. Confirmed the app uses React 19, TypeScript, and Vite in `frontend/package.json`.
- Rebuilt the desktop hierarchy as an operations desk with live case summary, request intake, case overview, photo-led offer cards, collapsible evidence, and an audit timeline from persisted events.
- Rebuilt the phone simulator as a warm travel companion. Its home page uses the same request/date state and case-creation API as desktop. Its trip page shows a large destination photo, plain-language progress, only the final PASS offer, exact group total, a two-step approval confirmation, and backend-confirmed result.
- Added responsive styling, large phone text, and touch targets of at least 54 CSS pixels for the main phone actions. Retained one React SPA, one case ID, one typed API client, and polling.

### In Progress
- Waiting for the operator's Docker rebuild before visual/browser verification of the new bundle.

### Pending
- Browser rendering at desktop and phone sizes; create, approval, rejection, refresh, and failure-state regression against the rebuilt services.

### Tests Executed
- TypeScript project check passed.
- Vite production build passed (36 modules transformed).
- Four local photo library tests passed.

### Test Results
- Source and build are ready. The running `localhost:8080` deployment is an older image until the operator manually rebuilds it; the redesigned UI has **NOT TESTED** browser status.

### Known Issues
- Codex's in-app browser refused `localhost` while direct host HTTP checks returned 200. Browser policy also rejected automated inspection of that tab. No alternate browser surface was used to bypass the restriction.
- The sample supplier catalog remains Auckland-only. Mobile route planning, voice input, real inventory, and payment are not claimed.

### Next Steps
- The operator runs `docker compose up --build -d` manually. After confirmation, inspect the rendered UI and execute end-to-end checks.

## 2026-10-09 — New Zealand Destination and Photo Extension

### Completed
- Re-read the V3.2 package in its actual `CareTrip_Final_Review_Package/` directory, all seven diagrams, and the three visual references; recorded the extension traceability in `docs/DESTINATION_IMAGE_TRACEABILITY.md`.
- Added maintainable bilingual aliases for six New Zealand destinations and selected attractions, deterministic scope checks, Chinese party/day parsing, relaxed pace, and per-person budget total handling.
- Added a Requirements migration for destination scope, attraction names, and pace without adding a business table. Known foreign destinations now terminate with a persisted scope audit event before supplier discovery.
- Created nine attributed local WebP photographs, shared image metadata and matching logic, desktop destination imagery, phone destination imagery, and a loading/failure fallback component.
- Preserved the original fixed Auckland A/C/B synthetic supplier fixture, evidence and approval controls, eight business tables, and one SPA/API/database architecture.

### In Progress
- Awaiting operator-managed Docker rebuild/start before migration, API integration, browser, and persistence verification of this extension.

### Pending
- The operator runs `docker compose up --build -d` manually. Then execute migration/readiness, all backend integration tests, browser image loading and failure checks, and cross-view regression.
- P1 online image search, caching, additional destination supplier fixtures, daily route planning, and travel support remain outside this extension.

### Tests Executed
- `pytest backend/tests/test_skills.py backend/tests/test_graph_contract.py -q`: 17 passed.
- Node photo-library tests: 4 passed, including Auckland/Queenstown/Rotorua matching, unknown attraction/destination fallback, and local WebP/source metadata integrity.
- TypeScript project check passed. Vite production build passed after allowing Windows `realpath` resolution outside the default sandbox.
- `alembic heads` identified `0002_destination_media`. Compose YAML parsed as `api`, `db`, `web` with named `caretrip_pgdata` volume.

### Test Results
- Pure Skills and photo matching pass. Database migration execution and browser rendering for this extension are **NOT TESTED** pending manual container startup.
- `docker compose config` could not run because the Docker CLI and Compose plugin are absent from the current shell installation. The unchanged Compose file parsed as YAML; this is not a substitute for Compose validation.

### Known Issues
- The synthetic supplier fixture still serves only the fixed Auckland scenario. Other supported New Zealand destinations show relevant images and requirements but no invented verified offers.
- The Docker Desktop data disk exists at `F:\Docker\DockerDesktopWSL\disk\docker_data.vhdx`; the current shell does not expose a Docker executable. No container was started, stopped, restarted, or deleted in this extension.

### Next Steps
- After the operator confirms `docker compose up --build -d`, run migration, readiness, full Pytest, and browser acceptance checks before marking this extension complete.

## Phase 1 — Audit and Contracts

### Completed
- Audited the local workspace. It contains the V3.2 review package and three historical reference images, but no application, migration, deployment, or test code.
- Read the V3.2 review, frontend contract, seven V3.2 Mermaid diagrams, and applicable V3.1 backend rules. V3.0 and images are historical references.
- Resolved conflicts by applying V3.2 first, then the frontend contract, diagrams, and applicable V3.1 rules. The current user instruction prohibits all Git operations, superseding historical handoff text.
- Defined the architecture traceability matrix below.

### In Progress
- Backend, Skills, and workflow implementation.

### Pending
- Frontend integration, automated verification, Docker startup, and final audit.

### Tests Executed
- Local tool availability checks only.

### Test Results
- No application tests existed at the start of Phase 1.
- The Docker data directory `F:\Docker\DockerDesktopWSL` exists, but `docker` is not on the initial shell PATH.
- The initial Python interpreter has no required backend packages installed.

### Known Issues
- The initial shell lacked the Windows `docker` command. A user-local Compose plugin was later found and used successfully. Docker Desktop settings point to `F:\Docker\DockerDesktopWSL`; the VHDX at that path grew during image builds.

### Next Steps
- Continue through the four phases below.

## Architecture Traceability Matrix

| Specification | Implementation target | Validation target |
|---|---|---|
| System Architecture | React SPA, FastAPI, LangGraph, PostgreSQL, Docker Compose | Compose and API integration tests |
| Workflow | Manager routing and five worker nodes | Graph branch and recovery tests |
| ERD | SQLAlchemy models and Alembic migration | Database constraint and migration tests |
| Frontend Interaction | Dashboard, phone simulator, shared API client | UI and cross-view tests |
| API Sequence | FastAPI case, clarification, approval, and read routes | API contract tests |
| Web Page Flow | Desktop workspace and timeline | Browser tests |
| Mobile Page Flow | Embedded phone verified offer and decision | Browser tests |

## Contract Decisions

- Eight business tables; LangGraph owns separate checkpoint tables.
- Offer snapshots are immutable. Evidence sources and aggregate assessments are separate.
- A pending approval is persisted before a side-effect-free graph interrupt.
- The approval service commits the decision before graph resume. Booking uses a unique idempotency key and database read-back.
- One case ID and REST data source power both UI views. The phone displays only the final PASS offer.
- All supplier and evidence data are synthetic. The default model mode is deterministic and labeled.

## Phase 2 — Backend and Skills

### Completed
- Implemented the eight SQLAlchemy business tables and executable initial Alembic migration. PostgreSQL has a partial unique index for pending approvals, a unique order per approval, and an immutable offer snapshot trigger.
- Implemented nine typed executable Skills, synthetic package/evidence tools, one Manager, and five worker responsibilities.
- Implemented conditional LangGraph routing, AsyncPostgresSaver checkpoints, clarification and approval interrupts, bounded reranking, durable decision handling, idempotent booking, order read-back, and terminal audit events.
- Implemented the contracted FastAPI read and mutation routes plus an explicit recovery route.

### In Progress
- No backend P0 implementation remains; exception injection coverage is incomplete.

### Pending
- Live provider smoke test with an operator-supplied key; forced database/checkpoint failure tests.

### Tests Executed
- Local `pytest -q`, graph compilation, Python compilation, container `pytest -q`, migration and table inspection.

### Test Results
- Final container suite: **17 passed, 1 external-library deprecation warning**.
- PostgreSQL has eight business tables, Alembic revision `0001_initial`, and four LangGraph checkpoint tables.
- The fixed demo, safe A path, no-PASS path, clarification and limit exhaustion, simulated provider timeout/invalid output, rejection, stale approval, cross-case guard, immutable offer trigger, duplicate approval, and booking replay pass automated tests.

### Known Issues
- The live model mode is implemented but was not executed because no user key was supplied.

### Next Steps
- Keep test fixtures and audit evidence current as the frontend and deployment are verified.

## Phase 3 — Frontend and Integration

### Completed
- Built the React/TypeScript/Vite dashboard, shared API client/types, and approximately 392 × 846 CSS-pixel inner phone viewport.
- Both panels use one case ID and backend polling; terminal states slow polling. The phone only exposes final PASS offers and uses the existing approval endpoint.
- Verified actual browser creation, A BLOCK/C REVIEW/B PASS display, phone approval, synchronized simulated order, phone rejection, and reload recovery.

### In Progress
- No P0 frontend implementation remains.

### Pending
- Optional additional mobile pages and automated browser test scripting.

### Tests Executed
- TypeScript check and Vite production build, both locally and inside the web image; interactive browser acceptance checks.

### Test Results
- Build passed. Browser success and rejection paths displayed the same persisted case state in both views.

### Known Issues
- The phone is a browser simulator, not a native app. Additional mobile page-flow screens are P1.

### Next Steps
- Maintain source/API contract alignment during final audit.

## Phase 4 — Verification and Final Audit

### Completed
- Validated Compose config, built and started `db`, `api`, and `web`; checked health/readiness, OpenAPI, recent logs, and migration.
- Restarted all three containers and read back the same completed case, one order, and 13 audit events.
- Restarted the API at pending approval; the persisted checkpoint resumed and produced one order after approval.
- Updated the V3.2 ERD, README, Skill contracts, and final repository audit.

### In Progress
- None for the local deterministic P0 path.

### Pending
- A real provider smoke test and forced fault injection are outside the verified P0 default path.

### Tests Executed
- Container `pytest -q`: 17 passed; browser F01–F07 journey and refresh; direct database and API read-back.

### Test Results
- Local deterministic P0 demo is running at `http://localhost:8080`.
- Docker Desktop settings specify `F:\Docker\DockerDesktopWSL`, and the disk image exists there. The exact `docker version` command could not run because the Windows Docker CLI is absent from PATH; the installed Compose plugin accessed the Engine successfully.

### Known Issues
- The `docker version` executable check, live provider call, and forced database/checkpoint failures are not tested.

### Next Steps
- Operator may add a server-side live model key for a separate smoke test. Keep the default deterministic demo for reliable hackathon presentation.

## Current Frontend Route and Photo Extension (2026-10-09)

### Completed
- Added four independent URL paths to the single React SPA: `/`, `/dashboard`, `/mobile`, and `/demo`; case links retain the same case ID.
- Added a brand landing page, separated operations and traveler layouts, and kept the side-by-side demonstration page.
- Copied the local WebP library into the web image build and verified the production output contains all nine photographs.
- Added an API-derived `ILLUSTRATIVE_DRAFT` day outline from persisted New Zealand requirements, with per-day local destination or attraction photographs on the traveler view.
- Kept the draft distinct from verified supplier offers and simulated bookings.

### In Progress
- Live deployment and browser acceptance checks for the changed image and route build.

### Pending
- The operator must manually run `docker compose up --build -d` under the current Docker instruction before live checks continue.
- Verify direct refresh of all four paths, case synchronization, Queenstown day photographs, approval, and order read-back against the rebuilt containers.

### Tests Executed
- Node local-photo and route tests: 6 passed.
- TypeScript project check: passed.
- Vite production build: passed, 38 modules transformed; all nine WebP files present in `dist/images`.
- Python source compile: passed.

### Test Results
- Frontend source, local media assets, and static bundle: PASS.
- New draft API and Python unit tests: NOT TESTED at runtime; the available host Python lacks backend requirements and Pytest.
- Current Docker deployment, browser routes, and refreshed database integration: NOT TESTED.

### Known Issues
- `docker.exe`, `docker-compose.exe`, and `npm` are unavailable on the current host PATH; Compose config could not be rerun in this environment. An earlier deployment report above describes the prior build only.
- The synthetic supplier catalog still offers the fixed Auckland demo only; Queenstown and Rotorua can show requirements and photos but no verified package.

### Next Steps
- After the operator starts the rebuilt services, run Pytest in the API environment and perform API, browser, approval, refresh, and persistence checks without stopping or removing containers.

# 2026-10-09 — P0 Interaction and Requirements Repair

## Completed

- Traced Home and Mobile planning actions. Destination cards only prefilled text in the running old bundle; current source now sends a Case creation request and displays the resulting Case.
- Replaced the single last-case Mobile history with a browser-local Case ID registry that reloads each Case from the API. New planning hides stale Case content.
- Normalized Unicode NZD input and clarification values; invalid currencies now receive an explicit error instead of consuming another clarification round.
- Added an opt-in Gemini requirements adapter using the official SDK, bounded structured output, and backend Pydantic validation. Mock mode remains the default and live provider failures do not silently become mock output.
- Clarified in both views that non-Auckland destinations have no approvable synthetic package.

## In Progress

- None in the local source repair.

## Pending

- Operator rebuild of the existing Compose stack, migrated PostgreSQL integration suite, and browser acceptance of the rebuilt source.
- Real Gemini requirements, Gemini Live voice/function tool, and Two Brains provider tests when explicitly enabled.

## Tests Executed and Results

- Backend Pytest: 34 passed, 10 skipped due to inaccessible migrated PostgreSQL from the audit shell.
- Frontend Node photo/route tests: 6 passed. TypeScript check and Vite production build: passed.
- In-app browser reached the older running bundle and reproduced the Home card's prefill-only action. The current bundle has not been browser-tested.

## Known Issues

- The audit shell has no Docker CLI and cannot connect to host ports 8080 or 5432, even though the in-app browser reaches an older 8080 page.
- The fixed Auckland three-traveler, three-day catalog is the only complete sample booking path. Mobile My Trips is browser-local history, not a server-wide account history.

## Next Steps

- The operator manually rebuilds the services, then the database suite and full Auckland/Queenstown cross-view acceptance can be rerun.

## Existing-container baseline

- Read-only Docker Engine inspection found `web`, `api`, and `db` running, with `api` and `db` healthy and a named PostgreSQL volume.
- The running API reported `ready` and `model_mode=mock_llm`.
- The existing API image passed all 10 PostgreSQL integration tests. This is baseline evidence for the prior image, not acceptance of the repaired source.
- The browser loaded all four routes in the prior bundle and reproduced the old Home destination button defect.
- Gemini voice availability reported configured; no real Gemini requirements, Live audio, tool call, or Two Brains invocation was verified.

# 2026-10-09 — Initial itinerary and Gemini provider repair

## Completed

- Configured the local demo environment for Gemini API mode and `gemini-3.8-flash` without displaying the key.
- Added a LangGraph initial itinerary node and kept the supplier, evidence, approval, booking, and audit routes intact.
- Added a local named-place catalog and distinct, nonempty fallback days for Auckland, Queenstown, Rotorua, and Taupō.
- Added separate Planner and Reviewer calls, one bounded revision on concern, backend schema and semantic checks, and explicit `GEMINI_FAILED` labeling.
- Saved text and voice guide turns in the same Case state and connected spoken clarification to the existing Requirement row.
- Updated Desktop and Mobile daily cards to show activity order, rest, intensity, checks, photographs, and source mode.
- Corrected a Google SDK JSON Schema incompatibility discovered during a real provider call.

## In Progress

- Container and browser acceptance of the rebuilt source.

## Pending

- The operator manually rebuilds the API and web containers. No container lifecycle command was issued by the assistant.
- Rerun all 10 PostgreSQL integration tests and the full Auckland approval and unique-order flow in the rebuilt API.
- Test all four destination Cases, reviewed revisions, voice audio, cross-view display, refresh, and recovery in the rebuilt application.

## Tests Executed and Results

- Local backend unit and graph contract suite excluding database integration: 41 passed.
- TypeScript project check and Vite production build: passed.
- Direct Gemini requirements adapter and separate Planner/Reviewer provider calls: passed. See `docs/ITINERARY_PROVIDER_VERIFICATION.md` for exact output and usage.
- Database-backed tests for this source: not run; host PostgreSQL probe blocked full collection, and running containers have an older image.

## Known Issues

- Gemini Live audio and function tool behavior remain unverified.
- A directly tested model plan initially failed semantic validation. The revised prompt and schema passed a bounded direct rerun, but graph-wide reliability remains unmeasured.
- Only the fixed Auckland Case has a synthetic verified package. Other supported destinations can receive illustrative itinerary drafts but no approvable offer.

## Next Steps

- After the operator rebuilds, verify ready status, run container Pytest, inspect Case and audit data, then perform browser acceptance.
