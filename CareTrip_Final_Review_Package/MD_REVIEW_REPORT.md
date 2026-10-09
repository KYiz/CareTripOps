# CareTrip Ops Markdown cross-document audit (2026-10-09)

## Coverage
Seven uploaded Markdown files reviewed. `CARETRIP_FINAL_REVIEW_V3_1(2).md` is byte-identical to `CARETRIP_FINAL_REVIEW_V3_1_SOURCE.md`, so only the latter is retained. This package contains four aligned current V3.2 documents and two unchanged historical source documents.

## Findings

1. **High — Diagram inventory drift:** README and Codex handoff list five MMDs, while the current UX diagrams set has seven. Fixed in README/Codex and documented in V3.2.
2. **High — Diagram scope ambiguity:** Two new Web/mobile page-flow MMDs add richer navigation than the binding frontend minimum. Clarified that they are illustrative UX references and do not create new P0 requirements.
3. **High — Historical priority contradiction:** V3.0 claims to be the single source of truth and V3.1 calls itself authoritative, whereas V3.2 explicitly supersedes both. Keep historic files unchanged; current read order makes precedence explicit. Do not ask Codex to execute old standalone instructions.
4. **Medium — Native-device / unsupported UI risk:** Image mockups include device-specific patterns and travel illustrations. Current spec explicitly excludes native iOS, Face ID, push notifications, real supplier claims and real payment. Added extra clarification.
5. **Medium — Role mismatch risk:** Mobile reference diagram contains navigation such as cases and agent progress. These are optional demonstration navigation, not a separate customer account, independently authorized role or second backend.
6. **Medium — Test coverage mismatch:** The mobile page flow includes a pending/stale approval path; existing F01–F09 plus backend T tests remain the binding acceptance criteria. Add screenshot/navigation checks only if those optional pages are implemented.
7. **Low — Redundant upload:** V3.1 main file and V3.1 source are exact duplicates. Preserve only source in the cleaned package.

## Unchanged critical invariants
- One React SPA with desktop plus phone-frame preview; one shared caseId and FastAPI/PostgreSQL backend.
- Manager plus five hybrid worker responsibilities; eight business tables.
- Preliminary offer is never bookable; only verified PASS offer reaches pending approval.
- Persist approval before graph resume, and read back committed simulated order before completion.
- All evidence and travel packages are synthetic.

## Validation status
The audit compares specification text and uploaded Mermaid source, not a running app. No runtime implementation, browser rendering or integration tests are claimed.
