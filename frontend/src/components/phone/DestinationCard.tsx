import { matchTravelImage } from '../../data/travelImages';
import { useI18n } from '../../i18n';
import TravelPhoto from '../TravelPhoto';

/** One destination with a one-tap sample trip. */
export default function DestinationCard({ name, mutating, plan }: { name: string; mutating: boolean; plan: () => void }) {
  const { t } = useI18n();
  return <article className="ct-phone-explore-card">
    <TravelPhoto image={matchTravelImage(name)} caption />
    <div><strong>{t(name)}</strong><small>{t("Synthetic package demo")}</small>
      <button type="button" disabled={mutating} onClick={plan}>{mutating ? t("Planning…") : t("Plan this trip →")}</button></div>
  </article>;
}
