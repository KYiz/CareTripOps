# CareTrip Ops — Final Architecture Review V3.2

**Status: DESIGN ONLY. No application code, deployment, or tests are claimed.**

## Binding document precedence

1. `CARETRIP_FINAL_REVIEW_V3_2.md` (this document): current decisions and discrepancy resolution.
2. `FRONTEND_UX_API_SPEC_V3_2.md`: binding frontend and shared-API behavior.
3. `diagrams/*_v3_2.mmd`: seven editable diagrams: system architecture, workflow, ERD, frontend interaction, frontend API sequence, Web page flow and mobile page flow. Diagrams explain the binding specifications and cannot independently add behavior.
4. `CARETRIP_FINAL_REVIEW_V3_1_SOURCE.md`: prior detailed backend rules and 15-test matrix, **only where not superseded**.
5. `CARETRIP_POC_SPEC_V3_0_SOURCE.md`: historic background, not the current authority.
6. `references/*.png`: original and potentially contradictory historical diagrams, not implementation requirements.

## Scope change and architectural decision

V3.1 described a single desktop browser UI. **V3.2 adds a second UI perspective, not a second application stack:** a desktop customer-service dashboard and an interactive, phone-sized customer preview rendered inside the same React SPA on a computer browser. Do **not** build an Android/iOS application or React Native frontend.

All frontend surfaces share one `caseId`, typed API client, one FastAPI backend, one LangGraph orchestration runtime, and one PostgreSQL business database. No schema expansion is warranted solely for presentation views; **keep the V3.1 eight business tables and existing Checkpointer tables**. The phone frame may be CSS only. Staff vs customer is a **role-play demonstration**, not actual RBAC or identity delegation.

## Unchanged technical stack

React + TypeScript + Vite; Python + FastAPI + Pydantic v2; LangGraph StateGraph and LangChain model adapter; PostgreSQL + SQLAlchemy/Alembic + AsyncPostgresSaver; Docker Compose `web`, `api`, `db`; pytest. Hybrid constrained Manager + five workers. Only W1 needs a live LLM in the smallest live path; optional W3 explanation. Python rules for evidence, ranking, simulated booking and review. Token budget: `MAX_LLM_CALLS_PER_CASE=3` including retries; `MAX_RERANKS=1`; deterministic offline mode labeled. No extra front/back frameworks, native mobile tooling, MCP servers, Kafka/RocketMQ, Redis/Celery or real payments.

## Corrections vs older images and V3.1

| ID | Conflict or added requirement | Binding V3.2 decision |
|---|---|---|
| U01 | Old image shows one linear frontend page | The React SPA exposes dashboard plus embedded phone preview; no separate mobile project |
| U02 | User roles on screenshot imply customer/child permissions | Both panels are demo views for one demo actor; do not claim authorization features |
| U03 | Microphone suggests voice transcription | Text input only; no ASR and no fake voice controls |
| U04 | Original architecture references 5 business tables and original ERD 7 | Current database remains V3.1 **8 business tables** including `offer_assessments` |
| U05 | Diagram displayed real location name with contradictory price currency | Use Auckland-area fictional sample packages, NZD 1000 budget; A820, C880, B920 |
| U06 | Unverified candidate shown as verified too early | Desktop preliminary/blocked labels distinct; phone displays only final PASS offer |
| U07 | Dual frontend views could independently mutate business state | Shared Case ID and API client; backend is authoritative, no local UI success fabrication |
| U08 | Phone approval might bypass HITL | Phone POSTs the **existing V3.1 approval endpoint**; service validates nonce/version, persists decision and resumes graph |
| U09 | Two screens may need a new database, app service or endpoints | No: existing GET offers/evidence/approval/order/events and POST decision endpoints suffice |
| U10 | Diagram shows SSE as required | P0 1–2 second REST polling; SSE P1 only, no WebSocket |
| U11 | Different views could disagree after user rejects or refreshes | Refetch both views from PG; show REJECTED/FAILED/HUMAN_REVIEW explicitly, with zero fake success |
| U12 | Mobile simulator may overrun hackathon time | Build smallest phone offer/approval/result path as P0 if practical; omit phone animation, transitions and native behavior before sacrificing backend correctness |

## Backend invariants remain binding

- Requirement clarification: check retry limit before the next question; resume via REST, not auto-loop.
- Rank initial offers, verify one candidate, manager excludes failed candidates, rerank at most once, re-check next candidate before a final PASS offer.
- Save pending approval idempotently before entering side-effect-free `interrupt`; service transaction validates and persists user decision before resuming graph; graph reads durable PG decision.
- Persist immutable offer price/version/expiry and per-source evidence; `offer_assessments` stores aggregate verdict. Approve and book only matching valid snapshots and Case.
- No booking before APPROVED, idempotent order UPSERT and read-back, no paid/ticketed/real claims. All terminal paths append audit events; one shared Case ID drives the two UI views.
- Graph checkpoint persistence and business ORM writes are not one atomic transaction. Side effects must be replay-safe.
- Local Docker Compose is not a public hosted site. Do not claim live model, hosting, tests or metrics without actual evidence.

## Web and mobile page-flow diagrams

- `diagrams/frontend_web_page_flow_v3_2.mmd` explains desktop navigation from Case intake through requirements, agents, evidence, approval and audited result.
- `diagrams/frontend_mobile_page_flow_v3_2.mmd` explains the iOS-inspired in-browser simulator, including shared Case selection, verified-plan display and approval/rejection.
- These are UX flow references, not separate app architecture or permission contracts. Do not implement every illustrated screen in P0; the frontend UX/API spec defines minimum behavior.
- UI reference mockups may explore light, dark and travel-accent styles but are nonbinding; do not implement invented Face ID, notifications, genuine travel inventory, prices or role access.

## P0 completion criteria

Pass the V3.1 required tests (T01–T06, T11, T13–T15) and new frontend acceptance checks **F01–F07** as feasible, report what actually ran, smoke test Docker Compose and one manual cross-view journey. F08–F09 must be verified by UI/source inspection. Never defer submission video and README behind noncritical polish.

## Required generated artifacts and handoff

Implement a single repository with English file content. Communicate with the user in Chinese. Follow `CODEX_START_HERE.md`, run feasible tests and report raw outcomes. Keep each substantive code file typically 100–300 lines and treat 400 as a soft threshold, not a hard cap. Do not split code just to meet line count. When an API or technology detail is unclear, reconcile it with the binding source and annotate the decision rather than silently inventing another stack.
