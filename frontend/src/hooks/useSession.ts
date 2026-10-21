import { useEffect, useState } from 'react';
import { api, setAuthRequiredHandler } from '../api/client';
import type { User } from '../types';

/** The signed-in user: undefined while checking, null when signed out. Any 401 signs the app out. */
export function useSession() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  useEffect(() => {
    setAuthRequiredHandler(() => setUser(null));
    api.me().then(setUser).catch(() => setUser(null));
    return () => setAuthRequiredHandler(null);
  }, []);

  async function signOut() {
    try { await api.logout(); } catch { /* The session is cleared locally either way. */ }
    setUser(null);
  }

  return { user, signedIn: Boolean(user), setUser, signOut };
}
