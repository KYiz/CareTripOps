# CareTrip Ops Acceptance Report — V3.3 Baseline and V4.0 Addendum

The V4.0 addendum at the end is the current-source assessment. Earlier V3.3 results remain historical evidence only.

**Assessment date:** 2026-10-09. **Status:** Partial acceptance only. The latest source has not completed live end-to-end acceptance. The operator manages all Docker lifecycle operations. No Git operation was performed.

## Module results

| Module | Implementation status | Test result | Issue | Required before demo? |
|---|---|---|---|---|
| FastAPI and Pydantic contracts | Source reviewed | Frontend request paths and payloads match implemented routes; current HTTP calls not tested. | Runtime response and database connection remain unverified. | Yes |
| LangGraph Manager and five worker responsibilities | Source reviewed | `StateGraph`, branches, interrupts, resume and recovery paths exist; current graph execution not tested. | Checkpoint and current recovery need live testing. | Yes |
| Nine Python Skills | Source reviewed | Executable functions and worker call sites inspected; host lacks Pytest and backend packages. | Fixed supplier fixture is Auckland only. | Yes: test and disclose scope |
| PostgreSQL and Alembic | Source reviewed | Eight models, migrations, offer trigger and order uniqueness inspected; migration not run this turn. | Current database state unknown. | Yes |
| Requirements, ranking, evidence and rerank | Source reviewed | Code and integration assertions cover clarification, A BLOCK, C REVIEW, B PASS and one rerank; not rerun. | Live model and current container state unverified. | Yes |
| Approval and simulated order | Source reviewed | Snapshot checks, nonce, state version, idempotency key and order read-back inspected; not rerun. | One demo actor; no production identity authorization. | Yes: rerun fixed demo |
| Audit and recovery | Source reviewed | Durable event and `RECOVERY_REQUIRED` code inspected; restart and failure injection not run. | Business commits and checkpoints are separate transactions. | Yes |
| Homepage `/` | Implemented; build tested | Natural-language form calls Case creation; destination cards prefill editable text; style chips filter destinations. TypeScript and Vite build passed. | Browser navigation and visual rendering not tested. | Yes |
| Dashboard `/dashboard` | Partially verified | Intake, clarification, recovery and backend-fed offers/evidence/audit statically traced. | Current browser interaction not tested; catalog scope limited. | Yes |
| Mobile `/mobile` | Partially verified | Case creation, clarification, approval and rejection share API client; phone error feedback added. | Browser interaction not tested; recovery remains an operations action. | Yes |
| Dual view `/demo` | Source reviewed | Both components share one Case ID and state in `App`; route unit tests passed. | Live synchronization and refresh not tested. | Yes |
| New Zealand images | Unit-tested mapping | Six Node photo/route tests passed; nine attributed local WebP files inspected. | Browser load-failure fallback and visual crop not tested. | Yes |
| Destination scope | Pure-function tested | Four independent checks passed, including mixed New Zealand/foreign request rejection. | Unknown place names still need clarification. | No for fixed demo |
| AI capability | Partial implementation | Default `mock_llm` is deterministic; optional OpenAI adapter is present but has no real-provider smoke test. | No Gemini, multimodal planner, real daily route generation, or image generation. | No for deterministic demo |
| Docker/Nginx | Environment-limited | Compose and Nginx source reviewed; no Docker executable in audit shell and port 8080 was closed. | Current build not deployed. | Yes |

## Required journey scenarios

| Scenario | Current result |
|---|---|
| Auckland request to simulated order | Not tested on current source; integration test exists. |
| Missing travelers or budget triggers clarification | Source path exists; not tested live. |
| A is blocked on evidence conflict | Source and test assertion exist; not rerun. |
| C cannot be directly approved | REVIEW rule exists; not rerun. |
| B passes fresh verification and reaches approval | Source path exists; not rerun. |
| Rejection produces no order | Source and test assertion exist; not rerun. |
| Approval produces exactly one order | Unique keys and test assertion exist; not rerun. |
| Repeat approval, refresh and replay do not duplicate an order | Source and integration assertion exist; not rerun. |
| Foreign destination is stopped | Pure destination function checked; full API terminal state not tested. |
| Photo match and fallback | Local mapping tested; browser image failure not tested. |
| Dashboard and Mobile synchronize | Shared Case ID statically confirmed; live browser check pending. |
| API/database failure avoids false success | UI error handling repaired; database fault injection not run. |

## Fixes made during the current audit

- The phone now accepts missing requirement fields through the existing clarification API.
- Mutation errors remain visible even after the next successful polling refresh.
- A request naming both a supported New Zealand destination and a known foreign destination is treated as outside the demo scope.

## Executed checks and limits

- Node photo and route tests: **6 passed**.
- TypeScript project check: **passed on current V3.3 source**.
- Vite production build: **passed on current V3.3 source** (38 modules transformed; nine WebP assets included).
- Destination pure-function checks: **4 passed**.
- Python source compilation: **passed**.
- Backend Pytest, API, migration, browser rendering, PostgreSQL read-back, restart, and current end-to-end flow: **not run** because the host lacks backend dependencies and the operator has not started the current Compose build.

The deterministic `mock_llm` parser is not real model reasoning. The optional live path uses `ChatOpenAI`; a real key and provider call were not tested. The system is accurately described as a LangGraph-orchestrated Agent Workflow PoC, not a team of autonomous LLM agents. Daily itinerary cards are explicitly illustrative; only the fixed Auckland synthetic catalog can yield a verified sample offer.

## Acceptance decisions

1. **Backend closed loop:** Source path exists for the fixed Auckland synthetic case; current live execution is not tested.
2. **Dashboard:** Main P0 controls are wired; current browser acceptance is pending.
3. **Mobile:** Creation, clarification and decision controls are wired; current browser acceptance is pending.
4. **Cross-view synchronization:** One API and Case ID are used; actual current synchronization is pending.
5. **LangGraph and Skills:** Executable code exists, but this report does not claim runtime success for the current build.
6. **Booking blockers:** Port 8080 was closed during the audit; non-Auckland requests have no approvable package. Mobile clarification was repaired but not browser-tested.
7. **Must do before submission:** Operator rebuilds and starts Compose; run migrations, backend tests, fixed-case approval/rejection/replay, browser checks for four paths, refresh recovery, image loading and PostgreSQL read-back.
8. **Demo readiness:** **Not yet accepted.** Source/build success is not equivalent to a running demo.

The operator should run `docker compose config` and `docker compose up --build -d` from the project root. After the operator confirms startup, run read-only service checks and the current end-to-end acceptance suite. Do not run container lifecycle commands from this audit workflow.
# V4.0 acceptance addendum — 2026-10-09

This addendum supersedes earlier claims about the latest source bundle. Code presence and successful compilation do not establish live service acceptance.

| Module | Implementation status | Test result | Issue | Must fix before a V4 demo? |
|---|---|---|---|---|
| Original planning, evidence, approval, and mock booking | Implemented in source; unchanged by V4 guide routing | 28 backend unit tests passed; 10 database integration tests skipped | Current PostgreSQL end-to-end regression is not run | Yes |
| Guide context and text mode | Implemented with case-bound REST API and deterministic responses | Pure guide tests passed; database endpoints not run | Requires migrated PostgreSQL and browser validation | Yes |
| Journey map and revision | Manual, illustrative stops; separate LangGraph graph and persisted proposal | Source and type checks passed; graph/database integration not run | Migration and accept/decline recovery unverified | Yes |
| Gemini Live audio and read-only function tool | Implemented as optional WebSocket bridge | SDK configuration shape check passed; no provider call or microphone/browser test | Model entitlement, audio I/O, tool calls, interruption, and retry unverified | Yes, if shown in demo |
| Planner/Reviewer collaboration | Optional three-call structured loop implemented | Schema rejection tests passed; no real model calls | Two Brains and Strict Shapes cannot be claimed yet | Yes, if claimed |
| Homepage, Dashboard, Mobile, Demo | V4 homepage and Mobile guide added; Dashboard and original routes retained | TypeScript and Vite build passed; six route/photo tests passed | Browser preview connection timed out; no visual or end-to-end acceptance | Yes |
| Docker and persistence | Compose configuration extended, migration added | Docker CLI unavailable in audit shell; containers not started by Codex | Operator startup and PostgreSQL restart test pending | Yes |
| AI evaluation | Opt-in ten-case before/after scoring harness implemented | Scoring unit tests passed; provider run NOT TESTED | Real model results are required for bonus | No for core demo; yes for bonus |

Current V4 demo readiness: **NOT VERIFIED**. The original booking demo should be rehearsed after the operator starts the rebuilt stack. Gemini Live and Two Brains must remain labeled unverified until real provider evidence exists.

## P0 repair and runtime recheck — 2026-10-09

This section describes the latest source changes. The running browser page still served the previous container bundle, so its result is baseline evidence rather than acceptance of these repairs.

| Module | Implementation status | Test result | Issue | Must fix before demo? |
|---|---|---|---|---|
| Home and Mobile destination planning | Source fixed | TypeScript and Vite build passed; old browser bundle reproduced prefill-only Home action | Operator rebuild and browser retest required | Yes |
| Mobile My Trips | Source fixed | TypeScript check passed; list now loads distinct browser-stored Case IDs through `GET /api/cases/{id}` | No account-wide or cross-device case index; new bundle not browser-tested | Yes |
| Chinese NZD and clarification | Source fixed | Three Chinese NZD extraction tests and currency normalization test passed | Database clarification persistence test skipped | Yes |
| Gemini requirements adapter | Implemented with official SDK and Pydantic validation | Fake-client structured response test passed; real provider call NOT TESTED | Requires `MODEL_MODE=api`, `LLM_PROVIDER=gemini`, server-side key, rebuild, and provider smoke test | Yes if claiming live Gemini |
| Queenstown supplier scope | Existing limitation disclosed in both views | Supplier fixture inspected; no Queenstown offers by design | Only fixed Auckland fixture yields approvable offer | No if clearly disclosed |
| PostgreSQL, migration, checkpoint, approval, unique order | Existing source path | 10 database integration tests skipped because this tool shell could not reach PostgreSQL | Operator-host database test and full flow required | Yes |
| Current browser pages | Older bundle reachable in in-app browser | Home destination card reproduced prefill-only behavior | Rebuilt bundle has not been served or tested | Yes |
| Gemini Live and Two Brains | Optional V4 source remains | No live provider, audio, tool-call, or dual-model test | Do not claim these bonuses | Only if featured |

**Executed on latest source:** 34 backend tests passed, 10 database tests skipped; six frontend photo/route tests passed; TypeScript check and Vite production build passed (41 modules). The audit shell could not connect to host ports 8080/5432 and did not expose the Docker CLI. The in-app browser could open an older page at 8080, but this does not provide shell access to PostgreSQL or validate the rebuilt bundle. No container lifecycle operation or Git operation was performed.

**Next operator step:** rebuild the existing services with `docker compose up --build -d` in the operator's PowerShell session. Then run `docker compose exec api pytest -q` and rehearse Auckland approval, rejection, duplicate decision, refresh, both views, and Queenstown no-package behavior. For a Gemini requirements smoke test, configure `MODEL_MODE=api` and `LLM_PROVIDER=gemini` in the server-side `.env`, keep the key out of logs and browser code, rebuild manually, and verify `MODEL_CALL_STARTED` plus provider usage or a clear provider error. A key's presence and a mode label are not proof of a successful call.

### Existing-container baseline (before rebuild)

- After a read-only environment access was granted, Docker Engine reported the project's `web`, `api`, and `db` containers running; `api` and `db` were healthy. PostgreSQL used the named volume `zeilhackathon_caretrip_pgdata`.
- HTTP `GET /healthz` returned `ok`; `GET /api/readyz` returned `ready` with `model_mode=mock_llm`.
- The existing API container executed `pytest -q tests/test_integration.py`: **10 passed, 0 failed, exit code 0**. This verifies the earlier image, not the repaired source tree.
- `GET /api/guide/capabilities` returned `voice_available=true`. This only confirms configuration detection; Gemini Live connection, microphone, audio, function calling, and Two Brains remain **NOT TESTED**.
- The in-app browser rendered `/`, `/dashboard`, `/mobile`, and `/demo` from the earlier bundle. Clicking the old Auckland Home destination card only filled the request field; it did not create a Case.
- No container was started, stopped, restarted, rebuilt, or deleted by this audit.
