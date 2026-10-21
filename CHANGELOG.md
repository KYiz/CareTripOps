# Changelog

All changes since CareTrip Ops V4.0 (commit `fe4d655`, the hackathon demo build). Grouped by area, newest work last
within each group. Test counts are for the final state: 187 backend, 15 frontend and 21 browser tests.

## V5.0

### Accounts, family and security
- Email-code sign-in (no passwords) with an HttpOnly session cookie replaces the per-Case browser token. Codes are
  peppered hashes, single use, limited to five guesses and rate limited per address and per IP.
- Sign-in by text message for accounts that verified a mobile number (console in development, Twilio in production).
- Family roles per trip: viewer, co-planner, and owner. Only the traveler approves, pays and cancels. A family member
  can plan a trip and hand it over; the new traveler's saved needs then apply, and offers checked against different
  needs go to a person.
- Step-up confirmation: paying, cancelling a booking and deleting the account need a code confirmed within 10 minutes.
- Terms of Use and Privacy Notice (bilingual templates for legal review), accepted at first sign-in and again when the
  version changes.
- Data export (JSON) and account deletion (refused while a booking is active; trips redacted, booking records
  anonymized, family access removed).
- Production mode refuses to start with demo secrets, console email or SMS, simulated payments, the in-process
  supplier or no Redis, and disables `/api/docs`. Nginx adds CSP and security headers; cross-site writes are rejected.

### Workflow and platform
- Workflow runs in a separate worker on a PostgreSQL job queue (one active run per trip, heartbeats, reaper,
  explicit recovery). Supplier outages are retried with backoff.
- Live updates over server-sent events from PostgreSQL `NOTIFY`; the browser reads a trip only when it changes, in one
  `/snapshot` request.
- Guide data moved out of one JSON column into conversation, itinerary-version and proposal tables.
- JSON logs with request IDs, optional Sentry, Prometheus `/metrics`, Redis-shared rate limits.
- Explicit migrations `0001`–`0013`; a one-off `migrate` service applies them before the API and worker start.
- Backup and verified-restore scripts.
- Nginx re-resolves the API through Docker's DNS, so recreating the API never leaves the site returning 502.

### Booking
- `SupplierProvider` interface with an HTTP client (timeouts, retries, circuit breaker, idempotency keys) and a
  supplier simulator service with inventory, expiring holds, price changes, rejections and fault injection.
- Packages for all six destinations, some with accessible airport transfers.
- Multi-factor ranking (accessibility, price, walking pace, cancellation flexibility, rating, and meals for dietary
  needs) with a reason for every factor.
- Stripe Checkout with authorize-then-capture, or clearly labelled simulated payments. A checkout lasts its full
  31-minute window; a supplier hold that lapsed meanwhile is renewed once at the approved price.
- Order lifecycle with cancellation and refunds by the offer's own policy, counted in New Zealand calendar days.
  A supplier refusing to cancel restores the booking and tells the family it still stands.
- Email outbox written with each change and sent by the worker with retries.

### Travelers and advisors
- Consented needs profile: wheelchair, walking limit, step-free access, accessible bathroom, diet, medical notes and
  emergency contact. Withdrawing consent erases it. Medical notes never reach a model.
- Each needed access claim (lift, step-free entry, accessible bathroom) is proven per offer from independent sources;
  the weakest claim decides, and each unproven claim gets its own advisor review.
- Trip companion: reminders a week and a day before departure (sent once each), a large-print printable trip card,
  and a Help button that shows 111 and alerts family and advisors.
- Advisor console: help requests, evidence reviews, every trip read-only with booking and payment state, the
  traveler's needs with an audit record of each view, and advisor notes.
- Travelers and co-planners can rewrite the illustrative outline; each save is a new version.
- English by default with Simplified Chinese throughout (UI, guide, generated outlines, emails), larger-text mode,
  44px targets, WCAG 2.1 AA.

### Agents
- Planner and Reviewer receive the traveler's mobility needs; guide revisions adjust the current outline instead of
  replacing it; the reviewed draft is kept when the model-call budget runs out; traveler text is treated as data.
- The rule-based outline follows mobility needs. Voice and text guides answer access questions only from verified
  claims and cite the evidence; place answers cite official pages.
- Guide intents understand "don't change the hotel"; an offer that expired during review goes to a person instead of
  looping through recovery.

### Quality
- Backend split into routers, workflow nodes and domain models; frontend into hooks and small components.
- Playwright browser journeys with axe checks in English and Chinese, on desktop and phone sizes.
- GitHub Actions: migrations up and down, `alembic check`, backend, frontend and browser suites, image builds and
  `nginx -t`. All three jobs passed on GitHub for the first pull request and its merge.
- Bugs fixed along the way include: a Chinese budget that crashed the parser, an advisor PASS that left the offer
  excluded, a cancellation stuck after a supplier refusal, a 500 when email failed, async handlers blocking the event
  loop, a cancel button hidden behind another panel, a dashboard that never showed bookings, header overflow, low
  contrast captions, and an unreachable scrolling conversation for keyboard users.
