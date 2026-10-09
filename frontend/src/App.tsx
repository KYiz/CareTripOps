import { useCallback, useEffect, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import { api } from './api/client';
import Dashboard from './components/Dashboard';
import PhoneSimulator from './components/PhoneSimulator';
import LandingPage from './components/LandingPage';
import type { CaseSnapshot } from './types';
import TravelPhoto from './components/TravelPhoto';
import { matchTravelImage } from './data/travelImages';
import { resolveRoute, routeHref, type AppRoute } from './routes';

const sampleRequest = 'Three travelers want a relaxed three-day Auckland trip. We need a lift serving all guest floors. Our total budget is NZD 1000.';
const sampleDate = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);

function initialCaseId(): string {
  const fromUrl = new URLSearchParams(location.search).get('caseId');
  if (fromUrl) return fromUrl;
  try { return localStorage.getItem('caretrip:last-case') ?? ''; } catch { return ''; }
}

export default function App() {
  const [caseId, setCaseId] = useState(initialCaseId);
  const selectedCaseId = useRef(caseId);
  selectedCaseId.current = caseId;
  const [request, setRequest] = useState('');
  const [demoDate, setDemoDate] = useState(sampleDate);
  const [snapshot, setSnapshot] = useState<CaseSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [tripIds, setTripIds] = useState<string[]>(() => {
    try {
      const ids = JSON.parse(localStorage.getItem('caretrip:case-ids') || '[]') as string[];
      const last = initialCaseId();
      return last && !ids.includes(last) ? [last, ...ids] : ids;
    } catch { return initialCaseId() ? [initialCaseId()] : []; }
  });
  const [tripSummaries, setTripSummaries] = useState<{ id: string; destination: string; status: string }[]>([]);
  const [tripListError, setTripListError] = useState(false);
  const [tripListLoading, setTripListLoading] = useState(false);
  const [voiceAvailable, setVoiceAvailable] = useState<boolean | null>(null);
  const [route, setRoute] = useState(() => resolveRoute(location.pathname));
  const terminal = snapshot && ['DEMO_COMPLETED', 'REJECTED', 'HUMAN_REVIEW', 'FAILED'].includes(snapshot.caseData.status);
  const pollMs = terminal ? 10000 : 1500;
  const link = (path: AppRoute) => routeHref(path, caseId);

  function navigate(event: MouseEvent<HTMLAnchorElement>, path: AppRoute) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (route === path) return;
    history.pushState(null, '', link(path));
    setRoute(path);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  useEffect(() => {
    fetch('/api/guide/capabilities').then(response => response.ok ? response.json() : null)
      .then(body => setVoiceAvailable(Boolean(body?.data?.voice_available)))
      .catch(() => setVoiceAvailable(false));
  }, []);

  useEffect(() => {
    const onHistory = () => {
      const id = new URLSearchParams(location.search).get('caseId') || '';
      if (id !== selectedCaseId.current) { selectedCaseId.current = id; setSnapshot(null); setCaseId(id); }
      setRoute(resolveRoute(location.pathname));
    };
    window.addEventListener('popstate', onHistory);
    return () => window.removeEventListener('popstate', onHistory);
  }, []);

  useEffect(() => {
    if (!caseId) return;
    try { localStorage.setItem('caretrip:last-case', caseId); } catch { /* Case access still requires its saved token. */ }
    if (route && route !== '/' && !new URLSearchParams(location.search).has('caseId')) {
      history.replaceState(null, '', link(route));
    }
  }, [caseId, route]);

  useEffect(() => {
    if (!tripIds.length) { setTripSummaries([]); setTripListError(false); setTripListLoading(false); return; }
    let active = true;
    setTripListLoading(true);
    void Promise.all(tripIds.map(async id => {
      try {
        const item = await api.caseData(id);
        return { id, destination: item.requirements?.destination || 'Trip in progress', status: item.status };
      } catch { return null; }
    })).then(items => { if (active) {
      setTripListError(items.some(item => item === null));
      setTripSummaries(items.filter((item): item is NonNullable<typeof item> => item !== null));
      setTripListLoading(false);
    } });
    return () => { active = false; };
  }, [tripIds, snapshot?.caseData.status]);

  const refresh = useCallback(async () => {
    if (!caseId) return;
    try {
      const next = await api.snapshot(caseId);
      if (selectedCaseId.current !== caseId) return;
      setSnapshot(next);
      setError('');
    } catch (cause) {
      if (selectedCaseId.current !== caseId) return;
      setError(cause instanceof Error ? cause.message : 'Unable to load case');
    }
  }, [caseId]);

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    void refresh().finally(() => setLoading(false));
    const timer = setInterval(() => void refresh(), pollMs);
    return () => clearInterval(timer);
  }, [caseId, refresh, pollMs]);

  async function createCase(requestOverride?: string, voiceStart = false) {
    if (mutating) return;
    setMutating(true);
    setActionError('');
    try {
      const created = await api.createCase(requestOverride ?? request, demoDate, voiceStart);
      const nextIds = [created.case_id, ...tripIds.filter(id => id !== created.case_id)];
      try { localStorage.setItem('caretrip:case-ids', JSON.stringify(nextIds)); localStorage.setItem('caretrip:last-case', created.case_id); } catch { /* Case access still requires its saved token. */ }
      setTripIds(nextIds);
      if (route === '/') {
        location.assign(`${routeHref('/mobile', created.case_id)}${voiceStart ? '&voice=1' : ''}`);
        return;
      }
      history.replaceState(null, '', `${location.pathname}?caseId=${encodeURIComponent(created.case_id)}${voiceStart ? '&voice=1' : ''}`);
      selectedCaseId.current = created.case_id;
      setSnapshot(null);
      setCaseId(created.case_id);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : 'Case creation failed');
    } finally { setMutating(false); }
  }

  function openCase(id: string) {
    if (id === caseId) return;
    selectedCaseId.current = id;
    setSnapshot(null); setError(''); setActionError('');
    history.pushState(null, '', `${location.pathname}?caseId=${encodeURIComponent(id)}`);
    setCaseId(id);
  }

  async function mutate(action: () => Promise<unknown>) {
    if (mutating) return;
    setMutating(true);
    setActionError('');
    try { await action(); await refresh(); }
    catch (cause) { await refresh(); setActionError(cause instanceof Error ? cause.message : 'Request failed'); }
    finally { setMutating(false); }
  }

  const dashboard = <Dashboard caseId={caseId} snapshot={snapshot} loading={loading} mutating={mutating} request={request}
    demoDate={demoDate} setRequest={setRequest} setDemoDate={setDemoDate} createCase={createCase}
    useSample={() => setRequest(sampleRequest)}
    clarify={(answers) => mutate(() => api.clarify(caseId, answers))} resume={() => mutate(() => api.resume(caseId))} />;
  const visibleError = actionError || error;
  const phone = <PhoneSimulator caseId={caseId} snapshot={snapshot} mutating={mutating} error={visibleError}
    trips={tripSummaries} tripListError={tripListError} tripListLoading={tripListLoading} openCase={openCase}
    request={request} demoDate={demoDate} setRequest={setRequest} setDemoDate={setDemoDate}
    createCase={createCase} useSample={() => setRequest(sampleRequest)}
    voiceAvailable={voiceAvailable}
    startVoicePlan={() => void createCase('I would like to plan a New Zealand trip by voice.', true)}
    clarify={(answers) => mutate(() => api.clarify(caseId, answers))}
    decide={(decision) => snapshot?.approval && mutate(() => api.decide(caseId, snapshot.approval!, decision))} />;

  return <div className={`app-shell ct-shell ct-route-${route?.slice(1) || 'home'}`}>
    <header className="ct-topbar">
      <a href={link('/')} onClick={event => navigate(event, '/')} className="ct-logo" aria-label="CareTrip home">C<span>✦</span></a>
      <div className="ct-brand"><strong>CareTrip <em>Ops</em></strong><span>NEW ZEALAND · TRAVEL WITH CONFIDENCE</span></div>
      <nav className="ct-route-nav" aria-label="Main navigation">
        <a href={link('/')} onClick={event => navigate(event, '/')} aria-current={route === '/' ? 'page' : undefined}>Home</a>
        <a href={link('/dashboard')} onClick={event => navigate(event, '/dashboard')} aria-current={route === '/dashboard' ? 'page' : undefined}>Dashboard</a>
        <a href={link('/mobile')} onClick={event => navigate(event, '/mobile')} aria-current={route === '/mobile' ? 'page' : undefined}>Mobile</a>
        <a href={link('/demo')} onClick={event => navigate(event, '/demo')} aria-current={route === '/demo' ? 'page' : undefined}>Demo</a>
      </nav>
      <div className="ct-header-right">
        <span className="ct-mode">{!caseId ? 'No case selected' : !snapshot ? 'Case data pending' : snapshot.caseData.model_mode === 'api'
          ? `${snapshot.caseData.llm_provider || 'Live'} ${snapshot.caseData.model_status === 'SUCCEEDED' ? 'used' : snapshot.caseData.model_status === 'FAILED' ? 'failed' : 'pending'}`
          : 'Mock model'}</span>
        <span className="ct-disclosure">Synthetic offers · Simulated booking</span>
      </div>
    </header>
    {route === '/' && <LandingPage caseId={caseId} link={link} request={request} setRequest={setRequest}
      demoDate={demoDate} setDemoDate={setDemoDate} createCase={createCase} mutating={mutating} />}
    {(route === '/dashboard' || route === '/demo') && <section className="ct-hero" aria-label="New Zealand travel">
      <TravelPhoto image={matchTravelImage(snapshot?.caseData.requirements?.destination)} eager caption />
      <div className="ct-hero-shade" />
      <div className="ct-hero-copy"><p className="ct-kicker">A KINDER WAY TO TRAVEL</p>
        <h1>Tell us where you dream of going.<br/><em>We will take care of the details.</em></h1>
        <p>Thoughtful New Zealand travel, checked by our team and confirmed by you.</p>
        <a href={route === '/dashboard' ? '#new-trip' : link('/mobile')} className="ct-hero-link">{route === '/dashboard' ? 'Start a new trip' : 'Open traveler view'} <span aria-hidden="true">↗</span></a>
      </div>
      {caseId && <div className="ct-case-chip">CASE <strong>{caseId.slice(0, 8).toUpperCase()}</strong></div>}
    </section>}
    {visibleError && <div className="error-banner ct-error" role="alert">{visibleError} {caseId && <button type="button" onClick={() => void refresh()}>Retry loading</button>}</div>}
    {route === '/dashboard' && <main className="ct-dashboard-page">{dashboard}</main>}
    {route === '/mobile' && <main className="ct-mobile-page"><div className="ct-mobile-intro"><p className="ct-kicker">CARETRIP COMPANION</p><h1>Your trip, made simple.</h1><p>Plan and review your New Zealand journey in this browser-based phone view.</p></div>{phone}</main>}
    {route === '/demo' && <main className="ct-workspace">{dashboard}{phone}</main>}
    {route === null && <main className="ct-not-found"><h1>Page not found</h1><p>This CareTrip page is not available.</p><a href={link('/')}>Return home</a></main>}
  </div>;
}
