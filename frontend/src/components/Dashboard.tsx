import { useState } from 'react';
import { roleRank } from '../types';
import type { CaseSnapshot, MemberRole } from '../types';
import TravelPhoto from './TravelPhoto';
import ItinerarySection from './dashboard/ItinerarySection';
import VerificationSection from './dashboard/VerificationSection';
import { matchAttractionImages, matchTravelImage } from '../data/travelImages';
import { useI18n } from '../i18n';
import { fieldLabel, needsPhrases, statusLabel } from '../labels';

interface Props {
  caseId: string; snapshot: CaseSnapshot | null; loading: boolean; mutating: boolean;
  request: string; demoDate: string; setRequest: (value: string) => void;
  setDemoDate: (value: string) => void; createCase: () => void; useSample: () => void;
  clarify: (answers: Record<string, string | number>) => void; resume: () => void;
  role: MemberRole | null;
}

function readable(value: string) { return value.replaceAll('_', ' ').toLowerCase(); }
function eventDetail(value: unknown): string {
  if (value == null) return '—';
  if (Array.isArray(value)) return value.map(eventDetail).join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export default function Dashboard(props: Props) {
  const { snapshot, caseId, loading, mutating } = props;
  const { t, formatDate } = useI18n();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const current = snapshot?.caseData;
  const canPlan = props.role !== null && roleRank[props.role] >= roleRank.CO_PLANNER;
  const requirements = current?.requirements;
  const attractions = requirements?.attractions ?? [];
  const verified = snapshot?.offers.find(offer => offer.label === 'VERIFIED' && offer.verdict === 'PASS');
  const order = snapshot?.orders.find(item => item.status === 'CONFIRMED');
  const events = snapshot?.events ?? [];
  const eventFor = (...types: string[]) => events.find(event => types.includes(event.event_type));
  const discovery = eventFor('SUPPLIERS_DISCOVERED');
  const verification = eventFor('EVIDENCE_ASSESSED');
  const approvalEvent = eventFor('APPROVAL_PREPARED', 'APPROVAL_DECIDED');
  const supplierEvent = eventFor('SUPPLIER_BOOKED');
  const bookingEvent = eventFor('ORDER_CONFIRMED');
  const stages = [
    { title: t('Supplier discovery'), detail: discovery ? t('search_suppliers skill · {n} synthetic catalog offers', { n: eventDetail(discovery.payload.count) }) : t('Waiting for the Comparison Worker'), event: discovery },
    { title: t('Offer verification'), detail: verification ? `${eventDetail(verification.payload.product_id)} · ${eventDetail(verification.payload.verdict)}` : t('Waiting for evidence assessment'), event: verification },
    { title: t('Human approval'), detail: snapshot?.approval ? `${snapshot.approval.status} · ${snapshot.approval.currency} ${snapshot.approval.approved_amount}` : t('No approval request yet'), event: approvalEvent },
    { title: t('Skill execution'), detail: supplierEvent ? t('The supplier confirmed the booking') : t('Runs after an approved offer'), event: supplierEvent },
    { title: t('Mock booking'), detail: order ? t('Simulated order {id}', { id: order.id }) : t('No order committed'), event: bookingEvent },
    { title: t('Audit trail'), detail: events.length ? t('{n} persisted events', { n: events.length }) : t('No persisted events yet'), event: events[0] },
  ];
  return <section className="ct-ops">
    <nav className="ct-side-nav" aria-label={t("Operations sections")}>
      <div className="ct-nav-title">{t("OPERATIONS DESK")}</div>
      <a href="#new-trip"><span>01</span> {t("New trip")}</a>
      <a href="#case-overview"><span>02</span> {t("Case overview")}</a>
      <a href="#offers"><span>03</span> {t("Offers")}</a>
        <a href="#verification"><span>04</span> {t("Verification")}</a>
        <a href="#execution"><span>05</span> {t("Execution")}</a>
        <a href="#activity"><span>06</span> {t("Audit trail")}</a>
      <div className="ct-nav-foot">{t("A human decision is required before any simulated booking.")}</div>
    </nav>

    <div className="ct-ops-content">
      <div className="ct-ops-heading"><div><p className="ct-kicker">{t("TRAVEL ADVISOR WORKSPACE")}</p><h2>{t("Good journeys start with listening.")}</h2>
        <p>{t("Guide each trip from the first idea through a clear, verified choice.")}</p></div>
        <span className="ct-live-dot">{current ? t(statusLabel(current.status)) : t("Ready for a new case")}</span></div>

      <div className="ct-summary-grid" aria-label={t("Live case summary")}>
        <div><span>{t("CASE STATUS")}</span><strong>{current ? t(statusLabel(current.status)) : t("Not started")}</strong><small>{caseId ? t('Case {id}', { id: caseId.slice(0, 8) }) : t("Create a trip below")}</small></div>
        <div><span>{t("VERIFIED CHOICE")}</span><strong>{verified ? verified.name ?? verified.product_id : t("Awaiting checks")}</strong><small>{verified ? t('{amount} total', { amount: `${verified.currency} ${verified.total_amount}` }) : t("Only a PASS offer can appear")}</small></div>
        <div><span>{t("BOOKING RESULT")}</span><strong>{order ? t("Confirmed in demo") : t("No order yet")}</strong><small>{order ? t('Order {id}', { id: order.id.slice(0, 8) }) : t("Approval comes first")}</small></div>
      </div>
      <div className="ct-source-key" aria-label={t("Data source labels")}><span>{t("PostgreSQL case and audit records")}</span><span>{t("Gemini itinerary only when marked reviewed")}</span><span>{t("Local destination photos and facts")}</span><span>{t("Synthetic supplier offers and simulated booking")}</span><span>{t("No live map, route or inventory feed")}</span></div>

      <section id="new-trip" className="ct-section ct-intake">
        <div className="ct-section-heading"><div><p className="ct-kicker">{t("01 / START HERE")}</p><h3>{t("What would you like to explore?")}</h3></div><span>{t("NEW CASE")}</span></div>
        <div className="ct-intake-grid"><div className="ct-intake-intro"><div className="ct-icon-badge">✦</div>
          <h4>{t("Tell us the trip in your own words.")}</h4><p>{t("Destination, days, companions, budget and the pace you prefer. The advisor will ask when something important is missing.")}</p>
          <button type="button" className="ct-text-button" onClick={props.useSample}>{t("Use the Auckland demo example ↗")}</button></div>
          <div className="ct-form"><label htmlFor="request">{t("Your travel idea")}</label>
            <textarea id="request" value={props.request} onChange={event => props.setRequest(event.target.value)}
              placeholder={t("For example: Three friends want a relaxed three-day Auckland trip. Total budget NZD 1000.")} rows={5} />
            <div className="ct-form-bottom"><div><label htmlFor="date">{t("Departure date")}</label><input id="date" type="date" value={props.demoDate} onChange={event => props.setDemoDate(event.target.value)} /></div>
              <div className="ct-currency-note"><span>{t("CURRENCY")}</span><strong>{t("NZD · total package")}</strong></div></div>
            <button className="ct-primary" onClick={() => props.createCase()} disabled={mutating || props.request.trim().length < 8 || !props.demoDate}>{mutating ? t("Preparing your trip…") : t("Plan this trip")} <span aria-hidden="true">→</span></button>
          </div></div>
      </section>

      <section id="case-overview" className="ct-section">
        <div className="ct-section-heading"><div><p className="ct-kicker">{t("02 / CASE OVERVIEW")}</p><h3>{t("A trip at a glance")}</h3></div>{current && <span className="ct-state-tag">{t(statusLabel(current.status))}</span>}</div>
        {!caseId ? <div className="ct-soft-empty">{t("Your new trip will appear here.")}</div> : loading && !snapshot ? <div className="ct-soft-empty">{t("Loading the latest case…")}</div> : !current ? <div className="ct-soft-empty">{t("Waiting for case details…")}</div> :
          <div className="ct-overview-card"><div className="ct-overview-facts"><div><span>{t("DESTINATION")}</span><strong>{requirements?.destination ? t(requirements.destination) : t("To confirm")}</strong></div>
            <div><span>{t("TRAVELERS")}</span><strong>{requirements?.traveler_count ?? t("To confirm")}</strong></div><div><span>{t("DURATION")}</span><strong>{requirements?.duration_days ? t('{n} days', { n: requirements.duration_days }) : t("To confirm")}</strong></div>
            <div><span>{t("TOTAL BUDGET")}</span><strong>{requirements?.budget ? `${requirements.currency ?? ''} ${requirements.budget}` : t("To confirm")}</strong></div></div>
            {requirements?.destination_scope === 'OUTSIDE_NZ' && <div className="ct-scope-note" role="status">{t("This demo currently supports trips within New Zealand only. Start a new case for a New Zealand destination.")}</div>}
            {requirements?.destination && <div className="ct-preferences"><span>{requirements.travel_pace === 'RELAXED' ? t("Gentle pace requested") : t("Standard pace")}</span>
              {attractions.length > 0 && <span>{t('Interested in {places}', { places: attractions.map(name => t(name)).join(t(' and ')) })}</span>}
              {needsPhrases(requirements.hard_constraints.needs).map(need => <span key={need.key} className="ct-need-chip">{t(need.key, need.vars)}</span>)}</div>}
            {current.itinerary_source === 'PENDING' && <div className="ct-soft-empty" role="status">{t("Gemini Planner and Reviewer are preparing the illustrative itinerary…")}</div>}
            <ItinerarySection caseData={current} booked={snapshot?.approval?.status === 'APPROVED' || Boolean(order)} />
            {requirements?.destination && attractions.length > 0 && <div className="ct-attractions">{matchAttractionImages(requirements.destination, attractions).map(image => <TravelPhoto key={image.attraction} image={image} caption />)}</div>}
            {current.status === 'NEEDS_CLARIFICATION' && canPlan && <div className="ct-clarification"><h4>{t("A little more detail will help")}</h4><p>{t("Answer these questions to continue planning.")}</p>
              <div className="ct-clarify-fields">{current.missing_fields.map(field => <label key={field}>{t(fieldLabel(field))}<input value={answers[field] ?? ''} onChange={event => setAnswers({ ...answers, [field]: event.target.value })} placeholder={field === 'departure_date' ? t("YYYY-MM-DD") : field} /></label>)}</div>
              <button className="ct-secondary" disabled={mutating || current.missing_fields.some(field => !answers[field])} onClick={() => props.clarify(answers)}>{t("Continue trip planning")}</button></div>}
            {current.status === 'RECOVERY_REQUIRED' && canPlan && <button className="ct-secondary" disabled={mutating || current.run_state !== 'idle'} onClick={props.resume}>{current.run_state === 'idle' ? t("Resume this case") : t("Resuming…")}</button>}
          </div>}
      </section>

      <section id="offers" className="ct-section"><div className="ct-section-heading"><div><p className="ct-kicker">{t("03 / EXPLORE OPTIONS")}</p><h3>{t("Sample travel choices")}</h3></div><span>{t('{n} OFFERS', { n: snapshot?.offers.length ?? 0 })}</span></div>
        {!snapshot?.offers.length ? <div className="ct-soft-empty">{current?.status === 'HUMAN_REVIEW' && requirements?.destination_scope === 'SUPPORTED'
          ? t('No synthetic package is available for {place} yet. The daily outline is illustrative; no offer can be approved.', { place: requirements.destination ? t(requirements.destination) : t('this trip') })
          : t("No sample offer has been found for this case.")}</div> : <div className="ct-offer-grid">{snapshot.offers.map(offer => <article className="ct-offer-card" key={offer.id}>
          <TravelPhoto image={matchTravelImage(requirements?.destination)} caption /><div className="ct-offer-body"><div className="ct-offer-title"><strong>{offer.name ?? offer.product_id}</strong><span className={`ct-offer-tag ct-${offer.label.toLowerCase()}`}>{offer.label.toLowerCase()}</span></div>
            <div className="ct-offer-price">{offer.currency} {offer.total_amount}<small>{t("synthetic catalog package · no live inventory")}</small></div><p>{offer.includes.map(item => t(item)).join(' · ')}</p>
            {offer.reason_code && <div className="ct-offer-reason">{readable(offer.reason_code)}</div>}
            <small>{t('Snapshot v{n} · valid until {date}', { n: offer.version, date: formatDate(offer.expires_at) })}</small></div></article>)}</div>}
      </section>

      <div className="ct-detail-grid"><section id="verification" className="ct-section"><div className="ct-section-heading"><div><p className="ct-kicker">{t("04 / TRUST & SAFETY")}</p><h3>{t("Verification")}</h3></div></div>
        <VerificationSection snapshot={snapshot} /></section>
        <section id="execution" className="ct-section"><div className="ct-section-heading"><div><p className="ct-kicker">{t("05 / EXECUTION PATH")}</p><h3>{t("What the agents actually did")}</h3></div></div>
          <div className="ct-execution-list">{stages.map(stage => <div className={`ct-execution-step ${stage.event ? 'is-recorded' : ''}`} key={stage.title}>
            <span aria-hidden="true">{stage.event ? '✓' : '·'}</span><div><strong>{stage.title}</strong><p>{stage.detail}</p>{stage.event && <small>{stage.event.agent_name} · {new Date(stage.event.created_at).toLocaleString()} · {readable(stage.event.event_type)}</small>}</div>
          </div>)}</div>
          {snapshot?.approval && <p className="ct-approval-status">{t('HITL authorization:')} <strong>{snapshot.approval.status}</strong> · {t('Offer version {n}', { n: snapshot.approval.offer_version })} · {t('Approval {id}', { id: snapshot.approval.approval_id.slice(0, 8) })}</p>}
        </section></div>
      <section id="activity" className="ct-section"><div className="ct-section-heading"><div><p className="ct-kicker">{t("06 / PERSISTED AUDIT TRAIL")}</p><h3>{t("Agent activity")}</h3></div><span>{t('{n} EVENTS', { n: events.length })}</span></div>
        <div className="ct-detail-card ct-timeline" tabIndex={0} role="region" aria-label={t("Agent activity")}>{!events.length ? <p className="ct-muted">{t("The timeline will appear after a case is created.")}</p> : events.map(event => <div className="ct-event" key={event.id}><span className="ct-event-dot"/><div><strong>{readable(event.event_type)}</strong><small>{event.agent_name} · {event.status} · {new Date(event.created_at).toLocaleString()}</small>
          {Object.keys(event.payload).length > 0 && <p>{Object.entries(event.payload).map(([key, value]) => `${readable(key)}: ${eventDetail(value)}`).join(' · ')}</p>}</div></div>)}</div></section>
      {snapshot && <div className="ct-result-strip">{order ? t('Backend-confirmed simulated package order {id}. The illustrative itinerary is separate and may have changed since approval.', { id: order.id }) : current?.status === 'REJECTED' ? t("The traveler declined this plan. No order was created.") : t("No simulated order has been committed.")}</div>}
    </div>
  </section>;
}
