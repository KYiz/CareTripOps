import { useState } from 'react';
import { api } from '../api/client';
import { useI18n } from '../i18n';

/** The phone's Help tab: emergency number first, then a one-tap request that reaches family and advisors. */
export default function HelpPanel({ caseId, startTrip }: { caseId: string; startTrip: () => void }) {
  const { t } = useI18n();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  async function ask() {
    if (busy) return;
    setBusy(true); setError('');
    try { await api.askForHelp(caseId, message); setSent(true); setMessage(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('Request failed')); }
    finally { setBusy(false); }
  }

  return <div className="ct-phone-help">
    <p className="ct-phone-kicker">{t("HELP")}</p><h2>{t("We are here to make it clear.")}</h2>
    <div className="ct-emergency" role="note"><strong>{t('In an emergency, call 111')}</strong>
      <p>{t('Ambulance, police and fire in New Zealand.')}</p>
      <a className="ct-phone-primary ct-danger" href="tel:111">{t('Call 111')}</a></div>
    {caseId && <section className="ct-help-request" aria-labelledby="help-request-title">
      <h3 id="help-request-title">{t('Need help with this trip?')}</h3>
      {sent ? <div className="ct-phone-message" role="status">{t('Your family and the CareTrip team have been told. An advisor will contact you soon.')}</div> : <>
        <p>{t('We will tell everyone on this trip and a CareTrip advisor straight away.')}</p>
        <label htmlFor="help-message">{t('What is happening? (optional)')}</label>
        <textarea id="help-message" rows={3} maxLength={500} value={message} onChange={event => setMessage(event.target.value)} />
        {error && <div className="ct-phone-alert" role="alert">{error}</div>}
        <button type="button" className="ct-phone-primary" disabled={busy} onClick={() => void ask()}>{busy ? t('Sending…') : t('I need help now')}</button>
      </>}
    </section>}
    <div className="ct-phone-message"><strong>{t("How do I start?")}</strong><p>{t("Tell us where you would like to go, who is coming, your budget and the pace you prefer.")}</p></div>
    <div className="ct-phone-message"><strong>{t("What happens next?")}</strong><p>{t("We check sample offers. You decide whether to approve a verified offer. No real payment or booking is made.")}</p></div>
    <button className="ct-phone-primary" type="button" onClick={startTrip}>{t("Start a trip →")}</button>
  </div>;
}
