import { useEffect, useState } from 'react';
import { fallbackImage, type TravelImage } from '../data/travelImages';
import { useI18n } from '../i18n';

interface Props { image: TravelImage; className?: string; eager?: boolean; caption?: boolean }

export default function TravelPhoto({ image, className = '', eager = false, caption = false }: Props) {
  const { t } = useI18n();
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [fallbackFailed, setFallbackFailed] = useState(false);
  useEffect(() => { setLoaded(false); setFailed(false); setFallbackFailed(false); }, [image.image_url]);
  const shown = failed ? fallbackImage : image;
  return <figure className={`travel-photo ${className} ${loaded ? 'is-loaded' : 'is-loading'}`}>
    <img src={shown.image_url} alt={shown.alt_text} loading={eager ? 'eager' : 'lazy'}
      onLoad={() => setLoaded(true)} onError={() => { if (!failed) { setFailed(true); setLoaded(false); } else setFallbackFailed(true); }} />
    {fallbackFailed && <span className="photo-unavailable">{t("Photo unavailable")}</span>}
    {caption && <figcaption>{shown.illustrative || failed ? t("Illustrative New Zealand photo") : t(shown.attraction ?? shown.destination ?? '')}
      <small>{t("Photo:")} {shown.attribution} · {shown.license} · <a href={shown.source_url} target="_blank" rel="noreferrer">{t("Source")}</a></small></figcaption>}
  </figure>;
}
