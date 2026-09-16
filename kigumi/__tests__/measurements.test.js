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

const { offsetForPointer } = require('../webview/measurements.js');

describe('offsetForPointer', () => {
    // A dimension's one degree of freedom once its ends are fixed: it slides
    // along the perpendicular and nowhere else.
    const from = { x: 0, y: 0 };
    const to = { x: 100, y: 0 };

    test('a pointer on the run sits at no offset', () => {
        expect(offsetForPointer(from, to, { x: 50, y: 0 })).toBeCloseTo(0, 9);
    });

    test('it measures across the run, not along it', () => {
        // Moving along the run changes nothing: that is not the freedom.
        expect(offsetForPointer(from, to, { x: 10, y: 30 }))
            .toBeCloseTo(offsetForPointer(from, to, { x: 90, y: 30 }), 9);
    });

    test('and gives the distance across', () => {
        expect(Math.abs(offsetForPointer(from, to, { x: 50, y: 30 }))).toBeCloseTo(30, 9);
    });

    test('the sign says which side, so it can be dragged through', () => {
        const above = offsetForPointer(from, to, { x: 50, y: 30 });
        const below = offsetForPointer(from, to, { x: 50, y: -30 });

        expect(Math.sign(above)).toBe(-Math.sign(below));
    });

    test('it follows the run round, not the screen', () => {
        // The same pointer relative to a vertical run gives the same offset as
        // it does to a horizontal one, turned.
        const across = offsetForPointer({ x: 0, y: 0 }, { x: 0, y: 100 }, { x: 30, y: 50 });

        expect(Math.abs(across)).toBeCloseTo(30, 9);
    });

    test('two ends on top of each other have no perpendicular to slide along', () => {
        expect(offsetForPointer(from, { x: 0, y: 0 }, { x: 5, y: 5 })).toBeNull();
    });
});

describe('an offset is stored in world units, not screen pixels', () => {
    // Where somebody put a dimension should not depend on how far they were
    // zoomed in at the time. What zoom changes is how big the drawing is; only
    // the drawn SIZE of things -- line weights, text -- stays in pixels.
    //
    // The scale comes off the run itself: a length known in the world and just
    // drawn on the page. These pin the arithmetic both ways round.
    const perWorld = (worldSpan, drawnSpan) => drawnSpan / worldSpan;

    test('the same drag at twice the zoom stores the same offset', () => {
        const pointer = { x: 50, y: 30 };
        const near = offsetForPointer({ x: 0, y: 0 }, { x: 100, y: 0 }, pointer);
        const far = offsetForPointer({ x: 0, y: 0 }, { x: 200, y: 0 },
                                     { x: 100, y: 60 });

        // 100px drawn for a 1m run, then 200px for the same run.
        expect(near / perWorld(1, 100)).toBeCloseTo(far / perWorld(1, 200), 9);
    });

    test('and is drawn twice as far out at twice the zoom', () => {
        const stored = 0.3;

        expect(stored * perWorld(1, 100)).toBeCloseTo(30, 9);
        expect(stored * perWorld(1, 200)).toBeCloseTo(60, 9);
    });

    test('a run of no world length has no scale to speak of', () => {
        // Two features on top of each other: nothing to divide by, and the
        // caller falls back to the viewport's pixel default.
        expect(Number.isFinite(perWorld(0, 100))).toBe(false);
    });
});

const { isBroken, BROKEN_REASONS } = require('../webview/measurements.js');

describe('which refusals are damage and which are just this view', () => {
    // Only one kind is something to go and mend, and only one kind should be
    // shouting. Two panels read this, so it is decided once.
    test('a reference that no longer resolves is broken', () => {
        expect(isBroken({ drawable: false, reason: 'unresolved' })).toBe(true);
    });

    test('a plane that disagrees with its viewport is broken', () => {
        expect(isBroken({ drawable: false, reason: 'plane-mismatch' })).toBe(true);
    });

    test('the view-dependent refusals are not', () => {
        // The same measurement reads fine under one viewport and is refused by
        // the next. That is information, not damage.
        for (const reason of ['not-measurable', 'kind-unavailable', 'degenerate']) {
            expect(isBroken({ drawable: false, reason })).toBe(false);
        }
    });

    test('something that draws is not broken whatever else it says', () => {
        expect(isBroken({ drawable: true, reason: 'unresolved' })).toBe(false);
    });

    test('no status is not a claim that anything is broken', () => {
        expect(isBroken(null)).toBe(false);
        expect(isBroken(undefined)).toBe(false);
    });

    test('the two reasons are the ones the statuses actually use', () => {
        // A reason renamed on one side and not the other would silently stop
        // anything being called broken.
        const AXES = { look: [0, -1, 0], right: [1, 0, 0], up: [0, 0, 1] };
        const unresolved = measurementStatus({ a: null, b: null }, AXES);
        const mismatched = measurementStatus({
            a: { at: [0, 0, 0], geometry: { kind: 'point', at: [0, 0, 0] } },
            b: { at: [1, 0, 1], geometry: { kind: 'point', at: [1, 0, 1] } },
            plane: { at: [0, 0, 0], normal: [1, 0, 0] },
        }, AXES, { orthographic: true });

        expect(BROKEN_REASONS).toContain(unresolved.reason);
        expect(BROKEN_REASONS).toContain(mismatched.reason);
    });
});

describe('a derived edge is identified by the faces that form it', () => {
    // Without them every derived edge on one timber shares a key, so focusing
    // one focuses both and an edit or a delete lands on whichever was found
    // first -- silently, on the wrong dimension.
    const edge = (path) => ({
        kind: 'edge', timber: 'T', type: 'EDGE',
        a: { csgPath: [path], feature: 'x' }, b: { csgPath: [], feature: 'y' },
    });
    const face = { timber: 'U', csgPath: ['z'], feature: 'top', type: 'FACE' };

    test('two different edges to the same face are two measurements', () => {
        expect(measurementKey({ a: edge('cutA'), b: face }))
            .not.toBe(measurementKey({ a: edge('cutB'), b: face }));
    });

    test('and one edge written either way round is still one measurement', () => {
        const forwards = { kind: 'edge', timber: 'T', type: 'EDGE',
            a: { csgPath: ['cut'], feature: 'x' }, b: { csgPath: [], feature: 'y' } };
        const backwards = { kind: 'edge', timber: 'T', type: 'EDGE',
            a: { csgPath: [], feature: 'y' }, b: { csgPath: ['cut'], feature: 'x' } };

        expect(measurementKey({ a: forwards, b: face }))
            .toBe(measurementKey({ a: backwards, b: face }));
    });

    test('an edge and a face are never the same anchor', () => {
        expect(measurementKey({ a: edge('cut'), b: face }))
            .not.toBe(measurementKey({ a: face, b: face }));
    });
});

const Measurements = require('../webview/measurements.js');

describe('what the 3D view measures', () => {
    // The 3D view's camera belongs to the reader and turns as they look around,
    // so a feature there is classified as it IS. Projecting instead called
    // every face not seen exactly edge-on an 'area' -- nothing to measure --
    // which is nearly all of them, in every direction the camera can point.
    const { solidForm, solidKinds, measurementStatus } = Measurements;
    const face = (normal) => ({ kind: 'plane', normal });
    const edge = (direction) => ({ kind: 'line', direction });
    const solid = { orthographic: false };
    const axes = { look: [-0.577, -0.577, -0.577], right: [1, 0, 0], up: [0, 0, 1] };

    test('a face is a plane from wherever it is seen', () => {
        expect(solidForm(face([0, 0, 1])).form).toBe('plane');
    });

    test('an edge is a line even when it points at you', () => {
        expect(solidForm(edge([0, 0, 1])).form).toBe('line');
    });

    test('two faces meeting at a corner admit an angle', () => {
        expect(solidKinds(solidForm(face([1, 0, 0])), solidForm(face([0, 0, 1]))))
            .toEqual(['angle']);
    });

    test('two parallel faces admit the distance between them', () => {
        expect(solidKinds(solidForm(face([1, 0, 0])), solidForm(face([-1, 0, 0]))))
            .toEqual(['perpendicular_distance']);
    });

    test('an edge lying in a face is parallel to it, not crossing it', () => {
        // A normal is not a direction: the line runs square to the normal
        // exactly when it lies in the plane.
        expect(solidKinds(solidForm(edge([0, 0, 1])), solidForm(face([1, 0, 0]))))
            .toEqual(['perpendicular_distance']);
    });

    test('and one square to a face does cross it', () => {
        expect(solidKinds(solidForm(edge([1, 0, 0])), solidForm(face([1, 0, 0]))))
            .toEqual(['angle']);
    });

    test('a corner reads 90 degrees, not a length', () => {
        const status = measurementStatus({
            a: { at: [0, 0, 0], geometry: face([1, 0, 0]) },
            b: { at: [0, 0, 0], geometry: face([0, 0, 1]) },
            kind: { operation: 'angle', space: '3d' },
        }, axes, solid);

        expect(status.drawable).toBe(true);
        expect(status.value).toEqual({ unit: 'angle', value: 90 });
    });

    test('a slab reads its whole thickness, not the projected part of it', () => {
        const status = measurementStatus({
            a: { at: [0, 0, 0], geometry: face([1, 0, 0]) },
            b: { at: [150, 0, 0], geometry: face([-1, 0, 0]) },
            kind: { operation: 'distance', space: '3d', direction: 'perpendicular' },
        }, axes, solid);

        expect(status.value).toEqual({ unit: 'length', value: 150 });
    });

    test('the same pair, judged as a sheet would, is not measurable at all', () => {
        // Which is what the 3D view was doing, and why a face went red.
        const status = measurementStatus({
            a: { at: [0, 0, 0], geometry: face([1, 0, 0]) },
            b: { at: [0, 0, 0], geometry: face([0, 0, 1]) },
        }, axes, { orthographic: true });

        expect(status.drawable).toBe(false);
        expect(status.reason).toBe('not-measurable');
    });
});

describe('naming a kind, and writing one back', () => {
    const { kindName, kindWire, measurementStatus } = Measurements;

    test('a structured kind composes to its name', () => {
        expect(kindName({ operation: 'distance', space: 'projected', direction: 'horizontal' }))
            .toBe('projected_horizontal_distance');
        expect(kindName({ operation: 'angle', space: '3d' })).toBe('angle');
    });

    test('a measurement a python file declared is drawable', () => {
        // Its kind arrives structured, and comparing that against a list of
        // names matched nothing: every one read as kind-unavailable.
        const status = measurementStatus({
            a: { at: [0, 0, 0], geometry: { kind: 'plane', normal: [1, 0, 0] } },
            b: { at: [100, 0, 0], geometry: { kind: 'plane', normal: [-1, 0, 0] } },
            kind: { operation: 'distance', space: 'projected', direction: 'perpendicular' },
        }, { look: [0, 0, -1], right: [1, 0, 0], up: [0, 1, 0] }, { orthographic: true });

        expect(status.drawable).toBe(true);
    });

    test('a solid angle is written structured, so it cannot be read back projected', () => {
        // `angle` is also what every measurement written before spaces existed
        // calls a projected one, and python reads the bare word that way.
        expect(kindWire('angle', '3d').space).toBe('3d');
        expect(kindWire('angle', 'projected').space).toBe('projected');
    });

    test('a name that carries its own space keeps it', () => {
        expect(kindWire('projected_angle', '3d').space).toBe('projected');
    });

    test('a name from before spaces existed is still projected', () => {
        // 'aligned' must not be composed as though it were a solid kind.
        expect(kindWire('aligned', '3d')).toEqual({
            operation: 'distance', space: 'projected', direction: 'perpendicular',
        });
    });

    test('a structured kind passes through unchanged', () => {
        const wire = { operation: 'angle', space: '3d', direction: 'perpendicular' };
        expect(kindWire(wire, 'projected')).toEqual(wire);
    });
});

describe('the arc of an angle lies in the angle\'s own plane', () => {
    // A drafted angle lies on the work. Drawn as a flat arc between two
    // projected directions it shows the PROJECTED angle, which agrees with the
    // number beside it only when the camera looks down the plane -- from
    // anywhere else a right angle reads as twenty degrees and the arc floats
    // free of the timber.
    const { angleArcPoints, angleLabelPoint } = Measurements;
    const square = { vertex: [0, 0, 0], from: [1, 0, 0], to: [0, 1, 0], normal: [0, 0, 1] };
    const radius = (point) => Math.hypot(point[0], point[1], point[2]);

    test('it starts on one ray and ends on the other', () => {
        const points = angleArcPoints(square, 100, 8);

        expect(points[0].map(Math.round)).toEqual([100, 0, 0]);
        expect(points[points.length - 1].map(Math.round)).toEqual([0, 100, 0]);
    });

    test('every point is the same distance from the vertex', () => {
        for (const point of angleArcPoints(square, 100, 8)) {
            expect(radius(point)).toBeCloseTo(100, 9);
        }
    });

    test('and every point lies in the plane', () => {
        // Square to the normal is what being in the plane means, and it is why
        // the plane is carried at all.
        for (const point of angleArcPoints(square, 100, 8)) {
            expect(point[2]).toBeCloseTo(0, 9);
        }
    });

    test('a plane can be worked out when none was sent', () => {
        // Older measurements carry no normal; the two rays still span one.
        const points = angleArcPoints(
            { vertex: [0, 0, 0], from: [1, 0, 0], to: [0, 0, 1] }, 10, 4);

        expect(points[points.length - 1].map(Math.round)).toEqual([0, 0, 10]);
    });

    test('an obtuse angle sweeps through the corner, not around the back', () => {
        // 135 degrees. Halfway round is 67.5, so the arc passes through the
        // quadrant between the two rays rather than the one opposite it -- and
        // it reaches `to` at the far end rather than stopping square.
        const obtuse = {
            vertex: [0, 0, 0], from: [1, 0, 0],
            to: [-0.7071067811865476, 0.7071067811865476, 0], normal: [0, 0, 1],
        };

        const points = angleArcPoints(obtuse, 100, 2);

        // cos 67.5, sin 67.5.
        expect(points[1][0]).toBeCloseTo(38.268343, 5);
        expect(points[1][1]).toBeCloseTo(92.387953, 5);
        expect(points[2].map((v) => Math.round(v))).toEqual([-71, 71, 0]);
    });

    test('the label sits past the arc, along its middle', () => {
        const label = angleLabelPoint(square, 100);

        expect(radius(label)).toBeGreaterThan(100);
        expect(label[0]).toBeCloseTo(label[1], 6);
    });

    test('the arc is drawn with enough segments to read as a curve', () => {
        expect(angleArcPoints(square, 100).length).toBeGreaterThan(8);
    });
});

describe('a frame is never stopped by one bad measurement', () => {
    // measureValue runs for every measurement on every frame, inside the render
    // loop. A throw there stops the frame -- which has happened: an arc built
    // from a form that had no direction took the whole viewer down until a
    // reload. A measurement that describes nothing should draw nothing, not
    // stop everything.
    const { measureValue, angleArcPoints, hasDirection } = Measurements;
    const AXES = { look: [0, 0, -1], right: [1, 0, 0], up: [0, 0, 1] };
    const FORMS = [{ form: 'plane' }, { form: 'line' }, { form: 'point' }, { form: 'area' }, {}];
    const KINDS = [
        'angle', 'perpendicular_distance', 'projected_angle',
        'projected_perpendicular_distance', 'projected_horizontal_distance',
        'projected_vertical_distance',
    ];

    test.each(KINDS)('%s answers for every shape of form, however empty', (kind) => {
        for (const a of FORMS) {
            for (const b of FORMS) {
                const value = measureValue(kind, [0, 0, 0], [1, 2, 3], a, b, AXES);
                expect(typeof value.value).toBe('number');
                expect(Number.isNaN(value.value)).toBe(false);
            }
        }
    });

    test('an angle between nothing is zero, not an exception', () => {
        expect(measureValue('projected_angle', [0, 0, 0], [1, 0, 0], {}, {}, AXES))
            .toEqual({ unit: 'angle', value: 0 });
    });

    test('rays of no length describe no corner, so no arc is drawn', () => {
        // Sweeping them would pile identical points on one spot, which reads as
        // a dot sitting on the timber.
        expect(angleArcPoints({ vertex: [0, 0, 0], from: [0, 0, 0], to: [0, 1, 0] }, 10))
            .toEqual([]);
    });

    test('and neither do two rays pointing the same way', () => {
        // Parallel rays span no plane, so there is no way round from one to the
        // other.
        expect(angleArcPoints({ vertex: [0, 0, 0], from: [1, 0, 0], to: [1, 0, 0] }, 10))
            .toEqual([]);
    });

    test('what counts as a direction', () => {
        expect(hasDirection([1, 0, 0])).toBe(true);
        expect(hasDirection([0, 0, 0])).toBe(false);
        expect(hasDirection([NaN, 0, 0])).toBe(false);
        expect(hasDirection([1, 0])).toBe(false);
        expect(hasDirection(null)).toBe(false);
    });
});

describe('which space a measurement is judged in', () => {
    // Three shipped bugs came from this decision, and it was only ever tested
    // through the answers it produced.
    const { measureSpace } = Measurements;

    test('its own kind says, when it has one written structured', () => {
        expect(measureSpace({ kind: { operation: 'angle', space: '3d' } }, {})).toBe('3d');
    });

    test('and that beats what the view says', () => {
        // A measurement carries the space it was taken in. The view it happens
        // to be shown in does not change what it measured.
        expect(measureSpace({ kind: { operation: 'angle', space: '3d' } }, { space: 'projected' }))
            .toBe('3d');
    });

    test('a kind that arrived as a bare name cannot say', () => {
        // `angle` is the solid name AND the pre-spaces projected one.
        expect(measureSpace({ kind: 'angle' }, { space: '3d' })).toBe('3d');
    });

    test('so the view answers instead', () => {
        expect(measureSpace({}, { space: '3d' })).toBe('3d');
    });

    test('and a sheet is what is assumed when nothing says', () => {
        // Only the 3D view has no sheet to project onto.
        expect(measureSpace({}, {})).toBe('projected');
        expect(measureSpace(null, null)).toBe('projected');
    });
});

describe('whether two solid features run together', () => {
    // A normal is not a direction, and getting that backwards calls an edge
    // lying in a face a crossing.
    const { solidParallel, solidForm } = Measurements;
    const face = (normal) => solidForm({ kind: 'plane', normal });
    const edge = (direction) => solidForm({ kind: 'line', direction });

    test('two faces are parallel when their NORMALS align', () => {
        expect(solidParallel(face([0, 0, 1]), face([0, 0, -1]))).toBe(true);
        expect(solidParallel(face([0, 0, 1]), face([1, 0, 0]))).toBe(false);
    });

    test('two edges when their DIRECTIONS do', () => {
        expect(solidParallel(edge([1, 0, 0]), edge([-1, 0, 0]))).toBe(true);
        expect(solidParallel(edge([1, 0, 0]), edge([0, 1, 0]))).toBe(false);
    });

    test('but an edge and a face when they are SQUARE to each other', () => {
        // The edge lies in the plane exactly when it runs across the normal.
        expect(solidParallel(edge([1, 0, 0]), face([0, 0, 1]))).toBe(true);
        expect(solidParallel(edge([0, 0, 1]), face([0, 0, 1]))).toBe(false);
    });

    test('and the answer does not depend on which was picked first', () => {
        expect(solidParallel(face([0, 0, 1]), edge([1, 0, 0])))
            .toBe(solidParallel(edge([1, 0, 0]), face([0, 0, 1])));
    });

    test('a feature with no orientation cannot be compared', () => {
        expect(solidParallel(solidForm({ kind: 'point' }), face([0, 0, 1]))).toBeNull();
    });
});
