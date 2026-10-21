import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { setCurrentLanguage, translate, type Lang, type Vars } from './language.ts';

export type { Lang } from './language.ts';
// Only an explicit choice is stored. The old key also held auto-detected values, so it is ignored and cleared.
const LANG_CHOICE_KEY = 'caretrip:lang-choice';
const LEGACY_LANG_KEY = 'caretrip:lang';
const TEXT_SIZE_KEY = 'caretrip:large-text';

function stored(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

function store(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* Preference simply is not remembered. */ }
}

/** English unless the visitor chose Chinese with the language switch (remembered in this browser). */
function initialLang(): Lang {
  try { localStorage.removeItem(LEGACY_LANG_KEY); } catch { /* Nothing to clear. */ }
  return stored(LANG_CHOICE_KEY) === 'zh' ? 'zh' : 'en';
}

interface I18n {
  lang: Lang; setLang: (lang: Lang) => void; t: (text: string, vars?: Vars) => string;
  largeText: boolean; setLargeText: (on: boolean) => void;
  formatDate: (value: string | Date) => string;
}

const I18nContext = createContext<I18n>({
  lang: 'en', setLang: () => {}, t: text => text, largeText: false, setLargeText: () => {},
  formatDate: value => new Date(value).toLocaleDateString(),
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const [largeText, setLargeText] = useState(() => stored(TEXT_SIZE_KEY) === 'true');
  setCurrentLanguage(lang);

  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-Hans' : 'en';
  }, [lang]);
  useEffect(() => {
    document.documentElement.classList.toggle('ct-large-text', largeText);
    store(TEXT_SIZE_KEY, String(largeText));
  }, [largeText]);

  const value = useMemo<I18n>(() => ({
    lang, largeText, setLargeText,
    setLang: next => { store(LANG_CHOICE_KEY, next); setLangState(next); },
    t: (text, vars) => translate(lang, text, vars),
    formatDate: input => new Date(input).toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-NZ',
      { year: 'numeric', month: 'long', day: 'numeric' }),
  }), [lang, largeText]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export const useI18n = () => useContext(I18nContext);
