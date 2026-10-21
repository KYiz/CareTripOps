import { useEffect, useState } from 'react';
import type { MouseEvent } from 'react';
import { AuthRequiredError, api } from './api/client';
import AccountPage from './components/AccountPage';
import AdvisorConsole from './components/AdvisorConsole';
import Dashboard from './components/Dashboard';
import LandingPage from './components/LandingPage';
import LegalPage from './components/LegalPage';
import LoginPanel from './components/LoginPanel';
import PhoneSimulator from './components/PhoneSimulator';
import TopBar from './components/TopBar';
import TripCardPage from './components/TripCardPage';
import TravelPhoto from './components/TravelPhoto';
import { matchTravelImage } from './data/travelImages';
import { useCaseSnapshot } from './hooks/useCaseSnapshot';
import { useSession } from './hooks/useSession';
import { StepUpCancelled, useStepUp } from './hooks/useStepUp';
import { useTrips } from './hooks/useTrips';
import { useI18n } from './i18n';
import { sampleTripRequest } from './labels';
import { PUBLIC_ROUTES, resolveRoute, routeHref, type AppRoute } from './routes';
import type { Invitation, Order } from './types';

const sampleDate = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);
const caseIdFromUrl = () => new URLSearchParams(location.search).get('caseId') ?? '';

export default function App() {
  const { t, lang } = useI18n();
  const { user, signedIn, setUser, signOut } = useSession();
  const { guard, dialog: stepUpDialog } = useStepUp();
  const [route, setRoute] = useState(() => resolveRoute(location.pathname));
  const [caseId, setCaseId] = useState(caseIdFromUrl);
  const { snapshot, loading, error, refresh } = useCaseSnapshot(caseId, signedIn);
  const trips = useTrips(signedIn, snapshot?.caseData.status);
  const [request, setRequest] = useState('');
  const [demoDate, setDemoDate] = useState(sampleDate);
  const [mutating, setMutating] = useState(false);
  const [actionError, setActionError] = useState('');
  const [voiceAvailable, setVoiceAvailable] = useState<boolean | null>(null);
  // A trip the visitor asked to plan before signing in; created right after sign-in.
  const [pendingCreate, setPendingCreate] = useState<{ request: string; voice: boolean } | null>(null);
  const link = (path: AppRoute) => routeHref(path, caseId);
  const failure = (cause: unknown, fallback: string) => {
    if (!(cause instanceof AuthRequiredError || cause instanceof StepUpCancelled)) setActionError(cause instanceof Error ? cause.message : t(fallback));
  };

  useEffect(() => {
    fetch('/api/guide/capabilities').then(response => response.ok ? response.json() : null)
      .then(body => setVoiceAvailable(Boolean(body?.data?.voice_available))).catch(() => setVoiceAvailable(false));
    const onHistory = () => { setCaseId(caseIdFromUrl()); setRoute(resolveRoute(location.pathname)); };
    window.addEventListener('popstate', onHistory);
    return () => window.removeEventListener('popstate', onHistory);
  }, []);

  // Keep ?caseId= in the address bar in step with the selected trip.
  useEffect(() => {
    const url = new URL(location.href);
    if (!caseId && url.searchParams.has('caseId')) {
      url.searchParams.delete('caseId'); url.searchParams.delete('voice');
      history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
    } else if (caseId && route && route !== '/' && !url.searchParams.has('caseId')) {
      history.replaceState(null, '', link(route));
    }
  }, [caseId, route]);

  function navigate(event: MouseEvent<HTMLAnchorElement>, path: AppRoute) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (route === path) return;
    history.pushState(null, '', link(path));
    setRoute(path);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  function openCase(id: string, path = location.pathname) {
    setActionError('');
    history.pushState(null, '', `${path}?caseId=${encodeURIComponent(id)}`);
    setCaseId(id);
  }

  async function createCase(requestOverride?: string, voice = false) {
    if (mutating) return;
    const text = requestOverride ?? request;
    if (!signedIn) { setPendingCreate({ request: text, voice }); return; }
    setMutating(true); setActionError('');
    try {
      const created = await api.createCase(text, demoDate, voice);
      const target = route === '/' ? '/mobile' : location.pathname;
      openCase(created.case_id, target);
      if (voice) history.replaceState(null, '', `${location.pathname}${location.search}&voice=1`);
      setRoute(resolveRoute(target));
    } catch (cause) { failure(cause, 'Case creation failed'); }
    finally { setMutating(false); }
  }

  useEffect(() => {
    if (!signedIn || !pendingCreate) return;
    setPendingCreate(null);
    void createCase(pendingCreate.request, pendingCreate.voice);
  }, [signedIn, pendingCreate]);

  // Back from Stripe Checkout: ask the server to read the payment straight away (the webhook may lag).
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const outcome = params.get('payment');
    if (!signedIn || !caseId || !outcome) return;
    params.delete('payment');
    history.replaceState(null, '', `${location.pathname}?${params}`);
    if (outcome === 'cancelled') { setActionError(t('Payment was not completed. Your room stays held for a short while; you can pay again below.')); return; }
    void api.syncPayment(caseId).then(refresh).catch(cause => failure(cause, 'Request failed'));
  }, [signedIn, caseId]);

  async function mutate(action: () => Promise<unknown>) {
    if (mutating) return;
    setMutating(true); setActionError('');
    // Paying, cancelling and deleting may ask for a fresh code first, then run again.
    try { await guard(action); } catch (cause) { failure(cause, 'Request failed'); }
    finally { await refresh(); setMutating(false); }
  }

  async function answerInvitation(invitation: Invitation, accept: boolean) {
    await mutate(() => api.answerInvitation(invitation.id, accept));
    await trips.reload();
    if (accept) openCase(invitation.case_id);
  }

  function goHome() { setCaseId(''); history.pushState(null, '', '/'); setRoute('/'); }
  async function leave() { await signOut(); goHome(); }

  const role = snapshot?.caseData.my_role ?? null;
  const useSample = () => setRequest(sampleTripRequest('Auckland', lang));
  const clarify = (answers: Record<string, string | number>) => mutate(() => api.clarify(caseId, answers));
  const intake = { request, setRequest, demoDate, setDemoDate, createCase, useSample };
  const dashboard = <Dashboard {...intake} caseId={caseId} snapshot={snapshot} loading={loading} mutating={mutating} role={role}
    clarify={clarify} resume={() => mutate(() => api.resume(caseId))} />;
  const visibleError = actionError || error;
  const phone = <PhoneSimulator {...intake} caseId={caseId} snapshot={snapshot} mutating={mutating} error={visibleError} role={role}
    trips={trips.trips} invitations={trips.invitations} answerInvitation={answerInvitation}
    tripListError={trips.failed} tripListLoading={trips.loading} openCase={id => openCase(id)} voiceAvailable={voiceAvailable}
    startVoicePlan={() => void createCase('I would like to plan a New Zealand trip by voice.', true)} clarify={clarify}
    decide={decision => snapshot?.approval && mutate(() => api.decide(caseId, snapshot.approval!, decision))}
    cancelOrder={(order: Order) => mutate(() => api.cancelOrder(caseId, order.id))} />;
  const privatePage = route !== null && !PUBLIC_ROUTES.includes(route);
  const needsSignIn = user === null && (privatePage || pendingCreate !== null);

  return <div className={`app-shell ct-shell ct-route-${route?.slice(1) || 'home'}`}>
    <TopBar route={route} user={user} caseId={caseId} snapshot={snapshot} link={link} navigate={navigate} signOut={() => void leave()} />
    {user === undefined && privatePage ? <main className="ct-auth-page"><p role="status">{t("Checking your sign-in…")}</p></main>
      : needsSignIn ? <LoginPanel onSignedIn={next => { setUser(next); setActionError(''); }}
        reason={pendingCreate ? t('Sign in to save and plan your trip. We will start planning right after.') : t('Sign in to see your trips.')} />
      : <>
    {route === '/' && <LandingPage caseId={caseId} link={link} request={request} setRequest={setRequest}
      demoDate={demoDate} setDemoDate={setDemoDate} createCase={createCase} mutating={mutating} />}
    {(route === '/dashboard' || route === '/demo') && <section className="ct-hero" aria-label={t("New Zealand travel")}>
      <TravelPhoto image={matchTravelImage(snapshot?.caseData.requirements?.destination)} eager caption />
      <div className="ct-hero-shade" />
      <div className="ct-hero-copy"><p className="ct-kicker">{t("A KINDER WAY TO TRAVEL")}</p>
        <h1>{t("Tell us where you dream of going.")}<br/><em>{t("We will take care of the details.")}</em></h1>
        <p>{t("Thoughtful New Zealand travel, checked by our team and confirmed by you.")}</p>
        <a href={route === '/dashboard' ? '#new-trip' : link('/mobile')} className="ct-hero-link">{route === '/dashboard' ? t("Start a new trip") : t("Open traveler view")} <span aria-hidden="true">↗</span></a>
      </div>
      {caseId && <div className="ct-case-chip">{t("CASE")} <strong>{caseId.slice(0, 8).toUpperCase()}</strong></div>}
    </section>}
    {visibleError && <div className="error-banner ct-error" role="alert">{visibleError} {caseId && <button type="button" onClick={() => void refresh()}>{t("Retry loading")}</button>}</div>}
    {route === '/dashboard' && <main className="ct-dashboard-page">{dashboard}</main>}
    {route === '/mobile' && <main className="ct-mobile-page"><div className="ct-mobile-intro"><p className="ct-kicker">{t("CARETRIP COMPANION")}</p><h1>{t("Your trip, made simple.")}</h1><p>{t("Plan and review your New Zealand journey in this browser-based phone view.")}</p></div>{phone}</main>}
    {route === '/demo' && <main className="ct-workspace">{dashboard}{phone}</main>}
    {route === '/advisor' && (user?.is_advisor ? <AdvisorConsole /> : <main className="ct-not-found"><h1>{t('Advisors only')}</h1><p>{t('This page is for CareTrip travel advisors.')}</p></main>)}
    {route === '/account' && user && <AccountPage user={user} onUserChange={setUser} guard={guard}
      onDeleted={() => { setUser(null); goHome(); }} />}
    {route === '/trip-card' && <TripCardPage caseId={caseId} />}
    {(route === '/terms' || route === '/privacy') && <LegalPage kind={route === '/terms' ? 'terms' : 'privacy'} />}
    {route === null && <main className="ct-not-found"><h1>{t("Page not found")}</h1><p>{t("This CareTrip page is not available.")}</p><a href={link('/')}>{t("Return home")}</a></main>}
    </>}
    {stepUpDialog}
  </div>;
}
