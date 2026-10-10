const {
    ROLES, featureKeyOf, featureStatesFor, featureStateSummary, leadingRole,
} = require('../webview/feature-states.js');

describe('feature states', () => {
    test('a selection focus and a hover answer name the same feature the same way', () => {
        expect(featureKeyOf({ timberKey: 'post#0', path: ['cut'], featureLabel: 'front' }))
            .toBe(featureKeyOf({ memberKey: 'post#0', path: ['cut'], featureLabel: 'front' }));
        expect(featureKeyOf({ memberKey: 'post#0', path: ['cut'] })).toBe('post#0|cut|');
    });

    test('sources naming one feature merge into one state with several roles', () => {
        const key = 'post#0|cut|front';
        const selection = { key, mesh: 'selection mesh' };
        const hover = { key, refused: true };
        const held = { key: 'girt#0||back' };

        const states = featureStatesFor({ selection, hover, held });

        expect(states.map((state) => state.key)).toEqual([key, 'girt#0||back']);
        expect(states[0].roles).toEqual({ selection, hover });
        expect(states[1].roles).toEqual({ held });
    });

    test('nothing lit, or a source with no key, is no state', () => {
        expect(featureStatesFor({})).toEqual([]);
        expect(featureStatesFor(null)).toEqual([]);
        expect(featureStatesFor({ hover: { mesh: 'no key' } })).toEqual([]);
    });

    test('a summary says which roles, and whether the hover is refused, as plain data', () => {
        const [state] = featureStatesFor({ selection: { key: 'a' }, hover: { key: 'a', refused: true } });

        expect(featureStateSummary(state)).toEqual(['a', ['selection', 'hover'], true]);
        expect(ROLES).toEqual(['selection', 'hover', 'held']);
    });
});

describe('which role a feature is drawn as', () => {
    const lead = (sources) => {
        const leading = leadingRole(featureStatesFor(sources)[0]);
        return leading && leading.role;
    };

    test.each([
        ['selection alone', { selection: { key: 'k' } }, 'selection'],
        ['hover over selection', { selection: { key: 'k' }, hover: { key: 'k' } }, 'hover'],
        ['held over hover', { hover: { key: 'k' }, held: { key: 'k' } }, 'held'],
        ['a refused hover over held', { hover: { key: 'k', refused: true }, held: { key: 'k' } }, 'hover'],
    ])('%s', (_name, sources, role) => {
        expect(lead(sources)).toBe(role);
    });

    test('no roles, no lead', () => {
        expect(leadingRole({ key: 'k', roles: {} })).toBeNull();
    });
});
