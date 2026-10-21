import { useCallback, useEffect, useRef, useState } from 'react';
import { AuthRequiredError, api } from '../api/client';
import { useI18n } from '../i18n';
import type { CaseSnapshot } from '../types';

const FALLBACK_POLL_MS = 30000;

/** Everything about one trip, kept current by server-sent events with a slow polling safety net. */
export function useCaseSnapshot(caseId: string, signedIn: boolean) {
  const { t } = useI18n();
  const [snapshot, setSnapshot] = useState<CaseSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const current = useRef(caseId);
  current.current = caseId;
  // Read through a ref so switching language does not reconnect the live stream.
  const translate = useRef(t);
  translate.current = t;

  useEffect(() => { setSnapshot(null); setError(''); }, [caseId]);

  const refresh = useCallback(async () => {
    if (!caseId || !signedIn) return;
    try {
      const next = await api.snapshot(caseId);
      if (current.current === caseId) { setSnapshot(next); setError(''); }
    } catch (cause) {
      if (current.current !== caseId || cause instanceof AuthRequiredError) return;
      setError(cause instanceof Error ? cause.message : translate.current('Unable to load case'));
    }
  }, [caseId, signedIn]);

  useEffect(() => {
    if (!caseId || !signedIn) return;
    // Coalesce: while a refresh is in flight, further change signals trigger exactly one more.
    let running = false, dirty = false, closed = false;
    const run = async () => {
      if (running) { dirty = true; return; }
      running = true;
      do { dirty = false; await refresh(); } while (dirty && !closed);
      running = false;
    };
    setLoading(true);
    void run().finally(() => setLoading(false));
    // The server pushes "changed" after every Case write; "ready" also fires after a reconnect.
    const source = new EventSource(`/api/cases/${encodeURIComponent(caseId)}/stream`);
    source.addEventListener('ready', () => void run());
    source.addEventListener('changed', () => void run());
    source.addEventListener('revoked', () => { source.close(); void run(); });
    const fallback = setInterval(() => void run(), FALLBACK_POLL_MS);
    return () => { closed = true; source.close(); clearInterval(fallback); };
  }, [caseId, signedIn, refresh]);

  return { snapshot, loading, error, refresh };
}
