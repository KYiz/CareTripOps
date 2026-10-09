import { useEffect, useState } from 'react';
import type { CaseSnapshot } from '../types';
import TravelPhoto from './TravelPhoto';
import { matchTravelImage, travelImages } from '../data/travelImages';
import GuidePanel from './GuidePanel';

interface Props {
  caseId: string; snapshot: CaseSnapshot | null; mutating: boolean; error: string;
  trips: { id: string; destination: string; status: string }[]; tripListError: boolean; tripListLoading: boolean; openCase: (id: string) => void;
  request: string; demoDate: string; setRequest: (value: string) => void;
  setDemoDate: (value: string) => void; createCase: (requestOverride?: string) => void; useSample: () => void;
  startVoicePlan: () => void;
  voiceAvailable: boolean | null;
  clarify: (answers: Record<string, string>) => void;
  decide: (decision: 'APPROVE' | 'REJECT') => void;
}

const clarificationLabels: Record<string, string> = {
  destination: 'Where in New Zealand?', departure_date: 'Departure date',
  traveler_count: 'Number of travelers', duration_days: 'Number of days',
  budget: 'Total budget', currency: 'Currency (NZD)',
};
const destinationNames = Array.from(new Set(travelImages.map(image => image.destination).filter((name): name is string => Boolean(name))));
const mobileThemes: Record<string, string[]> = {
  'Relaxing Getaways': ['Queenstown', 'Rotorua', 'Christchurch'],
  'Scenic Journeys': ['Auckland', 'Queenstown', 'Wellington', 'Taupō'],
  'Nature & Gardens': ['Rotorua', 'Christchurch', 'Taupō'],
  'Accessible Experiences': ['Auckland', 'Christchurch'],
  'Family Holidays': ['Queenstown', 'Taupō'],
  'Cultural Discovery': ['Auckland', 'Rotorua', 'Wellington'],
};

function friendlyStatus(status: string | undefined): string {
  if (!status) return 'Ready to plan';
  if (status === 'AWAITING_APPROVAL') return 'Ready for your decision';
  if (status === 'DEMO_COMPLETED') return 'Sample order recorded';
  if (status === 'REJECTED') return 'Plan declined';
  if (status === 'HUMAN_REVIEW') return 'A travel advisor will review this';
  if (status === 'NEEDS_CLARIFICATION') return 'A few details are needed';
  if (status === 'RECOVERY_REQUIRED') return 'An advisor is checking progress';
  return 'We are checking your trip';
}

export default function PhoneSimulator(props: Props) {
  const { caseId, snapshot, mutating, decide } = props;
  const [tab, setTab] = useState<'EXPLORE' | 'TRIPS' | 'TRIP' | 'GUIDE' | 'HELP'>('EXPLORE');
  const [confirming, setConfirming] = useState(false);
  const [planningNew, setPlanningNew] = useState(false);
  const [mobileTheme, setMobileTheme] = useState('All journeys');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  useEffect(() => { if (caseId) { setTab(new URLSearchParams(location.search).get('voice') === '1' ? 'GUIDE' : 'TRIP'); setPlanningNew(false); setConfirming(false); setAnswers({}); } }, [caseId]);
  const current = snapshot?.caseData;
  const requirements = current?.requirements;
  const approval = snapshot?.approval;
  const verified = snapshot?.offers.find(offer => offer.label === 'VERIFIED' && offer.verdict === 'PASS' && offer.id === approval?.offer_id);
  const order = snapshot?.orders.find(item => item.approval_id === approval?.approval_id);
  const completed = current?.status === 'DEMO_COMPLETED' && order?.status === 'SIMULATED_CONFIRMED';
  const destination = requirements?.destination;
  const attraction = requirements?.attractions?.[0];
  const photo = matchTravelImage(destination, attraction);
  const readyToApprove = Boolean(verified && approval?.status === 'PENDING' && current?.status === 'AWAITING_APPROVAL');

  return <aside className="ct-phone-column"><div className="ct-phone-label"><span>THE TRAVELER'S VIEW</span><small>Same case · same trusted facts</small></div>
    <div className="ct-phone-frame"><div className="ct-phone-island"/><div className="ct-phone-screen">
      <header className="ct-phone-header"><div className="ct-phone-mark">C<span>✦</span></div><strong>CareTrip <em>Companion</em></strong><span className="ct-phone-avatar" aria-hidden="true">✦</span></header>
      <div className="ct-phone-scroll">
        {props.error && <div className="ct-phone-alert" role="alert">{props.error}</div>}
        {tab === 'EXPLORE' && !caseId ? <div className="ct-phone-home">
          <TravelPhoto image={matchTravelImage(null)} className="ct-phone-home-photo" eager caption />
          <p className="ct-phone-kicker">A JOURNEY MADE FOR YOU</p><h2>Where would you like to go?</h2>
          <p className="ct-phone-lead">Tell us your idea. We will help with the details.</p>
          <label htmlFor="phone-request">Your travel idea</label>
          <textarea id="phone-request" value={props.request} onChange={event => props.setRequest(event.target.value)} rows={4}
            placeholder="I would like to visit Auckland with two friends for three days…" />
          <button type="button" className="ct-phone-example" onClick={props.useSample}>Try the Auckland example</button>
          <label htmlFor="phone-date">When would you like to leave?</label>
          <input id="phone-date" type="date" value={props.demoDate} onChange={event => props.setDemoDate(event.target.value)} />
          <button className="ct-phone-primary" disabled={mutating || props.request.trim().length < 8 || !props.demoDate} onClick={() => props.createCase()}>{mutating ? 'Planning your trip…' : 'Plan my trip'} <span aria-hidden="true">→</span></button>
          <button type="button" className="ct-phone-outline" disabled={mutating || props.voiceAvailable !== true} onClick={props.startVoicePlan}>{props.voiceAvailable === null ? 'Checking voice availability…' : props.voiceAvailable ? 'Start with voice →' : 'Live voice unavailable'}</button>
          {caseId && <button className="ct-my-trip-link" onClick={() => setTab('TRIP')}>View my current trip <span aria-hidden="true">→</span></button>}
          <p className="ct-phone-footnote">New Zealand demo · Live voice depends on Gemini availability · No payment</p>
          <h3>Or explore a destination</h3>
          {destinationNames.map(name => <article className="ct-phone-explore-card" key={name}>
            <TravelPhoto image={matchTravelImage(name)} caption />
            <div><strong>{name}</strong><small>{name === 'Auckland' ? 'Synthetic package demo' : 'Illustrative itinerary only'}</small>
              <button type="button" disabled={mutating} onClick={() => props.createCase(`Three travelers want a relaxed three-day trip to ${name}. Our total budget is NZD 1000. We need a lift serving all guest floors.`)}>{mutating ? 'Planning…' : 'Plan this trip →'}</button></div>
          </article>)}
        </div> : tab === 'EXPLORE' ? <div className="ct-phone-explore">
          <p className="ct-phone-kicker">EXPLORE NEW ZEALAND</p><h2>Find your next view.</h2>
          <p className="ct-phone-lead">Local destination ideas. Only Auckland has a synthetic sample package.</p>
          <button type="button" className="ct-phone-primary" onClick={() => { props.setRequest(''); setPlanningNew(true); setTab('TRIP'); }}>Plan a new trip →</button>
          <div className="ct-phone-themes" role="group" aria-label="Filter travel themes">
            {['All journeys', ...Object.keys(mobileThemes)].map(theme => <button key={theme} type="button" aria-pressed={mobileTheme === theme} onClick={() => setMobileTheme(theme)}>{theme}</button>)}
          </div>
          {destinationNames.filter(name => mobileTheme === 'All journeys' || mobileThemes[mobileTheme]?.includes(name)).map(name => <article className="ct-phone-explore-card" key={name}>
            <TravelPhoto image={matchTravelImage(name)} caption />
            <div><strong>{name}</strong><small>{name === 'Auckland' ? 'Synthetic package demo' : 'Illustrative itinerary only'}</small>
              <button type="button" disabled={mutating} onClick={() => props.createCase(`Three travelers want a relaxed three-day trip to ${name}. Our total budget is NZD 1000. We need a lift serving all guest floors.`)}>{mutating ? 'Planning…' : 'Plan this trip →'}</button></div>
          </article>)}
        </div> : tab === 'TRIPS' ? <div className="ct-phone-explore"><p className="ct-phone-kicker">MY TRIPS</p><h2>Your saved trips</h2><p className="ct-phone-lead">Cases opened in this browser. Each trip loads its own saved records.</p>
          {props.tripListError && <div className="ct-phone-alert" role="alert">Some saved trips could not be loaded. Check the connection and reopen this page.</div>}
          {props.tripListLoading ? <div className="ct-phone-message" role="status">Loading saved trips…</div> : props.trips.length ? props.trips.map(trip => <button className="ct-phone-trip-link" key={trip.id} type="button" onClick={() => { props.openCase(trip.id); setTab('TRIP'); }}><strong>{trip.destination}</strong><span>{friendlyStatus(trip.status)} · {trip.id.slice(0, 8)}</span></button>) : <div className="ct-phone-message">No accessible saved trips in this browser yet.</div>}
          <button className="ct-phone-primary" type="button" onClick={() => { setPlanningNew(true); setTab('TRIP'); }}>Plan a new trip →</button>
        </div> : tab === 'GUIDE' ? <GuidePanel caseId={caseId} /> : tab === 'HELP' ? <div className="ct-phone-help">
          <p className="ct-phone-kicker">HELP</p><h2>We are here to make it clear.</h2>
          <div className="ct-phone-message"><strong>How do I start?</strong><p>Tell us where you would like to go, who is coming, your budget and the pace you prefer.</p></div>
          <div className="ct-phone-message"><strong>What happens next?</strong><p>We check sample offers. You decide whether to approve a verified offer. No real payment or booking is made.</p></div>
          <button className="ct-phone-primary" type="button" onClick={() => { setPlanningNew(true); setTab('TRIP'); }}>Start a trip →</button>
        </div> : <div className="ct-phone-trip">
          {(!caseId || planningNew) && <div className="ct-phone-home ct-trip-create"><h3>Tell us your travel idea</h3><label htmlFor="phone-request">Your travel idea</label>
            <textarea id="phone-request" value={props.request} onChange={event => props.setRequest(event.target.value)} rows={4} placeholder="I would like to visit Auckland with two friends for three days…" />
            <button type="button" className="ct-phone-example" onClick={props.useSample}>Try the Auckland example</button>
            <label htmlFor="phone-date">Departure date</label><input id="phone-date" type="date" value={props.demoDate} onChange={event => props.setDemoDate(event.target.value)} />
            <button className="ct-phone-primary" disabled={mutating || props.request.trim().length < 8 || !props.demoDate} onClick={() => props.createCase()}>{mutating ? 'Planning…' : 'Plan my trip →'}</button></div>}
          {!planningNew && <>
          <p className="ct-phone-kicker">YOUR TRIP</p><h2>{destination ? `Let's explore ${destination}` : 'Your trip is taking shape'}</h2>
          <p className="ct-phone-lead">{friendlyStatus(current?.status)}</p>
          <TravelPhoto image={photo} className="ct-phone-trip-photo" eager caption />
          <div className="ct-phone-trip-facts"><div><span>TRAVELERS</span><strong>{requirements?.traveler_count ?? '—'}</strong></div>
            <div><span>TIME AWAY</span><strong>{requirements?.duration_days ? `${requirements.duration_days} days` : '—'}</strong></div>
            <div><span>PACE</span><strong>{requirements?.travel_pace === 'RELAXED' ? 'Gentle' : 'Easy to follow'}</strong></div></div>
          {current?.itinerary_source === 'PENDING' && <div className="ct-phone-message" role="status">Gemini Planner and Reviewer are preparing your daily outline…</div>}
          {Boolean(current?.draft_itinerary?.length) && <section className="ct-phone-days" aria-label="Illustrative daily trip outline">
            <p className="ct-phone-kicker">A FIRST LOOK AT YOUR DAYS</p>
            <h3>Your gentle trip outline</h3>
            <p className="ct-phone-draft-note">{current?.itinerary_source === 'GEMINI_REVIEWED' ? 'Gemini Planner and Reviewer checked this illustrative outline.' : current?.itinerary_source === 'GEMINI_FAILED' ? 'Gemini planning was unavailable. This is a local illustrative outline.' : 'This is a local illustrative outline.'} Version {current?.itinerary_version || 1}. Visits and travel details still need confirmation. {approval?.status === 'APPROVED' || completed ? 'This outline is separate from the approved sample package and simulated order; later changes are not booked or verified.' : ''}</p>
            {current?.draft_itinerary?.map(day => <article className="ct-phone-day" key={day.day_number}>
              <TravelPhoto image={matchTravelImage(destination, day.attraction)} className="ct-phone-day-photo" caption />
              <div className="ct-phone-day-copy"><span>DAY {day.day_number} · ILLUSTRATIVE · {day.intensity || 'LOW'} INTENSITY</span><strong>{day.title}</strong><p>{day.note}</p>
                {Boolean(day.activities?.length) && <ol>{day.activities?.map((activity, index) => <li key={`${index}-${activity}`}>{activity}</li>)}</ol>}
                <p><b>Rest:</b> {day.rest_note || 'Leave time to rest.'}</p>
                {day.verification_notes?.map(note => <small key={note}>To check: {note}</small>)}
              </div>
            </article>)}
          </section>}
          {!snapshot && caseId && !props.error && <div className="ct-phone-message" role="status">Loading your trip details…</div>}
          {snapshot && !verified && <div className="ct-phone-message"><div className="ct-phone-message-icon">✦</div><strong>{current?.status === 'HUMAN_REVIEW' ? 'We need to take a closer look' : 'We are checking your options'}</strong>
            <p>{requirements?.destination_scope === 'OUTSIDE_NZ' ? 'This demonstration currently supports travel within New Zealand only.' : current?.status === 'NEEDS_CLARIFICATION' ? 'Please add the details below to continue.' : current?.status === 'HUMAN_REVIEW' && !snapshot.offers.length ? `No synthetic package is available for ${destination || 'this trip'} yet. Your outline is illustrative only.` : 'We will show a plan here after the sample checks are complete.'}</p></div>}
          {current?.status === 'NEEDS_CLARIFICATION' && <section className="ct-phone-clarify" aria-label="Complete travel details">
            <h3>A few more details</h3>
            {current.missing_fields.map(field => <label key={field} htmlFor={`phone-${field}`}>{clarificationLabels[field] ?? field.replaceAll('_', ' ')}
              <input id={`phone-${field}`} type={field === 'departure_date' ? 'date' : ['traveler_count', 'duration_days', 'budget'].includes(field) ? 'number' : 'text'}
                min={['traveler_count', 'duration_days', 'budget'].includes(field) ? '1' : undefined}
                value={answers[field] ?? ''} onChange={event => setAnswers({ ...answers, [field]: event.target.value })}
                placeholder={field === 'currency' ? 'NZD' : undefined} /></label>)}
            <button className="ct-phone-primary" disabled={mutating || current.missing_fields.some(field => !answers[field]?.trim())}
              onClick={() => props.clarify(Object.fromEntries(current.missing_fields.map(field => [field, answers[field]])))}>
              {mutating ? 'Saving details…' : 'Continue planning'}
            </button>
          </section>}
          {verified && <div className="ct-phone-plan"><p className="ct-phone-kicker">VERIFIED SYNTHETIC PACKAGE</p><h3>{destination} · {requirements?.duration_days} days</h3>
            <p className="ct-phone-plan-copy">A sample package for {requirements?.traveler_count} travelers.</p>
            {attraction && <p className="ct-phone-plan-copy">A place you mentioned: {attraction}</p>}
            <div className="ct-phone-includes">{verified.includes.map(item => <div key={item}><span aria-hidden="true">✓</span>{item}</div>)}</div>
            <p className="ct-phone-plan-copy">This package is the approved offer snapshot. The daily outline is a separate suggestion; later Guide changes do not update this offer or order.</p>
            <div className="ct-phone-total"><span>TOTAL FOR THE GROUP</span><strong>{verified.currency} {verified.total_amount}</strong></div>
            <p className="ct-phone-validity">Sample offer · Version {verified.version} · Valid until {new Date(verified.expires_at).toLocaleDateString()}</p></div>}
          {readyToApprove && !confirming && <div className="ct-phone-actions"><p>You decide what happens next. No real booking or payment will be made.</p>
            <button className="ct-phone-primary" disabled={mutating} onClick={() => setConfirming(true)}>Review and approve <span aria-hidden="true">→</span></button>
            <button className="ct-phone-outline" disabled={mutating} onClick={() => decide('REJECT')}>Decline this plan</button></div>}
          {readyToApprove && confirming && <div className="ct-phone-confirm"><p className="ct-phone-kicker">FINAL CHECK</p><h3>Confirm this sample plan?</h3>
            <p>{verified?.product_id.replace('_', ' ')} · Version {verified?.version}<br/>Total {verified?.currency} {verified?.total_amount}</p>
            <p>This creates one simulated booking after your approval. No payment is taken.</p>
            <button className="ct-phone-primary" disabled={mutating} onClick={() => { setConfirming(false); decide('APPROVE'); }}>{mutating ? 'Submitting…' : `Confirm ${verified?.currency} ${verified?.total_amount}`}</button>
            <button className="ct-phone-outline" disabled={mutating} onClick={() => setConfirming(false)}>Go back</button></div>}
          {current?.status === 'APPROVED' && <div className="ct-phone-message">Your approval was saved. We are checking the simulated booking result…</div>}
          {completed && <div className="ct-phone-complete"><div aria-hidden="true">✓</div><h3>Sample package order recorded</h3><p>Simulated order {order.id.slice(0, 8)} was confirmed by the backend for the package snapshot. The illustrative daily outline is not an order confirmation.</p><strong>{order.currency} {order.total_amount}</strong></div>}
          {current?.status === 'REJECTED' && <div className="ct-phone-message">You declined this plan. No order was created.</div>}
          {['FAILED', 'RECOVERY_REQUIRED'].includes(current?.status ?? '') && <div className="ct-phone-alert">No booking was made. A travel advisor needs to review this case.</div>}
           {caseId && <p className="ct-phone-case">Case {caseId.slice(0, 8)} · Saved backend case</p>}
          </>}
        </div>}
      </div>
      <nav className="ct-phone-tabs" aria-label="Traveler pages"><button className={tab === 'EXPLORE' ? 'active' : ''} onClick={() => setTab('EXPLORE')}><span aria-hidden="true">✧</span>Explore</button>
        <button className={tab === 'TRIPS' || tab === 'TRIP' ? 'active' : ''} onClick={() => setTab('TRIPS')}><span aria-hidden="true">▣</span>My trips</button>
        <button className={tab === 'GUIDE' ? 'active' : ''} onClick={() => setTab('GUIDE')} disabled={!caseId}><span aria-hidden="true">✦</span>AI Guide</button>
        <button className={tab === 'HELP' ? 'active' : ''} onClick={() => setTab('HELP')}><span aria-hidden="true">?</span>Help</button></nav>
      <div className="ct-phone-home-indicator" />
    </div></div><p className="ct-phone-caption">A simple companion view inside the same React app.</p>
  </aside>;
}
