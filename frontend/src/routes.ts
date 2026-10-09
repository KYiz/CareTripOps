export type AppRoute = '/' | '/dashboard' | '/mobile' | '/demo';

export function resolveRoute(pathname: string): AppRoute | null {
  const path = pathname.replace(/\/$/, '') || '/';
  return path === '/' || path === '/dashboard' || path === '/mobile' || path === '/demo' ? path : null;
}

export function routeHref(path: AppRoute, caseId: string): string {
  return `${path}${caseId ? `?caseId=${encodeURIComponent(caseId)}` : ''}`;
}
