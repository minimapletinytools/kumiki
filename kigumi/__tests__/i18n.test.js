const { SUPPORTED_LOCALES, DEFAULT_LOCALE, resolveLocale, loadCatalog, createTranslator } = require('../i18n');
const en = require('../i18n/locales/en.json');
const ja = require('../i18n/locales/ja.json');

describe('resolveLocale', () => {
  test('picks a supported locale from an exact match', () => {
    expect(resolveLocale('ja')).toBe('ja');
  });

  test('normalizes a region-qualified tag down to its base language', () => {
    expect(resolveLocale('ja-JP')).toBe('ja');
    expect(resolveLocale('en-US')).toBe('en');
  });

  test('falls back to the default locale for unsupported/missing languages', () => {
    expect(resolveLocale('fr')).toBe(DEFAULT_LOCALE);
    expect(resolveLocale(undefined)).toBe(DEFAULT_LOCALE);
    expect(resolveLocale(null)).toBe(DEFAULT_LOCALE);
  });
});

describe('catalogs', () => {
  test('en and ja ship with the exact same key set', () => {
    const enKeys = Object.keys(en).sort();
    const jaKeys = Object.keys(ja).sort();
    expect(jaKeys).toEqual(enKeys);
  });

  test('loadCatalog reads the same content as requiring the json directly', () => {
    expect(loadCatalog('en')).toEqual(en);
    expect(loadCatalog('ja')).toEqual(ja);
  });

  test('SUPPORTED_LOCALES matches the locale files that actually exist', () => {
    expect(SUPPORTED_LOCALES.sort()).toEqual(['en', 'ja']);
  });
});

describe('createTranslator', () => {
  test('translates a plain key for the requested locale', () => {
    const t = createTranslator('ja');
    expect(t('viewer.options.theme.label')).toBe(ja['viewer.options.theme.label']);
  });

  test('interpolates {param} placeholders', () => {
    const t = createTranslator('en');
    expect(t('sidebar.frames', { count: 3 })).toBe('Frames (3)');
  });

  test('falls back to the English string for a locale-specific gap', () => {
    const t = createTranslator('ja');
    // Every key currently exists in both catalogs, so simulate a gap directly.
    expect(t('this.key.does.not.exist')).toBe('this.key.does.not.exist');
  });

  test('unsupported requested locale falls back to English strings', () => {
    const t = createTranslator('fr');
    expect(t('viewer.options.theme.label')).toBe(en['viewer.options.theme.label']);
  });
});

describe('every measurement kind has a name a person would use', () => {
  // The kind dropdown labels each entry with `viewer.measure.kind.<name>`, and
  // a missing key falls through as the key itself -- so a kind nobody
  // translated shows the reader a code reference. The SOLID kinds arrived
  // without entries and did exactly that.
  const Measurements = require('../webview/measurements.js');

  /** Every kind name the rules can hand the dropdown, in both spaces. */
  function everyKind() {
    const geometries = [
      { kind: 'point' },
      { kind: 'line', direction: [1, 0, 0] },
      { kind: 'line', direction: [0, 1, 0] },
      { kind: 'plane', normal: [0, 0, 1] },
      { kind: 'plane', normal: [1, 0, 0] },
      { kind: 'plane', normal: [0, 0, -1] },
    ];
    const look = [0, 0, -1];
    const names = new Set();
    for (const one of geometries) {
      for (const other of geometries) {
        for (const name of Measurements.availableKinds(
          Measurements.projectedForm(one, look), Measurements.projectedForm(other, look))) {
          names.add(name);
        }
        for (const name of Measurements.solidKinds(
          Measurements.solidForm(one), Measurements.solidForm(other))) {
          names.add(name);
        }
      }
    }
    return [...names];
  }

  const kinds = everyKind();

  test('the rules produce kinds to check, in both spaces', () => {
    expect(kinds).toEqual(expect.arrayContaining([
      'projected_perpendicular_distance', 'projected_angle',
      'perpendicular_distance', 'angle',
    ]));
  });

  test.each(kinds)('en names %s', (kind) => {
    expect(typeof en[`viewer.measure.kind.${kind}`]).toBe('string');
  });

  test.each(kinds)('ja names %s', (kind) => {
    expect(typeof ja[`viewer.measure.kind.${kind}`]).toBe('string');
  });

  test('and none of those names is the code name', () => {
    for (const kind of kinds) {
      expect(en[`viewer.measure.kind.${kind}`]).not.toContain('_');
    }
  });
});
