import { useI18n } from '../../i18n';
import type { GuideProposal } from '../../types';

interface Props { proposal: GuideProposal; canPlan: boolean; busy: boolean; decide: (accept: boolean) => void }

/** A gentler draft the guide prepared, with the planner and reviewer's work, for the traveler to accept or keep. */
export default function ProposalReview({ proposal, canPlan, busy, decide }: Props) {
  const { t } = useI18n();
  const trace = proposal.model_trace;
  return <section className="ct-guide-proposal"><small>{t('ILLUSTRATIVE ITINERARY REVISION · {status}', { status: t(proposal.status) })}</small>
    <h3>{t("A gentler draft for your review")}</h3>
    <p>{t("This changes the illustrative outline only. It is not verified or included in any approved package or simulated order. The offer, approval and price stay unchanged.")}</p>
    {trace && <details><summary>{t("See planner and reviewer work")}</summary>
      <p>{t('Planner initial draft ({model})', { model: trace.planner_model })}</p>
      {trace.planner_initial.map(day => <div key={day.day_number}>{t('Day {n}: {title}', { n: day.day_number, title: day.title })} — {day.note}</div>)}
      <p>{t('Reviewer feedback ({model})', { model: trace.reviewer_model })}</p>
      <ul>{trace.reviewer_feedback.concerns.map(item => <li key={item}>{item}</li>)}</ul>
      <p>{trace.reviewer_feedback.recommendation}</p>
      <p>{trace.revision_applied ? t("Planner revised the draft once after review.") : t("Reviewer found no change needed; the initial draft is shown below.")}</p>
    </details>}
    {proposal.days.map(day => <div key={day.day_number}><strong>{t('Day {n}: {title}', { n: day.day_number, title: day.title })}</strong><span>{day.note}</span>
      {Boolean(day.activities?.length) && <ol>{day.activities?.map((activity, index) => <li key={`${index}-${activity}`}>{activity}</li>)}</ol>}
      <span>{t("Rest:")} {day.rest_note || t("Leave time to rest.")}</span></div>)}
    {canPlan && proposal.status === 'PENDING' && <div className="ct-guide-decision">
      <button disabled={busy} onClick={() => decide(true)}>{t("Use this outline")}</button>
      <button disabled={busy} onClick={() => decide(false)}>{t("Keep my current outline")}</button></div>}
  </section>;
}
