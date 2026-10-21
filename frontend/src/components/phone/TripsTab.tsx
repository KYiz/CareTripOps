import { useI18n } from '../../i18n';
import { friendlyStatus } from '../../labels';
import type { CaseSummary, Invitation } from '../../types';
import { roleLabel } from '../FamilyPanel';

interface Props {
  trips: CaseSummary[]; invitations: Invitation[]; loading: boolean; failed: boolean; mutating: boolean;
  answerInvitation: (invitation: Invitation, accept: boolean) => void;
  openTrip: (caseId: string) => void; showTrip: () => void; planNew: () => void;
}

/** The traveler's own trips, trips shared by family, and invitations waiting for an answer. */
export default function TripsTab({ trips, invitations, loading, failed, mutating, answerInvitation, openTrip, showTrip, planNew }: Props) {
  const { t } = useI18n();
  return <div className="ct-phone-explore">
    <p className="ct-phone-kicker">{t("MY TRIPS")}</p><h2>{t("Your trips")}</h2>
    <p className="ct-phone-lead">{t("Trips you planned and trips family shared with you. They follow your account on any device.")}</p>
    {invitations.length > 0 && <section className="ct-invitations" aria-label={t("Trip invitations")}>
      <h3>{t("Invitations for you")}</h3>
      {invitations.map(invitation => <div className="ct-phone-message" key={invitation.id}>
        <strong>{invitation.destination ? t(invitation.destination) : t("A New Zealand trip")}</strong>
        <p>{t('{name} invited you · {role}', { name: invitation.invited_by, role: t(roleLabel[invitation.role]) })}</p>
        <button type="button" className="ct-phone-primary" disabled={mutating} onClick={() => { answerInvitation(invitation, true); showTrip(); }}>{t("Accept and open")}</button>
        <button type="button" className="ct-phone-outline" disabled={mutating} onClick={() => answerInvitation(invitation, false)}>{t("Decline")}</button>
      </div>)}
    </section>}
    {failed && <div className="ct-phone-alert" role="alert">{t("Your trips could not be loaded. Check the connection and reopen this page.")}</div>}
    {loading && !trips.length ? <div className="ct-phone-message" role="status">{t("Loading your trips…")}</div>
      : trips.length ? trips.map(trip => <button className="ct-phone-trip-link" key={trip.case_id} type="button" onClick={() => openTrip(trip.case_id)}>
        <strong>{trip.destination ? t(trip.destination) : t("Trip in progress")}</strong>
        <span>{t(friendlyStatus(trip.status))} · {t(roleLabel[trip.role])}</span></button>)
      : <div className="ct-phone-message">{t("No trips yet. Plan one to get started.")}</div>}
    <button className="ct-phone-primary" type="button" onClick={planNew}>{t("Plan a new trip →")}</button>
  </div>;
}
