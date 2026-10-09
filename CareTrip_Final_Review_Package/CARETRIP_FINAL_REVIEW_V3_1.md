# CareTrip Ops — Final Architecture Review & Implementation Plan

**Version V3.1 | 2026-10-09 | Status: DESIGN ONLY, NOT IMPLEMENTED OR TESTED**

## Read this first: precedence

1. This V3.1 review and decisions supersede any conflicting wording in `CARETRIP_POC_SPEC_V3_0_SOURCE.md`.
2. `diagrams/*.mmd` are the corrected source diagrams and must agree with V3.1.
3. The original PNGs in `references/` are historical evidence, **not the build specification**.
4. Never claim actual booking, payment, live inventory, supplier verification, multi-tenant authorization, production resilience, or measured model accuracy.

## Final verdict

**GO with constraints.** Keep React/TypeScript/Vite + FastAPI/Python + LangGraph + LangChain model adapter + PostgreSQL + SQLAlchemy/Alembic + Docker Compose. Keep the business roles **one deterministic Manager/Supervisor and five worker roles**. Only Requirements uses an LLM in the minimum live model path; optional natural-language rationale may use a second call. Evidence checking, filtering, ranking, booking, and review are deterministic. Consequently this is a **hybrid agentic workflow**, not six autonomous LLMs.

### Critical issues found, including errors remaining in V3.0

| ID | Priority | Cross-document or technical gap | V3.1 binding correction | Verification |
|---|---|---|---|---|
| R01 | Critical | Architecture image shows direct Manager-to-all-worker dispatch; workflow requires ordered dependencies | StateGraph router enforces required stages; no arbitrary skips | Graph branch tests |
| R02 | Critical | Original image marks a displayed hotel "Verified" before evidence conflict | Distinguish *preliminary*, *blocked*, and *verified final*; label evidence as synthetic | React screenshot/test |
| R03 | Critical | Mock workflow originally can rerank into the rejected hotel again | Explicit `excluded_offer_ids`, a single re-ranking pass, and re-verification of the next candidate | T02/T08 |
| R04 | Critical | V3.0 flowchart checks clarification limit *after* an interrupt, and incorrectly draws resume as unattended loop | Check limit **before** issuing a question/interrupt; resume only via an authenticated-as-demo API action | T03 and limit test |
| R05 | Critical | V3.0 `SAFE{Verified candidate?}` branch is ambiguous when initial candidate fails but lower ranked candidate passes | Evaluate candidates by ranked order, select the first PASS candidate; record `EVIDENCE_CONFLICT` and `MANAGER_RERANK` if top-ranked A fails | T02 |
| R06 | Critical | V3.0 implies `PENDING` approval creation in a node followed by `interrupt`, but does not prescribe durable single creation | Separate idempotent `prepare_approval` and side-effect-free `wait_approval`; run `interrupt()` only in latter | Replay/duplicate tests |
| R07 | Critical | API service marks PG approval APPROVED *before* graph resume; resume node must not expect PENDING only | `approval_service` atomically transitions PENDING→APPROVED (or rejects), then resumes; graph reads authoritative PG decision and validates nonce/version; recovery can resume from approved record | T06/T10 |
| R08 | Critical | Snapshot itself immutable, but `is_excluded` and `evidence_status` were placed on the same mutable row | Immutable quote columns; store evaluations/flags in a separate `offer_assessments` table (small justified eighth table) | UPDATE guard / model tests |
| R09 | High | Evidence source level (`STRONG/WEAK/...`) confused with aggregate claim verdict (`PASS/BLOCK/REVIEW`); `CONFLICTING` is not a single-source strength | `evidence` rows record source polarity/strength; `offer_assessments` store per-claim verdict and reason, with one current assessment per offer+claim | T02/T05 |
| R10 | High | CNY 3,000 input in report versus NZD 820/920 examples in demo and ¥2,980 on visual | Canonical demo: **Auckland area, NZD 1,000 budget**, A NZD 820, B NZD 920, C NZD 880; dates explicitly prefilled in demo form; no currency conversion | UI/demo fixtures |
| R11 | High | Generic hotel price treated as whole trip package | Sample item is a **synthetic 3-day travel package** containing hotel, local transport and activities; document included components and total amount | Fixtures and offer card |
| R12 | High | Approval offer/case foreign keys may cross cases; state_version check can become stale due to changing status | In DB transaction validate matched case_id and exact frozen offer_id/version/total/currency, expiry, approval generation/version; compare expected state version before transition; enforce composite FK where feasible | T07/cross-case test |
| R13 | High | PostgreSQL Checkpoints and ORM writes are not atomic | Business DB authoritative; checkpointer stores recoverable graph progress; side-effect nodes idempotent and reconciliation by key | T10 |
| R14 | High | Graph may show success while database order still missing | Booking transaction commits and order read-back validates before setting `DEMO_COMPLETED`; all terminal states append audit | T01/T10 |
| R15 | High | `GET /approvals` exposing nonce looks like security system | Demo-only random per-approval nonce; store hashed nonce server-side; return raw nonce only in controlled demo UI. Do not claim production authorization | API test/README disclaimer |
| R16 | High | Offline mock and real AI use indistinguishable in architecture image | React clearly labels `Deterministic Demo Mode` vs `Live Model Mode`; fail closed, never silently downgrade mode | T09 |
| R17 | Medium | 1-second polling versus SSE/WebSocket figure implies multiple channels | P0: GET polling only. P1: SSE from append-only audit IDs; no WebSockets | API contract |
| R18 | Medium | Image promises microphone input and user-role permissions not implemented | Text only, single demo actor, no ASR or multi-role RBAC | UI audit |
| R19 | Medium | Nginx proxy and `/healthz`/`readyz` routing inconsistent with `/api` | Expose backend `/healthz` and `/readyz`; proxy them explicitly or use `/api/readyz` alias; document one tested URL | curl smoke test |
| R20 | Medium | Single process background task registry loses tasks on restart | Single uvicorn worker; startup reconciliation marks incomplete cases `RECOVERY_REQUIRED` or explicit manual resume; no exactly-once claim | restart test |
| R21 | Medium | 5 worker roles + 6 call graph not necessarily 6 LLM agents | Role taxonomy in README; only W1 live LLM mandatory; optional W3 explanation LLM only after deterministic ranking | README review |
| R22 | Medium | Token budget did not specify prompts/tool loops/retries | Model mode, per-case call cap 3 incl retries, response token cap, no unnecessary history, counts when provider supports; timeouts fail safe | metrics / simulated 429 |
| R23 | Medium | General completion review skipped for user rejection/human review | Every terminal state appends `audit_events`; W5 generates successful-case report; deterministic close event on other terminals | T04/T05 |
| R24 | Medium | Public hosting and Docker Compose assumed synonymous in architecture graphic | Compose is local reproducible deployment; public hosted environment is separate P1 and needs independently demonstrated URL | README |

## Architecture contract

**Presentation:** React + TypeScript + Vite SPA; `NewCasePanel`, `StatusPanel`, `OfferComparison`, `EvidencePanel`, `ApprovalDialog`, `EventTimeline`, `MockOrderResult`. No microphone or authentication promises. The UI never invents events or success states.

**Application:** FastAPI + Pydantic v2 + SQLAlchemy 2.x + psycopg + Alembic. One worker process. REST read polling in P0. All mutating actions perform DB checks. Backend owns model keys.

**Agent runtime:** LangGraph `StateGraph`, `AsyncPostgresSaver`. Deterministic Supervisor computes next node from compact state and authoritative PG facts. Requirement interpretation is optionally live model through LangChain chat model adapter. Route/evidence/rank/approval/booking are not LLM-decided transactions.

**Tools:** Read-only JSON synthetic catalog/evidence → case offer snapshots. Python functions for product filtering, evidence aggregation, ranking, simulation, and audit. Tools are not MCP servers in P0.

**Persistence:** PostgreSQL `cases`, `requirements`, `offers`, `evidence`, **`offer_assessments`**, `approvals`, `orders`, `audit_events`; LangGraph-managed internal checkpoint tables separately. Quotes immutable; only assessments/approval/order records change. Do not manually create checkpoint tables.

**Deployment:** `web` Nginx-served Vite output, `api` Uvicorn/FastAPI, `db` Postgres with named volume and health checks in Docker Compose; `.env.example` without secrets; test browser at localhost:8080.

## Booking invariant and workflow

1. Create case (DB first); launch controlled graph runner with `thread_id=case_id`.
2. Requirements extraction → required fields complete? If incomplete and clarification_count below max, create question and `interrupt` in a side-effect-free wait node; otherwise `HUMAN_REVIEW`. All real user answers arrive via REST + `Command(resume=...)`.
3. Create immutable case-specific synthetic package offers, storing currency, included components, amount, expiry, version.
4. Produce preliminary deterministic rank. **Not a verified recommendation.**
5. Evidence Worker evaluates candidate required claims from labeled synthetic source records. Aggregates per claim into PASS/BLOCK/REVIEW, with sources and reason; BLOCK if source conflict affects a hard requirement, REVIEW for missing/weak evidence. Only PASS is eligible for final recommendation.
6. Manager records event (`EVIDENCE_CONFLICT`, `MANAGER_RERANK`), excludes A, and chooses next available candidate. The rerank budget permits one extra rank pass. **Revalidate B**; do not bypass Evidence. If none PASS or budget exceeded, `HUMAN_REVIEW`.
7. Save exactly one pending approval bound to case, offer ID/version/amount/currency, case version, expiry and demo nonce. Then `interrupt` in separate read-only wait node.
8. POST decision: server transaction validates nonce/version/ownership, performs one status transition; then resume graph. Graph reads durable decision; REJECT -> audited `REJECTED`; APPROVE -> proceed.
9. Booking node validates approval and offer again; atomic insert using deterministic `idempotency_key` plus UNIQUE; read back committed order. On failed/stale validations never claim success.
10. Review summary and terminal `DEMO_COMPLETED` after order read-back. Other terminal paths always emit audit events.

**Status vocabulary:** `RECEIVED`, `NEEDS_CLARIFICATION`, `REQUIREMENTS_READY`, `OFFERS_DISCOVERED`, `EVIDENCE_REVIEW`, `EVIDENCE_CONFLICT`, `OFFERS_VERIFIED`, `AWAITING_APPROVAL`, `APPROVED`, `REJECTED`, `MOCK_BOOKING`, `SIMULATED_CONFIRMED`, `DEMO_COMPLETED`, `HUMAN_REVIEW`, `FAILED`, `RECOVERY_REQUIRED`. `SIMULATED_CONFIRMED` is order status; `DEMO_COMPLETED` is successful case status. Never reuse production PAID/TICKETED/CLOSED.

## API contract: implement these routes (not schematic image names)

- `GET /healthz` and `GET /readyz` (plus Nginx proxy mapping as tested).
- `POST /api/cases` body `{ "request": "...", "demo_actor": "demo-user", "demo_date": "2026-10-16" }` → 201 case_id + status. Demo date is explicit prefill; do not silently invent departure date.
- `GET /api/cases/{case_id}` → status, active_node, next_action, requirements, state_version.
- `POST /api/cases/{case_id}/clarifications` → `{ "answers": { ... } }`; must be waiting; idempotent or safe to reject duplicates.
- `GET /api/cases/{case_id}/offers` → snapshots + preliminary/verified/blocked label, source/currency/version/expiry.
- `GET /api/cases/{case_id}/evidence` → source records **and** aggregate per-claim assessments.
- `GET /api/cases/{case_id}/approvals` → latest pending/decided demo approval, demo nonce when pending.
- `POST /api/cases/{case_id}/approvals/{approval_id}/decision` → `{ "decision":"APPROVE", "nonce":"...", "expected_state_version": N }`; repeated submissions return one terminal decision/order or safe 409; no duplicate effects.
- `GET /api/cases/{case_id}/orders` → simulated orders only.
- `GET /api/cases/{case_id}/events` → DB-backed, order by monotonic audit event id.
- `GET /api/cases/{case_id}/events/stream` **P1 only**.

**Common errors:** 404 case/offer unknown, 409 state/version/expiry conflict, 422 invalid input, 429 own rate budget, 503 model unavailable. Use safe failure, not silent fallback.

## PostgreSQL data model (V3.1)

Base tables mostly inherit V3.0 columns, with the following authoritative changes:

- `offers`: immutable snapshot (`id`, `case_id`, `catalog_product_id`, `version`, `total_amount`, `currency`, `includes jsonb`, `supplier_claims jsonb`, `expires_at`, `source_updated_at`, `created_at`); no `is_excluded` or mutable `evidence_status` on the snapshot. Unique `(case_id,catalog_product_id,version)` and `(id,case_id)` for matched-case FK references.
- `evidence`: source facts (`offer_id`, `claim_type`, `source`, `polarity`, `source_strength`, `source_time`, `reference`, `detail`). A single conflicting source is not automatically an aggregate `CONFLICTING` category.
- **`offer_assessments`**: `id`, `offer_id`, `claim_type`, `verdict PASS|BLOCK|REVIEW`, `reason_code`, `source_refs jsonb`, `assessed_at`, `assessment_version`; unique `(offer_id,claim_type,assessment_version)`; the latest version drives filtering. Per-case excluded IDs are in graph state and auditable event payloads.
- `approvals`: `case_id`, `offer_id`, `offer_version`, `approved_amount`, `currency`, `case_state_version`, `nonce_hash`, `status`, `created_at`, `decided_at`; partial unique `(case_id) WHERE status='PENDING'`. Cross-case FKs or transaction checks required.
- `orders`: `case_id`, `offer_id`, `approval_id`, `idempotency_key UNIQUE`, `SIMULATED_CONFIRMED|FAILED`, `total_amount`, `currency`, timestamps. Transaction rechecks ownership, snapshot, approval, amount and expiry.
- `audit_events`: append-only, monotonic bigint id, case id, role, event type, status, structured payload, latency and provider-reported token counts where available.
- `requirements`: single Case association; user-entered constraints and clarified fields. Dates and currencies are never guessed.

**Consistency:** Business tables are authoritative; checkpoint is a resumable orchestration snapshot, not proof of business commit. A failed checkpoint after a committed order must replay into *the same existing order* via idempotency lookup. Any side-effecting graph node must be replay-safe. Avoid pretending the two stores share an atomic transaction.

## Real model and token policy

- Default: `MODEL_MODE=mock_llm` for deterministic offline verification, visibly labeled.
- Optional `MODEL_MODE=api` requires user-supplied model credentials and a compatible model integration. W1 uses exactly one request in successful complete-input path; optional W3 explanation uses up to one more, but not before deterministic ranking. A third model request is reserved for retry; no hidden automatic 20-call loops.
- `MAX_LLM_CALLS_PER_CASE=3`, `MAX_RERANKS=1`, `MAX_CLARIFICATIONS=2`, model request timeout and output cap. Prompt includes concise task state only; source evidence and offer prices are tools/DB truth.
- On quota exhaustion, malformed JSON, or model timeout: error event, `HUMAN_REVIEW`/`FAILED` without booking. Switching to mock mode requires an **explicit** operator choice and visible indication.
- Token pricing/usage only reported when measured; no fabricated percentages.

## Demonstration contract

**Demo scenario:** NZD 1,000 budget, three travelers, three days, Auckland-area synthetic travel packages; date explicitly supplied by demo form. Package A NZD 820 preliminary rank #1, but accessibility source conflict blocks it. Package C NZD 880 missing floor coverage -> REVIEW. Package B NZD 920 passes the synthetic evidence policy and becomes verified #1 after arbitration. The UI shows the rejection reason, checked source lines, final package amount, human approval, and exactly one simulated order. Avoid showing a real hotel photograph/name associated with unverified claims.

## Test matrix and done gates

| Test | Expected result |
|---|---|
| T01 Safe/no-conflict | Completed with one simulated order only after approved |
| T02 Hotel A conflict | EVIDENCE_CONFLICT + MANAGER_RERANK; A excluded; B selected after verification |
| T03 Missing field | Pause and require REST clarification; stop after clarification cap |
| T04 Reject | REJECTED, zero orders, audit event |
| T05 No PASS option | HUMAN_REVIEW, zero orders |
| T06 Duplicate approval/order | One transition, one order, unique idempotency key |
| T07 Expired/stale offer | 409 and no booking against stale snapshot |
| T08 Rerank cap | At most one pass, no cycles forever |
| T09 Invalid model output / quota | Clear 503 or controlled case exception; never silently mislabel mock as live |
| T10 DB/checkpoint interrupted | Existing order reused; no duplicate, recovery state explicit |
| T11 Browser reload | Render accurate state/trace from API, no local fabricated timeline |
| T12 Compose restart | PG data still exists; no duplicate effects; hanging cases marked recoverable |
| T13 Cross-case approval attempt | 409/403; cannot authorize an offer from another case |
| T14 Event append on rejection/failed/manual | Every terminal path has at least one audit event |
| T15 Demo currencies/dates | NZD-only canonical fixture, explicitly prefilled date, no silent FX |

**P0 must pass:** T01–T06, T11, T13–T15 and local Compose smoke test; remaining cases should be attempted, with truthful test results. If implementation time is nearly over, prioritize one end-to-end user-facing demonstration, README and video over P1.

## Phased delivery plan (timeboxed)

1. **Phase A / Foundation:** Docker Compose (`web`, `api`, `db`), Vite React page, FastAPI health+Case CRUD, PG+Alembic. Smoke test.
2. **Phase B / Domain kernel:** immutable sample offers, evidence source records, assessment rules, preliminary/verified rank, unit tests. No LLM yet.
3. **Phase C / Agent runtime:** StateGraph, deterministic Supervisor, checkpoint, audit events, conflict arbitration and exclusion. Test graph independently.
4. **Phase D / Human and booking:** prepare approval, `interrupt`, REST resume, approval transaction, mocked order UPSERT/readback; verify duplicates and rejection.
5. **Phase E / UI wiring:** refreshable Case view, evidence panel, timeline, approval buttons and demo result. First use GET polling; SSE optional.
6. **Phase F / Real LLM smoke:** explicitly enable API mode, test one short request and measure usage; leave deterministic mode available and clearly labeled.
7. **Phase G / Handoff:** `docker compose config`, `docker compose up --build -d`, health curl, backend pytest, manual browser run, README truth table, source disclosure, video under 3 minutes with face, submit by 16:00.

**Cut list:** hosting bonus → SSE → visual polish → LLM-generated explanation → complex review. **Do not cut:** real PG, trace, arbitration, approval-before-booking, idempotency, core tests, README or video.

## Codex handoff

Start from `CODEX_START_HERE.md`. Do not interpret an original PNG screenshot as stronger authority than V3.1. Create a new repository during the event. Deliver only claims you can demonstrate from real code, logs and tests. Treat the spec as a design, not proof that anything has already been built.
