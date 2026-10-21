import type { MouseEvent } from 'react';
import { useI18n } from '../i18n';
import type { AppRoute } from '../routes';
import type { CaseSnapshot, User } from '../types';

interface Props {
  route: AppRoute | null; user: User | null | undefined; caseId: string; snapshot: CaseSnapshot | null;
  link: (path: AppRoute) => string; navigate: (event: MouseEvent<HTMLAnchorElement>, path: AppRoute) => void;
  signOut: () => void;
}

function modelLabel(t: (text: string, vars?: Record<string, string>) => string, caseId: string, snapshot: CaseSnapshot | null) {
  if (!caseId) return t('No case selected');
  if (!snapshot) return t('Case data pending');
  const data = snapshot.caseData;
  if (data.model_mode !== 'api') return t('Mock model');
  const key = data.model_status === 'SUCCEEDED' ? '{provider} used' : data.model_status === 'FAILED' ? '{provider} failed' : '{provider} pending';
  return t(key, { provider: data.llm_provider || 'Live' });
}

export default function TopBar({ route, user, caseId, snapshot, link, navigate, signOut }: Props) {
  const { t, lang, setLang, largeText, setLargeText } = useI18n();
  const pages: [AppRoute, string][] = [['/', 'Home'], ['/dashboard', 'Dashboard'], ['/mobile', 'Mobile'], ['/demo', 'Demo']];
  if (user?.is_advisor) pages.push(['/advisor', 'Advisor']);
  if (user) pages.push(['/account', 'Account']);
  return <header className="ct-topbar">
    <a href={link('/')} onClick={event => navigate(event, '/')} className="ct-logo" aria-label={t("CareTrip home")}>C<span>✦</span></a>
    <div className="ct-brand"><strong>{t("CareTrip")} <em>{t("Ops")}</em></strong><span>{t("NEW ZEALAND · TRAVEL WITH CONFIDENCE")}</span></div>
    <nav className="ct-route-nav" aria-label={t("Main navigation")}>
      {pages.map(([path, label]) => <a key={path} href={link(path)} onClick={event => navigate(event, path)}
        aria-current={route === path ? 'page' : undefined}>{t(label)}</a>)}
    </nav>
    <div className="ct-header-right">
      {user && <span className="ct-account" title={user.email}>{user.display_name || user.email}</span>}
      {user && <button type="button" className="ct-save-case" onClick={signOut}>{t("Sign out")}</button>}
      {user && <span className="ct-mode">{modelLabel(t, caseId, snapshot)}</span>}
      <div className="ct-prefs" role="group" aria-label={t('Display preferences')}>
        {/* A toggle keeps one label; aria-pressed carries the on/off state. */}
        <button type="button" className="ct-pref" aria-pressed={largeText} onClick={() => setLargeText(!largeText)}>{t('Larger text')}</button>
        <button type="button" className="ct-pref" lang={lang === 'zh' ? 'en' : 'zh-Hans'} onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
          aria-label={lang === 'zh' ? 'Switch to English' : '切换到中文'}>{lang === 'zh' ? 'English' : '中文'}</button>
      </div>
      <span className="ct-disclosure">{t("Synthetic offers · Simulated booking")}</span>
    </div>
  </header>;
}
