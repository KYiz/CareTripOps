import { matchTravelImage } from '../../data/travelImages';
import { useI18n } from '../../i18n';
import type { CaseData } from '../../types';
import TravelPhoto from '../TravelPhoto';

const SOURCE_NOTE: Record<string, string> = {
  GEMINI_REVIEWED: 'Gemini Planner and Reviewer generated this outline.',
  GEMINI_FAILED: 'Gemini planning failed; this local outline needs further review.',
  TRAVELER_EDITED: 'The traveler or their family edited this outline. It has not been checked.',
};

/** The illustrative day-by-day outline, with where it came from and what still needs checking. */
export default function ItinerarySection({ caseData, booked }: { caseData: CaseData; booked: boolean }) {
  const { t } = useI18n();
  const days = caseData.draft_itinerary ?? [];
  if (!days.length) return null;
  const destination = caseData.requirements?.destination;
  return <section className="ct-dashboard-days" aria-label={t("Illustrative itinerary")}>
    <h4>{t('Illustrative itinerary · version {n}', { n: caseData.itinerary_version || 1 })}</h4>
    <p>{t(SOURCE_NOTE[caseData.itinerary_source ?? ''] ?? "Local rule-based outline. No model itinerary was generated.")}{' '}
      {booked ? t("This outline is separate from the approved sample package. Later Guide revisions are not verified or included in the simulated order.") : ''}</p>
    {days.map(day => <article key={day.day_number}><TravelPhoto image={matchTravelImage(destination, day.attraction)} caption />
      <div><strong>{t('Day {n}: {title}', { n: day.day_number, title: day.title })}</strong><p>{day.note}</p>
        <small>{t('{intensity} intensity', { intensity: t(day.intensity || 'LOW') })}</small>
        {Boolean(day.activities?.length) && <ol>{day.activities?.map((activity, index) => <li key={`${index}-${activity}`}>{activity}</li>)}</ol>}
        <p>{t("Rest:")} {day.rest_note || t("Leave time to rest.")}</p>
        {day.verification_notes?.map(note => <small key={note}>{t("To check:")} {note}</small>)}</div></article>)}
  </section>;
}
