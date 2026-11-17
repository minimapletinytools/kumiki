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

/**
 * `key`'s string with its {link} a link to `href`, reading `linkKey`'s string; and its {link2}, if
 * given, a link to `href2`, reading `linkKey2`'s.
 */
export function withLink(key, linkKey, href, linkKey2 = null, href2 = null) {
    const links = { link: [linkKey, href], ...(linkKey2 ? { link2: [linkKey2, href2] } : {}) };
    const fragment = document.createDocumentFragment();
    for (const part of t(key).split(/(\{link2?\})/)) {
        const name = part.slice(1, -1);
        if (part.startsWith('{') && links[name]) {
            const [label, url] = links[name];
            fragment.append(Object.assign(document.createElement('a'), { href: url, target: '_blank', rel: 'noopener noreferrer', textContent: t(label) }));
        } else if (part) {
            fragment.append(part);
        }
    }
    return fragment;
}

/**
 * Every element with data-i18n="key" (and data-i18n-title, data-i18n-placeholder) in its language. One
 * with data-i18n-link="linkKey" and data-href gets its {link} as a link (withLink), and with
 * data-i18n-link2 and data-href2 its {link2} too.
 */
export function translatePage(root = document) {
    for (const element of root.querySelectorAll('[data-i18n]')) {
        if (element.dataset.i18nLink) {
            element.replaceChildren(withLink(element.dataset.i18n, element.dataset.i18nLink, element.dataset.href,
                element.dataset.i18nLink2 || null, element.dataset.href2 || null));
        }
        else element.textContent = t(element.dataset.i18n);
    }
    for (const element of root.querySelectorAll('[data-i18n-title]')) element.title = t(element.dataset.i18nTitle);
    for (const element of root.querySelectorAll('[data-i18n-placeholder]')) element.placeholder = t(element.dataset.i18nPlaceholder);
}

/** A message the session wrote: in the panel's language when it gives a key we have, else as it wrote it. */
export function textOf(key, params, fallback) {
    return key && typeof strings[key] === 'string' ? t(key, params) : fallback;
}
