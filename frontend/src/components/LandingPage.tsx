import { useRef, useState } from 'react';
import TravelPhoto from './TravelPhoto';
import { matchTravelImage } from '../data/travelImages';
import type { AppRoute } from '../routes';
import { useI18n } from '../i18n';
import { sampleTripRequest } from '../labels';

interface Props {
  caseId: string; link: (path: AppRoute) => string;
  request: string; setRequest: (value: string) => void;
  demoDate: string; setDemoDate: (value: string) => void;
  createCase: (requestOverride?: string) => void; mutating: boolean;
}

const destinations = [
  { name: 'Auckland', description: 'Harbour views and an easy city escape.', styles: ['Scenic Journeys', 'Cultural Discovery', 'Accessible Experiences'] },
  { name: 'Queenstown', description: 'Lakeside scenery and gentle mountain views.', styles: ['Relaxing Getaways', 'Scenic Journeys', 'Family Holidays'] },
  { name: 'Rotorua', description: 'Geothermal landscapes and quiet lake moments.', styles: ['Relaxing Getaways', 'Nature & Gardens', 'Cultural Discovery'] },
  { name: 'Wellington', description: 'Harbour walks, museums and local culture.', styles: ['Scenic Journeys', 'Cultural Discovery'] },
  { name: 'Christchurch', description: 'Gardens, heritage and an unhurried pace.', styles: ['Nature & Gardens', 'Relaxing Getaways', 'Accessible Experiences'] },
  { name: 'Taupō', description: 'Open lake views and a refreshing nature break.', styles: ['Scenic Journeys', 'Nature & Gardens', 'Family Holidays'] },
] as const;

const travelStyles = ['All journeys', 'Relaxing Getaways', 'Scenic Journeys', 'Nature & Gardens',
  'Cultural Discovery', 'Family Holidays', 'Accessible Experiences'] as const;

const experiences = [
  { title: 'Queenstown Scenic Gondola', destination: 'Queenstown', attraction: 'Skyline Queenstown' },
  { title: 'Rotorua Geothermal Colours', destination: 'Rotorua', attraction: 'Wai-O-Tapu' },
  { title: 'Lake Taupō Views', destination: 'Taupō', attraction: 'Lake Taupō' },
  { title: 'Auckland Harbour', destination: 'Auckland', attraction: 'Auckland Harbour' },
] as const;

export default function LandingPage(props: Props) {
  const { t, lang } = useI18n();
  const [style, setStyle] = useState<string>('All journeys');
  const requestRef = useRef<HTMLTextAreaElement>(null);
  const shown = destinations.filter(destination => style === 'All journeys' || destination.styles.some(item => item === style));

  function prepareIdea(destination: string, attraction?: string) {
    props.setRequest(lang === 'zh'
      ? `我想和两位朋友去${destination}玩三天，总预算 1000 纽币，希望节奏轻松${attraction ? `，想去看看${attraction}` : ''}。`
      : `I would like to visit ${destination} for three days with two friends. Our total budget is NZD 1000. We prefer a relaxed pace${attraction ? ` and would enjoy ${attraction}` : ''}.`);
    document.getElementById('trip-planner')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    requestRef.current?.focus();
  }

  return <main className="ct-landing">
    <section className="ct-landing-hero" id="trip-planner">
      <TravelPhoto image={matchTravelImage('Queenstown', 'Lake Wakatipu')} eager caption />
      <div className="ct-landing-shade" />
      <div className="ct-landing-copy"><p className="ct-kicker">{t("CARETRIP · NEW ZEALAND")}</p>
        <h1>{t("Your next wonderful")}<br/><em>{t("journey starts here.")}</em></h1>
        <p>{t("Tell us your dream trip. We'll help plan the rest.")}</p>
        <div className="ct-landing-planner"><label htmlFor="landing-request">{t("Where would you like to go? Tell us what you enjoy.")}</label>
          <textarea ref={requestRef} id="landing-request" value={props.request} onChange={event => props.setRequest(event.target.value)} rows={3}
            placeholder={t("I would like to visit Auckland with two friends for three days. Our total budget is NZD 1000.")} />
          <div className="ct-landing-planner-row"><label htmlFor="landing-date">{t("Departure date")}<input id="landing-date" type="date" value={props.demoDate} onChange={event => props.setDemoDate(event.target.value)} /></label>
            <button type="button" onClick={() => props.createCase()} disabled={props.mutating || props.request.trim().length < 8 || !props.demoDate}>
              {props.mutating ? t("Planning your trip…") : t("Plan My Trip")} <span aria-hidden="true">→</span></button></div>
        </div>
        <small>{t("New Zealand demo · Synthetic offers · No payment")}</small>
      </div>
    </section>

    <section className="ct-landing-section" id="travel-styles"><div className="ct-landing-section-heading"><div><p className="ct-kicker">{t("EXPLORE BY TRAVEL STYLE")}</p><h2>{t("Find a journey that feels right.")}</h2></div><p>{t("Choose a style to narrow the destinations below.")}</p></div>
      <div className="ct-style-filters" role="group" aria-label={t("Filter destinations by travel style")}>{travelStyles.map(item =>
        <button key={item} type="button" aria-pressed={style === item} onClick={() => setStyle(item)}>{t(item)}</button>)}</div>
    </section>

    <section className="ct-landing-section" id="destinations"><div className="ct-landing-section-heading"><div><p className="ct-kicker">{t("POPULAR DESTINATIONS")}</p><h2>{t("New Zealand, at your pace.")}</h2></div><p>{t('{n} destinations · Each has synthetic sample stays with checked access details.', { n: shown.length })}</p></div>
      <div className="ct-destination-grid">{shown.map(destination => <article key={destination.name} className="ct-destination-card">
        <TravelPhoto image={matchTravelImage(destination.name)} caption />
        <div className="ct-destination-copy"><p className="ct-kicker">{t("NEW ZEALAND")}</p><h3>{t(destination.name)}</h3><p>{t(destination.description)}</p>
          <div className="ct-destination-tags">{destination.styles.slice(0, 2).map(item => <span key={item}>{t(item)}</span>)}</div>
          <small>{t("Synthetic package demo available")}</small>
          <button type="button" disabled={props.mutating} onClick={() => props.createCase(sampleTripRequest(destination.name, lang))}>{t("Plan This Trip")} <span aria-hidden="true">↗</span></button></div>
      </article>)}</div>
    </section>

    <section className="ct-landing-section" id="experiences"><div className="ct-landing-section-heading"><div><p className="ct-kicker">{t("FEATURED EXPERIENCES")}</p><h2>{t("Ideas for your next chapter.")}</h2></div><p>{t("Illustrative inspiration only. Visits, availability and prices are not verified.")}</p></div>
      <div className="ct-experience-grid">{experiences.map(experience => <article key={experience.title} className="ct-experience-card">
        <TravelPhoto image={matchTravelImage(experience.destination, experience.attraction)} caption />
        <div><small>{t("ILLUSTRATIVE IDEA")}</small><h3>{t(experience.title)}</h3><button type="button" onClick={() => prepareIdea(experience.destination, experience.attraction)}>{t("Add to my idea →")}</button></div>
      </article>)}</div>
    </section>

    <section className="ct-companion-feature" id="companion"><div className="ct-companion-image"><TravelPhoto image={matchTravelImage('Rotorua', 'Wai-O-Tapu')} caption /></div>
      <div className="ct-companion-copy"><p className="ct-kicker">{t("MORE THAN A TRIP PLAN")}</p><h2>{t("A companion for the journey.")}</h2>
        <p>{t("Before you leave, CareTrip helps shape and check a trip. During the journey, the guide can use your saved outline to answer questions and suggest a gentler day.")}</p>
        <div className="ct-companion-steps"><span>01 <strong>{t("Plan together")}</strong><small>{t("Describe the trip in your own words.")}</small></span>
          <span>02 <strong>{t("Choose with confidence")}</strong><small>{t("Review a checked sample offer before approving.")}</small></span>
          <span>03 <strong>{t("Explore at your pace")}</strong><small>{t("Ask the guide about your selected stop.")}</small></span></div>
        <a href={props.link('/mobile')}>{t("Meet your travel companion →")}</a>
        <small>{t("Guide text mode uses case facts. Live voice requires separate configuration and verification.")}</small>
      </div></section>

    <section className="ct-partners"><div><p className="ct-kicker">{t("A FUTURE TRAVEL NETWORK")}</p><h2>{t("Thoughtfully chosen experiences.")}</h2><p>{t("We are exploring ways to connect trusted travel providers with people who value a gentler journey.")}</p></div>
      <div className="ct-partners-card"><span>{t("SPONSORED · DEMO CONCEPT")}</span><strong>{t("Local stays & scenic days")}</strong><p>{t("Illustrative partner placement. No commercial partnership, inventory or booking is implied.")}</p></div></section>

    <section className="ct-landing-entries" id="my-trips"><div><p className="ct-kicker">{t("YOUR TRIP, YOUR CHOICE")}</p><h2>{t("One journey, two clear views.")}</h2><p>{t("Both views read the same case and the same backend records.")}</p></div>
      <div className="ct-entry-grid"><a href={props.link('/mobile')}><strong>{props.caseId ? t("Continue my trip") : t("Traveler companion")}</strong><span>{t("Plan, understand the sample offer and decide.")}</span><b aria-hidden="true">↗</b></a>
        <a href={props.link('/dashboard')}><strong>{t("Operations dashboard")}</strong><span>{t("Review cases, evidence, decisions and audit events.")}</span><b aria-hidden="true">↗</b></a>
        <a href={props.link('/demo')}><strong>{t("Side-by-side demo")}</strong><span>{t("Follow both views of the same case together.")}</span><b aria-hidden="true">↗</b></a></div>
      {props.caseId && <p className="ct-landing-current">{t('Current case: {id}', { id: props.caseId.slice(0, 8) })}</p>}
    </section>
    <section className="ct-landing-help" id="help"><h2>{t("Need a hand?")}</h2><p>{t("Start with your travel idea. If a detail is missing, CareTrip will ask you to add it. A sample booking only follows your approval of a verified offer.")}</p><a href={props.link('/mobile')}>{t("Open the traveler view →")}</a></section>
    <p className="ct-landing-disclaimer">{t("ZEIL Hackathon 2026 — Project · Synthetic supplier data · Simulated booking only")}</p>
  </main>;
}
