// Warns where ja.json doesn't match en.json: an entry missing or extra, or a {placeholder} that
// differs. The page shows the English for anything missing, so this never fails the build.
import { readFileSync } from 'node:fs';

const read = (name) => JSON.parse(readFileSync(new URL(`../src/i18n/${name}.json`, import.meta.url), 'utf8'));
const en = read('en');
const ja = read('ja');
const problems = [];
const holes = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',');

function compare(source, translated, where) {
  if (where === '_comment') return;
  if (translated === undefined) return problems.push(`${where}: missing in ja.json`);
  if (Array.isArray(source)) {
    if (!Array.isArray(translated) || translated.length !== source.length) return problems.push(`${where}: a list of ${source.length} in en.json`);
    return source.forEach((item, i) => compare(item, translated[i], `${where}[${i}]`));
  }
  if (source && typeof source === 'object') {
    for (const key of Object.keys(source)) compare(source[key], translated[key], where ? `${where}.${key}` : key);
    for (const key of Object.keys(translated)) if (!(key in source)) problems.push(`${where ? `${where}.` : ''}${key}: in ja.json only`);
    return;
  }
  if (holes(source) !== holes(String(translated))) problems.push(`${where}: placeholders {${holes(source)}} in en.json, {${holes(String(translated))}} in ja.json`);
}

compare(en, ja, '');
if (problems.length) {
  console.warn(`ja.json differs from en.json in ${problems.length} place(s); those show in English:`);
  for (const problem of problems) console.warn(`  ${problem}`);
}
