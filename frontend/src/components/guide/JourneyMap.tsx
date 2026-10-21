import { useState } from 'react';
import { useI18n } from '../../i18n';
import type { GuideContext, ItinerarySource } from '../../types';
import ItineraryEditor from '../ItineraryEditor';

export function sourceLabel(source: ItinerarySource | undefined): string {
  return source === 'PENDING' ? 'Gemini planning in progress' : source === 'GEMINI_REVIEWED' ? 'Gemini reviewed'
    : source === 'GEMINI_FAILED' ? 'Gemini unavailable; local outline' : source === 'TRAVELER_EDITED' ? 'Edited by you or your family'
    : 'Local outline';
}

interface Props {
  caseId: string; context: GuideContext | null; canPlan: boolean; busy: boolean;
  chooseAttraction: (attraction: string) => void; onEdited: () => void;
}

/** The day-by-day outline: explore a stop, or rewrite the days in your own words. */
export default function JourneyMap({ caseId, context, canPlan, busy, chooseAttraction, onEdited }: Props) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);
  const days = context?.days ?? [];
  return <section className="ct-journey-map" aria-label={t("Illustrative journey map")}>
    <div className="ct-guide-heading"><h3>{t("Your journey")}</h3>
      <small>{t('Version {n}', { n: context?.itinerary_version || 1 })} · {t(sourceLabel(context?.itinerary_source))} {t("· No GPS tracking")}</small></div>
    {canPlan && days.length > 0 && !editing && context?.itinerary_source !== 'PENDING' && context?.itinerary_version
      ? <button type="button" className="ct-guide-edit" onClick={() => setEditing(true)} disabled={busy}>{t('Edit the outline')}</button> : null}
    {editing && context ? <ItineraryEditor caseId={caseId} version={context.itinerary_version} days={days}
      onDone={saved => { setEditing(false); if (saved) onEdited(); }} />
      : days.length ? days.map(day => <div className="ct-journey-stop" key={day.day_number}>
        <span className={day.attraction === context?.selected_attraction ? 'selected' : ''}>{day.day_number}</span>
        <div><small>{t('DAY {n} · {intensity} INTENSITY', { n: day.day_number, intensity: t(day.intensity || 'LOW') })}</small><strong>{day.title}</strong><p>{day.note}</p>
          {Boolean(day.activities?.length) && <ol>{day.activities?.map((activity, index) => <li key={`${index}-${activity}`}>{activity}</li>)}</ol>}
          <p>{t("Rest:")} {day.rest_note || t("Leave time to rest.")}</p>
          {day.verification_notes?.map(note => <small key={note}>{t("To check:")} {note}</small>)}
          {canPlan && day.attraction && <button type="button" onClick={() => chooseAttraction(day.attraction!)} disabled={busy || day.attraction === context?.selected_attraction}>
            {day.attraction === context?.selected_attraction ? t("Current selection") : t('Explore {place}', { place: t(day.attraction) })}</button>}
        </div></div>) : <p className="ct-guide-disclosure">{t("Your daily outline will appear after the trip details are ready.")}</p>}
  </section>;
}
