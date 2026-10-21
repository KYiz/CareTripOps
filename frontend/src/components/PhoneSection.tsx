import { useState } from 'react';
import { api } from '../api/client';
import { useI18n } from '../i18n';
import type { User } from '../types';

/** Add, prove and remove the mobile number used for signing in by text message. */
export default function PhoneSection({ user, onUserChange }: { user: User; onUserChange: (user: User) => void }) {
  const { t } = useI18n();
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);
  const [devCode, setDevCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError('');
    try { await action(); } catch (cause) { setError(cause instanceof Error ? cause.message : t('Request failed')); }
    finally { setBusy(false); }
  }
  const send = () => run(async () => { setDevCode((await api.addPhone(phone)).dev_code ?? ''); setSent(true); setCode(''); });
  const verify = () => run(async () => {
    const result = await api.verifyPhone(phone, code);
    onUserChange({ ...user, phone: result.phone }); setSent(false); setPhone(''); setDevCode('');
  });
  const remove = () => run(async () => { await api.removePhone(); onUserChange({ ...user, phone: null }); });

  return <section className="ct-account-section" aria-labelledby="phone-title">
    <h2 id="phone-title">{t('Sign in by text message')}</h2>
    {error && <div className="ct-auth-error" role="alert">{error}</div>}
    {user.phone ? <>
      <p>{t('Codes can also be texted to {phone}.', { phone: user.phone })}</p>
      <button type="button" className="ct-link-button" disabled={busy} onClick={() => void remove()}>{t('Remove this number')}</button>
    </> : <form className="ct-needs" onSubmit={event => { event.preventDefault(); void (sent ? verify() : send()); }}>
      <p className="ct-account-lead">{t('Add a mobile number to get sign-in codes by text instead of email.')}</p>
      <label htmlFor="phone-number">{t('Your mobile number')}</label>
      <input id="phone-number" type="tel" autoComplete="tel" inputMode="tel" value={phone} disabled={sent}
        onChange={event => setPhone(event.target.value)} placeholder="021 555 0100" />
      {sent && <>
        {devCode && <p className="ct-auth-dev" role="status">{t("Development mode: your code is")} <strong>{devCode}</strong></p>}
        <label htmlFor="phone-code">{t("6-digit code")}</label>
        <input id="phone-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} autoFocus value={code}
          onChange={event => setCode(event.target.value.replace(/\D/g, ''))} />
      </>}
      <button type="submit" className="ct-auth-primary" disabled={busy || (sent ? code.length !== 6 : phone.replace(/\D/g, '').length < 8)}>
        {sent ? t('Confirm this number') : t('Text me a code')}</button>
    </form>}
  </section>;
}
