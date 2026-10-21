import { useI18n } from '../../i18n';
import { CLAIM_LABELS } from '../../labels';
import type { CaseSnapshot } from '../../types';

const readable = (value: string) => value.replaceAll('_', ' ').toLowerCase();

/** One verdict per offer and access claim, with the sources behind it. */
export default function VerificationSection({ snapshot }: { snapshot: CaseSnapshot | null }) {
  const { t } = useI18n();
  const assessments = snapshot?.evidence.assessments ?? [];
  const names = new Map(snapshot?.offers.map(offer => [offer.id, offer.name ?? offer.product_id]));
  return <div className="ct-detail-card">
    <p className="ct-muted">{t("Evidence below comes from the synthetic supplier catalog, not an external provider.")}</p>
    {!assessments.length ? <p className="ct-muted">{t("No evidence has been assessed yet.")}</p> : assessments.map(item =>
      <details key={`${item.offer_id}-${item.claim_type}`} className="ct-assessment">
        <summary><strong>{names.get(item.offer_id) ?? item.product_id}</strong> · {t(CLAIM_LABELS[item.claim_type] ?? readable(item.claim_type))}
          <span className={`ct-offer-tag ct-${item.verdict.toLowerCase()}`}>{item.verdict}</span></summary>
        <p>{readable(item.reason_code)}</p>
        {snapshot?.evidence.sources.filter(source => source.offer_id === item.offer_id && source.claim_type === item.claim_type)
          .map(source => <p key={source.reference}><b>{source.polarity}</b> · {source.detail} <small>{source.reference}</small></p>)}
      </details>)}
  </div>;
}
