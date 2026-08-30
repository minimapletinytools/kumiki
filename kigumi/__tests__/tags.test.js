const { coerceTags, coerceTag } = require('../webview/tags.js');

describe('tag coercion', () => {
    test('a typed tag keeps its kind and name', () => {
        expect(coerceTag({ kind: 'slice', name: 'bent1' })).toEqual({ kind: 'slice', name: 'bent1' });
    });

    test('a bare string reads as a generic tag', () => {
        // Kumiki coerces strings the same way, so a payload built by hand in a
        // test or an older runner still renders instead of vanishing.
        expect(coerceTag('wonky')).toEqual({ kind: 'generic', name: 'wonky' });
    });

    test('an unknown kind is shown as generic rather than dropped', () => {
        expect(coerceTag({ kind: 'invented', name: 'x' })).toEqual({ kind: 'generic', name: 'x' });
    });

    test('names are trimmed and empty ones dropped', () => {
        expect(coerceTags([' bent1 ', '', '   ', { kind: 'slice', name: ' gable ' }])).toEqual([
            { kind: 'generic', name: 'bent1' },
            { kind: 'slice', name: 'gable' },
        ]);
    });

    test('a tag with no name at all is dropped', () => {
        expect(coerceTags([null, {}, { kind: 'slice' }, 7])).toEqual([]);
    });

    test('a missing tag list is an empty list, not a throw', () => {
        expect(coerceTags(undefined)).toEqual([]);
    });
});
