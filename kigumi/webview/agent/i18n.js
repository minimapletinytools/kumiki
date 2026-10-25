// The agent panel's strings: looked up in the catalog the session sends with its state (the app's
// locale, English behind it; i18n/locales/*.json, the agent.* keys).
let strings = {};

/** Use `catalog` from now on. */
export function setStrings(catalog) {
    if (catalog && typeof catalog === 'object') strings = catalog;
}

/** The string for `key`, with {name} filled in from `params`; the key itself if there is none. */
export function t(key, params) {
    const template = typeof strings[key] === 'string' ? strings[key] : key;
    return params ? template.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match)) : template;
}

/** Every element with data-i18n="key" (and data-i18n-title, data-i18n-placeholder) in its language. */
export function translatePage(root = document) {
    for (const element of root.querySelectorAll('[data-i18n]')) element.textContent = t(element.dataset.i18n);
    for (const element of root.querySelectorAll('[data-i18n-title]')) element.title = t(element.dataset.i18nTitle);
    for (const element of root.querySelectorAll('[data-i18n-placeholder]')) element.placeholder = t(element.dataset.i18nPlaceholder);
}

/** A message the session wrote: in the panel's language when it gives a key we have, else as it wrote it. */
export function textOf(key, params, fallback) {
    return key && typeof strings[key] === 'string' ? t(key, params) : fallback;
}
