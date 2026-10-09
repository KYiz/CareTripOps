# CareTrip Ops — Final Review Package V3.2

**Specification and diagram package, not implemented application source.** No application deployment or integration testing has been performed by the package author.

## Read order

1. `CODEX_START_HERE.md`
2. `CARETRIP_FINAL_REVIEW_V3_2.md`
3. `FRONTEND_UX_API_SPEC_V3_2.md`
4. `diagrams/*.mmd` (seven current Mermaid diagrams)
5. `CARETRIP_FINAL_REVIEW_V3_1_SOURCE.md` (prior reference)
6. `CARETRIP_POC_SPEC_V3_0_SOURCE.md` (older reference)
7. `references/*.png` (historical screenshots only)

## What's new

The project remains a **web app**, delivered with React/Vite on the browser and FastAPI/LangGraph/PostgreSQL in Docker. The web app presents **two synchronized views**: a desktop customer-service workbench and a phone-sized interactive customer mockup embedded on the desktop. It is **not** a React Native/mobile app. A new Frontend UX/API spec, Frontend Interaction diagram and API Sequence diagram describe this UI. Current system architecture and workflow diagrams are updated. The ERD is retained (eight business tables): there is no need to invent new tables for visual components.

## Files

- `diagrams/system_architecture_v3_2.mmd`: cloud-independent app boundaries and both browser views
- `diagrams/workflow_v3_2.mmd`: full orchestration including user approval through the phone view
- `diagrams/erd_v3_2.mmd`: 8 business tables (unchanged from corrected V3.1)
- `diagrams/frontend_interaction_v3_2.mmd`: React components, API endpoints and shared Case ID
- `diagrams/frontend_api_sequence_v3_2.mmd`: cross-view interactions, approval, graph resume and business persistence
- `diagrams/frontend_web_page_flow_v3_2.mmd`: desktop screen navigation and state views
- `diagrams/frontend_mobile_page_flow_v3_2.mmd`: iOS-inspired in-browser phone navigation and approval states

## Design references

Web and mobile multi-page mockup images are visual exploration only; these page flows are editable diagrams, not a mandate for every screen to ship in P0. A native iOS application, genuine push notifications, Face ID and real supplier booking are outside scope.

## Rules

V3.2 documents supersede prior versions where contradictory. Previous diagrams and specs are included **for comparison only**. All example evidence, suppliers, prices and bookings are synthetic. Keep actual model and deterministic demo modes clearly distinct. Only report tests and deployment successfully observed after implementation.
