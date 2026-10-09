export type CaseStatus = 'RECEIVED' | 'NEEDS_CLARIFICATION' | 'REQUIREMENTS_READY' | 'OFFERS_DISCOVERED' | 'EVIDENCE_REVIEW' | 'EVIDENCE_CONFLICT' | 'OFFERS_VERIFIED' | 'AWAITING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'MOCK_BOOKING' | 'DEMO_COMPLETED' | 'HUMAN_REVIEW' | 'FAILED' | 'RECOVERY_REQUIRED';

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
  hard_constraints: { elevator_required?: boolean };
  missing_fields: string[];
}

export interface CaseData {
  case_id: string;
  status: CaseStatus;
  active_node: string;
  state_version: number;
  requirements: Requirements | null;
  draft_itinerary?: DraftDay[];
  itinerary_source?: 'PENDING' | 'GEMINI_REVIEWED' | 'DETERMINISTIC_DRAFT' | 'GEMINI_FAILED';
  itinerary_version?: number;
  missing_fields: string[];
  next_action: string | null;
  model_mode: 'mock_llm' | 'api';
  model_status: 'MOCK' | 'PENDING' | 'SUCCEEDED' | 'FAILED';
  llm_provider: 'openai' | 'gemini' | null;
  created_at: string;
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
  reason_code: string | null;
}

export interface EvidenceSource {
  offer_id: string;
  product_id: string;
  claim_type: string;
  source: string;
  polarity: string;
  strength: string;
  reference: string;
  detail: string;
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
export interface Order { id: string; case_id: string; offer_id: string; approval_id: string; status: string; total_amount: string; currency: string; created_at: string }
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
  itinerary_source: 'PENDING' | 'GEMINI_REVIEWED' | 'DETERMINISTIC_DRAFT' | 'GEMINI_FAILED';
  itinerary_version: number;
  missing_fields: string[];
  conversation: { role: 'traveler' | 'guide'; text: string; source: 'text' | 'voice'; created_at: string }[];
  proposal: GuideProposal | null; location_mode: 'MANUAL'; source: 'CASE_REQUIREMENTS';
}
export interface GuideReply { intent: 'REVISION' | 'PACKAGE_CHANGE' | 'NEXT_ACTIVITY' | 'ATTRACTION_QUESTION' | 'CLARIFICATION'; reply: string; model_mode: string; citations: string[] }
