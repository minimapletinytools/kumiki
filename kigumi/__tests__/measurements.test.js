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

const { projectedForm, availableKinds, kindApplies, measureValue, angleLayout } =
    require('../webview/measurements.js');

// A front elevation: looking north, x across the sheet and z up it.
const FRONT = { look: [0, 1, 0], right: [1, 0, 0], up: [0, 0, 1] };

const face = (normal) => ({ kind: 'plane', normal });
const edge = (direction) => ({ kind: 'line', direction });

describe('projectedForm', () => {
    // What a feature looks like once projected is what decides the measurement,
    // not what the feature is.
    test('a face square to the view covers it, and an area has no distance', () => {
        expect(projectedForm(face([0, 1, 0]), FRONT.look).form).toBe('area');
    });

    test('a face seen edge-on behaves as a line', () => {
        expect(projectedForm(face([0, 0, 1]), FRONT.look).form).toBe('line');
    });

    test('an edge along the line of sight behaves as a point', () => {
        expect(projectedForm(edge([0, 1, 0]), FRONT.look).form).toBe('point');
    });

    test('an edge across the view stays a line', () => {
        expect(projectedForm(edge([1, 0, 0]), FRONT.look).form).toBe('line');
    });

    test('a point is a point however it is looked at', () => {
        expect(projectedForm({ kind: 'point' }, FRONT.look).form).toBe('point');
    });

    test('an edge-on face draws along itself, not along its normal', () => {
        const drawn = projectedForm(face([0, 0, 1]), FRONT.look).direction;

        // Square to its own normal, and to the line of sight.
        expect(drawn[2]).toBeCloseTo(0, 6);
        expect(drawn[1]).toBeCloseTo(0, 6);
    });
});

describe('availableKinds', () => {
    const point = { form: 'point' };

    test('two points admit the distance and either component', () => {
        expect(availableKinds(point, point)).toEqual(['aligned', 'horizontal', 'vertical']);
    });

    test('a point and a line admit the perpendicular', () => {
        expect(availableKinds(point, projectedForm(edge([1, 0, 0]), FRONT.look)))
            .toEqual(['perpendicular']);
    });

    test('two perpendicular faces admit an angle and not a distance', () => {
        // The case that started this: the distance between the middles of two
        // faces that meet at a corner is a number about nothing.
        const kinds = availableKinds(
            projectedForm(face([0, 0, 1]), FRONT.look),
            projectedForm(face([1, 0, 0]), FRONT.look),
        );

        expect(kinds).toEqual(['angle']);
    });

    test('two parallel faces admit a separation and not an angle', () => {
        const kinds = availableKinds(
            projectedForm(face([0, 0, 1]), FRONT.look),
            projectedForm(face([0, 0, -1]), FRONT.look),
        );

        expect(kinds).toContain('perpendicular');
        expect(kinds).not.toContain('angle');
    });

    test('a face that is not edge-on admits nothing at all', () => {
        expect(availableKinds(projectedForm(face([0, 1, 0]), FRONT.look), point)).toEqual([]);
    });

    test('a measurement can ask whether its kind applies here', () => {
        const a = projectedForm(face([0, 0, 1]), FRONT.look);
        const b = projectedForm(face([1, 0, 0]), FRONT.look);

        expect(kindApplies('angle', a, b)).toBe(true);
        expect(kindApplies('aligned', a, b)).toBe(false);
    });
});

describe('measureValue', () => {
    const a = projectedForm(face([0, 0, 1]), FRONT.look);
    const b = projectedForm(face([1, 0, 0]), FRONT.look);

    test('the angle between two perpendicular faces is a right angle', () => {
        expect(measureValue('angle', [0, 0, 0], [1, 0, 1], a, b, FRONT).value)
            .toBeCloseTo(90, 6);
    });

    test('the components are taken along the sheet, not the world', () => {
        const across = measureValue('horizontal', [0, 0, 0], [3, 9, 4], a, b, FRONT);
        const up = measureValue('vertical', [0, 0, 0], [3, 9, 4], a, b, FRONT);

        expect(across.value).toBeCloseTo(3, 9);
        expect(up.value).toBeCloseTo(4, 9);
    });

    test('the aligned distance drops the depth between them', () => {
        // Nine units of it, in this view.
        expect(measureValue('aligned', [0, 0, 0], [3, 9, 4], a, b, FRONT).value)
            .toBeCloseTo(5, 9);
    });

    test('a perpendicular is square to whichever of the two is a line', () => {
        const line = projectedForm(edge([1, 0, 0]), FRONT.look);
        const value = measureValue('perpendicular', [0, 0, 0], [7, 0, 2], { form: 'point' }, line, FRONT);

        // Seven along the line does not count; two away from it does.
        expect(value.value).toBeCloseTo(2, 9);
    });

    test('an angle comes back in degrees and a distance in world units', () => {
        expect(measureValue('angle', [0, 0, 0], [1, 0, 1], a, b, FRONT).unit).toBe('angle');
        expect(measureValue('aligned', [0, 0, 0], [1, 0, 1], a, b, FRONT).unit).toBe('length');
    });
});

describe('angleLayout', () => {
    test('the arc is drawn where the two lines cross', () => {
        const layout = angleLayout({ x: 0, y: 100 }, { x: 1, y: 0 },
                                   { x: 100, y: 0 }, { x: 0, y: -1 }, { radius: 30 });

        expect(layout.vertex.x).toBeCloseTo(100, 6);
        expect(layout.vertex.y).toBeCloseTo(100, 6);
    });

    test('its ends sit on the arc at the given radius', () => {
        const layout = angleLayout({ x: 0, y: 100 }, { x: 1, y: 0 },
                                   { x: 100, y: 0 }, { x: 0, y: -1 }, { radius: 30 });
        const reach = (point) => Math.hypot(point.x - layout.vertex.x, point.y - layout.vertex.y);

        expect(reach(layout.start)).toBeCloseTo(30, 6);
        expect(reach(layout.end)).toBeCloseTo(30, 6);
    });

    test('it is drawn in the corner being measured, not the one opposite', () => {
        const layout = angleLayout({ x: 0, y: 100 }, { x: 1, y: 0 },
                                   { x: 100, y: 0 }, { x: 0, y: -1 }, { radius: 30 });

        // Both features lie left of and above the crossing, so the arc does too.
        expect(layout.start.x).toBeLessThanOrEqual(layout.vertex.x);
        expect(layout.end.y).toBeLessThanOrEqual(layout.vertex.y);
    });

    test('lines that never cross have no corner to draw in', () => {
        expect(angleLayout({ x: 0, y: 0 }, { x: 1, y: 0 },
                           { x: 0, y: 50 }, { x: 1, y: 0 }, {})).toBeNull();
    });
});
