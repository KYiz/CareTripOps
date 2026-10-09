# CareTrip Ops V4.0 — Core Fix and Verification Record

**Date:** 9 October 2026 (Pacific/Auckland)  
**Scope:** The seven requested core issues only. This record distinguishes code changes from observed runtime behavior. No Git command, Docker lifecycle action, API key read, or real Gemini pressure test was performed.

## Status by requested issue

| Request | Change or inspection | Actual verification | Status and remaining risk |
|---|---|---|---|
| 1. Fresh and existing Alembic migrations | `0003_guide_state.py` and `0004_case_access.py` now inspect `cases` columns and add only missing fields. No data deletion or reset. | Python compilation passed. No PostgreSQL service was available to run `alembic upgrade head` on an empty and an existing database. | **Code fixed; DB migration unverified.** The initial migration still uses current SQLAlchemy metadata, so an empty-DB upgrade and an upgrade from pre-`0004` must both be run before acceptance. |
| 2. Case Token, refresh and WebSocket | Existing API emits a random token, stores its SHA-256 hash, checks HTTP `X-Case-Token` and a WebSocket subprotocol. Browser saves the token by Case ID. A missing token now gives a clear create-new-trip message; token storage failure is explicit. Added frontend token tests and backend WebSocket authorization test. | Three new frontend token tests passed, including module reload and distinct tokens for two snapshots; TypeScript passed. Backend API/WebSocket and browser refresh were not run. | **Frontend token path tested in isolation; server and browser E2E unverified.** Old Cases have no recoverable token and require a new Case. |
| 3. Auckland requirements → evidence → HITL → one mock order | Existing graph, Skills, approval, and unique Order constraints were inspected. Existing integration test covers A BLOCK, C REVIEW, B PASS, approval and one order. | No current PostgreSQL integration test ran. | **Implemented in code, not demonstrated on this revision.** |
| 4. Rejection, duplicate decision, resume, cross-Case access, Dashboard/Mobile sync | Existing integration tests cover rejection, duplicate approval, and cross-Case HTTP access. Added authorized/unauthorized WebSocket and a recovery test that simulates a committed approval followed by a startup recovery marker. Both UI views use one Case snapshot API. | Backend tests and browser sync were not run. | **Tests prepared; runtime acceptance pending.** The recovery test does not simulate an actual process crash or checkpoint outage. |
| 5. Approved package versus later Guide revision | Mobile, Dashboard, and Guide now state that the daily outline is illustrative, separate from the approved synthetic package, and not included in the simulated order. The completion heading identifies a package order rather than a confirmed trip. Business records remain unchanged. | TypeScript passed. Browser rendering and user comprehension were not observed. | **UI wording fixed; browser acceptance pending.** A future package-to-itinerary version relationship would be needed for commercial use. |
| 6. Gemini Requirements / Planner / Reviewer calls and quality | Confirmed source paths: `MODEL_MODE=api` Requirements calls the provider; Gemini Planner and Reviewer are separate async calls, with at most one feedback-driven revision and Pydantic/rule validation. `mock_llm` uses deterministic extraction and local itinerary templates. | No configured API service was reachable at localhost:8080, and no key was read. No real Gemini calls or quality review ran in this session. | **Implementation inspected; real invocation and quality unverified.** Do not label model output as verified travel facts. |
| 7. Five-Case mock concurrency, async blocking and pool | Added a five-Case integration test checking separate approvals/offers. Existing duplicate-decision test covers two concurrent submissions. Inspected default SQLAlchemy pool, process-local task map, and synchronous DB calls in async routes. | No PostgreSQL or backend pytest environment available; no latency, pool or event-loop measurements. | **Test prepared; performance and isolation unverified.** Do not add concurrency infrastructure without measurements. |

## Commands and observed results

| Check | Result |
|---|---|
| `python -m compileall -q app alembic/versions tests` in `backend/` | **Passed.** Syntax compilation only. |
| TypeScript `tsc -b --pretty false` via bundled Node | **Passed.** Type checking only. |
| Node tests: `routes`, `photoLibrary`, `caseAccess` | **9 passed, 0 failed, 0 skipped.** Three tests covered token storage/reuse, old-Case messaging, and per-Case snapshot isolation. |
| `python -m pytest -q` | **Not run:** host Python reports `No module named pytest`. Alternate Anaconda pytest executable failed to start with a system DLL relocation error. |
| PostgreSQL availability | Local port 5432 closed. No database was accessed or changed. |
| Web availability | Local port 8080 closed. No browser end-to-end request was possible. |
| Vite production build | Current attempt stopped before module transform with Windows `realpath EPERM` on `frontend/src/main.tsx`; this revision has TypeScript validation but no successful production build. |

## Operator acceptance sequence after an authorized rebuild

The updated API image must include the changed migrations and integration tests. The operator should build/start the existing Compose stack; this audit did not do so. The following checks are required before declaring the demo stable:

1. On a **new, empty** PostgreSQL database, run `alembic upgrade head`; confirm the Case columns appear once and API readiness succeeds. Independently repeat the upgrade on a preserved database at an earlier migration revision; verify the existing Case/Order row counts are unchanged.
2. Run `docker compose exec api pytest -q`, especially `test_integration.py` and the new Case-token, WebSocket, recovery, and five-Case tests. Record counts and failures; do not infer success from test definitions.
3. Build the web image and exercise `/`, `/dashboard`, `/mobile`, and `/demo` in one browser: create an Auckland Case, observe A/C/B assessments, approve once, see one simulated order in both views, refresh, and reopen My Trips. Repeat with rejection and with a different browser lacking the token.
4. With the **configured API mode** already available, create one small representative Case to observe Requirements and Planner/Reviewer audit events and inspect source labels and output quality. Do not load-test the real Gemini key. Voice WebSocket needs a separate microphone and browser test.
5. Accept an illustrative Guide revision after approval; verify both views clearly state that the changed outline is not part of the approved synthetic package or simulated order.

**Current answer:** The source has a coherent Auckland simulated workflow, but this revision has **not** yet demonstrated a stable real frontend-to-backend simulated travel service closure. A successful migration, current PostgreSQL tests, frontend build, and browser smoke test remain required.
