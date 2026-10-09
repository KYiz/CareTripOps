import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { GuideContext, GuideReply } from '../types';
import TravelPhoto from './TravelPhoto';
import { matchTravelImage } from '../data/travelImages';
import { useLiveGuide } from './useLiveGuide';

interface Props { caseId: string }
export default function GuidePanel({ caseId }: Props) {
  const [context, setContext] = useState<GuideContext | null>(null);
  const [draft, setDraft] = useState('');
  const [revisionRequest, setRevisionRequest] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [state, setState] = useState<'Idle' | 'Thinking'>('Idle');
  const refresh = useCallback(async () => {
    if (!caseId) return;
    try { setContext(await api.guide(caseId)); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Guide context is unavailable'); }
  }, [caseId]);
  const voice = useLiveGuide(caseId, refresh);

  useEffect(() => { void refresh(); }, [refresh]);

  async function chooseAttraction(attraction: string) {
    if (busy) return;
    setBusy(true);
    try { setContext(await api.selectAttraction(caseId, attraction)); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not select this place'); }
    finally { setBusy(false); }
  }

  async function ask(value = draft) {
    const message = value.trim();
    if (busy || message.length < 2) return;
    setDraft(''); setBusy(true); setState('Thinking');
    try {
      const reply: GuideReply = await api.guideMessage(caseId, message);
      setRevisionRequest(reply.intent === 'REVISION' ? message : '');
      await refresh(); setError('');
    } catch (cause) { await refresh(); setError(cause instanceof Error ? cause.message : 'The guide could not answer'); }
    finally { setBusy(false); setState('Idle'); }
  }

  async function revise() {
    if (!revisionRequest || busy) return;
    setBusy(true); setState('Thinking');
    try {
      setContext(await api.requestRevision(caseId, revisionRequest));
      setRevisionRequest(''); setError('');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'A revised draft could not be prepared'); }
    finally { setBusy(false); setState('Idle'); }
  }

  async function decideProposal(accept: boolean) {
    if (!context?.proposal || busy) return;
    setBusy(true);
    try { setContext(await api.decideRevision(caseId, context.proposal.id, accept)); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'The decision could not be saved'); }
    finally { setBusy(false); }
  }

  if (!caseId) return <div className="ct-guide-empty"><h2>Meet your travel companion</h2><p>Plan a trip first. Your guide will then use the same trip details to help you explore.</p></div>;
  const selectedIndex = context?.days.findIndex(day => day.attraction === context.selected_attraction) ?? -1;
  const next = context?.days.slice(selectedIndex + 1).find(day => day.attraction);
  const displayState = voice.state !== 'Idle' ? voice.state : state;
  return <div className="ct-guide">
    <div className="ct-guide-hero"><div className={`ct-guide-avatar ${displayState.toLowerCase()}`} aria-label={`Guide status: ${displayState}`}>
      <div className="ct-guide-hair"/><div className="ct-guide-face"><i/><i/><b/></div><div className="ct-guide-scarf"/>
    </div><div><p className="ct-phone-kicker">YOUR AI TRAVEL COMPANION</p><h2>Explore at your own pace.</h2><span className="ct-guide-status">● {displayState} · {voice.state === 'Idle' ? 'Text guide' : 'Gemini Live'}</span></div></div>
    <p className="ct-guide-disclosure">Text answers use simple case rules. Live voice uses Gemini when available. Places and timing are illustrative until checked by a travel advisor.</p>
    {error && <div className="ct-phone-alert" role="alert">{error}</div>}
    {voice.error && <div className="ct-phone-alert" role="alert">{voice.error}</div>}
    {!voice.available && <div className="ct-phone-message">Voice is unavailable right now. You can continue this trip by typing below.</div>}
    {Boolean(context?.missing_fields.length) && <div className="ct-phone-message"><strong>Tell me a little more</strong><p>You can speak or type the missing details: {context?.missing_fields.join(', ')}. I will remember what you have already shared.</p></div>}
    {voice.available && <div className="ct-guide-voice"><div><strong>Speak with your guide</strong><small>Audio goes to Gemini while connected. CareTrip does not store the recording; a requested revision is saved as text. Stop at any time.</small></div>
      {voice.state === 'Idle' || voice.state === 'Disconnected' ? <button type="button" onClick={() => void voice.start()}>{voice.state === 'Disconnected' ? 'Retry voice' : 'Start voice'}</button>
        : <button type="button" onClick={voice.stop}>Stop voice</button>}
      {voice.transcript && <p aria-live="polite">{voice.transcript}</p>}</div>}
    {context?.destination && <section className="ct-guide-place"><TravelPhoto image={matchTravelImage(context.destination, context.selected_attraction)} caption />
      <div><small>SELECTED PLACE · MANUAL MODE</small><h3>{context.selected_attraction ?? context.destination}</h3>
        <p>{next ? `Next idea: ${next.attraction}` : 'No further stop is listed.'}</p><span>Trip status: {context.case_status.replaceAll('_', ' ').toLowerCase()} · Take a rest whenever you need one.</span></div></section>}
    <section className="ct-journey-map" aria-label="Illustrative journey map"><div className="ct-guide-heading"><h3>Your journey</h3><small>Version {context?.itinerary_version || 1} · {context?.itinerary_source === 'PENDING' ? 'Gemini planning in progress' : context?.itinerary_source === 'GEMINI_REVIEWED' ? 'Gemini reviewed' : context?.itinerary_source === 'GEMINI_FAILED' ? 'Gemini unavailable; local outline' : 'Local outline'} · No GPS tracking</small></div>
      {context?.days.length ? context.days.map(day => <div className="ct-journey-stop" key={day.day_number}>
        <span className={day.attraction === context.selected_attraction ? 'selected' : ''}>{day.day_number}</span>
        <div><small>DAY {day.day_number} · {day.intensity || 'LOW'} INTENSITY</small><strong>{day.title}</strong><p>{day.note}</p>
          {Boolean(day.activities?.length) && <ol>{day.activities?.map((activity, index) => <li key={`${index}-${activity}`}>{activity}</li>)}</ol>}
          <p>Rest: {day.rest_note || 'Leave time to rest.'}</p>
          {day.verification_notes?.map(note => <small key={note}>To check: {note}</small>)}
          {day.attraction && <button type="button" onClick={() => chooseAttraction(day.attraction!)} disabled={busy || day.attraction === context.selected_attraction}>{day.attraction === context.selected_attraction ? 'Current selection' : `Explore ${day.attraction}`}</button>}
        </div></div>) : <p className="ct-guide-disclosure">Your daily outline will appear after the trip details are ready.</p>}
    </section>
    <section className="ct-guide-chat" aria-label="Ask the travel guide"><div className="ct-guide-heading"><h3>Ask me anything</h3><small>About this trip</small></div>
      <div className="ct-guide-messages" aria-live="polite"><div className="ct-guide-bubble guide">Hello! I can explain your selected place, suggest the next stop, or prepare a gentler draft.</div>
        {context?.conversation.map((item, index) => <div className={`ct-guide-bubble ${item.role === 'traveler' ? 'you' : 'guide'}`} key={`${item.created_at}-${index}`}>{item.text}</div>)}</div>
      <div className="ct-guide-quick">{['Tell me about this place', 'What is next?', 'I am tired. Make this gentler.'].map(question =>
        <button type="button" key={question} onClick={() => void ask(question)} disabled={busy}>{question}</button>)}</div>
      <form onSubmit={event => { event.preventDefault(); void ask(); }}><label htmlFor="guide-question">Your question</label>
        <div><input id="guide-question" value={draft} onChange={event => setDraft(event.target.value)} placeholder="Ask about your trip…" maxLength={1000} /><button type="submit" disabled={busy || draft.trim().length < 2}>Send</button></div></form>
      {revisionRequest && <button type="button" className="ct-guide-revise" onClick={() => void revise()} disabled={busy}>Prepare a gentler draft →</button>}
    </section>
    {context?.proposal && <section className="ct-guide-proposal"><small>ILLUSTRATIVE ITINERARY REVISION · {context.proposal.status}</small>
      <h3>A gentler draft for your review</h3><p>This changes the illustrative outline only. It is not verified or included in any approved package or simulated order. The offer, approval and price stay unchanged.</p>
      {context.proposal.model_trace && <details><summary>See planner and reviewer work</summary>
        <p>Planner initial draft ({context.proposal.model_trace.planner_model})</p>
        {context.proposal.model_trace.planner_initial.map(day => <div key={day.day_number}>Day {day.day_number}: {day.title} — {day.note}</div>)}
        <p>Reviewer feedback ({context.proposal.model_trace.reviewer_model})</p>
        <ul>{context.proposal.model_trace.reviewer_feedback.concerns.map(item => <li key={item}>{item}</li>)}</ul>
        <p>{context.proposal.model_trace.reviewer_feedback.recommendation}</p>
        <p>{context.proposal.model_trace.revision_applied ? 'Planner revised the draft once after review.' : 'Reviewer found no change needed; the initial draft is shown below.'}</p>
      </details>}
      {context.proposal.days.map(day => <div key={day.day_number}><strong>Day {day.day_number}: {day.title}</strong><span>{day.note}</span>
        {Boolean(day.activities?.length) && <ol>{day.activities?.map((activity, index) => <li key={`${index}-${activity}`}>{activity}</li>)}</ol>}
        <span>Rest: {day.rest_note || 'Leave time to rest.'}</span></div>)}
      {context.proposal.status === 'PENDING' && <div className="ct-guide-decision"><button disabled={busy} onClick={() => void decideProposal(true)}>Use this outline</button><button disabled={busy} onClick={() => void decideProposal(false)}>Keep my current outline</button></div>}
    </section>}
  </div>;
}
