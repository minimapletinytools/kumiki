const {
    projectedSeparation, dimensionLayout, DEGENERATE_PIXELS,
} = require('../webview/measurements.js');

describe('projectedSeparation', () => {
    // A drawing is a projection, so a dimension is the separation seen from the
    // viewport, not the distance between the two features in space.
    test('two points across the view are their full distance apart', () => {
        expect(projectedSeparation([0, 0, 0], [3, 0, 0], [0, 0, -1])).toBeCloseTo(3, 9);
    });

    test('depth does not count toward it', () => {
        // Two mortises at different depths, dimensioned on the front elevation,
        // read as their separation across that face.
        const flat = projectedSeparation([0, 0, 0], [3, 0, 0], [0, 1, 0]);
        const deep = projectedSeparation([0, 0, 0], [3, 5, 0], [0, 1, 0]);

        expect(deep).toBeCloseTo(flat, 9);
    });

    test('two points separated only in depth are zero apart', () => {
        // The degenerate case: nothing to dimension in this view, and the
        // viewport has to refuse rather than draw a number.
        expect(projectedSeparation([0, 0, 0], [0, 4, 0], [0, 1, 0])).toBeCloseTo(0, 9);
    });

    test('it does not care which way round the two are', () => {
        expect(projectedSeparation([1, 2, 3], [4, 6, 8], [0, 0, -1]))
            .toBeCloseTo(projectedSeparation([4, 6, 8], [1, 2, 3], [0, 0, -1]), 9);
    });

    test('the direction of sight need not be a unit vector', () => {
        expect(projectedSeparation([0, 0, 0], [3, 5, 0], [0, 7, 0])).toBeCloseTo(3, 9);
    });

    test('a diagonal run measures the diagonal, not its parts', () => {
        expect(projectedSeparation([0, 0, 0], [3, 0, 4], [0, 1, 0])).toBeCloseTo(5, 9);
    });
});

describe('dimensionLayout', () => {
    const from = { x: 100, y: 100 };
    const to = { x: 200, y: 100 };

    test('the dimension line runs parallel to what it measures', () => {
        const layout = dimensionLayout(from, to, { offset: 20 });

        expect(layout.line.from.y).toBeCloseTo(layout.line.to.y, 9);
        expect(layout.line.to.x - layout.line.from.x).toBeCloseTo(100, 9);
    });

    test('it sits clear of the thing it measures', () => {
        // Offset, with witness lines reaching back -- so the drawing itself is
        // not obscured by its own dimensions.
        const layout = dimensionLayout(from, to, { offset: 20 });

        expect(Math.abs(layout.line.from.y - from.y)).toBeCloseTo(20, 9);
        expect(layout.witness).toHaveLength(2);
    });

    test('the offset can go to either side', () => {
        const above = dimensionLayout(from, to, { offset: 20 });
        const below = dimensionLayout(from, to, { offset: -20 });

        expect(Math.sign(above.line.from.y - from.y)).toBe(-Math.sign(below.line.from.y - from.y));
    });

    test('a witness line stops short of the feature and passes the dimension', () => {
        // Neither end quite touches, which is what keeps a drawing readable
        // where lines meet.
        const layout = dimensionLayout(from, to, { offset: 20, gap: 4, overshoot: 6 });
        const witness = layout.witness[0];

        expect(Math.abs(witness.from.y - from.y)).toBeCloseTo(4, 9);
        expect(Math.abs(witness.to.y - from.y)).toBeCloseTo(26, 9);
    });

    test('the label sits in the middle of the dimension line', () => {
        const layout = dimensionLayout(from, to, { offset: 20 });

        expect(layout.label.x).toBeCloseTo(150, 9);
        expect(layout.label.y).toBeCloseTo(layout.line.from.y, 9);
    });

    test('the label is never upside down', () => {
        // A dimension read from the other side says the same thing, and text
        // that has been turned over says nothing at all.
        for (const angle of [0, 45, 90, 135, 180, 225, 270, 315]) {
            const radians = angle * Math.PI / 180;
            const end = { x: from.x + 100 * Math.cos(radians), y: from.y + 100 * Math.sin(radians) };
            const layout = dimensionLayout(from, end, { offset: 20 });

            expect(layout.label.angle).toBeGreaterThanOrEqual(-90);
            expect(layout.label.angle).toBeLessThanOrEqual(90);
        }
    });

    test('two anchors on the same spot have no dimension to draw', () => {
        // Rather than a zero-length line with a number beside it, which would
        // be a lie rather than an empty result.
        expect(dimensionLayout(from, { x: 100, y: 100 }, {})).toBeNull();
        expect(dimensionLayout(from, { x: 100 + DEGENERATE_PIXELS / 2, y: 100 }, {})).toBeNull();
    });

    test('a diagonal run is offset perpendicular to itself', () => {
        const layout = dimensionLayout({ x: 0, y: 0 }, { x: 100, y: 100 }, { offset: 10 });
        const alongX = layout.line.from.x - 0;
        const alongY = layout.line.from.y - 0;

        // Perpendicular: the offset has no component along the run.
        expect(alongX * 100 + alongY * 100).toBeCloseTo(0, 6);
    });
});
