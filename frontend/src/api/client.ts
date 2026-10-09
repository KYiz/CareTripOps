import type { Approval, AuditEvent, CaseData, CaseSnapshot, EvidenceData, GuideContext, GuideReply, Offer, Order } from '../types';

type Envelope<T> = { data: T; request_id: string };

export function caseAccessToken(caseId: string): string {
  try { return localStorage.getItem(`caretrip:access:${caseId}`) ?? ''; } catch { return ''; }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const caseId = /^\/api\/cases\/([^/]+)/.exec(path)?.[1];
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json',
    ...(caseId ? { 'X-Case-Token': caseAccessToken(caseId) } : {}), ...init?.headers } });
  const body = await response.json().catch(() => null);
  if (caseId && response.status === 403 && body?.error?.code === 'CASE_ACCESS_DENIED') {
    throw new Error(caseAccessToken(caseId)
      ? 'This trip cannot be opened with the access saved in this browser. Please start a new trip.'
      : 'This trip has no saved access token in this browser, including trips created before secure access. Please start a new trip.');
  }
  if (!response.ok) throw new Error(body?.error?.message ?? `Request failed: ${response.status}. Please try again.`);
  if (!body || !('data' in body)) throw new Error('The server returned an invalid response. Please try again.');
  return (body as Envelope<T>).data;
}

export const api = {
  caseData: (caseId: string) => call<CaseData>(`/api/cases/${caseId}`),
  createCase: async (request: string, demoDate: string, voiceDraft = false) => {
    const created = await call<{ case_id: string; status: string; access_token: string }>('/api/cases', {
    method: 'POST', body: JSON.stringify({ request, demo_actor: 'demo-user', demo_date: demoDate, voice_draft: voiceDraft }),
    });
    try { localStorage.setItem(`caretrip:access:${created.case_id}`, created.access_token); }
    catch { throw new Error('This browser could not save access to the new trip. Please enable local storage and start a new trip.'); }
    return created;
  },
  async snapshot(caseId: string): Promise<CaseSnapshot> {
    const base = `/api/cases/${caseId}`;
    const [caseData, offers, evidence, approval, orders, events] = await Promise.all([
      call<CaseData>(base), call<Offer[]>(`${base}/offers`), call<EvidenceData>(`${base}/evidence`),
      call<Approval | null>(`${base}/approvals`), call<Order[]>(`${base}/orders`), call<AuditEvent[]>(`${base}/events`),
    ]);
    return { caseData, offers, evidence, approval, orders, events };
  },
  clarify: (caseId: string, answers: Record<string, string | number>) => call(`/api/cases/${caseId}/clarifications`, {
    method: 'POST', body: JSON.stringify({ answers }),
  }),
  decide: (caseId: string, approval: Approval, decision: 'APPROVE' | 'REJECT') => call(`/api/cases/${caseId}/approvals/${approval.approval_id}/decision`, {
    method: 'POST', body: JSON.stringify({ decision, nonce: approval.nonce, expected_state_version: approval.case_state_version }),
  }),
  resume: (caseId: string) => call(`/api/cases/${caseId}/resume`, { method: 'POST' }),
  guide: (caseId: string) => call<GuideContext>(`/api/cases/${caseId}/guide`),
  selectAttraction: (caseId: string, attraction: string) => call<GuideContext>(`/api/cases/${caseId}/guide/attraction`, {
    method: 'POST', body: JSON.stringify({ attraction }),
  }),
  guideMessage: (caseId: string, message: string) => call<GuideReply>(`/api/cases/${caseId}/guide/messages`, {
    method: 'POST', body: JSON.stringify({ message }),
  }),
  requestRevision: (caseId: string, request: string) => call<GuideContext>(`/api/cases/${caseId}/guide/revisions`, {
    method: 'POST', body: JSON.stringify({ request }),
  }),
  decideRevision: (caseId: string, proposalId: string, accept: boolean) => call<GuideContext>(`/api/cases/${caseId}/guide/revisions/decision`, {
    method: 'POST', body: JSON.stringify({ proposal_id: proposalId, accept }),
  }),
};
