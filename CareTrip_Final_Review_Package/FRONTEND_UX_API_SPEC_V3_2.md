# CareTrip Ops V3.2 — Frontend UX, Shared API and Browser Phone Simulator

**Status:** Implementation specification, not proof of implementation. **Language:** English for all project artifacts. **Communication with the user:** Chinese.

## 1. Product surface and hard boundaries

Build **one browser-based React + TypeScript + Vite application**, offering two simultaneously visible perspectives on a large desktop screen:

1. **Desktop Operations Dashboard:** The travel-agent/operator view for entering requests, observing actual agent events, reviewing evidence and preliminary/final offers, and seeing mock-booking status.
2. **In-Browser Phone Simulator:** A CSS phone-frame viewport showing the customer's simplified view of the *same* Case: verified offer, transparent simulation disclaimer, Approve/Reject, and the committed mock-booking outcome. Target inner viewport about 390 x 844 CSS pixels, scaling to fit the available screen. This is a **web component**, not an installed app or a mobile runtime.

No React Native, Expo, Android Studio, WebView application, genuine phone access, separate backend, mobile push notifications, SMS, camera, microphone, user account systems, delegation authority, or payment features. Both are **demo presentation modes for one actor**, not two authenticated users.

## 1.1 Page-flow references and visual treatments

The editable `frontend_web_page_flow_v3_2.mmd` and `frontend_mobile_page_flow_v3_2.mmd` describe proposed navigation and state transitions. They do not imply two separate apps or require full multi-page implementation in P0. Desktop and iOS-inspired mobile layouts may vary in visual theme while sharing the same case state, API types and source-of-truth behavior. Image mockups are nonbinding; omit unsupported native device interactions and imaginary travel inventory. Features beyond the screen-level contract below require an explicit scope decision.

## 2. Visual hierarchy / responsive layout

- Top header: project identity, Case ID, case status, visibly marked `Deterministic Demo Mode` or `Live Model Mode`; `Synthetic data / Simulation only` disclosure.
- Desktop left main column: request form, explicit sample departure date, price currency (NZD), constraints, progress, offer comparison, and evidence/Manager rationale.
- Desktop right rail: narrower phone frame and primary customer action UI. On narrow browser windows use stacked layout or a `Dashboard / Phone Preview` tab; never create a native app.
- Timeline is a separate expandable dashboard section sourced from `/events`, ordered by monotonic event ID. Empty/loading/error states are real.
- Input uses text only. No nonfunctional microphone icon or faux live user roles. Synthetic supplier packages must not be illustrated with real hotel imagery implying the evidence is real.
- All visible text in the shipped UI is English; labels indicate prices in NZD.

## 3. Frontend state ownership

Single in-memory selected `caseId`, optionally reflected in `?caseId=...` for reload. One shared `apiClient` with typed response schemas; both visual views derive from *the same* fetched Case, offers, assessments, events, approval and order. Do not copy independent sets of business state into Dashboard vs Phone. Initial P0 refresh can poll GET endpoints at 1–2 s while active, stop or slow down after a terminal state, and refetch immediately after a mutation. Use the existing in-spec REST endpoints; **no new API endpoints are necessary** for the simulator.

Source-of-truth priority: PostgreSQL business records served by FastAPI. Graph checkpoints are internal and do not drive frontend truth directly. Never optimistically display `DEMO_COMPLETED`. After any approval timeout or network error, refetch persisted approval and orders before retrying, avoiding duplicate UI actions.

## 4. Screen-level behavior and permissions

| Component / view | Primary states | Behavior / API |
|---|---|---|
| `CaseForm` (desktop) | idle, submitting, input error | Text request; explicit NZD and sample date; POST `/api/cases` once per user submission; save case ID |
| `CaseStatus` (desktop) | running, clarification, approval, terminal | GET `/api/cases/{caseId}`; current node, status and next action; render backend errors |
| `AgentTimeline` (desktop) | none, events, API error | GET `/api/cases/{caseId}/events`; show true Manager reason and ordered events |
| `OfferComparison` (desktop) | preliminary, blocked, verified | GET `/offers`; show preliminary offer A without verified badge; show A blocked with conflict; only B approved if PASS |
| `EvidencePanel` (desktop) | source records + verdict | GET `/evidence`; support/contradict source summaries; show synthetic label |
| `PhoneFrame` (same React SPA) | waiting, verified, terminal | Style-only shell, no device services; read existing fetched Case state |
| `VerifiedTravelPlan` (phone) | waiting, verified, conflict unavailable | Display ONLY final PASS offer; exact amount, included package components, validity, and simulation disclaimer |
| `ApprovalActions` (phone) | waiting, pending, sending, decided | GET `/approvals`; POST `/approvals/{approvalId}/decision` with nonce + expected version; disable repeated submission pending response |
| `BookingResult` (phone & desktop) | no order, rejected, manual, completed | GET `/orders`; show mock order confirmation only if persisted and Case is `DEMO_COMPLETED` |

**Clarification:** For P0, the desktop dashboard presents clarifying questions and POSTs answers to the existing clarification endpoint. The phone simulator does not need a second input mechanism for requirements. It is acceptable that mobile view is idle until a verified offer exists.

## 5. Synchronization invariants

1. A single `caseId` identifies the case in both views; switching selected Case updates both.
2. Desktop displays preliminary, blocked and verified offers accurately. Phone **never** shows a preliminary or blocked offer as bookable.
3. Approval is rendered only when the backend has a `PENDING` approval for a final verified offer; action includes nonce, expected version, and explicit simulation label.
4. Once user approves, show `Processing simulated booking…` while re-fetching. Display confirmation only after PG order read-back and `DEMO_COMPLETED`.
5. `REJECTED`, `HUMAN_REVIEW`, `FAILED`, `RECOVERY_REQUIRED`, stale approval and model quota failures show their own honest screens. Never show a generic green completion card.
6. A browser reload preserves Case selection if URL holds Case ID and reconstructs backend facts. Switching between dashboard and phone never creates another Case.
7. The fixed demo story is Auckland, three travelers, three days, NZD 1,000 budget and explicitly prefilled departure date. Package A 820 (BLOCK), C 880 (REVIEW), B 920 (PASS). These are **synthetic full travel package totals**, not hotel-room nightly rates.

## 6. Shared typed API contract

Use V3.1 REST routes unchanged: `POST /api/cases`, `GET /api/cases/{caseId}`, `POST /api/cases/{caseId}/clarifications`, `GET /api/cases/{caseId}/offers`, `GET /api/cases/{caseId}/evidence`, `GET /api/cases/{caseId}/approvals`, `POST /api/cases/{caseId}/approvals/{approvalId}/decision`, `GET /api/cases/{caseId}/orders`, `GET /api/cases/{caseId}/events`. The auth model remains a single explicitly labeled demo actor.

- Success and failure envelopes, UUID IDs, enum values, money strings, UTC timestamps and error codes follow V3.1.
- Ensure field-level correspondence between Pydantic schemas, OpenAPI, typed React responses, SQLAlchemy models and LangGraph state references. Refetch after any POST; backend state is authoritative.
- Use REST GET polling in P0. SSE `/events/stream` is P1; do not implement WebSocket.
- No raw model keys in browser, no real personal data, no simulated approval that skips backend verification.

## 7. Suggested simple React structure (not mandatory one-file-per-widget)

```text
frontend/src/
  App.tsx
  api/client.ts
  types.ts
  components/
    Dashboard.tsx       # Request, status, timeline, evidence, offers
    PhoneSimulator.tsx  # Phone frame, verified plan, approval, result
    OfferDetails.tsx    # Shared safe display logic when useful
  styles.css
```

Aim for 100–300 lines in substantive source files with **400 lines as a soft review threshold**, not a mandatory cap. Splitting follows responsibilities, not mechanical line limits. Avoid adding Redux, Next.js or an additional state synchronization service solely for the phone frame.

## 8. Acceptance tests added to V3.1

- **F01:** Desktop submits one Case, phone shows the same Case ID and backend status without creating its own Case.
- **F02:** Before evidence verification, phone shows no verified/approvable offer; desktop can show labeled preliminary A.
- **F03:** Conflict events are fetched from PG; A is BLOCK, C REVIEW, B PASS; phone displays only verified B.
- **F04:** Phone Approve writes one decision via API; order count is zero before approval, one after confirmed; desktop refetches and shows the same order.
- **F05:** Phone Reject leads to `REJECTED`, both views show rejection, no order exists.
- **F06:** Duplicate clicks/network retry do not create multiple approval transitions/orders; refetch recovers after timeout.
- **F07:** Refresh at `?caseId=<uuid>` rebuilds both views using API; no hardcoded success events.
- **F08:** Backend failure, stale snapshot, human-review and deterministic/live modes are visibly distinct.
- **F09:** No native mobile libraries, second database, microphone, fake real hotel claims or browser API secrets.

## 9. Delivery priority and video demo

P0: functional dashboard + **minimal** in-browser phone frame (verified offer, approval, outcome) connected to real REST/PG state. P1: fine UI polish, motion, advanced responsive variations, SSE and public deployment. Keep the end-to-end evidence conflict, Manager arbitration, explicit approval and idempotent booking intact.

Suggested under-3-minute demo: create sample Case in desktop, observe Manager BLOCK A/recommend B with cited synthetic evidence, see B on phone frame, approve once on phone, observe completed simulated order on both views. Distinguish live API mode from deterministic offline mode. Face on camera required by event rules.
