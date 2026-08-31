const { DisplayOptionsStore } = require('../webview/display-options-store.js');

const THEME_IDS = ['cream', 'forest', 'slate-night'];

function store() {
    return new DisplayOptionsStore({ themeIds: THEME_IDS });
}

describe('taking a value', () => {
    test('a change is reported so callers can skip the work of applying it', () => {
        const options = store();
        expect(options.set('shadowsEnabled', true)).toBe(true);
        expect(options.set('shadowsEnabled', true)).toBe(false);
        expect(options.get('shadowsEnabled')).toBe(true);
    });

    test('an unknown option is ignored rather than invented', () => {
        expect(store().set('nonsense', 1)).toBe(false);
    });
});

describe('normalizing, which differs per option', () => {
    test('a percent snaps to its step and clamps to its range', () => {
        const options = store();
        options.set('unselectedTransparencyPercent', 73);
        expect(options.get('unselectedTransparencyPercent')).toBe(75);
        options.set('unselectedTransparencyPercent', 1000);
        expect(options.get('unselectedTransparencyPercent')).toBe(95);
    });

    test('a percent given nonsense falls back to its default', () => {
        const options = store();
        options.set('unselectedTransparencyPercent', 40);
        options.set('unselectedTransparencyPercent', NaN);
        expect(options.get('unselectedTransparencyPercent')).toBe(70);
    });

    test('edge thickness clamps rather than snapping', () => {
        const options = store();
        options.set('edgeLineThicknessPx', 12);
        expect(options.get('edgeLineThicknessPx')).toBe(6);
        options.set('edgeLineThicknessPx', 0.1);
        expect(options.get('edgeLineThicknessPx')).toBe(0.5);
    });

    test('an unknown edge mode falls back to the default', () => {
        const options = store();
        options.set('edgeMode', 'invented');
        expect(options.get('edgeMode')).toBe('noOverlay');
    });

    test('an unknown theme is ignored, not replaced', () => {
        // setTheme('nonsense') has always been a no-op. Coercing it to the
        // default would repaint the frame instead.
        const options = store();
        options.set('activeTheme', 'cream');
        expect(options.set('activeTheme', 'nonsense')).toBe(false);
        expect(options.get('activeTheme')).toBe('cream');
    });
});

describe('saving and restoring', () => {
    test('the payload round-trips through a fresh store', () => {
        const saved = store();
        saved.set('activeTheme', 'slate-night');
        saved.set('units', 'imperial');
        saved.set('edgeLineThicknessPx', 3);

        const restored = store();
        restored.applyPayload(saved.toPayload());

        expect(restored.toPayload()).toEqual(saved.toPayload());
    });

    test('restoring reports which options actually moved', () => {
        const options = store();
        expect(options.applyPayload({ units: 'imperial', shadowsEnabled: false }))
            .toEqual(['units']);   // shadows already false
    });

    test('a payload with junk in it leaves the defaults standing', () => {
        const options = store();
        options.applyPayload({ units: 'furlongs', activeTheme: 'nonsense', edgeMode: 42 });
        expect(options.get('units')).toBe('metric');
        expect(options.get('activeTheme')).toBe('forest');
        expect(options.get('edgeMode')).toBe('noOverlay');
    });

    test('a missing payload is survivable', () => {
        expect(store().applyPayload(null)).toEqual([]);
    });
});

describe('per-scene overrides', () => {
    test('resolve falls through to the global while nothing overrides', () => {
        const options = store();
        options.set('units', 'imperial');
        expect(options.resolve('some-drawing', 'units')).toBe('imperial');
    });

    test('an override wins for its own scene only', () => {
        // Nothing writes overrides yet; this is the seam a per-drawing theme
        // will use, and it is here so readers never have to change.
        const options = store();
        options.overridesBySceneId.set('drawing-1', { activeTheme: 'cream' });
        expect(options.resolve('drawing-1', 'activeTheme')).toBe('cream');
        expect(options.resolve('default-3d', 'activeTheme')).toBe('forest');
    });
});

describe('listeners', () => {
    test('a change notifies with what moved', () => {
        const options = store();
        const seen = [];
        options.onChanged((event) => seen.push(event));
        options.set('units', 'imperial');
        options.set('units', 'imperial');
        expect(seen).toEqual([{ key: 'units', value: 'imperial' }]);
    });
});
