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
        expect(availableKinds(point, point)).toEqual(['projected_perpendicular_distance', 'projected_horizontal_distance',
             'projected_vertical_distance']);
    });

    test('a point and a line admit the perpendicular', () => {
        expect(availableKinds(point, projectedForm(edge([1, 0, 0]), FRONT.look)))
            .toEqual(['projected_perpendicular_distance']);
    });

    test('two perpendicular faces admit an angle and not a distance', () => {
        // The case that started this: the distance between the middles of two
        // faces that meet at a corner is a number about nothing.
        const kinds = availableKinds(
            projectedForm(face([0, 0, 1]), FRONT.look),
            projectedForm(face([1, 0, 0]), FRONT.look),
        );

        expect(kinds).toEqual(['projected_angle']);
    });

    test('two parallel faces admit a separation and not an angle', () => {
        const kinds = availableKinds(
            projectedForm(face([0, 0, 1]), FRONT.look),
            projectedForm(face([0, 0, -1]), FRONT.look),
        );

        expect(kinds).toContain('projected_perpendicular_distance');
        expect(kinds).not.toContain('projected_angle');
    });

    test('a face that is not edge-on admits nothing at all', () => {
        expect(availableKinds(projectedForm(face([0, 1, 0]), FRONT.look), point)).toEqual([]);
    });

    test('a measurement can ask whether its kind applies here', () => {
        const a = projectedForm(face([0, 0, 1]), FRONT.look);
        const b = projectedForm(face([1, 0, 0]), FRONT.look);

        expect(kindApplies('projected_angle', a, b)).toBe(true);
        expect(kindApplies('projected_perpendicular_distance', a, b)).toBe(false);
        // The name it used to go by still resolves, for measurements already saved.
        expect(kindApplies('angle', a, b)).toBe(true);
    });
});

describe('measureValue', () => {
    const a = projectedForm(face([0, 0, 1]), FRONT.look);
    const b = projectedForm(face([1, 0, 0]), FRONT.look);

    test('the angle between two perpendicular faces is a right angle', () => {
        expect(measureValue('projected_angle', [0, 0, 0], [1, 0, 1], a, b, FRONT).value)
            .toBeCloseTo(90, 6);
    });

    test('the components are taken along the sheet, not the world', () => {
        const across = measureValue('projected_horizontal_distance', [0, 0, 0], [3, 9, 4], a, b, FRONT);
        const up = measureValue('projected_vertical_distance', [0, 0, 0], [3, 9, 4], a, b, FRONT);

        expect(across.value).toBeCloseTo(3, 9);
        expect(up.value).toBeCloseTo(4, 9);
    });

    test('between two points it is the distance, with the depth dropped', () => {
        // Nine units of depth, in this view. Two points have no line to be
        // square to, so the perpendicular distance is simply the distance --
        // which is why this and the old `aligned` are now one kind.
        const point = { form: 'point' };

        expect(measureValue(
            'projected_perpendicular_distance', [0, 0, 0], [3, 9, 4], point, point, FRONT,
        ).value).toBeCloseTo(5, 9);
    });

    test('a perpendicular is square to whichever of the two is a line', () => {
        const line = projectedForm(edge([1, 0, 0]), FRONT.look);
        const value = measureValue('projected_perpendicular_distance', [0, 0, 0], [7, 0, 2], { form: 'point' }, line, FRONT);

        // Seven along the line does not count; two away from it does.
        expect(value.value).toBeCloseTo(2, 9);
    });

    test('an angle comes back in degrees and a distance in world units', () => {
        expect(measureValue('projected_angle', [0, 0, 0], [1, 0, 1], a, b, FRONT).unit).toBe('angle');
        expect(measureValue('projected_perpendicular_distance', [0, 0, 0], [1, 0, 1], a, b, FRONT).unit).toBe('length');
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

const { measurementStatus, planeMatchesView } = require('../webview/measurements.js');

describe('a measurement is judged on its own plane', () => {
    // The plane is the measurement's, not the viewport's. That is what keeps a
    // number steady while the 3D view's camera orbits: the plane does not move
    // when the camera does.
    const AXES = { look: [0, -1, 0], right: [1, 0, 0], up: [0, 0, 1] };
    const point = (at) => ({ at, geometry: { kind: 'point', at } });
    const ORTHO = { orthographic: true };
    const PERSPECTIVE = { orthographic: false };

    const pair = (plane) => ({
        a: point([0, 0, 0]), b: point([1, 0, 1]), plane,
    });

    test('with no plane it falls back to the viewport, as it always did', () => {
        expect(measurementStatus(pair(undefined), AXES, ORTHO).drawable).toBe(true);
    });

    test('a plane matching the view is drawn', () => {
        const status = measurementStatus(
            pair({ at: [0, 0, 0], normal: [0, -1, 0] }), AXES, ORTHO);

        expect(status.drawable).toBe(true);
    });

    test('the normal may point the other way -- a plane has no front', () => {
        const status = measurementStatus(
            pair({ at: [0, 0, 0], normal: [0, 1, 0] }), AXES, ORTHO);

        expect(status.drawable).toBe(true);
    });

    test('a plane square to the view is refused rather than re-planed', () => {
        // Re-planing would change a number someone has already read off the
        // sheet, which is worse than saying it cannot be drawn.
        const status = measurementStatus(
            pair({ at: [0, 0, 0], normal: [1, 0, 0] }), AXES, ORTHO);

        expect(status.drawable).toBe(false);
        expect(status.reason).toBe('plane-mismatch');
    });

    test('a perspective camera projects onto no plane, so it does not ask', () => {
        // The 3D view and a drawing's preview. The measurement keeps its own
        // plane and is drawn through whatever the camera is doing.
        const status = measurementStatus(
            pair({ at: [0, 0, 0], normal: [1, 0, 0] }), AXES, PERSPECTIVE);

        expect(status.reason).not.toBe('plane-mismatch');
    });

    test('the value comes from the plane, not from the viewport', () => {
        // Two points a unit apart in x and in z. Seen down y the separation is
        // the diagonal; seen down x it is the z component alone. The plane
        // decides which, whatever the viewport says.
        const downY = measurementStatus(
            pair({ at: [0, 0, 0], normal: [0, 1, 0] }), AXES, PERSPECTIVE);
        const downX = measurementStatus(
            pair({ at: [0, 0, 0], normal: [1, 0, 0] }), AXES, PERSPECTIVE);

        expect(downY.value.value).toBeCloseTo(Math.SQRT2, 9);
        expect(downX.value.value).toBeCloseTo(1, 9);
    });
});

describe('planeMatchesView', () => {
    test('no plane matches anything, which is what absent means', () => {
        expect(planeMatchesView(null, [0, 1, 0])).toBe(true);
    });

    test('parallel matches, square does not', () => {
        expect(planeMatchesView({ normal: [0, 2, 0] }, [0, 1, 0])).toBe(true);
        expect(planeMatchesView({ normal: [1, 0, 0] }, [0, 1, 0])).toBe(false);
    });

    test('a hair off parallel is still off', () => {
        expect(planeMatchesView({ normal: [0.01, 1, 0] }, [0, 1, 0])).toBe(false);
    });
});


const { anchorReference } = require('../webview/measurements.js');

describe('anchorReference', () => {
    // A measurement comes back with its anchors resolved, and is rewritten by
    // sending it back. What resolving added must not come with it: the file
    // holds which feature, and where that feature is belongs to whichever
    // frame is loaded at the time.
    const resolved = {
        timber: 'post#0',
        csgPath: ['cut', 'mortise'],
        feature: 'cheek',
        type: 'FACE',
        at: [1, 2, 3],
        geometry: { kind: 'plane', normal: [0, 0, 1], at: [1, 2, 3] },
    };

    test('keeps what names the feature and drops where it resolved to', () => {
        expect(anchorReference(resolved)).toEqual({
            timber: 'post#0',
            csgPath: ['cut', 'mortise'],
            feature: 'cheek',
            type: 'FACE',
        });
    });

    test('an edge keeps both the parents that form it', () => {
        const edge = {
            kind: 'edge',
            timber: 'post#0',
            a: { csgPath: ['cut'], feature: 'shoulder' },
            b: { csgPath: [], feature: 'top' },
            type: 'EDGE',
            at: [0, 0, 0],
            geometry: { kind: 'line', direction: [1, 0, 0], at: [0, 0, 0] },
        };

        expect(anchorReference(edge)).toEqual({
            kind: 'edge',
            timber: 'post#0',
            a: { csgPath: ['cut'], feature: 'shoulder' },
            b: { csgPath: [], feature: 'top' },
            type: 'EDGE',
        });
    });

    test('a missing anchor stays missing rather than becoming an empty one', () => {
        expect(anchorReference(null)).toBeNull();
    });

    test('a reference that was never resolved survives the round trip', () => {
        const reference = { timber: 'post#0', csgPath: [], feature: 'top', type: 'FACE' };

        expect(anchorReference(reference)).toEqual(reference);
    });
});

describe('which kinds a focused measurement offers to change to', () => {
    // What the info pane's dropdown is built from: the kinds this pair admits
    // in this view, and the one currently being drawn.
    const AXES = { look: [0, -1, 0], right: [1, 0, 0], up: [0, 0, 1] };
    const point = (at) => ({ at, geometry: { kind: 'point', at } });

    test('two points admit three, so there is a choice to offer', () => {
        const status = measurementStatus({ a: point([0, 0, 0]), b: point([1, 0, 1]) }, AXES);

        expect(status.available.length).toBe(3);
    });

    test('the default is the first, which is what a new one is written with', () => {
        const status = measurementStatus({ a: point([0, 0, 0]), b: point([1, 0, 1]) }, AXES);

        expect(status.kind).toBe(status.available[0]);
    });

    test('a written kind is what is drawn, not the default', () => {
        const status = measurementStatus({
            a: point([0, 0, 0]), b: point([1, 0, 1]),
            kind: 'projected_vertical_distance',
        }, AXES);

        expect(status.kind).toBe('projected_vertical_distance');
    });

    test('two in line still admit the kinds that would not read zero', () => {
        // Refused as degenerate under the default kind, and horizontal or
        // vertical between the same two points is a real number -- so the
        // dropdown has somewhere to go, which is the point of offering it on a
        // refusal at all.
        const status = measurementStatus({ a: point([0, 0, 0]), b: point([0, 5, 0]) }, AXES);

        expect(status.drawable).toBe(false);
        expect(status.reason).toBe('degenerate');
        expect(availableKinds(status.formA, status.formB).length).toBe(3);
    });
});

describe('an angle says it is an angle', () => {
    // The viewer decides whether to draw an arc or a dimension line from the
    // status. It used to ask `status.kind === 'angle'` -- the bare legacy name
    // -- and the kinds became composed, so every angle fell through and was
    // drawn as a linear dimension: the right number, the wrong picture, and
    // degrees labelled as a length.
    //
    // The value's unit is what the viewer asks now, so these pin that the two
    // agree and that nothing answers to the old bare name.
    const AXES = { look: [0, -1, 0], right: [1, 0, 0], up: [0, 0, 1] };
    const crossing = {
        a: { at: [0, 0, 0], geometry: { kind: 'line', direction: [1, 0, 0], at: [0, 0, 0] } },
        b: { at: [1, 0, 1], geometry: { kind: 'line', direction: [0, 0, 1], at: [1, 0, 1] } },
    };

    test('two crossing lines admit an angle and nothing else', () => {
        expect(measurementStatus(crossing, AXES).kind).toBe('projected_angle');
    });

    test('and the value calls itself an angle', () => {
        expect(measurementStatus(crossing, AXES).value.unit).toBe('angle');
    });

    test('no kind answers to the bare name the viewer used to look for', () => {
        // If a kind is ever named plain 'angle' again, the two ways of asking
        // stop agreeing and this is where it shows.
        const kinds = availableKinds(
            { form: 'line', direction: [1, 0, 0] },
            { form: 'line', direction: [0, 0, 1] },
        );

        expect(kinds).not.toContain('angle');
        expect(kinds).toContain('projected_angle');
    });

    test('a distance calls itself a length, so the two branches cannot blur', () => {
        const apart = {
            a: { at: [0, 0, 0], geometry: { kind: 'point', at: [0, 0, 0] } },
            b: { at: [1, 0, 1], geometry: { kind: 'point', at: [1, 0, 1] } },
        };

        expect(measurementStatus(apart, AXES).value.unit).toBe('length');
    });
});

const { perpendicularEnds } = require('../webview/measurements.js');

describe('where the two ends of a perpendicular distance are drawn', () => {
    // The value has the along-the-line part taken out; the picture did not, so
    // two parallel edges offset along their length were drawn as a slanted
    // line, longer than the number beside it.
    const along = (x, y) => ({ x, y });
    const spanOf = (ends) => Math.hypot(ends.to.x - ends.from.x, ends.to.y - ends.from.y);
    const isSquareTo = (ends, direction) => {
        const run = { x: ends.to.x - ends.from.x, y: ends.to.y - ends.from.y };
        return Math.abs(run.x * direction.x + run.y * direction.y);
    };

    test('two points are drawn between themselves', () => {
        // No line to be square to, so the distance IS the distance.
        const ends = perpendicularEnds({ x: 0, y: 0 }, { x: 3, y: 4 }, null, null);

        expect(ends).toEqual({ from: { x: 0, y: 0 }, to: { x: 3, y: 4 } });
    });

    test('two parallel lines are joined square across', () => {
        // Offset 10 along x and 4 apart across it: the drawn span should be 4,
        // not the 10.77 between the raw anchors.
        const ends = perpendicularEnds(
            { x: 0, y: 0 }, { x: 10, y: 4 }, along(1, 0), along(1, 0));

        expect(isSquareTo(ends, along(1, 0))).toBeCloseTo(0, 9);
        expect(spanOf(ends)).toBeCloseTo(4, 9);
    });

    test('and each end stays on its own feature', () => {
        // Sliding a point along the line it lies on does not change which
        // feature it marks. Moving it off would.
        const ends = perpendicularEnds(
            { x: 0, y: 0 }, { x: 10, y: 4 }, along(1, 0), along(1, 0));

        expect(ends.from.y).toBeCloseTo(0, 9);
        expect(ends.to.y).toBeCloseTo(4, 9);
    });

    test('the dimension sits between the two, not at one end', () => {
        const ends = perpendicularEnds(
            { x: 0, y: 0 }, { x: 10, y: 4 }, along(1, 0), along(1, 0));

        expect(ends.from.x).toBeCloseTo(5, 9);
        expect(ends.to.x).toBeCloseTo(5, 9);
    });

    test('lines pointing opposite ways are still one pair', () => {
        // A feature's direction has no preferred sense, so the two may come
        // back antiparallel. Sliding one the wrong way would pull them apart.
        const ends = perpendicularEnds(
            { x: 0, y: 0 }, { x: 10, y: 4 }, along(1, 0), along(-1, 0));

        expect(isSquareTo(ends, along(1, 0))).toBeCloseTo(0, 9);
        expect(spanOf(ends)).toBeCloseTo(4, 9);
    });

    test('a point and a line meet at the foot of the perpendicular', () => {
        const ends = perpendicularEnds(
            { x: 0, y: 0 }, { x: 10, y: 4 }, null, along(1, 0));

        expect(ends.from).toEqual({ x: 0, y: 0 });
        expect(ends.to.x).toBeCloseTo(0, 9);
        expect(spanOf(ends)).toBeCloseTo(4, 9);
    });

    test('whichever way round the point and the line arrive', () => {
        const ends = perpendicularEnds(
            { x: 10, y: 4 }, { x: 0, y: 0 }, along(1, 0), null);

        expect(ends.to).toEqual({ x: 0, y: 0 });
        expect(ends.from.x).toBeCloseTo(0, 9);
        expect(spanOf(ends)).toBeCloseTo(4, 9);
    });

    test('already square stays where it is', () => {
        const ends = perpendicularEnds(
            { x: 0, y: 0 }, { x: 0, y: 4 }, along(1, 0), along(1, 0));

        expect(ends.from).toEqual({ x: 0, y: 0 });
        expect(ends.to).toEqual({ x: 0, y: 4 });
    });
});

const { measurementKey } = require('../webview/measurements.js');

describe('measurementKey', () => {
    // One definition, shared by the sheet, the drawing panel and the tree --
    // three places that must agree about which measurement was clicked.
    const anchor = (feature) => ({
        timber: 'post#0', csgPath: ['cut'], feature, type: 'FACE',
    });

    test('the same pair is the same key', () => {
        expect(measurementKey({ a: anchor('x'), b: anchor('y') }))
            .toBe(measurementKey({ a: anchor('x'), b: anchor('y') }));
    });

    test('written either way round it is one measurement', () => {
        expect(measurementKey({ a: anchor('x'), b: anchor('y') }))
            .toBe(measurementKey({ a: anchor('y'), b: anchor('x') }));
    });

    test('different pairs are different', () => {
        expect(measurementKey({ a: anchor('x'), b: anchor('y') }))
            .not.toBe(measurementKey({ a: anchor('x'), b: anchor('z') }));
    });

    test('an id tells two of the same pair apart', () => {
        expect(measurementKey({ a: anchor('x'), b: anchor('y'), measureId: 'second' }))
            .not.toBe(measurementKey({ a: anchor('x'), b: anchor('y') }));
    });

    test('a missing anchor does not throw', () => {
        expect(typeof measurementKey({ a: anchor('x'), b: null })).toBe('string');
    });
});
