// The website's languages: English (en.json, the source) and Japanese (ja.json, translated from it).
import en from './en.json';
import ja from './ja.json';

export type Lang = 'en' | 'ja';
export type Strings = typeof en;

// An entry missing from a translation shows in English, so a new English string never breaks the build.
function withFallback(source: any, translated: any): any {
  if (translated === undefined) return source;
  if (Array.isArray(source)) {
    return Array.isArray(translated) && translated.length === source.length
      ? source.map((item, i) => withFallback(item, translated[i]))
      : source;
  }
  if (source && typeof source === 'object') {
    return Object.fromEntries(Object.entries(source).map(([key, value]) => [key, withFallback(value, translated[key])]));
  }
  return typeof translated === typeof source ? translated : source;
}

const catalogs: Record<Lang, Strings> = { en, ja: withFallback(en, ja) };

export function strings(lang: Lang): Strings {
  return catalogs[lang];
}

/** `template` with each {name} replaced by values[name]. */
export function fill(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (match, key) => (key in values ? values[key] : match));
}

const base = import.meta.env.BASE_URL.replace(/\/$/, '');

/** A page's link in `lang`: /install, or /ja/install. */
export function localePath(lang: Lang, path: string): string {
  if (lang === 'en') return `${base}${path}`;
  return `${base}/ja${path === '/' ? '/' : path}`;
}
