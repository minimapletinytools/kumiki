const { phantomSegment, alongForPointer } = require('../webview/measurements.js');

describe('phantomSegment: a feature drawn on to a point past its end', () => {
    const extent = [[0, 0, 0], [3, 0, 0]];

    test('nothing when the point is on the feature', () => {
        expect(phantomSegment(extent, [1.5, 0, 0])).toBeNull();
        expect(phantomSegment(extent, [3, 0, 0])).toBeNull();
    });

    test('from the nearer end, past either end', () => {
        expect(phantomSegment(extent, [5, 0, 0])).toEqual({ from: [3, 0, 0], to: [5, 0, 0] });
        expect(phantomSegment(extent, [-2, 0, 0])).toEqual({ from: [0, 0, 0], to: [-2, 0, 0] });
    });

    test('nothing for a feature with no extent to draw on: a point, or a plane', () => {
        expect(phantomSegment(null, [5, 0, 0])).toBeNull();
    });
});

describe('alongForPointer: sliding a dimension along its features', () => {
    // Along the page's x, 10 pixels to a world unit.
    const slide = { x: 1, y: 0, perWorld: 10 };

    test('only the pointer travel along the slide counts', () => {
        expect(alongForPointer(0.5, { x: 20, y: 40 }, slide)).toBeCloseTo(2.5, 9);
    });

    test('backwards is negative', () => {
        expect(alongForPointer(0, { x: -15, y: 0 }, slide)).toBeCloseTo(-1.5, 9);
    });

    test('nothing to slide along when it has no length on the page', () => {
        expect(alongForPointer(0, { x: 5, y: 0 }, { x: 1, y: 0, perWorld: 0 })).toBeNull();
    });
});
