export type AppRoute = '/' | '/dashboard' | '/mobile' | '/demo' | '/advisor' | '/account' | '/terms' | '/privacy' | '/trip-card';

const ROUTES: AppRoute[] = ['/', '/dashboard', '/mobile', '/demo', '/advisor', '/account', '/terms', '/privacy', '/trip-card'];
/** Pages anyone can read without signing in. */
export const PUBLIC_ROUTES: AppRoute[] = ['/', '/terms', '/privacy'];
/** Pages about the person rather than a trip: their links never carry a case ID. */
const PERSONAL_ROUTES: AppRoute[] = ['/advisor', '/account', '/terms', '/privacy'];

export function resolveRoute(pathname: string): AppRoute | null {
  const path = pathname.replace(/\/$/, '') || '/';
  return ROUTES.find(route => route === path) ?? null;
}

export function routeHref(path: AppRoute, caseId: string): string {
  return `${path}${caseId && !PERSONAL_ROUTES.includes(path) ? `?caseId=${encodeURIComponent(caseId)}` : ''}`;
}
