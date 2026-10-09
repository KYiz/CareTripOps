# CareTrip Ops V3.2 Mermaid Review

## Baseline
V3.2 diagrams supersede V3.1 diagrams in the uploaded set. The uploaded V3.1 and V3.2 ERDs are text-identical.

## Frontend model
One React + TypeScript + Vite SPA contains a desktop operations view and an in-browser 390 x 844 phone simulator. The phone view is iOS-inspired presentation only, not a native iOS application. Both views share the selected Case ID, typed FastAPI client and backend-persisted data.

## New diagrams
- frontend_web_page_flow_v3_2.mmd: Desktop page and operational navigation flow.
- frontend_mobile_page_flow_v3_2.mmd: Phone simulator navigation and decision flow.

## Existing files
- frontend_interaction_v3_2.mmd: Cross-view integration and REST endpoints.
- frontend_api_sequence_v3_2.mmd: Request/response and approval sequence.
- workflow_v3_2.mmd: Agent/business process.
- system_architecture_v3_2.mmd: Deployment/component boundaries.
- erd_v3_2.mmd: Business data schema.

## Visual-reference differences
Do not infer native Face ID, native push notifications, actual supplier booking, live supplier pricing, unsupported administrative modules, or invented worker roles from generated UI mockups.

## Validation
New diagrams passed basic source checks for balanced node delimiters and subgraphs. Mermaid CLI rendering was unavailable in this environment; full parser/render validation has not been performed.
