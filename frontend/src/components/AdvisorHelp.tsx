import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { useI18n } from '../i18n';
import type { HelpRequest } from '../types';

/** Travelers and families asking for help, oldest first, until an advisor picks each one up. */
export default function AdvisorHelp({ onCount }: { onCount: (n: number) => void }) {
  const { t } = useI18n();
  const [requests, setRequests] = useState<HelpRequest[] | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try { const rows = await api.helpRequests(); setRequests(rows); onCount(rows.length); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('Request failed')); }
  }, [t, onCount]);
  useEffect(() => { void load(); const timer = setInterval(() => void load(), 15000); return () => clearInterval(timer); }, [load]);

  async function acknowledge(request: HelpRequest) {
    setBusy(request.id); setError('');
    try { await api.acknowledgeHelp(request.id, notes[request.id] ?? ''); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('Request failed')); }
    finally { setBusy(''); }
  }

  return <section aria-labelledby="advisor-help-title">
    <h2 id="advisor-help-title" className="ct-advisor-heading">{t('Help requests')}</h2>
    <p className="ct-advisor-lead">{t('Contact the person straight away, then record what you did.')}</p>
    {error && <div className="ct-auth-error" role="alert">{error}</div>}
    {requests === null ? <p role="status">{t('Loading…')}</p> : !requests.length ? <p className="ct-advisor-empty">{t('Nobody is waiting for help.')}</p> :
      requests.map(request => <article className="ct-review-card ct-help-card" key={request.id} aria-labelledby={`help-${request.id}`}>
        <header><h3 id={`help-${request.id}`}>{request.from}</h3>
          <span>{t(request.destination ?? '')} · {t('Case {id}', { id: request.case_id.slice(0, 8) })} · {new Date(request.created_at).toLocaleString()}</span></header>
        <p className="ct-help-message">“{request.message}”</p>
        <p><a href={`mailto:${request.email}`}>{request.email}</a> · <a href={`/dashboard?caseId=${request.case_id}`}>{t('Open the trip')}</a></p>
        <label htmlFor={`help-note-${request.id}`}>{t('What did you do?')}</label>
        <textarea id={`help-note-${request.id}`} rows={2} value={notes[request.id] ?? ''} onChange={event => setNotes({ ...notes, [request.id]: event.target.value })} />
        <div className="ct-review-actions"><button type="button" className="ct-phone-primary" disabled={busy === request.id || !(notes[request.id] ?? '').trim()}
          onClick={() => void acknowledge(request)}>{t('I have contacted them')}</button></div>
      </article>)}
  </section>;
}
