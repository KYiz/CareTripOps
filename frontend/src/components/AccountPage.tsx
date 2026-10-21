import { useState } from 'react';
import { api } from '../api/client';
import { StepUpCancelled } from '../hooks/useStepUp';
import { useI18n } from '../i18n';
import type { User } from '../types';
import NeedsProfileForm from './NeedsProfileForm';
import PhoneSection from './PhoneSection';

interface Props {
  user: User; onUserChange: (user: User) => void; onDeleted: () => void;
  guard: <T>(action: () => Promise<T>) => Promise<T>;
}

/** The traveler's own details: name, travel needs, a copy of their data, and account deletion. */
export default function AccountPage({ user, onUserChange, onDeleted, guard }: Props) {
  const { t } = useI18n();
  const [name, setName] = useState(user.display_name ?? '');
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  async function run(action: () => Promise<unknown>, done = '') {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try { await action(); setNotice(done); }
    catch (cause) { if (!(cause instanceof StepUpCancelled)) setError(cause instanceof Error ? cause.message : t('Request failed')); }
    finally { setBusy(false); }
  }

  const download = () => run(async () => {
    const data = await api.exportData();
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    const link = Object.assign(document.createElement('a'), { href: url, download: 'caretrip-my-data.json' });
    link.click();
    URL.revokeObjectURL(url);
  }, t('Your data was downloaded.'));

  return <main className="ct-account-page">
    <p className="ct-kicker">{t('YOUR ACCOUNT')}</p>
    <h1>{t('Account and privacy')}</h1>
    {notice && <p className="ct-family-notice" role="status">{notice}</p>}
    {error && <div className="ct-auth-error" role="alert">{error}</div>}

    <section className="ct-account-section" aria-labelledby="details-title">
      <h2 id="details-title">{t('Your details')}</h2>
      <p>{t('Email')}: <strong>{user.email}</strong></p>
      <form className="ct-needs" onSubmit={event => { event.preventDefault();
        void run(async () => onUserChange(await api.updateProfile(name.trim())), t('Saved.')); }}>
        <label htmlFor="account-name">{t('Your name')}</label>
        <input id="account-name" maxLength={80} autoComplete="name" value={name} onChange={event => setName(event.target.value)} />
        <button type="submit" className="ct-auth-primary" disabled={busy || !name.trim()}>{t('Save name')}</button>
      </form>
    </section>

    <PhoneSection user={user} onUserChange={onUserChange} />

    <NeedsProfileForm onConsentChange={granted => onUserChange({ ...user, sensitive_consent: granted })} />

    <section className="ct-account-section" aria-labelledby="data-title">
      <h2 id="data-title">{t('Your data')}</h2>
      <p className="ct-account-lead">{t('Download a copy of everything CareTrip holds about you: your details, needs, trips, bookings and emails.')}</p>
      <button type="button" className="ct-auth-primary" disabled={busy} onClick={() => void download()}>{t('Download my data')}</button>
    </section>

    <section className="ct-account-section ct-account-danger" aria-labelledby="delete-title">
      <h2 id="delete-title">{t('Delete my account')}</h2>
      <p className="ct-account-lead">{t('Your trips and messages are erased and family members lose access. Booking records are kept without your name for accounting. Please cancel current bookings first.')}</p>
      <label className="ct-check"><input type="checkbox" checked={understood} onChange={event => setUnderstood(event.target.checked)} />
        {t('I understand this cannot be undone')}</label>
      <button type="button" className="ct-auth-primary ct-danger" disabled={busy || !understood}
        onClick={() => void run(async () => { await guard(() => api.deleteAccount()); onDeleted(); })}>{t('Delete my account')}</button>
    </section>
    <p className="ct-auth-note"><a href="/terms">{t('Terms of Use')}</a> · <a href="/privacy">{t('Privacy Notice')}</a></p>
  </main>;
}
