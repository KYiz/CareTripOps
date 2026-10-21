# Skill contracts

Skills are typed Python functions, not autonomous agents. Workflow nodes in `app/workflow/` call them; side effects
with suppliers and payments live in `app/booking.py`. Supplier data in this build comes from the simulator.

| Skill | Input → output | Rules | Side effects and replay | Tests |
|---|---|---|---|---|
| `extract_requirements` | `RequirementInput → RequirementOutput` | Never invents a currency or date. Destinations and attractions come from `destinations.py`; English and Chinese requests. API mode uses Gemini or OpenAI; errors go to a person, never a mock fallback. | None; the requirements node persists once per Case. | `test_skills.py` extraction, Chinese and foreign-scope tests |
| `validate_requirements` | `RequirementOutput → list[str]` | Destination, date, travelers, days, budget and NZD are required. | Pure. | missing-field and currency tests |
| `search_suppliers` | `RequirementOutput, SupplierProvider → list[OfferData]` | Requirements must be complete. Offers carry supplier refs, attributes (lift, step-free, bathroom, walking, rating, diets, transfers), cancellation policy and per-claim evidence. | Discovery stores immutable snapshots (DB trigger) once per Case/product/version. | `test_supplier_offers_are_priced_for_the_party_and_carry_evidence` |
| `required_claims` | `elevator_required, needs → list[str]` | Words like "lift" need lift + step-free; a wheelchair adds the claims it needs; saved needs add step-free or bathroom. | Pure. | `test_claims_follow_the_words_and_the_saved_needs` |
| `compare_offers` | `RankingInput → RankingOutput` | Budget and currency are hard limits; so is a walking limit of 200 m or less against a lot of walking. Score = accessibility (mean of the needed claims) 35%, price 25%, pace 15%, flexibility 15%, rating 10%, plus meals 10% with dietary needs (normalised), with a reason per factor. | Pure; the comparison node stores `offer_rankings`. | ranking tests |
| `verify_evidence` / `assess_offer` | `list[EvidenceData], claim → AssessmentData`; `…, claims → {claim: AssessmentData}` | Per claim: any contradiction blocks; strong support passes; otherwise REVIEW. No claims needed → one PASS. The weakest claim decides the offer (`db.offer_verdict`). Advisors add later versions per claim. | Pure; discovery stores sources (URL, content hash) and version 1 of each claim. | `test_evidence_conflict_review_and_pass` |
| `rerank_offers` | `RankingInput, verdicts → RankingOutput` | Excludes BLOCK and REVIEW verdicts. The Manager allows `MAX_RERANKS`; then an advisor review or a person. | Pure. | `test_rerank_excludes_blocked_and_unsettled_offers` |
| `refund_percent` | `policy, departure, today → int` | The most generous rule whose `days_before` is met; 0 otherwise. | Pure. | `test_refund_follows_the_offer_policy` |
| `prepare_approval` | `ApprovalInput → Approval` | Case OFFERS_VERIFIED; snapshot version, amount, currency, expiry and latest PASS verdict must match. | One PENDING approval per Case (partial unique index). | integration approval tests |
| `generate_review` | `ReviewInput → ReviewOutput` | Called only after the order is CONFIRMED. | Pure; the review node sets BOOKED once. | `test_review_summarises_the_confirmed_order` |

Booking (`app/booking.py`): hold → authorize → book → capture, each external call keyed by our own IDs
(`hold:`, `pay:`, `book:`, `capture:`, `cancel:`, `refund:` + order ID), so retries never double-book or double-charge.

## Model budget

`MODEL_MODE=mock_llm` is the default. In `api` mode the per-Case call counter (`MAX_LLM_CALLS_PER_CASE`, default 7) is
committed before each provider request and covers requirements, the initial Planner/Reviewer and one reviewed revision.
A failed itinerary call yields a labelled local outline (`GEMINI_FAILED`). If the Reviewer asks for a change but no
call is left, the reviewed first draft is kept when it passes our deterministic checks (`revision_skipped` in the trace);
otherwise the local outline is used. Evidence, ranking, approval, payment and booking never depend on a model.

## Planner and Reviewer (`app/two_brains.py`)

- Inputs: destination, pace, travelers, budget, allowed places with their source pages, the current days and the
  traveler's mobility needs (wheelchair, walking limit, step-free; never diet, medical notes or contacts). The
  traveler's words are passed as data, and the prompt says so.
- Initial plans create days from the request; guide revisions (`revision=True`) adjust the current days to the
  traveler's change request and keep the rest.
- Every model day is validated: same day count, only allowed places, no repeats, one or two activities, and no
  prices, durations, distances or booking claims. The rule-based outline follows the same needs (gentle days and a
  step-free check when mobility is limited).
