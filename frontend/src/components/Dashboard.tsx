import { useState } from 'react';
import type { CaseSnapshot } from '../types';
import TravelPhoto from './TravelPhoto';
import { matchAttractionImages, matchTravelImage } from '../data/travelImages';

interface Props {
  caseId: string; snapshot: CaseSnapshot | null; loading: boolean; mutating: boolean;
  request: string; demoDate: string; setRequest: (value: string) => void;
  setDemoDate: (value: string) => void; createCase: () => void; useSample: () => void;
  clarify: (answers: Record<string, string | number>) => void; resume: () => void;
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
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const current = snapshot?.caseData;
  const requirements = current?.requirements;
  const attractions = requirements?.attractions ?? [];
  const verified = snapshot?.offers.find(offer => offer.label === 'VERIFIED' && offer.verdict === 'PASS');
  const order = snapshot?.orders.find(item => item.status === 'SIMULATED_CONFIRMED');
  const events = snapshot?.events ?? [];
  const eventFor = (...types: string[]) => events.find(event => types.includes(event.event_type));
  const discovery = eventFor('SUPPLIERS_DISCOVERED');
  const verification = eventFor('EVIDENCE_ASSESSED');
  const approvalEvent = eventFor('APPROVAL_PREPARED', 'APPROVAL_DECIDED');
  const bookingEvent = eventFor('MOCK_ORDER_COMMITTED');
  const stages = [
    { title: 'Supplier discovery', detail: discovery ? `search_suppliers skill · ${eventDetail(discovery.payload.count)} synthetic catalog offers` : 'Waiting for the Comparison Worker', event: discovery },
    { title: 'Offer verification', detail: verification ? `${eventDetail(verification.payload.product_id)} · ${eventDetail(verification.payload.verdict)}` : 'Waiting for evidence assessment', event: verification },
    { title: 'Human approval', detail: snapshot?.approval ? `${snapshot.approval.status} · ${snapshot.approval.currency} ${snapshot.approval.approved_amount}` : 'No approval request yet', event: approvalEvent },
    { title: 'Skill execution', detail: bookingEvent ? 'Booking Worker committed the mock booking skill' : 'Runs after an approved offer', event: bookingEvent },
    { title: 'Mock booking', detail: order ? `Simulated order ${order.id}` : 'No order committed', event: bookingEvent },
    { title: 'Audit trail', detail: events.length ? `${events.length} persisted events` : 'No persisted events yet', event: events[0] },
  ];
  return <section className="ct-ops">
    <nav className="ct-side-nav" aria-label="Operations sections">
      <div className="ct-nav-title">OPERATIONS DESK</div>
      <a href="#new-trip"><span>01</span> New trip</a>
      <a href="#case-overview"><span>02</span> Case overview</a>
      <a href="#offers"><span>03</span> Offers</a>
        <a href="#verification"><span>04</span> Verification</a>
        <a href="#execution"><span>05</span> Execution</a>
        <a href="#activity"><span>06</span> Audit trail</a>
      <div className="ct-nav-foot">A human decision is required before any simulated booking.</div>
    </nav>

    <div className="ct-ops-content">
      <div className="ct-ops-heading"><div><p className="ct-kicker">TRAVEL ADVISOR WORKSPACE</p><h2>Good journeys start with listening.</h2>
        <p>Guide each trip from the first idea through a clear, verified choice.</p></div>
        <span className="ct-live-dot">{current ? readable(current.status) : 'Ready for a new case'}</span></div>

      <div className="ct-summary-grid" aria-label="Live case summary">
        <div><span>CASE STATUS</span><strong>{current ? readable(current.status) : 'Not started'}</strong><small>{caseId ? `Case ${caseId.slice(0, 8)}` : 'Create a trip below'}</small></div>
        <div><span>VERIFIED CHOICE</span><strong>{verified ? verified.product_id.replace('_', ' ') : 'Awaiting checks'}</strong><small>{verified ? `${verified.currency} ${verified.total_amount} total` : 'Only a PASS offer can appear'}</small></div>
        <div><span>BOOKING RESULT</span><strong>{order ? 'Confirmed in demo' : 'No order yet'}</strong><small>{order ? `Order ${order.id.slice(0, 8)}` : 'Approval comes first'}</small></div>
      </div>
      <div className="ct-source-key" aria-label="Data source labels"><span>PostgreSQL case and audit records</span><span>Gemini itinerary only when marked reviewed</span><span>Local destination photos and facts</span><span>Synthetic supplier offers and simulated booking</span><span>No live map, route or inventory feed</span></div>

      <section id="new-trip" className="ct-section ct-intake">
        <div className="ct-section-heading"><div><p className="ct-kicker">01 / START HERE</p><h3>What would you like to explore?</h3></div><span>NEW CASE</span></div>
        <div className="ct-intake-grid"><div className="ct-intake-intro"><div className="ct-icon-badge">✦</div>
          <h4>Tell us the trip in your own words.</h4><p>Destination, days, companions, budget and the pace you prefer. The advisor will ask when something important is missing.</p>
          <button type="button" className="ct-text-button" onClick={props.useSample}>Use the Auckland demo example ↗</button></div>
          <div className="ct-form"><label htmlFor="request">Your travel idea</label>
            <textarea id="request" value={props.request} onChange={event => props.setRequest(event.target.value)}
              placeholder="For example: Three friends want a relaxed three-day Auckland trip. Total budget NZD 1000." rows={5} />
            <div className="ct-form-bottom"><div><label htmlFor="date">Departure date</label><input id="date" type="date" value={props.demoDate} onChange={event => props.setDemoDate(event.target.value)} /></div>
              <div className="ct-currency-note"><span>CURRENCY</span><strong>NZD · total package</strong></div></div>
            <button className="ct-primary" onClick={() => props.createCase()} disabled={mutating || props.request.trim().length < 8 || !props.demoDate}>{mutating ? 'Preparing your trip…' : 'Plan this trip'} <span aria-hidden="true">→</span></button>
          </div></div>
      </section>

      <section id="case-overview" className="ct-section">
        <div className="ct-section-heading"><div><p className="ct-kicker">02 / CASE OVERVIEW</p><h3>A trip at a glance</h3></div>{current && <span className="ct-state-tag">{readable(current.status)}</span>}</div>
        {!caseId ? <div className="ct-soft-empty">Your new trip will appear here.</div> : loading && !snapshot ? <div className="ct-soft-empty">Loading the latest case…</div> : !current ? <div className="ct-soft-empty">Waiting for case details…</div> :
          <div className="ct-overview-card"><div className="ct-overview-facts"><div><span>DESTINATION</span><strong>{requirements?.destination ?? 'To confirm'}</strong></div>
            <div><span>TRAVELERS</span><strong>{requirements?.traveler_count ?? 'To confirm'}</strong></div><div><span>DURATION</span><strong>{requirements?.duration_days ? `${requirements.duration_days} days` : 'To confirm'}</strong></div>
            <div><span>TOTAL BUDGET</span><strong>{requirements?.budget ? `${requirements.currency ?? ''} ${requirements.budget}` : 'To confirm'}</strong></div></div>
            {requirements?.destination_scope === 'OUTSIDE_NZ' && <div className="ct-scope-note" role="status">This demo currently supports trips within New Zealand only. Start a new case for a New Zealand destination.</div>}
            {requirements?.destination && <div className="ct-preferences"><span>{requirements.travel_pace === 'RELAXED' ? 'Gentle pace requested' : 'Standard pace'}</span>
              {attractions.length > 0 && <span>Interested in {attractions.join(' and ')}</span>}</div>}
            {current.itinerary_source === 'PENDING' && <div className="ct-soft-empty" role="status">Gemini Planner and Reviewer are preparing the illustrative itinerary…</div>}
            {Boolean(current.draft_itinerary?.length) && <section className="ct-dashboard-days" aria-label="Illustrative itinerary"><h4>Illustrative itinerary · version {current.itinerary_version || 1}</h4>
              <p>{current.itinerary_source === 'GEMINI_REVIEWED' ? 'Gemini Planner and Reviewer generated this outline.' : current.itinerary_source === 'GEMINI_FAILED' ? 'Gemini planning failed; this local outline needs further review.' : 'Local rule-based outline. No model itinerary was generated.'} {snapshot?.approval?.status === 'APPROVED' || order ? 'This outline is separate from the approved sample package. Later Guide revisions are not verified or included in the simulated order.' : ''}</p>
              {current.draft_itinerary?.map(day => <article key={day.day_number}><TravelPhoto image={matchTravelImage(requirements?.destination, day.attraction)} caption />
                <div><strong>Day {day.day_number}: {day.title}</strong><p>{day.note}</p><small>{day.intensity || 'LOW'} intensity</small>
                  {Boolean(day.activities?.length) && <ol>{day.activities?.map((activity, index) => <li key={`${index}-${activity}`}>{activity}</li>)}</ol>}
                  <p>Rest: {day.rest_note || 'Leave time to rest.'}</p>
                  {day.verification_notes?.map(note => <small key={note}>To check: {note}</small>)}</div></article>)}
            </section>}
            {requirements?.destination && attractions.length > 0 && <div className="ct-attractions">{matchAttractionImages(requirements.destination, attractions).map(image => <TravelPhoto key={image.attraction} image={image} caption />)}</div>}
            {current.status === 'NEEDS_CLARIFICATION' && <div className="ct-clarification"><h4>A little more detail will help</h4><p>Answer these questions to continue planning.</p>
              <div className="ct-clarify-fields">{current.missing_fields.map(field => <label key={field}>{readable(field)}<input value={answers[field] ?? ''} onChange={event => setAnswers({ ...answers, [field]: event.target.value })} placeholder={field === 'departure_date' ? 'YYYY-MM-DD' : field} /></label>)}</div>
              <button className="ct-secondary" disabled={mutating || current.missing_fields.some(field => !answers[field])} onClick={() => props.clarify(answers)}>Continue trip planning</button></div>}
            {current.status === 'RECOVERY_REQUIRED' && <button className="ct-secondary" disabled={mutating} onClick={props.resume}>Resume this case</button>}
          </div>}
      </section>

      <section id="offers" className="ct-section"><div className="ct-section-heading"><div><p className="ct-kicker">03 / EXPLORE OPTIONS</p><h3>Sample travel choices</h3></div><span>{snapshot?.offers.length ?? 0} OFFERS</span></div>
        {!snapshot?.offers.length ? <div className="ct-soft-empty">{current?.status === 'HUMAN_REVIEW' && requirements?.destination_scope === 'SUPPORTED'
          ? `No synthetic package is available for ${requirements.destination || 'this trip'} yet. The daily outline is illustrative; no offer can be approved.`
          : 'No sample offer has been found for this case.'}</div> : <div className="ct-offer-grid">{snapshot.offers.map(offer => <article className="ct-offer-card" key={offer.id}>
          <TravelPhoto image={matchTravelImage(requirements?.destination)} caption /><div className="ct-offer-body"><div className="ct-offer-title"><strong>{offer.product_id.replace('_', ' ')}</strong><span className={`ct-offer-tag ct-${offer.label.toLowerCase()}`}>{offer.label.toLowerCase()}</span></div>
            <div className="ct-offer-price">{offer.currency} {offer.total_amount}<small>synthetic catalog package · no live inventory</small></div><p>{offer.includes.join(' · ')}</p>
            {offer.reason_code && <div className="ct-offer-reason">{readable(offer.reason_code)}</div>}
            <small>Snapshot v{offer.version} · valid until {new Date(offer.expires_at).toLocaleDateString()}</small></div></article>)}</div>}
      </section>

      <div className="ct-detail-grid"><section id="verification" className="ct-section"><div className="ct-section-heading"><div><p className="ct-kicker">04 / TRUST & SAFETY</p><h3>Verification</h3></div></div>
        <div className="ct-detail-card"><p className="ct-muted">Evidence below comes from the synthetic supplier catalog, not an external provider.</p>{!snapshot?.evidence.assessments.length ? <p className="ct-muted">No evidence has been assessed yet.</p> : snapshot.evidence.assessments.map(item => <details key={item.offer_id} className="ct-assessment">
          <summary><strong>{item.product_id.replace('_', ' ')}</strong><span className={`ct-offer-tag ct-${item.verdict.toLowerCase()}`}>{item.verdict}</span></summary>
          <p>{readable(item.reason_code)}</p>{snapshot.evidence.sources.filter(source => source.offer_id === item.offer_id).map(source => <p key={source.reference}><b>{source.polarity}</b> · {source.detail} <small>{source.reference}</small></p>)}
        </details>)}</div></section>
        <section id="execution" className="ct-section"><div className="ct-section-heading"><div><p className="ct-kicker">05 / EXECUTION PATH</p><h3>What the agents actually did</h3></div></div>
          <div className="ct-execution-list">{stages.map(stage => <div className={`ct-execution-step ${stage.event ? 'is-recorded' : ''}`} key={stage.title}>
            <span aria-hidden="true">{stage.event ? '✓' : '·'}</span><div><strong>{stage.title}</strong><p>{stage.detail}</p>{stage.event && <small>{stage.event.agent_name} · {new Date(stage.event.created_at).toLocaleString()} · {readable(stage.event.event_type)}</small>}</div>
          </div>)}</div>
          {snapshot?.approval && <p className="ct-approval-status">HITL authorization: <strong>{snapshot.approval.status}</strong> · Offer version {snapshot.approval.offer_version} · Approval {snapshot.approval.approval_id.slice(0, 8)}</p>}
        </section></div>
      <section id="activity" className="ct-section"><div className="ct-section-heading"><div><p className="ct-kicker">06 / PERSISTED AUDIT TRAIL</p><h3>Agent activity</h3></div><span>{events.length} EVENTS</span></div>
        <div className="ct-detail-card ct-timeline">{!events.length ? <p className="ct-muted">The timeline will appear after a case is created.</p> : events.map(event => <div className="ct-event" key={event.id}><span className="ct-event-dot"/><div><strong>{readable(event.event_type)}</strong><small>{event.agent_name} · {event.status} · {new Date(event.created_at).toLocaleString()}</small>
          {Object.keys(event.payload).length > 0 && <p>{Object.entries(event.payload).map(([key, value]) => `${readable(key)}: ${eventDetail(value)}`).join(' · ')}</p>}</div></div>)}</div></section>
      {snapshot && <div className="ct-result-strip">{order ? `Backend-confirmed simulated package order ${order.id}. The illustrative itinerary is separate and may have changed since approval.` : current?.status === 'REJECTED' ? 'The traveler declined this plan. No order was created.' : 'No simulated order has been committed.'}</div>}
    </div>
  </section>;
}
