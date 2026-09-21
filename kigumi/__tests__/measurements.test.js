const {
    dimensionLayout, DEGENERATE_PIXELS,
} = require('../webview/measurements.js');

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

const { angleLayout } = require('../webview/measurements.js');

// A front elevation: looking north, x across the sheet and z up it.
const FRONT = { look: [0, 1, 0], right: [1, 0, 0], up: [0, 0, 1] };

const face = (normal) => ({ kind: 'plane', normal });
const edge = (direction) => ({ kind: 'line', direction });

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

    //: What the runner sends with it. The number is worked out there now, so
    //: these check which views will draw it, not what it comes to.
    const SETTLED = {
        kind: { operation: 'distance', space: 'projected', direction: 'perpendicular' },
        available: ['projected_perpendicular_distance'],
        space: 'projected',
        value: { unit: 'length', value: Math.SQRT2 },
        reason: null,
        a: { form: 'point' },
        b: { form: 'point' },
    };

    const pair = (plane) => ({
        a: point([0, 0, 0]), b: point([1, 0, 1]), plane, settled: SETTLED,
    });

    test('with no plane there is nothing to refuse it for', () => {
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

    test('the value is the runner\'s, so no camera can move it', () => {
        // It used to be worked out here against axes.look, which for a
        // measurement carrying no plane made the same two points read as their
        // separation from one angle and their diagonal from another. Now the
        // number arrives settled and every view reports the same one.
        const seen = [AXES, { look: [1, 0, 0], right: [0, 1, 0], up: [0, 0, 1] },
                      { look: [0, 0, 1], right: [1, 0, 0], up: [0, 1, 0] }]
            .map((axes) => measurementStatus(pair(undefined), axes, PERSPECTIVE).value.value);

        expect(seen).toEqual([Math.SQRT2, Math.SQRT2, Math.SQRT2]);
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

describe('naming a kind, and writing one back', () => {
    const { kindName, kindWire, measurementStatus } = Measurements;

    test('a structured kind composes to its name', () => {
        expect(kindName({ operation: 'distance', space: 'projected', direction: 'horizontal' }))
            .toBe('projected_horizontal_distance');
        expect(kindName({ operation: 'angle', space: '3d' })).toBe('angle');
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
    // The arc is built for every angle on every frame, inside the render loop.
    // A throw there stops the frame -- which has happened: an arc built from a
    // form that had no direction took the whole viewer down until a reload. A
    // measurement that describes nothing should draw nothing, not stop
    // everything.
    //
    // What a measurement comes to is the runner's now, so the value side of
    // this lives with it -- see TestWhatTheRunnerSettles. What is still drawn
    // from numbers here is the arc, and these are its edges.
    const { angleArcPoints, hasDirection } = Measurements;

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

describe('the runner settles what a measurement comes to', () => {
    // The value does not depend on the camera -- a measurement carries the
    // plane it was taken on -- so it is worked out once, where the anchors are
    // resolved, and sent with them. This file used to work it out again on
    // every frame from its own copy of the rules, which is how two answers to
    // one question drift apart.
    const AXES = { look: [0, -1, 0], right: [1, 0, 0], up: [0, 0, 1] };
    const ORTHO = { orthographic: true };
    const point = (at) => ({ at, geometry: { kind: 'point', at } });

    const settled = (over) => Object.assign({
        kind: { operation: 'distance', space: 'projected', direction: 'perpendicular' },
        available: ['projected_perpendicular_distance'],
        space: 'projected',
        value: { unit: 'length', value: 0.125 },
        reason: null,
        a: { form: 'point' },
        b: { form: 'point' },
    }, over || {});

    const measure = (over) => Object.assign({
        a: point([0, 0, 0]), b: point([1, 0, 1]), settled: settled(),
    }, over || {});

    test('the number drawn is the one the runner sent', () => {
        // Deliberately not what this file would work out for the same two
        // points, which is the diagonal. If the sent value did not win, this
        // reads SQRT2.
        const status = measurementStatus(measure(), AXES, ORTHO);

        expect(status.drawable).toBe(true);
        expect(status.value.value).toBe(0.125);
    });

    test('and so is the kind, by its composed name', () => {
        expect(measurementStatus(measure(), AXES, ORTHO).kind)
            .toBe('projected_perpendicular_distance');
    });

    test('and the kinds it offers to change to', () => {
        const status = measurementStatus(
            measure({ settled: settled({ available: ['projected_angle'] }) }), AXES, ORTHO);

        expect(status.available).toEqual(['projected_angle']);
    });

    test('a refusal arrives with it, rather than being re-derived', () => {
        const status = measurementStatus(
            measure({ settled: settled({ reason: 'degenerate', value: null }) }), AXES, ORTHO);

        expect(status.drawable).toBe(false);
        expect(status.reason).toBe('degenerate');
    });

    test('the forms come across too, so nothing here classifies a feature', () => {
        const status = measurementStatus(
            measure({ settled: settled({ a: { form: 'plane', normal: [0, 0, 1] } }) }),
            AXES, ORTHO);

        expect(status.formA).toEqual({ form: 'plane', normal: [0, 0, 1] });
    });

    test('but whether THIS view shows that plane is still asked here', () => {
        // The one question a settled answer cannot carry: it is about the
        // camera, which belongs to the reader and moves.
        const status = measurementStatus(
            measure({ plane: { at: [0, 0, 0], normal: [1, 0, 0] } }), AXES, ORTHO);

        expect(status.drawable).toBe(false);
        expect(status.reason).toBe('plane-mismatch');
    });

    test('an unresolved measurement is still refused before anything else', () => {
        const status = measurementStatus(
            measure({ unresolved: ['a'] }), AXES, ORTHO);

        expect(status.reason).toBe('unresolved');
    });

    test('without one it is refused, not worked out here', () => {
        // The runner sends an answer for every measurement it can place and a
        // refusal for every one it cannot, warning on the latter. So a
        // measurement with neither came from some path that predates that, and
        // inventing a number for it is what this file stopped doing: it could
        // only judge against whatever camera was showing, which is the drift
        // a measurement's own plane exists to prevent.
        const status = measurementStatus(
            measure({ settled: undefined }), AXES, ORTHO);

        expect(status.drawable).toBe(false);
        expect(status.reason).toBe('not-settled');
    });
});
