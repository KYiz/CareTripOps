import type { TravelerNeeds } from './types';
// English labels for backend enums. Components pass them through t() to display them.

const STATUS: Record<string, string> = {
  RECEIVED: 'Received', NEEDS_CLARIFICATION: 'Needs details', REQUIREMENTS_READY: 'Details complete',
  OFFERS_DISCOVERED: 'Offers found', EVIDENCE_REVIEW: 'Checking evidence', EVIDENCE_CONFLICT: 'Evidence conflict',
  OFFERS_VERIFIED: 'Offer verified', AWAITING_REVIEW: 'Advisor checking evidence', AWAITING_APPROVAL: 'Awaiting approval',
  APPROVED: 'Approved', AWAITING_PAYMENT: 'Awaiting payment', REJECTED: 'Declined', BOOKING: 'Booking',
  BOOKED: 'Booked', CANCELLED: 'Cancelled',
  HUMAN_REVIEW: 'Advisor review', FAILED: 'Failed', RECOVERY_REQUIRED: 'Paused, needs resume',
};

const FIELD: Record<string, string> = {
  destination: 'Where in New Zealand?', departure_date: 'Departure date', traveler_count: 'Number of travelers',
  duration_days: 'Number of days', budget: 'Total budget', currency: 'Currency (NZD)',
};

export const statusLabel = (status: string) => STATUS[status] ?? status.replaceAll('_', ' ').toLowerCase();
export const fieldLabel = (field: string) => FIELD[field] ?? field.replaceAll('_', ' ');

/** The traveler-facing summary of where a trip stands. */
export function friendlyStatus(status: string | undefined, runState?: string): string {
  if (!status) return 'Ready to plan';
  if (status === 'AWAITING_APPROVAL') return 'Ready for your decision';
  if (status === 'BOOKED') return 'Your trip is booked';
  if (status === 'AWAITING_PAYMENT') return 'Ready for payment';
  if (status === 'AWAITING_REVIEW') return 'An advisor is checking accessibility details';
  if (status === 'BOOKING') return 'Confirming with the hotel';
  if (status === 'CANCELLED') return 'Booking cancelled';
  if (status === 'REJECTED') return 'Plan declined';
  if (status === 'HUMAN_REVIEW') return 'A travel advisor will review this';
  if (status === 'NEEDS_CLARIFICATION') return 'A few details are needed';
  if (status === 'RECOVERY_REQUIRED') return runState && runState !== 'idle' ? 'Resuming your trip' : 'Planning paused';
  return 'We are checking your trip';
}

/** A sample trip request in the reader's language; the backend parser understands both. */
export function sampleTripRequest(destination: string, lang: 'en' | 'zh'): string {
  return lang === 'zh'
    ? `我们三个人想去${destination}轻松玩三天，总预算 1000 纽币，需要能到达所有客房楼层的电梯。`
    : `Three travelers want a relaxed three-day trip to ${destination}. Our total budget is NZD 1000. We need a lift serving all guest floors.`;
}

/** Plain-language refund rules, most generous first. Keys go through t(). */
export function policyLines(policy: { days_before: number; refund_percent: number }[]): { key: string; vars: Record<string, number> }[] {
  const rules = [...policy].sort((a, b) => b.days_before - a.days_before);
  if (!rules.length) return [{ key: 'This booking cannot be refunded after confirmation.', vars: {} }];
  const lines = rules.map((rule): { key: string; vars: Record<string, number> } => rule.refund_percent >= 100
    ? { key: 'Full refund if you cancel at least {days} days before departure.', vars: { days: rule.days_before } }
    : { key: '{percent}% refund if you cancel at least {days} days before departure.', vars: { percent: rule.refund_percent, days: rule.days_before } });
  return [...lines, { key: 'No refund closer to departure than that.', vars: {} }];
}

export const FAILURE_REASONS: Record<string, string> = {
  PRICE_CHANGED: 'The hotel changed its price before we could hold your room.',
  SOLD_OUT: 'The hotel had no rooms left for your dates.',
  SUPPLIER_REJECTED: 'The hotel could not accept this booking.',
  HOLD_EXPIRED: 'The room hold ran out before payment was completed.',
  PAYMENT_NOT_COMPLETED: 'Payment was not completed in time.',
  PAYMENT_NOT_AUTHORIZED: 'The payment was not authorized.',
};

/** Short names for the access claims an offer must prove. */
export const CLAIM_LABELS: Record<string, string> = {
  lift_serves_all_guest_floors: 'Lift to every guest floor',
  step_free_entry: 'Step-free entrance',
  accessible_bathroom: 'Accessible bathroom',
  no_access_need: 'No access need',
};

const WHEELCHAIR_LABELS: Record<string, string> = {
  SOMETIMES: 'Wheelchair for longer distances', MANUAL: 'Manual wheelchair', POWER: 'Power wheelchair or scooter',
};
const DIET_LABELS: Record<string, string> = {
  VEGETARIAN: 'Vegetarian', VEGAN: 'Vegan', GLUTEN_FREE: 'Gluten-free', HALAL: 'Halal', KOSHER: 'Kosher',
  DIABETIC: 'Diabetic-friendly', LOW_SODIUM: 'Low salt', NUT_ALLERGY: 'Nut allergy', SOFT_FOOD: 'Soft food',
};

/** The saved needs a trip was planned around, as translatable phrases. */
export function needsPhrases(needs: Partial<TravelerNeeds> | undefined): { key: string; vars: Record<string, string> }[] {
  if (!needs) return [];
  const out: { key: string; vars: Record<string, string> }[] = [];
  if (needs.wheelchair && WHEELCHAIR_LABELS[needs.wheelchair]) out.push({ key: WHEELCHAIR_LABELS[needs.wheelchair], vars: {} });
  if (needs.step_free) out.push({ key: 'Step-free access', vars: {} });
  if (needs.accessible_bathroom) out.push({ key: 'Accessible bathroom', vars: {} });
  if (needs.max_walk_meters != null) out.push({ key: 'Walks up to {meters} m', vars: { meters: String(needs.max_walk_meters) } });
  for (const diet of needs.dietary ?? []) out.push({ key: DIET_LABELS[diet] ?? diet, vars: {} });
  return out;
}

export const FACTOR_REASONS: Record<string, string> = {
  LIFT_YES_STEP_FREE_YES: 'Lift to all floors and step-free entry',
  NO_ACCESS_NEED: 'Fits your access needs',
  WALKING_LOW: 'Little walking needed',
  WALKING_MODERATE: 'Some walking needed',
  WALKING_HIGH: 'A lot of walking',
};
