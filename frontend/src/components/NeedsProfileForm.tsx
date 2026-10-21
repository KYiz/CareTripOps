import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useI18n } from '../i18n';
import type { Dietary, EmergencyContact, TravelerNeeds, Wheelchair } from '../types';

const EMPTY_NEEDS: TravelerNeeds = { wheelchair: 'NONE', max_walk_meters: null, step_free: false, accessible_bathroom: false,
  dietary: [], medical_notes: '' };
const EMPTY_CONTACT: EmergencyContact = { name: '', relationship: '', phone: '' };
const WALK_LIMITS = [50, 100, 200, 500, 1000];

/** Health and access needs, stored only after explicit consent; withdrawing consent erases them. */
export default function NeedsProfileForm({ onConsentChange }: { onConsentChange: (granted: boolean) => void }) {
  const { t } = useI18n();
  const [consent, setConsent] = useState<boolean | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [needs, setNeeds] = useState(EMPTY_NEEDS);
  const [contact, setContact] = useState(EMPTY_CONTACT);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const wheelchairs: [Wheelchair, string][] = [['NONE', t('No wheelchair')], ['SOMETIMES', t('Sometimes, for longer distances')],
    ['MANUAL', t('Manual wheelchair')], ['POWER', t('Power wheelchair or scooter')]];
  const diets: [Dietary, string][] = [['VEGETARIAN', t('Vegetarian')], ['VEGAN', t('Vegan')], ['GLUTEN_FREE', t('Gluten-free')],
    ['HALAL', t('Halal')], ['KOSHER', t('Kosher')], ['DIABETIC', t('Diabetic-friendly')], ['LOW_SODIUM', t('Low salt')],
    ['NUT_ALLERGY', t('Nut allergy')], ['SOFT_FOOD', t('Soft food')]];

  async function load() {
    try {
      const profile = await api.travelerProfile();
      setConsent(profile.consent); setNeeds(profile.needs); setContact(profile.emergency_contact);
    } catch (cause) { setError(cause instanceof Error ? cause.message : t('Request failed')); }
  }
  useEffect(() => { void load(); }, []);

  async function run(action: () => Promise<unknown>, done: string) {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try { await action(); setNotice(done); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('Request failed')); }
    finally { setBusy(false); }
  }

  const changeConsent = (granted: boolean) => run(async () => {
    await api.setConsent(granted);
    onConsentChange(granted);
    setAgreed(false);
    await load();
  }, granted ? t('Thank you. You can now add your needs.') : t('Consent withdrawn. Your health and access details were erased.'));
  const set = <K extends keyof TravelerNeeds>(key: K, value: TravelerNeeds[K]) => setNeeds(current => ({ ...current, [key]: value }));
  const toggleDiet = (diet: Dietary) => set('dietary', needs.dietary.includes(diet) ? needs.dietary.filter(d => d !== diet) : [...needs.dietary, diet]);

  return <section className="ct-account-section" aria-labelledby="needs-title">
    <h2 id="needs-title">{t('Travel needs')}</h2>
    <p className="ct-account-lead">{t('We use these to search only for rooms and outings that suit you, and to check suppliers’ accessibility claims.')}</p>
    {notice && <p className="ct-family-notice" role="status">{notice}</p>}
    {error && <div className="ct-auth-error" role="alert">{error}</div>}
    {consent === false && <div className="ct-terms">
      <label className="ct-terms-check"><input type="checkbox" checked={agreed} onChange={event => setAgreed(event.target.checked)} />
        <span>{t('I agree that CareTrip may store my health and access needs to plan suitable trips. I can withdraw this at any time, which erases them.')}</span></label>
      <button type="button" className="ct-auth-primary" disabled={!agreed || busy} onClick={() => void changeConsent(true)}>{t('Give consent')}</button>
    </div>}
    {consent && <form className="ct-needs" onSubmit={event => { event.preventDefault();
      void run(() => api.saveTravelerProfile(needs, contact), t('Saved. New trips will use these needs.')); }}>
      <label htmlFor="needs-wheelchair">{t('Wheelchair')}</label>
      <select id="needs-wheelchair" value={needs.wheelchair} onChange={event => set('wheelchair', event.target.value as Wheelchair)}>
        {wheelchairs.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <label htmlFor="needs-walk">{t('How far can you walk comfortably?')}</label>
      <select id="needs-walk" value={needs.max_walk_meters ?? ''} onChange={event => set('max_walk_meters', event.target.value ? Number(event.target.value) : null)}>
        <option value="">{t('No particular limit')}</option>
        {WALK_LIMITS.map(meters => <option key={meters} value={meters}>{meters < 1000 ? t('About {meters} metres', { meters: String(meters) }) : t('About 1 kilometre')}</option>)}
      </select>
      <label className="ct-check"><input type="checkbox" checked={needs.step_free} onChange={event => set('step_free', event.target.checked)} />
        {t('I need step-free access (no stairs)')}</label>
      <label className="ct-check"><input type="checkbox" checked={needs.accessible_bathroom} onChange={event => set('accessible_bathroom', event.target.checked)} />
        {t('I need an accessible bathroom (roll-in shower, grab rails)')}</label>
      <fieldset><legend>{t('Food')}</legend>
        <div className="ct-check-grid">{diets.map(([value, label]) => <label key={value} className="ct-check">
          <input type="checkbox" checked={needs.dietary.includes(value)} onChange={() => toggleDiet(value)} />{label}</label>)}</div>
      </fieldset>
      <label htmlFor="needs-medical">{t('Medical notes for your travel advisor')}</label>
      <textarea id="needs-medical" rows={3} maxLength={1000} value={needs.medical_notes} onChange={event => set('medical_notes', event.target.value)} />
      <small>{t('Only CareTrip travel advisors see these notes. They are never sent to AI services.')}</small>
      <fieldset><legend>{t('Emergency contact')}</legend>
        <label htmlFor="contact-name">{t('Name')}</label>
        <input id="contact-name" maxLength={80} value={contact.name} onChange={event => setContact({ ...contact, name: event.target.value })} />
        <label htmlFor="contact-relationship">{t('Relationship')}</label>
        <input id="contact-relationship" maxLength={40} value={contact.relationship} onChange={event => setContact({ ...contact, relationship: event.target.value })} />
        <label htmlFor="contact-phone">{t('Phone')}</label>
        <input id="contact-phone" type="tel" maxLength={30} value={contact.phone} onChange={event => setContact({ ...contact, phone: event.target.value.replace(/[^0-9+()\- ]/g, '') })} />
      </fieldset>
      <button type="submit" className="ct-auth-primary" disabled={busy}>{t('Save my needs')}</button>
      <button type="button" className="ct-link-button" disabled={busy} onClick={() => void changeConsent(false)}>{t('Withdraw consent and erase these details')}</button>
    </form>}
  </section>;
}
