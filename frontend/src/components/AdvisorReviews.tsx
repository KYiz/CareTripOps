import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { useI18n } from '../i18n';
import { CLAIM_LABELS } from '../labels';
import type { ReviewTask } from '../types';

/** Offers whose accessibility evidence was inconclusive, for a travel advisor to settle, one claim at a time. */
export default function AdvisorReviews() {
  const { t, formatDate } = useI18n();
  const [tasks, setTasks] = useState<ReviewTask[] | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    try { setTasks(await api.advisorReviews()); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('The review queue could not be loaded.')); }
  }, [t]);
  useEffect(() => { void load(); const timer = setInterval(() => void load(), 15000); return () => clearInterval(timer); }, [load]);

  async function decide(task: ReviewTask, decision: 'PASS' | 'BLOCK') {
    setBusy(task.id); setError(''); setNotice('');
    try {
      const result = await api.resolveReview(task.id, decision, notes[task.id] ?? '');
      setNotice(t(result.case_resumed ? 'Saved. The trip is planning again with your decision.' : 'Saved.'));
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : t('The decision could not be saved')); }
    finally { setBusy(''); }
  }

  return <section aria-labelledby="advisor-reviews-title">
    <h2 id="advisor-reviews-title" className="ct-advisor-heading">{t('Evidence review queue')}</h2>
    <p className="ct-advisor-lead">{t('These offers claim an accessibility feature that the evidence could not confirm. Check with the supplier, then pass or block the claim.')}</p>
    {error && <div className="ct-auth-error" role="alert">{error}</div>}
    {notice && <div className="ct-family-notice" role="status">{notice}</div>}
    {tasks === null ? <p role="status">{t('Loading…')}</p> : !tasks.length ? <p className="ct-advisor-empty">{t('No open reviews. Nicely done.')}</p> :
      tasks.map(task => <article className="ct-review-card" key={task.id} aria-labelledby={`review-${task.id}`}>
        <header><h3 id={`review-${task.id}`}>{task.offer.name ?? task.offer.product_id}</h3>
          <span>{t(task.destination ?? '')} · {t('Case {id}', { id: task.case_id.slice(0, 8) })} · {formatDate(task.created_at)}</span></header>
        <p><strong>{t('Claim to check')}:</strong> {t(CLAIM_LABELS[task.claim_type] ?? task.claim_type)} · {task.offer.currency} {task.offer.total_amount}</p>
        <ul className="ct-review-evidence">{task.evidence.map(item => <li key={item.reference}>
          <b>{item.polarity}</b> · {item.source.replaceAll('_', ' ')} ({item.strength.toLowerCase()}) — {item.detail}
          {item.url && <> · <a href={item.url} target="_blank" rel="noreferrer">{item.reference}</a></>}</li>)}</ul>
        <label htmlFor={`note-${task.id}`}>{t('What did you confirm, and with whom?')}</label>
        <textarea id={`note-${task.id}`} rows={2} value={notes[task.id] ?? ''} onChange={event => setNotes({ ...notes, [task.id]: event.target.value })} />
        <div className="ct-review-actions">
          <button type="button" className="ct-phone-primary" disabled={busy === task.id || !(notes[task.id] ?? '').trim()} onClick={() => void decide(task, 'PASS')}>{t('Confirmed: claim is true')}</button>
          <button type="button" className="ct-phone-outline" disabled={busy === task.id || !(notes[task.id] ?? '').trim()} onClick={() => void decide(task, 'BLOCK')}>{t('Not true: block this offer')}</button>
        </div>
      </article>)}
  </section>;
}
