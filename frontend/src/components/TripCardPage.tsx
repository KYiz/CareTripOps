import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useI18n } from '../i18n';
import { CLAIM_LABELS, policyLines } from '../labels';
import type { TripCard } from '../types';

/** A large-print page to print or keep on the phone: where to stay, what was checked, who to call. */
export default function TripCardPage({ caseId }: { caseId: string }) {
  const { t, formatDate } = useI18n();
  const [card, setCard] = useState<TripCard | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!caseId) return;
    api.tripCard(caseId).then(setCard).catch(cause => setError(cause instanceof Error ? cause.message : t('Request failed')));
  }, [caseId]);

  if (!caseId) return <main className="ct-trip-card"><p>{t('Open a trip first to see its trip card.')}</p></main>;
  if (error) return <main className="ct-trip-card"><div className="ct-auth-error" role="alert">{error}</div></main>;
  if (!card) return <main className="ct-trip-card"><p role="status">{t('Loading…')}</p></main>;
  return <main className="ct-trip-card">
    <div className="ct-trip-card-actions"><button type="button" className="ct-auth-primary" onClick={() => window.print()}>{t('Print this card')}</button></div>
    <p className="ct-kicker">{t('CARETRIP TRIP CARD')}</p>
    <h1>{card.destination ? t(card.destination) : t('Your trip')}</h1>
    {card.traveler && <p className="ct-trip-card-lead">{card.traveler}</p>}
    <section><h2>{t('When')}</h2>
      <p>{card.departure_date ? formatDate(card.departure_date) : t('To confirm')} · {t('{n} days', { n: card.days ?? '' })} · {t('{n} travelers', { n: card.travelers ?? '' })}</p></section>
    {card.stay ? <section><h2>{t('Where you are staying')}</h2>
      <p className="ct-trip-card-big">{card.stay.name}</p>
      <p>{t('Booking reference {ref}', { ref: card.booking_ref ?? '' })}</p>
      {card.stay.verified_claims.length > 0 && <><h3>{t('Checked for you')}</h3>
        <ul>{card.stay.verified_claims.map(claim => <li key={claim}>✓ {t(CLAIM_LABELS[claim] ?? claim)}</li>)}</ul></>}
      <ul>{card.stay.includes.map(item => <li key={item}>{t(item)}</li>)}</ul>
      <h3>{t('If plans change')}</h3>
      <ul>{policyLines(card.cancellation_policy).map(line => <li key={line.key}>{t(line.key, line.vars)}</li>)}</ul>
    </section> : <section><p>{t('This trip is not booked yet.')}</p></section>}
    <section className="ct-trip-card-help"><h2>{t('If you need help')}</h2>
      <p className="ct-trip-card-big">{t('Emergency: {number}', { number: card.emergency_number })}</p>
      {card.support_phone && <p>{t('CareTrip support: {phone}', { phone: card.support_phone })}</p>}
      {card.emergency_contact?.name && <p>{t('Emergency contact: {name} ({relationship}) {phone}', {
        name: card.emergency_contact.name, relationship: card.emergency_contact.relationship || '—', phone: card.emergency_contact.phone })}</p>}
    </section>
    {card.itinerary.length > 0 && <section><h2>{t('Day by day')}</h2>
      <ol className="ct-trip-card-days">{card.itinerary.map(day => <li key={day.day_number}><strong>{t('Day {n}: {title}', { n: day.day_number, title: day.title })}</strong>
        <p>{day.note}</p>{day.rest_note && <p>{t("Rest:")} {day.rest_note}</p>}</li>)}</ol>
      <p className="ct-trip-card-note">{t('The daily outline is a suggestion. Opening hours and travel times still need checking.')}</p></section>}
  </main>;
}
