import { useState } from 'react';
import { useI18n } from '../i18n';
import AdvisorHelp from './AdvisorHelp';
import AdvisorReviews from './AdvisorReviews';
import AdvisorTrips from './AdvisorTrips';

type Tab = 'HELP' | 'REVIEWS' | 'TRIPS';

/** The advisor's workspace: urgent help first, then evidence reviews, then every trip. */
export default function AdvisorConsole() {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>('HELP');
  const [helpCount, setHelpCount] = useState(0);
  const tabs: [Tab, string][] = [['HELP', helpCount ? t('Help requests ({n})', { n: helpCount }) : t('Help requests')],
    ['REVIEWS', t('Evidence reviews')], ['TRIPS', t('Trips')]];
  return <main className="ct-advisor-page">
    <p className="ct-kicker">{t('TRAVEL ADVISOR')}</p>
    <h1>{t('Advisor console')}</h1>
    <div className="ct-advisor-tabs" role="group" aria-label={t('Advisor console sections')}>
      {tabs.map(([key, label]) => <button key={key} type="button" aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</button>)}
    </div>
    {/* Help stays mounted so its count keeps updating while another section is open. */}
    <div hidden={tab !== 'HELP'}><AdvisorHelp onCount={setHelpCount} /></div>
    {tab === 'REVIEWS' && <AdvisorReviews />}
    {tab === 'TRIPS' && <AdvisorTrips />}
  </main>;
}
