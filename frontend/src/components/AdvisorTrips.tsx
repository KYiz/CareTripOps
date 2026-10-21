import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useI18n } from '../i18n';
import { needsPhrases, statusLabel } from '../labels';
import type { AdvisorCase, AdvisorTraveler, CaseNote } from '../types';

function TripDetail({ trip }: { trip: AdvisorCase }) {
  const { t } = useI18n();
  const [traveler, setTraveler] = useState<AdvisorTraveler | null>(null);
  const [notes, setNotes] = useState<CaseNote[]>([]);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const fail = (cause: unknown) => setError(cause instanceof Error ? cause.message : t('Request failed'));
  useEffect(() => { api.advisorNotes(trip.case_id).then(setNotes).catch(fail); }, [trip.case_id]);

  async function addNote() {
    try { const note = await api.addAdvisorNote(trip.case_id, draft); setNotes([...notes, note]); setDraft(''); }
    catch (cause) { fail(cause); }
  }

  return <div className="ct-advisor-detail">
    {error && <div className="ct-auth-error" role="alert">{error}</div>}
    <p><a href={`/dashboard?caseId=${trip.case_id}`}>{t('Open the trip dashboard (read only)')}</a></p>
    {!traveler ? <button type="button" className="ct-phone-outline" onClick={() => api.advisorTraveler(trip.case_id).then(setTraveler).catch(fail)}>
      {t('Show health and access details (this is recorded)')}</button>
      : !traveler.consent ? <p>{t('The traveler has not shared health and access details.')}</p> : <div className="ct-advisor-profile">
        <p>{needsPhrases(traveler.needs ?? undefined).map(need => t(need.key, need.vars)).join(' · ') || t('No access needs saved.')}</p>
        {traveler.needs?.medical_notes && <p><strong>{t('Medical notes')}:</strong> {traveler.needs.medical_notes}</p>}
        {traveler.emergency_contact?.name && <p><strong>{t('Emergency contact')}:</strong> {traveler.emergency_contact.name}
          {traveler.emergency_contact.relationship && ` (${traveler.emergency_contact.relationship})`} {traveler.emergency_contact.phone}</p>}
      </div>}
    <h4>{t('Advisor notes')}</h4>
    {notes.length ? <ul className="ct-advisor-notes">{notes.map(note => <li key={note.id}><p>{note.text}</p>
      <small>{note.author} · {new Date(note.created_at).toLocaleString()}</small></li>)}</ul> : <p>{t('No notes yet.')}</p>}
    <label htmlFor={`note-${trip.case_id}`}>{t('Add a note')}</label>
    <textarea id={`note-${trip.case_id}`} rows={2} maxLength={4000} value={draft} onChange={event => setDraft(event.target.value)} />
    <button type="button" className="ct-phone-primary" disabled={!draft.trim()} onClick={() => void addNote()}>{t('Save note')}</button>
  </div>;
}

/** Every recent trip with its booking and payment state; trips with open help or reviews come first. */
export default function AdvisorTrips() {
  const { t } = useI18n();
  const [trips, setTrips] = useState<AdvisorCase[] | null>(null);
  const [open, setOpen] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { api.advisorCases().then(setTrips).catch(cause => setError(cause instanceof Error ? cause.message : t('Request failed'))); }, []);

  return <section aria-labelledby="advisor-trips-title">
    <h2 id="advisor-trips-title" className="ct-advisor-heading">{t('Trips')}</h2>
    {error && <div className="ct-auth-error" role="alert">{error}</div>}
    {trips === null ? <p role="status">{t('Loading…')}</p> : !trips.length ? <p className="ct-advisor-empty">{t('No trips yet.')}</p> :
      <ul className="ct-advisor-trips">{trips.map(trip => <li key={trip.case_id}>
        <button type="button" className="ct-advisor-trip" aria-expanded={open === trip.case_id} onClick={() => setOpen(open === trip.case_id ? '' : trip.case_id)}>
          <strong>{trip.destination ? t(trip.destination) : t('Trip in progress')} · {trip.traveler}</strong>
          <span>{t(statusLabel(trip.status))}
            {trip.order && ` · ${t('Booking')}: ${trip.order.status.toLowerCase().replaceAll('_', ' ')} · ${trip.order.currency} ${trip.order.total}`}
            {trip.order?.payment && ` · ${t('Payment')}: ${trip.order.payment.status.toLowerCase().replaceAll('_', ' ')}`}</span>
          {(trip.open_help > 0 || trip.open_reviews > 0) && <span className="ct-advisor-flags">
            {trip.open_help > 0 && t('{n} help requests', { n: trip.open_help })} {trip.open_reviews > 0 && t('{n} reviews', { n: trip.open_reviews })}</span>}
        </button>
        {open === trip.case_id && <TripDetail trip={trip} />}
      </li>)}</ul>}
  </section>;
}
