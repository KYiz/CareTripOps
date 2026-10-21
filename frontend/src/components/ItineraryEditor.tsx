import { useState } from 'react';
import { api } from '../api/client';
import { useI18n } from '../i18n';
import type { DayEdit, DraftDay } from '../types';

interface Props { caseId: string; version: number; days: DraftDay[]; onDone: (saved: boolean) => void }

/** Rewrite the outline in your own words. Saving makes a new version; places and timing stay unverified. */
export default function ItineraryEditor({ caseId, version, days, onDone }: Props) {
  const { t } = useI18n();
  const [edits, setEdits] = useState<DayEdit[]>(() => days.map(day => ({ day_number: day.day_number, title: day.title,
    note: day.note, activities: day.activities ?? [], rest_note: day.rest_note ?? '' })));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const change = (index: number, patch: Partial<DayEdit>) => setEdits(edits.map((day, i) => i === index ? { ...day, ...patch } : day));

  async function save() {
    setBusy(true); setError('');
    try { await api.editItinerary(caseId, version, edits); onDone(true); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('Request failed')); setBusy(false); }
  }

  return <form className="ct-itinerary-editor" onSubmit={event => { event.preventDefault(); void save(); }}>
    <p>{t('Change any day in your own words. Places and timing still need checking.')}</p>
    {error && <div className="ct-phone-alert" role="alert">{error}</div>}
    {edits.map((day, index) => <fieldset key={day.day_number}><legend>{t('Day {n}', { n: day.day_number })}</legend>
      <label htmlFor={`edit-title-${day.day_number}`}>{t('Title')}</label>
      <input id={`edit-title-${day.day_number}`} maxLength={120} required value={day.title} onChange={event => change(index, { title: event.target.value })} />
      <label htmlFor={`edit-note-${day.day_number}`}>{t('What happens')}</label>
      <textarea id={`edit-note-${day.day_number}`} rows={2} maxLength={1000} value={day.note} onChange={event => change(index, { note: event.target.value })} />
      <label htmlFor={`edit-activities-${day.day_number}`}>{t('Activities (one per line)')}</label>
      <textarea id={`edit-activities-${day.day_number}`} rows={3} value={day.activities.join('\n')}
        onChange={event => change(index, { activities: event.target.value.split('\n').slice(0, 8) })} />
      <label htmlFor={`edit-rest-${day.day_number}`}>{t('Rest')}</label>
      <input id={`edit-rest-${day.day_number}`} maxLength={300} value={day.rest_note} onChange={event => change(index, { rest_note: event.target.value })} />
    </fieldset>)}
    <div className="ct-guide-decision">
      <button type="submit" disabled={busy || edits.some(day => !day.title.trim())}>{busy ? t('Saving…') : t('Save my outline')}</button>
      <button type="button" disabled={busy} onClick={() => onDone(false)}>{t('Cancel')}</button>
    </div>
  </form>;
}
