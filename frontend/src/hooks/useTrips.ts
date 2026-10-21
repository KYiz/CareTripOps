import { useCallback, useEffect, useState } from 'react';
import { AuthRequiredError, api } from '../api/client';
import type { CaseSummary, Invitation } from '../types';

/** The traveler's trips and pending invitations; reloads when `changeKey` changes. */
export function useTrips(signedIn: boolean, changeKey: unknown) {
  const [trips, setTrips] = useState<CaseSummary[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const reload = useCallback(async () => {
    if (!signedIn) { setTrips([]); setInvitations([]); return; }
    setLoading(true);
    try {
      const [mine, invited] = await Promise.all([api.cases(), api.invitations()]);
      setTrips(mine); setInvitations(invited); setFailed(false);
    } catch (cause) { if (!(cause instanceof AuthRequiredError)) setFailed(true); }
    finally { setLoading(false); }
  }, [signedIn]);

  useEffect(() => { void reload(); }, [reload, changeKey]);
  return { trips, invitations, loading, failed, reload };
}
