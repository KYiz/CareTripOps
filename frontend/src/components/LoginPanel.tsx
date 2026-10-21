import { useState } from 'react';
import { ApiError, api, type SignInContact } from '../api/client';
import type { User } from '../types';
import { useI18n } from '../i18n';

interface Props { onSignedIn: (user: User) => void; reason?: string }

export default function LoginPanel({ onSignedIn, reason }: Props) {
  const { t } = useI18n();
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  // Text messages work once a number has been verified on the Account page.
  const [byPhone, setByPhone] = useState(false);
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'EMAIL' | 'CODE'>('EMAIL');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [devCode, setDevCode] = useState('');
  // First sign-in, or the terms changed: the server keeps the code valid until they are accepted.
  const [needsTerms, setNeedsTerms] = useState(false);
  const [agreed, setAgreed] = useState(false);

  const contact = (): SignInContact => byPhone ? { phone: phone.trim() } : { email: email.trim() };
  const contactText = byPhone ? phone.trim() : email.trim();

  async function sendCode() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const sent = await api.requestCode(contact());
      setDevCode(sent.dev_code ?? '');
      setStep('CODE'); setCode('');
    } catch (cause) { setError(cause instanceof Error ? cause.message : t('The code could not be sent.')); }
    finally { setBusy(false); }
  }

  async function verify() {
    if (busy) return;
    setBusy(true); setError('');
    try { onSignedIn(await api.verifyCode(contact(), code.trim(), agreed)); }
    catch (cause) {
      if (cause instanceof ApiError && cause.code === 'TERMS_REQUIRED') setNeedsTerms(true);
      else setError(cause instanceof Error ? cause.message : t('That code did not work.'));
    }
    finally { setBusy(false); }
  }

  return <main className="ct-auth-page"><section className="ct-auth-card" aria-labelledby="auth-title">
    <p className="ct-kicker">{t("CARETRIP · SIGN IN")}</p>
    <h1 id="auth-title">{step === 'EMAIL' ? t("Welcome. Let’s find your trips.") : byPhone ? t('Check your text messages') : t("Check your email")}</h1>
    {reason && step === 'EMAIL' && <p className="ct-auth-reason">{reason}</p>}
    {error && <div className="ct-auth-error" role="alert">{error}</div>}
    {step === 'EMAIL' ? <form onSubmit={event => { event.preventDefault(); void sendCode(); }}>
      {byPhone ? <>
        <p>{t('We will text a 6-digit code to the mobile number saved on your account.')}</p>
        <label htmlFor="auth-phone">{t('Your mobile number')}</label>
        <input id="auth-phone" type="tel" autoComplete="tel" inputMode="tel" required value={phone}
          onChange={event => setPhone(event.target.value)} placeholder="021 555 0100" autoFocus />
        <button type="submit" className="ct-auth-primary" disabled={busy || phone.replace(/\D/g, '').length < 8}>{busy ? t("Sending…") : t('Text me a code')}</button>
      </> : <>
        <p>{t("We will email you a 6-digit code. No password to remember.")}</p>
        <label htmlFor="auth-email">{t("Your email address")}</label>
        <input id="auth-email" type="email" autoComplete="email" inputMode="email" required value={email}
          onChange={event => setEmail(event.target.value)} placeholder={t("name@example.com")} autoFocus />
        <button type="submit" className="ct-auth-primary" disabled={busy || !email.includes('@')}>{busy ? t("Sending…") : t("Email me a code")}</button>
      </>}
      <div className="ct-auth-links"><button type="button" onClick={() => { setByPhone(!byPhone); setError(''); }}>
        {byPhone ? t('Use my email address instead') : t('Use my mobile number instead')}</button></div>
    </form> : <form onSubmit={event => { event.preventDefault(); void verify(); }}>
      <p>{byPhone ? t('If this number is saved on a CareTrip account, we texted a 6-digit code to') : t("We sent a 6-digit code to")} <strong>{contactText}</strong>{t(". It works for a few minutes.")}</p>
      {devCode && <p className="ct-auth-dev" role="status">{t("Development mode: your code is")} <strong>{devCode}</strong>{byPhone ? t('. Real text messages are not sent locally.') : t(". Real emails are not sent locally.")}</p>}
      <label htmlFor="auth-code">{t("6-digit code")}</label>
      <input id="auth-code" autoFocus inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6}
        value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ''))} placeholder="123456" />
      {needsTerms && <div className="ct-terms" role="group" aria-labelledby="terms-title">
        <p id="terms-title"><strong>{t('One more step before your first sign-in')}</strong></p>
        <label className="ct-terms-check"><input type="checkbox" checked={agreed} onChange={event => setAgreed(event.target.checked)} />
          <span>{t('I have read and accept the')} <a href="/terms" target="_blank" rel="noopener">{t('Terms of Use')}</a> {t('and the')} <a href="/privacy" target="_blank" rel="noopener">{t('Privacy Notice')}</a>.</span>
        </label>
      </div>}
      <button type="submit" className="ct-auth-primary" disabled={busy || code.length !== 6 || (needsTerms && !agreed)}>
        {busy ? t("Checking…") : needsTerms ? t('Agree and sign in') : t("Sign in")}</button>
      <div className="ct-auth-links">
        <button type="button" onClick={() => void sendCode()} disabled={busy}>{t("Send a new code")}</button>
        <button type="button" onClick={() => { setStep('EMAIL'); setError(''); setDevCode(''); setNeedsTerms(false); setAgreed(false); }} disabled={busy}>{byPhone ? t('Use a different number') : t("Use a different email")}</button>
      </div>
    </form>}
    <p className="ct-auth-note">{t("Family members invited to a trip sign in the same way, with the email address the invitation was sent to.")}</p>
    <p className="ct-auth-note"><a href="/terms">{t('Terms of Use')}</a> · <a href="/privacy">{t('Privacy Notice')}</a></p>
  </section></main>;
}
