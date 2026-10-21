import { zh } from './locales/zh.ts';

export type Lang = 'en' | 'zh';
export type Vars = Record<string, string | number>;

/** English source text is the key; Chinese comes from the dictionary and falls back to English. */
export function translate(lang: Lang, text: string, vars?: Vars): string {
  const template = lang === 'zh' ? zh[text] ?? text : text;
  return vars ? template.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? '')) : template;
}

// Held outside React so the API client can send Accept-Language.
let activeLang: Lang = 'en';
export const currentLanguage = (): Lang => activeLang;
export function setCurrentLanguage(lang: Lang) { activeLang = lang; }
