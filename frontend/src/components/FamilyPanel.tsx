import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { CaseMembers, InviteRole, MemberRole } from '../types';
import { useI18n } from '../i18n';

// English keys; render through t().
export const roleLabel: Record<MemberRole, string> = { OWNER: 'Traveler', CO_PLANNER: 'Helps plan', VIEWER: 'Can view', ADVISOR: 'Travel advisor' };
const roleHelp: Record<InviteRole, string> = {
  CO_PLANNER: 'Can add trip details and use the guide. Cannot approve or pay.',
  VIEWER: 'Can see the trip and its progress only.',
  OWNER: 'Hands the trip to them: they approve and pay, and you keep helping plan.',
};
const inviteLabel: Record<InviteRole, string> = { VIEWER: 'Can view', CO_PLANNER: 'Helps plan', OWNER: 'Hand over to the traveler' };

export default function FamilyPanel({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  const [data, setData] = useState<CaseMembers | null>(null);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<InviteRole>('VIEWER');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    try { setData(await api.members(caseId)); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('Family members could not be loaded.')); }
  }, [caseId]);
  useEffect(() => { void load(); }, [load]);

  async function act(action: () => Promise<unknown>, done: string) {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try { await action(); setNotice(done); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('That did not work. Please try again.')); }
    finally { setBusy(false); }
  }

  const owner = data?.my_role === 'OWNER';
  return <section className="ct-family" aria-labelledby={`family-${caseId}`}>
    <h3 id={`family-${caseId}`}>{t("Family and helpers")}</h3>
    <p className="ct-family-lead">{owner ? t("Invite family to follow or help plan. Only you can approve the trip.") : t('Your role: {role}. Only the traveler can approve the trip.', { role: t(roleLabel[data?.my_role ?? 'VIEWER']) })}</p>
    {error && <div className="ct-phone-alert" role="alert">{error}</div>}
    {notice && <div className="ct-family-notice" role="status">{notice}</div>}
    <ul className="ct-family-list">
      {data?.members.map(member => <li key={member.user_id}>
        <div><strong>{member.display_name || member.email}</strong><small>{t(roleLabel[member.role])}</small></div>
        {owner && member.role !== 'OWNER' && <button type="button" disabled={busy}
          onClick={() => void act(() => api.removeMember(caseId, member.user_id), t('{email} no longer has access.', { email: member.email }))}>{t("Remove")}</button>}
      </li>)}
      {data?.invitations.map(invitation => <li key={invitation.id} className="is-pending">
        <div><strong>{invitation.email}</strong><small>{t("Invited ·")} {t(roleLabel[invitation.role])}</small></div>
        <button type="button" disabled={busy}
          onClick={() => void act(() => api.revokeInvitation(caseId, invitation.id), t('Invitation cancelled.'))}>{t("Cancel")}</button>
      </li>)}
    </ul>
    {owner && <form className="ct-family-invite" onSubmit={event => { event.preventDefault();
      void act(() => api.invite(caseId, email.trim(), role), t('Invitation sent to {email}.', { email: email.trim() })).then(() => setEmail('')); }}>
      <label htmlFor={`invite-email-${caseId}`}>{t("Family member’s email")}</label>
      <input id={`invite-email-${caseId}`} type="email" autoComplete="off" value={email} onChange={event => setEmail(event.target.value)} placeholder={t("name@example.com")} />
      <fieldset><legend>{t("What can they do?")}</legend>
        {(['VIEWER', 'CO_PLANNER', 'OWNER'] as const).map(option => <label key={option} className="ct-family-role">
          <input type="radio" name={`invite-role-${caseId}`} value={option} checked={role === option} onChange={() => setRole(option)} />
          <span><strong>{t(inviteLabel[option])}</strong><small>{t(roleHelp[option])}</small></span>
        </label>)}
      </fieldset>
      <button type="submit" className="ct-phone-primary" disabled={busy || !email.includes('@')}>{busy ? t("Sending…") : t("Send invitation")}</button>
    </form>}
  </section>;
}
