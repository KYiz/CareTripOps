export type CaseStatus = 'RECEIVED' | 'NEEDS_CLARIFICATION' | 'REQUIREMENTS_READY' | 'OFFERS_DISCOVERED' | 'EVIDENCE_REVIEW' | 'EVIDENCE_CONFLICT' | 'OFFERS_VERIFIED' | 'AWAITING_REVIEW' | 'AWAITING_APPROVAL' | 'APPROVED' | 'AWAITING_PAYMENT' | 'REJECTED' | 'BOOKING' | 'BOOKED' | 'CANCELLED' | 'HUMAN_REVIEW' | 'FAILED' | 'RECOVERY_REQUIRED';

export interface Requirements {
  destination: string | null;
  destination_scope: 'SUPPORTED' | 'OUTSIDE_NZ' | 'UNKNOWN';
  attractions: string[];
  travel_pace: 'RELAXED' | 'STANDARD';
  departure_date: string | null;
  traveler_count: number | null;
  duration_days: number | null;
  budget: string | null;
  currency: string | null;
  // `needs` is the traveler's saved profile snapshot; viewers do not receive it.
  hard_constraints: { elevator_required?: boolean; needs?: Partial<TravelerNeeds> };
  missing_fields: string[];
}

export interface CaseData {
  case_id: string;
  status: CaseStatus;
  active_node: string;
  state_version: number;
  requirements: Requirements | null;
  draft_itinerary?: DraftDay[];
  itinerary_source?: ItinerarySource;
  itinerary_version?: number;
  missing_fields: string[];
  next_action: string | null;
  model_mode: 'mock_llm' | 'api';
  model_status: 'MOCK' | 'PENDING' | 'SUCCEEDED' | 'FAILED';
  llm_provider: 'openai' | 'gemini' | null;
  my_role: MemberRole;
  run_state: 'idle' | 'queued' | 'running';
  created_at: string;
}

// ADVISOR: CareTrip staff reading a trip they are not a member of.
export type MemberRole = 'OWNER' | 'CO_PLANNER' | 'VIEWER' | 'ADVISOR';
/** Roles an owner can invite someone into; OWNER hands the trip over. */
export type InviteRole = 'CO_PLANNER' | 'VIEWER' | 'OWNER';
export const roleRank: Record<MemberRole, number> = { VIEWER: 1, ADVISOR: 1, CO_PLANNER: 2, OWNER: 3 };
export interface User {
  id: string; email: string; display_name: string | null; is_advisor: boolean;
  terms_version: string | null; sensitive_consent: boolean; phone: string | null;
}
export type Wheelchair = 'NONE' | 'SOMETIMES' | 'MANUAL' | 'POWER';
export type Dietary = 'VEGETARIAN' | 'VEGAN' | 'GLUTEN_FREE' | 'HALAL' | 'KOSHER' | 'DIABETIC' | 'LOW_SODIUM' | 'NUT_ALLERGY' | 'SOFT_FOOD';
export interface TravelerNeeds {
  wheelchair: Wheelchair; max_walk_meters: number | null; step_free: boolean; accessible_bathroom: boolean;
  dietary: Dietary[]; medical_notes: string;
}
export interface EmergencyContact { name: string; relationship: string; phone: string }
export interface TravelerProfile { needs: TravelerNeeds; emergency_contact: EmergencyContact; updated_at: string | null; consent: boolean }
export interface CaseSummary { case_id: string; role: MemberRole; status: CaseStatus; destination: string | null; created_at: string }
export interface Invitation { id: string; case_id: string; role: MemberRole; invited_by: string; destination: string | null; expires_at: string }
export interface CaseMember { user_id: string; email: string; display_name: string | null; role: MemberRole; joined_at: string }
export interface CaseMembers {
  members: CaseMember[];
  invitations: { id: string; email: string; role: MemberRole; expires_at: string }[];
  my_role: MemberRole;
}

export interface DraftDay {
  day_number: number;
  title: string;
  note: string;
  attraction: string | null;
  activities?: string[];
  rest_note?: string;
  intensity?: 'LOW' | 'MODERATE';
  verification_notes?: string[];
  source_urls?: string[];
  status: 'ILLUSTRATIVE_DRAFT';
}

export interface Offer {
  id: string;
  case_id: string;
  product_id: string;
  version: number;
  total_amount: string;
  currency: string;
  includes: string[];
  supplier_claims: Record<string, boolean | null>;
  expires_at: string;
  label: 'PRELIMINARY' | 'BLOCKED' | 'REVIEW' | 'VERIFIED';
  verdict: 'PASS' | 'BLOCK' | 'REVIEW' | null;
  claims: Record<string, 'PASS' | 'BLOCK' | 'REVIEW'>;
  reason_code: string | null;
  name: string | null;
  attributes: OfferAttributes;
  cancellation_policy: PolicyRule[];
  under_review: boolean;
  ranking: { round: number; eligible: boolean; score: number; factors: RankingFactor[] } | null;
}

export interface OfferAttributes {
  lift_all_floors?: boolean | null; step_free_entry?: boolean | null; accessible_bathroom?: boolean | null;
  walking_level?: 'LOW' | 'MODERATE' | 'HIGH'; rating?: number; dietary_options?: Dietary[]; accessible_transfer?: boolean;
}
export interface PolicyRule { days_before: number; refund_percent: number }
export interface RankingFactor { factor: 'accessibility' | 'price' | 'pace' | 'flexibility' | 'rating' | 'meals' | 'budget' | 'evidence'; code: string; value: number; weight: number }

export interface EvidenceSource {
  offer_id: string;
  product_id: string;
  claim_type: string;
  source: string;
  polarity: string;
  strength: string;
  reference: string;
  detail: string;
  url: string | null;
  source_time: string;
}

export interface Assessment {
  offer_id: string;
  product_id: string;
  claim_type: string;
  verdict: 'PASS' | 'BLOCK' | 'REVIEW';
  reason_code: string;
  source_refs: string[];
}

export interface EvidenceData { sources: EvidenceSource[]; assessments: Assessment[] }
export interface Approval { approval_id: string; case_id: string; offer_id: string; offer_version: number; approved_amount: string; currency: string; case_state_version: number; status: string; nonce: string | null }
export interface Order {
  id: string; case_id: string; offer_id: string; approval_id: string;
  status: 'PENDING_PAYMENT' | 'CONFIRMED' | 'CANCELLATION_REQUESTED' | 'CANCELLED' | 'FAILED';
  total_amount: string; currency: string; departure_date: string | null; supplier_booking_ref: string | null;
  failure_reason: string | null; refund_amount: string | null; cancelled_at: string | null;
  cancellation_policy: PolicyRule[]; cancellation_quote: { refund_percent: number; refund_amount: string } | null;
  payment: { provider: 'simulated' | 'stripe'; status: string; refunded_amount: string; checkout_url: string | null } | null;
  created_at: string;
}
export interface ReviewTask {
  id: string; case_id: string; case_status: CaseStatus; destination: string | null; claim_type: string; reason_code: string; created_at: string;
  offer: { id: string; product_id: string; name: string | null; total_amount: string; currency: string; attributes: OfferAttributes };
  evidence: { source: string; polarity: string; strength: string; reference: string; detail: string; url: string | null }[];
}
export interface AuditEvent { id: number; agent_name: string; event_type: string; status: string; payload: Record<string, unknown>; created_at: string }
export interface CaseSnapshot { caseData: CaseData; offers: Offer[]; evidence: EvidenceData; approval: Approval | null; orders: Order[]; events: AuditEvent[] }

export interface GuideModelTrace {
  mode: 'GEMINI_TWO_BRAINS'; planner_model: string; reviewer_model: string;
  revision_applied?: boolean;
  planner_initial: DraftDay[]; reviewer_feedback: { concerns: string[]; recommendation: string };
  planner_revised: DraftDay[];
}
export interface GuideProposal { id: string; request: string; status: 'PENDING' | 'ACCEPTED' | 'DECLINED'; days: DraftDay[]; scope: 'ILLUSTRATIVE_ONLY'; model_trace?: GuideModelTrace | null }
export interface GuideContext {
  case_id: string; case_status: CaseStatus; destination: string | null; travel_pace: string | null;
  traveler_count: number | null; elevator_required: boolean;
  attractions: string[]; selected_attraction: string | null; days: DraftDay[];
  itinerary_source: ItinerarySource;
  itinerary_version: number;
  missing_fields: string[];
  conversation: { role: 'traveler' | 'guide'; text: string; source: 'text' | 'voice'; created_at: string }[];
  proposal: GuideProposal | null; location_mode: 'MANUAL'; source: 'CASE_REQUIREMENTS';
}
export type ItinerarySource = 'PENDING' | 'GEMINI_REVIEWED' | 'DETERMINISTIC_DRAFT' | 'GEMINI_FAILED' | 'TRAVELER_EDITED';
/** Where a guide answer comes from: an official place page, or the evidence behind a verified access claim. */
export interface Citation { kind: 'PLACE' | 'EVIDENCE'; title: string; url: string | null }
export interface GuideReply {
  intent: 'REVISION' | 'PACKAGE_CHANGE' | 'NEXT_ACTIVITY' | 'ATTRACTION_QUESTION' | 'ACCESS_QUESTION' | 'CLARIFICATION';
  reply: string; model_mode: string; citations: Citation[];
}
export interface DayEdit { day_number: number; title: string; note: string; activities: string[]; rest_note: string }

export interface TripCard {
  case_id: string; language: string; traveler: string | null; destination: string | null; travelers: number | null;
  days: number | null; departure_date: string | null; booking_ref: string | null;
  stay: { name: string | null; includes: string[]; attributes: OfferAttributes; verified_claims: string[] } | null;
  cancellation_policy: PolicyRule[]; itinerary: DraftDay[];
  emergency_contact: EmergencyContact | null; support_phone: string | null; emergency_number: string;
}
export interface HelpRequest { id: string; case_id: string; message: string; destination: string | null; from: string; email: string; created_at: string }
export interface AdvisorCase {
  case_id: string; status: CaseStatus; destination: string | null; language: string; traveler: string; updated_at: string;
  open_reviews: number; open_help: number;
  order: { status: string; total: string; currency: string; departure_date: string | null; payment: { provider: string; status: string } | null } | null;
}
export interface AdvisorTraveler { traveler: string | null; email: string | null; consent: boolean; needs: TravelerNeeds | null; emergency_contact: EmergencyContact | null }
export interface CaseNote { id: number; text: string; author: string; created_at: string }
