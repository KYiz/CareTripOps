import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Citation, GuideContext, GuideReply } from '../types';
import TravelPhoto from './TravelPhoto';
import { matchTravelImage } from '../data/travelImages';
import { useLiveGuide } from './useLiveGuide';
import { useI18n } from '../i18n';
import JourneyMap from './guide/JourneyMap';
import ProposalReview from './guide/ProposalReview';
import { fieldLabel, statusLabel } from '../labels';

interface Props { caseId: string; canPlan: boolean; liveVersion: number }
export default function GuidePanel({ caseId, canPlan, liveVersion }: Props) {
  const { t } = useI18n();
  const [context, setContext] = useState<GuideContext | null>(null);
  const [draft, setDraft] = useState('');
  const [revisionRequest, setRevisionRequest] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [state, setState] = useState<'Idle' | 'Thinking'>('Idle');
  // Sources for the latest answer: official place pages, or the evidence behind verified access features.
  const [citations, setCitations] = useState<Citation[]>([]);
  const refresh = useCallback(async () => {
    if (!caseId) return;
    try { setContext(await api.guide(caseId)); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('Guide context is unavailable')); }
  }, [caseId]);
  const voice = useLiveGuide(caseId, refresh);

  // liveVersion grows with the Case audit trail, so turns saved by other family members appear here too.
  useEffect(() => { void refresh(); }, [refresh, liveVersion]);

  async function chooseAttraction(attraction: string) {
    if (busy) return;
    setBusy(true);
    try { setContext(await api.selectAttraction(caseId, attraction)); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('Could not select this place')); }
    finally { setBusy(false); }
  }

  async function ask(value = draft) {
    const message = value.trim();
    if (busy || message.length < 2) return;
    setDraft(''); setBusy(true); setState('Thinking');
    try {
      const reply: GuideReply = await api.guideMessage(caseId, message);
      setRevisionRequest(reply.intent === 'REVISION' ? message : '');
      setCitations(reply.citations);
      await refresh(); setError('');
    } catch (cause) { await refresh(); setError(cause instanceof Error ? cause.message : t('The guide could not answer')); }
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
    catch (cause) { setError(cause instanceof Error ? cause.message : t('The decision could not be saved')); }
    finally { setBusy(false); }
  }

  if (!caseId) return <div className="ct-guide-empty"><h2>{t("Meet your travel companion")}</h2><p>{t("Plan a trip first. Your guide will then use the same trip details to help you explore.")}</p></div>;
  const selectedIndex = context?.days.findIndex(day => day.attraction === context.selected_attraction) ?? -1;
  const next = context?.days.slice(selectedIndex + 1).find(day => day.attraction);
  const displayState = voice.state !== 'Idle' ? voice.state : state;
  return <div className="ct-guide">
    <div className="ct-guide-hero"><div className={`ct-guide-avatar ${displayState.toLowerCase()}`} role="img" aria-label={t('Guide status: {state}', { state: t(displayState) })}>
      <div className="ct-guide-hair"/><div className="ct-guide-face"><i/><i/><b/></div><div className="ct-guide-scarf"/>
    </div><div><p className="ct-phone-kicker">{t("YOUR AI TRAVEL COMPANION")}</p><h2>{t("Explore at your own pace.")}</h2><span className="ct-guide-status">● {t(displayState)} · {voice.state === 'Idle' ? t("Text guide") : t("Gemini Live")}</span></div></div>
    <p className="ct-guide-disclosure">{t("Text answers use simple case rules. Live voice uses Gemini when available. Places and timing are illustrative until checked by a travel advisor.")}</p>
    {error && <div className="ct-phone-alert" role="alert">{error}</div>}
    {voice.error && <div className="ct-phone-alert" role="alert">{voice.error}</div>}
    {!canPlan && <div className="ct-phone-message">{t("You can follow this trip. Asking the guide and changing the outline are for the traveler and planning helpers.")}</div>}
    {canPlan && !voice.available && <div className="ct-phone-message">{t("Voice is unavailable right now. You can continue this trip by typing below.")}</div>}
    {Boolean(context?.missing_fields.length) && <div className="ct-phone-message"><strong>{t("Tell me a little more")}</strong><p>{t('You can speak or type the missing details: {fields}. I will remember what you have already shared.', { fields: (context?.missing_fields ?? []).map(field => t(fieldLabel(field))).join(t(', ')) })}</p></div>}
    {canPlan && voice.available && <div className="ct-guide-voice"><div><strong>{t("Speak with your guide")}</strong><small>{t("Audio goes to Gemini while connected. CareTrip does not store the recording; a requested revision is saved as text. Stop at any time.")}</small></div>
      {voice.state === 'Idle' || voice.state === 'Disconnected' ? <button type="button" onClick={() => void voice.start()}>{voice.state === 'Disconnected' ? t("Retry voice") : t("Start voice")}</button>
        : <button type="button" onClick={voice.stop}>{t("Stop voice")}</button>}
      {voice.transcript && <p aria-live="polite">{voice.transcript}</p>}</div>}
    {context?.destination && <section className="ct-guide-place"><TravelPhoto image={matchTravelImage(context.destination, context.selected_attraction)} caption />
      <div><small>{t("SELECTED PLACE · MANUAL MODE")}</small><h3>{t(context.selected_attraction ?? context.destination)}</h3>
        <p>{next ? t('Next idea: {place}', { place: t(next.attraction ?? '') }) : t("No further stop is listed.")}</p><span>{t('Trip status: {status} · Take a rest whenever you need one.', { status: t(statusLabel(context.case_status)) })}</span></div></section>}
    <JourneyMap caseId={caseId} context={context} canPlan={canPlan} busy={busy} chooseAttraction={place => void chooseAttraction(place)} onEdited={() => void refresh()} />
    <section className="ct-guide-chat" aria-label={t("Ask the travel guide")}><div className="ct-guide-heading"><h3>{t("Ask me anything")}</h3><small>{t("About this trip")}</small></div>
      <div className="ct-guide-messages" role="log" aria-live="polite" aria-label={t("Conversation with the guide")} tabIndex={0}><div className="ct-guide-bubble guide">{t("Hello! I can explain your selected place, suggest the next stop, or prepare a gentler draft.")}</div>
        {context?.conversation.map((item, index) => <div className={`ct-guide-bubble ${item.role === 'traveler' ? 'you' : 'guide'}`} key={`${item.created_at}-${index}`}>{item.text}</div>)}</div>
      {citations.length > 0 && <div className="ct-guide-sources"><strong>{t('Sources for this answer')}</strong>
        <ul>{citations.map(item => <li key={item.title}>{item.kind === 'EVIDENCE' ? t('Evidence') : t('Official page')}: {item.url
          ? <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a> : item.title}</li>)}</ul></div>}
      {canPlan && <><div className="ct-guide-quick">{[t('Tell me about this place'), t('What is next?'), t('Is my stay step-free?'), t('I am tired. Make this gentler.')].map(question =>
        <button type="button" key={question} onClick={() => void ask(question)} disabled={busy}>{question}</button>)}</div>
      <form onSubmit={event => { event.preventDefault(); void ask(); }}><label htmlFor="guide-question">{t("Your question")}</label>
        <div><input id="guide-question" value={draft} onChange={event => setDraft(event.target.value)} placeholder={t("Ask about your trip…")} maxLength={1000} /><button type="submit" disabled={busy || draft.trim().length < 2}>{t("Send")}</button></div></form>
      {revisionRequest && <button type="button" className="ct-guide-revise" onClick={() => void revise()} disabled={busy}>{t("Prepare a gentler draft →")}</button>}</>}
    </section>
    {context?.proposal && <ProposalReview proposal={context.proposal} canPlan={canPlan} busy={busy} decide={accept => void decideProposal(accept)} />}
  </div>;
}
