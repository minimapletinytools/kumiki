// Node-side i18n: resolves the active locale and loads the matching flat, dotted
// key -> string catalog from ./locales. The extension follows VS Code's display
// language (vscode.env.language); the app and the browser version follow the
// system's, unless their app.language setting names one.
const fs = require('fs');
const path = require('path');

const SUPPORTED_LOCALES = ['en', 'ja'];
const DEFAULT_LOCALE = 'en';
const LOCALES_DIR = path.join(__dirname, 'locales');

const catalogCache = new Map();

function loadCatalog(locale) {
    if (catalogCache.has(locale)) {
        return catalogCache.get(locale);
    }
    let catalog = {};
    try {
        catalog = JSON.parse(fs.readFileSync(path.join(LOCALES_DIR, `${locale}.json`), 'utf8'));
    } catch (_error) {
        catalog = {};
    }
    catalogCache.set(locale, catalog);
    return catalog;
}

// Normalizes a BCP-47-ish tag (e.g. "ja-JP", "en-US", "PT-br") down to one of
// our supported locales, or null if nothing matches.
function normalizeLocale(candidate) {
    if (typeof candidate !== 'string' || !candidate) {
        return null;
    }
    const lower = candidate.toLowerCase();
    if (SUPPORTED_LOCALES.includes(lower)) {
        return lower;
    }
    const base = lower.split('-')[0];
    return SUPPORTED_LOCALES.includes(base) ? base : null;
}

// vscodeLanguage is expected to be vscode.env.language (or undefined/null).
function resolveLocale(vscodeLanguage) {
    return normalizeLocale(vscodeLanguage) || DEFAULT_LOCALE;
}

// The app.language setting's choices (the standalone app and the browser version).
const LANGUAGE_SETTING = 'app.language';
const LANGUAGE_CHOICES = [
    { id: 'default', label: 'Default (system language)' },
    { id: 'en', label: 'English' },
    { id: 'ja', label: '日本語' },
];

// The language to use: the setting's, else (at 'default') the system's.
function chooseLanguage(setting, systemLanguage) {
    return normalizeLocale(setting) || systemLanguage;
}

function interpolate(template, params) {
    if (!params) {
        return template;
    }
    return template.replace(/\{(\w+)\}/g, (match, key) => (
        Object.prototype.hasOwnProperty.call(params, key) ? String(params[key]) : match
    ));
}

// Returns a t(key, params) bound to the given VS Code display language,
// falling back to the English string (then the raw key) for anything
// missing from a non-English catalog.
function createTranslator(vscodeLanguage) {
    const locale = resolveLocale(vscodeLanguage);
    const catalog = loadCatalog(locale);
    const fallbackCatalog = locale === DEFAULT_LOCALE ? catalog : loadCatalog(DEFAULT_LOCALE);
    return function t(key, params) {
        const template = Object.prototype.hasOwnProperty.call(catalog, key)
            ? catalog[key]
            : fallbackCatalog[key];
        if (typeof template !== 'string') {
            return key;
        }
        return interpolate(template, params);
    };
}

module.exports = {
    SUPPORTED_LOCALES,
    DEFAULT_LOCALE,
    normalizeLocale,
    resolveLocale,
    loadCatalog,
    createTranslator,
    LANGUAGE_SETTING,
    LANGUAGE_CHOICES,
    chooseLanguage,
};
