import { useState } from 'react';
import type { CaseSnapshot, MemberRole, Offer, Order } from '../types';
import { useI18n } from '../i18n';
import { FACTOR_REASONS, FAILURE_REASONS, policyLines } from '../labels';

interface Props {
  snapshot: CaseSnapshot; role: MemberRole | null; mutating: boolean;
  destination: string | null | undefined; travelers: number | null | undefined; days: number | null | undefined;
  decide: (decision: 'APPROVE' | 'REJECT') => void;
  cancelOrder: (order: Order) => void;
}

function Feature({ ok, label }: { ok: boolean | null | undefined; label: string }) {
  const { t } = useI18n();
  return <li className={`ct-feature ${ok ? 'is-yes' : ok === false ? 'is-no' : 'is-unknown'}`}>
    <span aria-hidden="true">{ok ? '✓' : ok === false ? '✕' : '?'}</span>
    {t(label)} <small>· {t(ok ? 'Yes' : ok === false ? 'No' : 'Not confirmed')}</small></li>;
}

/** Plain reasons from the ranking, strongest first. */
function reasons(offer: Offer): string[] {
  const factors = offer.ranking?.factors ?? [];
  const out: string[] = [];
  for (const factor of factors) {
    if (factor.factor === 'accessibility' && (FACTOR_REASONS[factor.code] || factor.value >= 1)) out.push(FACTOR_REASONS[factor.code] ?? 'Meets all your access needs');
    if (factor.factor === 'meals' && factor.value >= 1) out.push('Meals suit your diet');
    if (factor.factor === 'pace' && FACTOR_REASONS[factor.code] && factor.value >= 1) out.push(FACTOR_REASONS[factor.code]);
    if (factor.factor === 'flexibility' && factor.value >= 1) out.push('Generous free-cancellation terms');
    if (factor.factor === 'rating' && factor.value >= 0.9) out.push('Highly rated by guests');
  }
  return out;
}

export default function BookingPanel({ snapshot, role, mutating, destination, travelers, days, decide, cancelOrder }: Props) {
  const { t, formatDate } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const status = snapshot.caseData.status;
  const approval = snapshot.approval;
  const offer = snapshot.offers.find(item => item.id === approval?.offer_id && item.verdict === 'PASS');
  const order = [...snapshot.orders].reverse().find(item => item.approval_id === approval?.approval_id);
  const owner = role === 'OWNER';
  if (!offer) return null;
  const awaitingDecision = approval?.status === 'PENDING' && status === 'AWAITING_APPROVAL';

  return <>
    <div className="ct-phone-plan">
      <p className="ct-phone-kicker">{t('RECOMMENDED STAY')}</p>
      <h3>{offer.name ?? offer.product_id}</h3>
      <p className="ct-phone-plan-copy">{t(destination ?? '')} · {t('{n} days', { n: days ?? '' })} · {t('{n} travelers', { n: travelers ?? '' })}</p>
      <ul className="ct-features" aria-label={t('Access at this stay')}>
        <Feature ok={offer.attributes.lift_all_floors} label="Lift to every guest floor" />
        <Feature ok={offer.attributes.step_free_entry} label="Step-free entrance" />
        {offer.claims.accessible_bathroom && <Feature ok={offer.attributes.accessible_bathroom} label="Accessible bathroom" />}
        <Feature ok={offer.attributes.walking_level === 'LOW'} label="Little walking needed" />
        {offer.attributes.accessible_transfer && <Feature ok label="Accessible airport transfer" />}
      </ul>
      {reasons(offer).length > 0 && <div className="ct-why"><strong>{t('Why we recommend it')}</strong>
        <ul>{reasons(offer).map(reason => <li key={reason}>{t(reason)}</li>)}</ul></div>}
      <div className="ct-phone-includes">{offer.includes.map(item => <div key={item}><span aria-hidden="true">✓</span>{t(item)}</div>)}</div>
      <div className="ct-policy"><strong>{t('If plans change')}</strong>
        <ul>{policyLines(offer.cancellation_policy).map(line => <li key={line.key}>{t(line.key, line.vars)}</li>)}</ul></div>
      <div className="ct-phone-total"><span>{t('TOTAL FOR THE GROUP')}</span><strong>{offer.currency} {offer.total_amount}</strong></div>
      <p className="ct-phone-validity">{t('Price held until {date}', { date: formatDate(offer.expires_at) })}</p>
    </div>

    {awaitingDecision && !owner && <div className="ct-phone-message">{t('This plan is waiting for the traveler’s decision. Only the traveler can approve it.')}</div>}
    {awaitingDecision && owner && !confirming && <div className="ct-phone-actions"><p>{t('You decide what happens next. Nothing is booked or charged until you approve.')}</p>
      <button className="ct-phone-primary" disabled={mutating} onClick={() => setConfirming(true)}>{t('Review and approve')} <span aria-hidden="true">→</span></button>
      <button className="ct-phone-outline" disabled={mutating} onClick={() => decide('REJECT')}>{t('Decline this plan')}</button></div>}
    {awaitingDecision && owner && confirming && <div className="ct-phone-confirm"><p className="ct-phone-kicker">{t('FINAL CHECK')}</p>
      <h3>{t('Book this stay?')}</h3>
      <p>{offer.name} · {t('Total {amount}', { amount: `${offer.currency} ${offer.total_amount}` })}</p>
      <p>{t('We will hold the room, then ask for payment. Your card is only charged once the hotel confirms.')}</p>
      <button className="ct-phone-primary" disabled={mutating} onClick={() => { setConfirming(false); decide('APPROVE'); }}>
        {mutating ? t('Submitting…') : t('Approve {amount}', { amount: `${offer.currency} ${offer.total_amount}` })}</button>
      <button className="ct-phone-outline" disabled={mutating} onClick={() => setConfirming(false)}>{t('Go back')}</button></div>}

    {(status === 'APPROVED' || status === 'BOOKING') && order?.status !== 'FAILED' &&
      <div className="ct-phone-message" role="status">{t('Holding your room and confirming with the hotel…')}</div>}

    {status === 'AWAITING_PAYMENT' && order?.status === 'PENDING_PAYMENT' && <div className="ct-phone-confirm">
      <p className="ct-phone-kicker">{t('PAYMENT')}</p><h3>{t('Your room is held for you')}</h3>
      <p>{t('Your card is only charged after the hotel confirms. If anything fails, the hold on your card is released.')}</p>
      {owner && order.payment?.checkout_url
        ? <a className="ct-phone-primary ct-pay-link" href={order.payment.checkout_url}>{t('Pay securely with Stripe')} <span aria-hidden="true">→</span></a>
        : <p>{t('Waiting for the traveler to complete payment.')}</p>}
    </div>}

    {order?.status === 'CONFIRMED' && <div className="ct-phone-complete"><div className="ct-phone-check" aria-hidden="true">✓</div>
      <h3>{t('Your trip is booked')}</h3>
      <p>{t('Booking reference {ref}', { ref: order.supplier_booking_ref ?? '' })}</p>
      <strong>{order.currency} {order.total_amount}</strong>
      {order.payment?.provider === 'simulated' && <p className="ct-simulated">{t('Demo payment: no card was charged.')}</p>}
      {order.cancellation_quote && <p>{t('If you cancel today you get {amount} back ({percent}%).', {
        amount: `${order.currency} ${order.cancellation_quote.refund_amount}`, percent: order.cancellation_quote.refund_percent })}</p>}
      <a className="ct-phone-primary ct-pay-link" href={`/trip-card?caseId=${encodeURIComponent(order.case_id)}`}>{t('Open my large-print trip card')}</a>
      {owner && !cancelling && <button className="ct-phone-outline" disabled={mutating} onClick={() => setCancelling(true)}>{t('Cancel this booking')}</button>}
      {owner && cancelling && <div className="ct-cancel-confirm" role="alertdialog" aria-label={t('Cancel this booking?')}>
        <p><strong>{t('Cancel this booking?')}</strong></p>
        <p>{t('The hotel will be told straight away. Refund: {amount}.', { amount: `${order.currency} ${order.cancellation_quote?.refund_amount ?? '0.00'}` })}</p>
        <button className="ct-phone-primary ct-danger" disabled={mutating} onClick={() => { setCancelling(false); cancelOrder(order); }}>{t('Yes, cancel the booking')}</button>
        <button className="ct-phone-outline" disabled={mutating} onClick={() => setCancelling(false)}>{t('Keep my booking')}</button>
      </div>}
    </div>}

    {order?.status === 'CANCELLATION_REQUESTED' && <div className="ct-phone-message" role="status">{t('Cancelling with the hotel…')}</div>}
    {order?.status === 'CANCELLED' && <div className="ct-phone-message"><strong>{t('Booking cancelled')}</strong>
      <p>{t('Refund: {amount}. It usually reaches your card within 5–10 days.', { amount: `${order.currency} ${order.refund_amount ?? '0.00'}` })}</p></div>}
    {order?.status === 'FAILED' && <div className="ct-phone-alert"><strong>{t('We could not complete this booking')}</strong>
      <p>{t(FAILURE_REASONS[order.failure_reason ?? ''] ?? 'Something went wrong with the booking.')}</p>
      <p>{t('No money was taken. Any hold on your card has been released. A travel advisor will contact you.')}</p></div>}
    {status === 'REJECTED' && <div className="ct-phone-message">{t('You declined this plan. No order was created.')}</div>}
  </>;
}
