import { useEffect, useState } from 'react';
import { roleRank } from '../types';
import type { CaseSnapshot, CaseSummary, Invitation, MemberRole, Order } from '../types';
import TravelPhoto from './TravelPhoto';
import { matchTravelImage, travelImages } from '../data/travelImages';
import GuidePanel from './GuidePanel';
import HelpPanel from './HelpPanel';
import FamilyPanel, { roleLabel } from './FamilyPanel';
import DestinationCard from './phone/DestinationCard';
import TripsTab from './phone/TripsTab';
import BookingPanel from './BookingPanel';
import { useI18n } from '../i18n';
import { fieldLabel, friendlyStatus, sampleTripRequest } from '../labels';

interface Props {
  caseId: string; snapshot: CaseSnapshot | null; mutating: boolean; error: string;
  role: MemberRole | null;
  trips: CaseSummary[]; tripListError: boolean; tripListLoading: boolean; openCase: (id: string) => void;
  invitations: Invitation[]; answerInvitation: (invitation: Invitation, accept: boolean) => void;
  request: string; demoDate: string; setRequest: (value: string) => void;
  setDemoDate: (value: string) => void; createCase: (requestOverride?: string) => void; useSample: () => void;
  startVoicePlan: () => void;
  voiceAvailable: boolean | null;
  clarify: (answers: Record<string, string>) => void;
  decide: (decision: 'APPROVE' | 'REJECT') => void;
  cancelOrder: (order: Order) => void;
}

const destinationNames = Array.from(new Set(travelImages.map(image => image.destination).filter((name): name is string => Boolean(name))));
const mobileThemes: Record<string, string[]> = {
  'Relaxing Getaways': ['Queenstown', 'Rotorua', 'Christchurch'],
  'Scenic Journeys': ['Auckland', 'Queenstown', 'Wellington', 'Taupō'],
  'Nature & Gardens': ['Rotorua', 'Christchurch', 'Taupō'],
  'Accessible Experiences': ['Auckland', 'Christchurch'],
  'Family Holidays': ['Queenstown', 'Taupō'],
  'Cultural Discovery': ['Auckland', 'Rotorua', 'Wellington'],
};

export default function PhoneSimulator(props: Props) {
  const { caseId, snapshot, mutating, decide } = props;
  const { t, lang } = useI18n();
  const [tab, setTab] = useState<'EXPLORE' | 'TRIPS' | 'TRIP' | 'GUIDE' | 'HELP'>('EXPLORE');
  const [planningNew, setPlanningNew] = useState(false);
  const [mobileTheme, setMobileTheme] = useState('All journeys');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  useEffect(() => { if (caseId) { setTab(new URLSearchParams(location.search).get('voice') === '1' ? 'GUIDE' : 'TRIP'); setPlanningNew(false); setAnswers({}); } }, [caseId]);
  const current = snapshot?.caseData;
  const requirements = current?.requirements;
  const approval = snapshot?.approval;
  const verified = snapshot?.offers.find(offer => offer.label === 'VERIFIED' && offer.verdict === 'PASS' && offer.id === approval?.offer_id);
  const destination = requirements?.destination;
  const attraction = requirements?.attractions?.[0];
  const photo = matchTravelImage(destination, attraction);
  const canPlan = props.role !== null && roleRank[props.role] >= roleRank.CO_PLANNER;

  return <aside className="ct-phone-column"><div className="ct-phone-label"><span>{t("THE TRAVELER'S VIEW")}</span><small>{t("Same case · same trusted facts")}</small></div>
    <div className="ct-phone-frame"><div className="ct-phone-island"/><div className="ct-phone-screen">
      <header className="ct-phone-header"><div className="ct-phone-mark">C<span>✦</span></div><strong>{t("CareTrip")} <em>{t("Companion")}</em></strong><span className="ct-phone-avatar" aria-hidden="true">✦</span></header>
      <div className="ct-phone-scroll">
        {props.error && <div className="ct-phone-alert" role="alert">{props.error}</div>}
        {tab === 'EXPLORE' && !caseId ? <div className="ct-phone-home">
          <TravelPhoto image={matchTravelImage(null)} className="ct-phone-home-photo" eager caption />
          <p className="ct-phone-kicker">{t("A JOURNEY MADE FOR YOU")}</p><h2>{t("Where would you like to go?")}</h2>
          <p className="ct-phone-lead">{t("Tell us your idea. We will help with the details.")}</p>
          <label htmlFor="phone-request">{t("Your travel idea")}</label>
          <textarea id="phone-request" value={props.request} onChange={event => props.setRequest(event.target.value)} rows={4}
            placeholder={t("I would like to visit Auckland with two friends for three days…")} />
          <button type="button" className="ct-phone-example" onClick={props.useSample}>{t("Try the Auckland example")}</button>
          <label htmlFor="phone-date">{t("When would you like to leave?")}</label>
          <input id="phone-date" type="date" value={props.demoDate} onChange={event => props.setDemoDate(event.target.value)} />
          <button className="ct-phone-primary" disabled={mutating || props.request.trim().length < 8 || !props.demoDate} onClick={() => props.createCase()}>{mutating ? t("Planning your trip…") : t("Plan my trip")} <span aria-hidden="true">→</span></button>
          <button type="button" className="ct-phone-outline" disabled={mutating || props.voiceAvailable !== true} onClick={props.startVoicePlan}>{props.voiceAvailable === null ? t("Checking voice availability…") : props.voiceAvailable ? t("Start with voice →") : t("Live voice unavailable")}</button>
          {caseId && <button className="ct-my-trip-link" onClick={() => setTab('TRIP')}>{t("View my current trip")} <span aria-hidden="true">→</span></button>}
          <p className="ct-phone-footnote">{t("New Zealand demo · Live voice depends on Gemini availability · No payment")}</p>
          <h3>{t("Or explore a destination")}</h3>
          {destinationNames.map(name => <DestinationCard key={name} name={name} mutating={mutating} plan={() => props.createCase(sampleTripRequest(name, lang))} />)}
        </div> : tab === 'EXPLORE' ? <div className="ct-phone-explore">
          <p className="ct-phone-kicker">{t("EXPLORE NEW ZEALAND")}</p><h2>{t("Find your next view.")}</h2>
          <p className="ct-phone-lead">{t("Local destination ideas, each with synthetic sample stays.")}</p>
          <button type="button" className="ct-phone-primary" onClick={() => { props.setRequest(''); setPlanningNew(true); setTab('TRIP'); }}>{t("Plan a new trip →")}</button>
          <div className="ct-phone-themes" role="group" aria-label={t("Filter travel themes")}>
            {['All journeys', ...Object.keys(mobileThemes)].map(theme => <button key={theme} type="button" aria-pressed={mobileTheme === theme} onClick={() => setMobileTheme(theme)}>{t(theme)}</button>)}
          </div>
          {destinationNames.filter(name => mobileTheme === 'All journeys' || mobileThemes[mobileTheme]?.includes(name)).map(name => <DestinationCard key={name} name={name} mutating={mutating} plan={() => props.createCase(sampleTripRequest(name, lang))} />)}
        </div> : tab === 'TRIPS' ? <TripsTab trips={props.trips} invitations={props.invitations} loading={props.tripListLoading} failed={props.tripListError}
          mutating={mutating} answerInvitation={props.answerInvitation} openTrip={id => { props.openCase(id); setTab('TRIP'); }} showTrip={() => setTab('TRIP')}
          planNew={() => { setPlanningNew(true); setTab('TRIP'); }} />
         : tab === 'GUIDE' ? <GuidePanel caseId={caseId} canPlan={canPlan} liveVersion={snapshot?.events.length ?? 0} /> : tab === 'HELP' ? <HelpPanel caseId={caseId} startTrip={() => { setPlanningNew(true); setTab('TRIP'); }} />
         : <div className="ct-phone-trip">
          {(!caseId || planningNew) && <div className="ct-phone-home ct-trip-create"><h3>{t("Tell us your travel idea")}</h3><label htmlFor="phone-request">{t("Your travel idea")}</label>
            <textarea id="phone-request" value={props.request} onChange={event => props.setRequest(event.target.value)} rows={4} placeholder={t("I would like to visit Auckland with two friends for three days…")} />
            <button type="button" className="ct-phone-example" onClick={props.useSample}>{t("Try the Auckland example")}</button>
            <label htmlFor="phone-date">{t("Departure date")}</label><input id="phone-date" type="date" value={props.demoDate} onChange={event => props.setDemoDate(event.target.value)} />
            <button className="ct-phone-primary" disabled={mutating || props.request.trim().length < 8 || !props.demoDate} onClick={() => props.createCase()}>{mutating ? t("Planning…") : t("Plan my trip →")}</button></div>}
          {!planningNew && <>
          <p className="ct-phone-kicker">{t("YOUR TRIP")}</p><h2>{destination ? t("Let's explore {place}", { place: t(destination) }) : t("Your trip is taking shape")}</h2>
          <p className="ct-phone-lead">{t(friendlyStatus(current?.status, current?.run_state))}</p>
          <TravelPhoto image={photo} className="ct-phone-trip-photo" eager caption />
          <div className="ct-phone-trip-facts"><div><span>{t("TRAVELERS")}</span><strong>{requirements?.traveler_count ?? '—'}</strong></div>
            <div><span>{t("TIME AWAY")}</span><strong>{requirements?.duration_days ? t('{n} days', { n: requirements.duration_days }) : '—'}</strong></div>
            <div><span>{t("PACE")}</span><strong>{requirements?.travel_pace === 'RELAXED' ? t("Gentle") : t("Easy to follow")}</strong></div></div>
          {current?.itinerary_source === 'PENDING' && <div className="ct-phone-message" role="status">{t("Gemini Planner and Reviewer are preparing your daily outline…")}</div>}
          {Boolean(current?.draft_itinerary?.length) && <section className="ct-phone-days" aria-label={t("Illustrative daily trip outline")}>
            <p className="ct-phone-kicker">{t("A FIRST LOOK AT YOUR DAYS")}</p>
            <h3>{t("Your gentle trip outline")}</h3>
            <p className="ct-phone-draft-note">{current?.itinerary_source === 'GEMINI_REVIEWED' ? t("Gemini Planner and Reviewer checked this illustrative outline.") : current?.itinerary_source === 'GEMINI_FAILED' ? t("Gemini planning was unavailable. This is a local illustrative outline.") : t("This is a local illustrative outline.")} {t('Version {n}. Visits and travel details still need confirmation.', { n: current?.itinerary_version || 1 })} {approval?.status === 'APPROVED' ? t("This outline is separate from the approved stay and booking; later changes are not booked or verified.") : ''}</p>
            {current?.draft_itinerary?.map(day => <article className="ct-phone-day" key={day.day_number}>
              <TravelPhoto image={matchTravelImage(destination, day.attraction)} className="ct-phone-day-photo" caption />
              <div className="ct-phone-day-copy"><span>{t('DAY {n} · ILLUSTRATIVE · {intensity} INTENSITY', { n: day.day_number, intensity: t(day.intensity || 'LOW') })}</span><strong>{day.title}</strong><p>{day.note}</p>
                {Boolean(day.activities?.length) && <ol>{day.activities?.map((activity, index) => <li key={`${index}-${activity}`}>{activity}</li>)}</ol>}
                <p><b>{t("Rest:")}</b> {day.rest_note || t("Leave time to rest.")}</p>
                {day.verification_notes?.map(note => <small key={note}>{t("To check:")} {note}</small>)}
              </div>
            </article>)}
          </section>}
          {!snapshot && caseId && !props.error && <div className="ct-phone-message" role="status">{t("Loading your trip details…")}</div>}
          {snapshot && !verified && <div className="ct-phone-message"><div className="ct-phone-message-icon">✦</div><strong>{current?.status === 'HUMAN_REVIEW' ? t("We need to take a closer look") : current?.status === 'AWAITING_REVIEW' ? t('An advisor is checking accessibility details for you') : t("We are checking your options")}</strong>
            <p>{requirements?.destination_scope === 'OUTSIDE_NZ' ? t("This demonstration currently supports travel within New Zealand only.") : current?.status === 'NEEDS_CLARIFICATION' ? t("Please add the details below to continue.") : current?.status === 'HUMAN_REVIEW' && !snapshot.offers.length ? t('No synthetic package is available for {place} yet. Your outline is illustrative only.', { place: destination ? t(destination) : t('this trip') }) : t("We will show a plan here after the sample checks are complete.")}</p></div>}
          {current?.status === 'NEEDS_CLARIFICATION' && !canPlan && <div className="ct-phone-message">{t("The traveler or a planning helper needs to add a few details.")}</div>}
          {current?.status === 'NEEDS_CLARIFICATION' && canPlan && <section className="ct-phone-clarify" aria-label={t("Complete travel details")}>
            <h3>{t("A few more details")}</h3>
            {current.missing_fields.map(field => <label key={field} htmlFor={`phone-${field}`}>{t(fieldLabel(field))}
              <input id={`phone-${field}`} type={field === 'departure_date' ? 'date' : ['traveler_count', 'duration_days', 'budget'].includes(field) ? 'number' : 'text'}
                min={['traveler_count', 'duration_days', 'budget'].includes(field) ? '1' : undefined}
                value={answers[field] ?? ''} onChange={event => setAnswers({ ...answers, [field]: event.target.value })}
                placeholder={field === 'currency' ? t("NZD") : undefined} /></label>)}
            <button className="ct-phone-primary" disabled={mutating || current.missing_fields.some(field => !answers[field]?.trim())}
              onClick={() => props.clarify(Object.fromEntries(current.missing_fields.map(field => [field, answers[field]])))}>
              {mutating ? t("Saving details…") : t("Continue planning")}
            </button>
          </section>}
          {snapshot && <BookingPanel snapshot={snapshot} role={props.role} mutating={mutating} destination={destination}
            travelers={requirements?.traveler_count} days={requirements?.duration_days} decide={decide} cancelOrder={props.cancelOrder} />}
          {current?.status === 'RECOVERY_REQUIRED' && current.run_state !== 'idle' && <div className="ct-phone-message" role="status">{t("We are picking up where your trip left off…")}</div>}
          {(current?.status === 'FAILED' || (current?.status === 'RECOVERY_REQUIRED' && current.run_state === 'idle')) && <div className="ct-phone-alert">{t("Planning paused. A travel advisor or planning helper can resume it. Any booking already confirmed stays as it is.")}</div>}
          {caseId && snapshot && <FamilyPanel caseId={caseId} />}
          {caseId && <p className="ct-phone-case">{t('Case {id}', { id: caseId.slice(0, 8) })}{props.role ? t(' · You: {role}', { role: t(roleLabel[props.role]) }) : ''}</p>}
          </>}
        </div>}
      </div>
      <nav className="ct-phone-tabs" aria-label={t("Traveler pages")}><button className={tab === 'EXPLORE' ? 'active' : ''} onClick={() => setTab('EXPLORE')}><span aria-hidden="true">✧</span>{t("Explore")}</button>
        <button className={tab === 'TRIPS' || tab === 'TRIP' ? 'active' : ''} onClick={() => setTab('TRIPS')}><span aria-hidden="true">▣</span>{t("My trips")}</button>
        <button className={tab === 'GUIDE' ? 'active' : ''} onClick={() => setTab('GUIDE')} disabled={!caseId}><span aria-hidden="true">✦</span>{t("AI Guide")}</button>
        <button className={tab === 'HELP' ? 'active' : ''} onClick={() => setTab('HELP')}><span aria-hidden="true">?</span>{t("Help")}</button></nav>
      <div className="ct-phone-home-indicator" />
    </div></div><p className="ct-phone-caption">{t("A simple companion view inside the same React app.")}</p>
  </aside>;
}
