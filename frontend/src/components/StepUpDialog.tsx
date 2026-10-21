import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useI18n } from '../i18n';

interface Props { onConfirmed: () => void; onCancel: () => void }

/** Asks for a fresh emailed code before paying, cancelling a booking or deleting the account. */
export default function StepUpDialog({ onConfirmed, onCancel }: Props) {
  const { t } = useI18n();
  const [code, setCode] = useState('');
  const [devCode, setDevCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function send() {
    setBusy(true); setError('');
    try { setDevCode((await api.requestStepUp()).dev_code ?? ''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('The code could not be sent.')); }
    finally { setBusy(false); }
  }

  async function confirm() {
    if (busy) return;
    setBusy(true); setError('');
    try { await api.verifyStepUp(code); onConfirmed(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('That code did not work.')); setBusy(false); }
  }

  useEffect(() => {
    void send();
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onCancel(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return <div className="ct-modal-backdrop">
    <section className="ct-auth-card ct-modal" role="dialog" aria-modal="true" aria-labelledby="step-up-title">
      <p className="ct-kicker">{t('CARETRIP · CONFIRM IT IS YOU')}</p>
      <h1 id="step-up-title">{t('Please confirm it is you')}</h1>
      <p>{t('This step uses your money or your account, so we have emailed you a new 6-digit code.')}</p>
      {error && <div className="ct-auth-error" role="alert">{error}</div>}
      {devCode && <p className="ct-auth-dev" role="status">{t("Development mode: your code is")} <strong>{devCode}</strong>{t(". Real emails are not sent locally.")}</p>}
      <form onSubmit={event => { event.preventDefault(); void confirm(); }}>
        <label htmlFor="step-up-code">{t("6-digit code")}</label>
        <input id="step-up-code" autoFocus inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6}
          value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ''))} placeholder="123456" />
        <button type="submit" className="ct-auth-primary" disabled={busy || code.length !== 6}>{busy ? t("Checking…") : t('Confirm and continue')}</button>
        <div className="ct-auth-links">
          <button type="button" onClick={() => void send()} disabled={busy}>{t("Send a new code")}</button>
          <button type="button" onClick={onCancel}>{t('Cancel')}</button>
        </div>
      </form>
    </section>
  </div>;
}
