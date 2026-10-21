import type {
  Approval, AuditEvent, CaseData, CaseMembers, CaseSnapshot, CaseSummary, EvidenceData, GuideContext, GuideReply,
  AdvisorCase, AdvisorTraveler, CaseNote, DayEdit, EmergencyContact, HelpRequest, InviteRole, Invitation, MemberRole, Offer, Order, ReviewTask, TravelerNeeds, TravelerProfile, TripCard, User,
} from '../types';

import { currentLanguage, translate } from '../language.ts';

/** Readable text for the server's error codes; unknown codes fall back to the server's message. */
export const ERROR_TEXT: Record<string, string> = {
  AUTH_REQUIRED: 'Please sign in to continue.',
  LOGIN_CODE_INVALID: 'That code is not valid. Check the latest email or request a new code.',
  INVALID_EMAIL: 'Enter a valid email address.',
  RATE_LIMITED: 'That happened too many times in a short while. Please wait a little and try again.',
  CROSS_SITE_REQUEST: 'This request was blocked for your safety. Please reload the page.',
  CASE_NOT_FOUND: 'This trip could not be found, or it has not been shared with you.',
  ROLE_FORBIDDEN: 'Your role on this trip does not allow this action.',
  GRAPH_NOT_PAUSED: 'The trip is still being prepared. Please try again in a moment.',
  INVALID_STATE: 'This trip has moved on. The page has been refreshed.',
  STALE_OFFER: 'The offer changed before your decision was saved. A travel advisor will review it.',
  PAYMENT_UNAVAILABLE: 'Payment status could not be checked. Please try again.',
  ORDER_NOT_FOUND: 'This booking could not be found.',
  CONFIRMATION_REQUIRED: 'Please confirm the cancellation.',
  ADVISOR_ONLY: 'Only travel advisors can do this.',
  REVIEW_ALREADY_RESOLVED: 'Another advisor already resolved this review.',
  APPROVAL_CONFLICT: 'This decision could not be saved. Please refresh and try again.',
  INVALID_CLARIFICATION: 'Please check the details you entered.',
  CLARIFICATION_LIMIT: 'We have asked for details several times. A travel advisor will help from here.',
  DESTINATION_OUTSIDE_NZ: 'This demo supports trips within New Zealand only.',
  INVALID_CURRENCY: 'This New Zealand demo uses NZD.',
  ALREADY_MEMBER: 'This person already has access to the trip.',
  INVITE_SELF: 'You are already the traveler on this trip.',
  INVALID_ROLE: 'Family members can be invited to view, to help plan, or to take over as the traveler.',
  INVITATION_NOT_FOUND: 'This invitation is no longer available.',
  OWNER_REQUIRED: 'The traveler cannot be removed from their own trip.',
  MEMBER_NOT_FOUND: 'This person no longer has access.',
  MODEL_UNAVAILABLE: 'Trip planning is temporarily unavailable. Please try again later.',
  REVISION_UNAVAILABLE: 'A gentler draft could not be prepared right now.',
  INVALID_REQUEST: 'Please check the information and try again.',
  INTERNAL_ERROR: 'Something went wrong. Please try again.',
  INVALID_PHONE: 'Enter a mobile number such as 021 555 0100 or +64 21 555 0100.',
  PHONE_TAKEN: 'This mobile number is already used by another CareTrip account.',
  SMS_UNAVAILABLE: 'We could not send a text message. Please use your email address.',
  ITINERARY_CHANGED: 'Someone else changed the outline. Please look at the latest one first.',
  NO_ITINERARY: 'There is no outline to edit yet.',
  HANDOVER_UNAVAILABLE: 'This trip already has a booking in progress, so it cannot change hands.',
  HELP_ALREADY_ACKNOWLEDGED: 'Another advisor already picked this up.',
  EMAIL_UNAVAILABLE: 'We could not send the email right now. Please try again in a minute.',
  TERMS_REQUIRED: 'Please read and accept the Terms of Use and Privacy Notice to continue.',
  STEP_UP_REQUIRED: 'For your safety, please confirm with a code sent to your email.',
  CONSENT_REQUIRED: 'Please agree to CareTrip storing your health and access needs first.',
  ACTIVE_BOOKINGS: 'Please cancel or finish your current bookings before deleting the account.',
};

type Envelope<T> = { data: T; request_id: string };
export type SignInContact = { email: string } | { phone: string };
type CodeSent = { sent: boolean; expires_in_minutes: number; dev_code?: string };

/** Raised when the session is missing or expired; the app shows the sign-in screen. */
export class AuthRequiredError extends Error {
  constructor() { super(translate(currentLanguage(), 'Please sign in to continue.')); this.name = 'AuthRequiredError'; }
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  constructor(message: string, code: string, status: number) {
    super(message); this.name = 'ApiError'; this.code = code; this.status = status;
  }
}

let onAuthRequired: (() => void) | null = null;
export function setAuthRequiredHandler(handler: (() => void) | null) { onAuthRequired = handler; }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  // Same-origin requests carry the HttpOnly session cookie automatically.
  const response = await fetch(path, { credentials: 'same-origin', ...init,
    // The server answers guide questions and writes new itineraries in this language.
    headers: { 'Content-Type': 'application/json', 'Accept-Language': currentLanguage(), ...init?.headers } });
  const body = await response.json().catch(() => null);
  if (response.status === 401) { onAuthRequired?.(); throw new AuthRequiredError(); }
  if (!response.ok) {
    const code: string = body?.error?.code ?? 'HTTP_ERROR';
    const known = ERROR_TEXT[code];
    throw new ApiError(known ? translate(currentLanguage(), known)
      : body?.error?.message ?? translate(currentLanguage(), 'Request failed: {status}. Please try again.', { status: response.status }),
      code, response.status);
  }
  if (!body || !('data' in body)) throw new Error(translate(currentLanguage(), 'The server returned an invalid response. Please try again.'));
  return (body as Envelope<T>).data;
}

const post = (body?: unknown): RequestInit => ({ method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  me: () => call<User>('/api/auth/me'),
  // Sign in with an email address, or with a mobile number already verified on an account.
  requestCode: (contact: SignInContact) => call<CodeSent>('/api/auth/request-code', post(contact)),
  verifyCode: (contact: SignInContact, code: string, acceptTerms = false) =>
    call<User>('/api/auth/verify', post({ ...contact, code, accept_terms: acceptTerms })),
  addPhone: (phone: string) => call<CodeSent>('/api/auth/me/phone', { method: 'PUT', body: JSON.stringify({ phone }) }),
  verifyPhone: (phone: string, code: string) => call<{ phone: string }>('/api/auth/me/phone/verify', post({ phone, code })),
  removePhone: () => call<{ removed: boolean }>('/api/auth/me/phone', { method: 'DELETE' }),
  requestStepUp: () => call<{ sent: boolean; dev_code?: string }>('/api/auth/step-up/request', post()),
  verifyStepUp: (code: string) => call<{ confirmed: boolean }>('/api/auth/step-up/verify', post({ code })),
  logout: () => call<{ signed_out: boolean }>('/api/auth/logout', post()),
  updateProfile: (displayName: string) => call<User>('/api/auth/me', { method: 'PATCH', body: JSON.stringify({ display_name: displayName }) }),
  setConsent: (granted: boolean) => call<{ granted: boolean }>('/api/auth/me/consent', { method: 'PUT', body: JSON.stringify({ granted }) }),
  travelerProfile: () => call<TravelerProfile>('/api/profile'),
  saveTravelerProfile: (needs: TravelerNeeds, emergencyContact: EmergencyContact) =>
    call<TravelerProfile>('/api/profile', { method: 'PUT', body: JSON.stringify({ needs, emergency_contact: emergencyContact }) }),
  exportData: () => call<Record<string, unknown>>('/api/auth/me/export'),
  deleteAccount: () => call<{ deleted: boolean }>('/api/auth/me', { method: 'DELETE' }),

  cases: () => call<CaseSummary[]>('/api/cases'),
  invitations: () => call<Invitation[]>('/api/invitations'),
  answerInvitation: (id: string, accept: boolean) => call<{ case_id: string; accepted: boolean }>(`/api/invitations/${id}`, post({ accept })),
  members: (caseId: string) => call<CaseMembers>(`/api/cases/${caseId}/members`),
  invite: (caseId: string, email: string, role: InviteRole) => call(`/api/cases/${caseId}/invitations`, post({ email, role })),
  revokeInvitation: (caseId: string, invitationId: string) => call(`/api/cases/${caseId}/invitations/${invitationId}`, { method: 'DELETE' }),
  removeMember: (caseId: string, userId: string) => call(`/api/cases/${caseId}/members/${userId}`, { method: 'DELETE' }),

  caseData: (caseId: string) => call<CaseData>(`/api/cases/${caseId}`),
  createCase: (request: string, demoDate: string, voiceDraft = false) =>
    call<{ case_id: string; status: string; role: MemberRole }>('/api/cases', post({ request, demo_date: demoDate, voice_draft: voiceDraft })),
  async snapshot(caseId: string): Promise<CaseSnapshot> {
    const base = `/api/cases/${caseId}`;
    const [caseData, offers, evidence, approval, orders, events] = await Promise.all([
      call<CaseData>(base), call<Offer[]>(`${base}/offers`), call<EvidenceData>(`${base}/evidence`),
      call<Approval | null>(`${base}/approvals`), call<Order[]>(`${base}/orders`), call<AuditEvent[]>(`${base}/events`),
    ]);
    return { caseData, offers, evidence, approval, orders, events };
  },
  clarify: (caseId: string, answers: Record<string, string | number>) => call(`/api/cases/${caseId}/clarifications`, post({ answers })),
  decide: (caseId: string, approval: Approval, decision: 'APPROVE' | 'REJECT') => call(`/api/cases/${caseId}/approvals/${approval.approval_id}/decision`,
    post({ decision, nonce: approval.nonce, expected_state_version: approval.case_state_version })),
  resume: (caseId: string) => call(`/api/cases/${caseId}/resume`, post()),
  syncPayment: (caseId: string) => call<{ payment_status: string | null }>(`/api/cases/${caseId}/payments/sync`, post()),
  cancelOrder: (caseId: string, orderId: string) =>
    call<{ refund_percent: number; refund_amount: string }>(`/api/cases/${caseId}/orders/${orderId}/cancel`, post({ confirm: true })),
  tripCard: (caseId: string) => call<TripCard>(`/api/cases/${caseId}/trip-card`),
  askForHelp: (caseId: string, message: string) => call<{ id: string; notified: number }>(`/api/cases/${caseId}/help`, post({ message })),
  helpRequests: () => call<HelpRequest[]>('/api/advisor/help'),
  acknowledgeHelp: (id: string, note: string) => call<{ acknowledged: boolean }>(`/api/advisor/help/${id}`, post({ note })),
  advisorCases: () => call<AdvisorCase[]>('/api/advisor/cases'),
  advisorTraveler: (caseId: string) => call<AdvisorTraveler>(`/api/advisor/cases/${caseId}/traveler`),
  advisorNotes: (caseId: string) => call<CaseNote[]>(`/api/advisor/cases/${caseId}/notes`),
  addAdvisorNote: (caseId: string, text: string) => call<CaseNote>(`/api/advisor/cases/${caseId}/notes`, post({ text })),
  advisorReviews: () => call<ReviewTask[]>('/api/advisor/reviews'),
  resolveReview: (taskId: string, decision: 'PASS' | 'BLOCK', note: string) =>
    call<{ id: string; status: string; case_resumed: boolean }>(`/api/advisor/reviews/${taskId}`, post({ decision, note })),
  guide: (caseId: string) => call<GuideContext>(`/api/cases/${caseId}/guide`),
  selectAttraction: (caseId: string, attraction: string) => call<GuideContext>(`/api/cases/${caseId}/guide/attraction`, post({ attraction })),
  editItinerary: (caseId: string, baseVersion: number, days: DayEdit[]) =>
    call<{ version: number }>(`/api/cases/${caseId}/itinerary`, { method: 'PUT', body: JSON.stringify({ base_version: baseVersion, days }) }),
  guideMessage: (caseId: string, message: string) => call<GuideReply>(`/api/cases/${caseId}/guide/messages`, post({ message })),
  requestRevision: (caseId: string, request: string) => call<GuideContext>(`/api/cases/${caseId}/guide/revisions`, post({ request })),
  decideRevision: (caseId: string, proposalId: string, accept: boolean) => call<GuideContext>(`/api/cases/${caseId}/guide/revisions/decision`,
    post({ proposal_id: proposalId, accept })),
};
