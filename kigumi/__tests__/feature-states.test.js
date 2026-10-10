const { ROLES, featureKeyOf, featureStatesFor, featureStateSummary } = require('../webview/feature-states.js');

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
