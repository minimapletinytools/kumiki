const {
    MeasureMode, couldMeasure, sameReference, STATES,
} = require('../webview/measure-mode.js');

function face(feature, path = ['cut'], timber = 'post#0') {
    return { pick: { reference: { timber, csgPath: path, feature, type: 'FACE' } } };
}

function edge(a, b, timber = 'post#0') {
    return {
        pick: {
            reference: {
                kind: 'edge',
                timber,
                a: { csgPath: ['cut'], feature: a },
                b: { csgPath: ['body'], feature: b },
            },
        },
    };
}

describe('measure mode', () => {
    it('starts off', () => {
        expect(new MeasureMode().state).toBe(STATES.OFF);
        expect(new MeasureMode().isActive).toBe(false);
    });

    it('the first pick enters the mode and holds one end', () => {
        const mode = new MeasureMode();

        const result = mode.pick(face('a').pick, 'front');

        expect(result.action).toBe('from');
        expect(mode.state).toBe(STATES.FROM);
        expect(mode.measurement).toBeNull();
    });

    it('the second pick makes the measurement', () => {
        const mode = new MeasureMode();
        mode.pick(face('a').pick, 'front');

        const result = mode.pick(face('b').pick, 'front');

        expect(result.action).toBe('to');
        expect(mode.state).toBe(STATES.BETWEEN);
        expect(result.measurement.a.feature).toBe('a');
        expect(result.measurement.b.feature).toBe('b');
    });

    it('the measurement belongs to the viewport the second pick was in', () => {
        // The first may be taken from whichever view shows it best; the
        // dimension is drawn where the pair was completed.
        const mode = new MeasureMode();
        mode.pick(face('a').pick, 'front');
        mode.pick(face('b').pick, 'top');

        expect(mode.measurement.viewportId).toBe('top');
    });

    it('re-picking the second end moves the measurement to that view', () => {
        const mode = new MeasureMode();
        mode.pick(face('a').pick, 'front');
        mode.pick(face('b').pick, 'top');

        mode.pick(face('c').pick, 'right');

        expect(mode.measurement.viewportId).toBe('right');
    });

    it('releasing the second end forgets which view it was in', () => {
        const mode = new MeasureMode();
        mode.pick(face('a').pick, 'front');
        mode.pick(face('b').pick, 'top');

        mode.escape();

        expect(mode.viewportId).toBeNull();
    });

    it('a third pick replaces the second rather than making another', () => {
        // The misclick case: one measurement in flight, never two.
        const mode = new MeasureMode();
        mode.pick(face('a').pick, 'front');
        mode.pick(face('b').pick, 'front');

        const result = mode.pick(face('c').pick, 'front');

        expect(result.action).toBe('replaced');
        expect(mode.measurement.b.feature).toBe('c');
        expect(mode.state).toBe(STATES.BETWEEN);
    });

    it('escape from two ends releases the second and keeps the first', () => {
        const mode = new MeasureMode();
        mode.pick(face('a').pick, 'front');
        mode.pick(face('b').pick, 'front');

        const result = mode.escape();

        expect(result.action).toBe('released-to');
        expect(mode.state).toBe(STATES.FROM);
        expect(mode.measurement).toBeNull();
    });

    it('escape from one end leaves the mode', () => {
        const mode = new MeasureMode();
        mode.pick(face('a').pick, 'front');

        const result = mode.escape();

        expect(result.action).toBe('left');
        expect(mode.state).toBe(STATES.OFF);
        expect(mode.isActive).toBe(false);
    });

    it('leaving takes two escapes from two ends', () => {
        const mode = new MeasureMode();
        mode.pick(face('a').pick, 'front');
        mode.pick(face('b').pick, 'front');

        mode.escape();
        mode.escape();

        expect(mode.state).toBe(STATES.OFF);
    });

    it('escape does nothing when nothing is held', () => {
        expect(new MeasureMode().escape().action).toBe('none');
    });

    it('leaving releases both ends at once', () => {
        const mode = new MeasureMode();
        mode.pick(face('a').pick, 'front');
        mode.pick(face('b').pick, 'front');

        expect(mode.leave().action).toBe('left');
        expect(mode.state).toBe(STATES.OFF);
    });

    it('a pick that names no feature is refused', () => {
        // Still drilling down through compounds, so there is nothing to measure.
        const mode = new MeasureMode();

        const result = mode.pick({ path: ['cut'] }, 'front');

        expect(result.action).toBe('refused');
        expect(result.reason).toBe('no-feature');
        expect(mode.state).toBe(STATES.OFF);
    });

    it('measuring a feature to itself is refused', () => {
        const mode = new MeasureMode();
        mode.pick(face('a').pick, 'front');

        const result = mode.pick(face('a').pick, 'front');

        expect(result.action).toBe('refused');
        expect(result.reason).toBe('same-feature');
        expect(mode.state).toBe(STATES.FROM);
    });
});

describe('comparing references', () => {
    it('the same face is the same reference', () => {
        expect(sameReference(face('a').pick.reference, face('a').pick.reference)).toBe(true);
    });

    it('the same feature name on a different node is not', () => {
        expect(sameReference(
            face('a', ['cut']).pick.reference,
            face('a', ['other']).pick.reference,
        )).toBe(false);
    });

    it('the same feature name on a different timber is not', () => {
        expect(sameReference(
            face('a', ['cut'], 'post#0').pick.reference,
            face('a', ['cut'], 'post#1').pick.reference,
        )).toBe(false);
    });

    it('an edge is the same edge written either way round', () => {
        // The rule DerivedFeaturePath applies when it sorts its parents.
        const one = edge('mortise_right', 'rough.left').pick.reference;
        const other = {
            kind: 'edge',
            timber: 'post#0',
            a: { csgPath: ['body'], feature: 'rough.left' },
            b: { csgPath: ['cut'], feature: 'mortise_right' },
        };

        expect(sameReference(one, other)).toBe(true);
    });

    it('an edge and a face are never the same', () => {
        expect(sameReference(
            edge('mortise_right', 'rough.left').pick.reference,
            face('mortise_right').pick.reference,
        )).toBe(false);
    });
});


describe('whether a second pick could finish the measurement', () => {
    const AXES = { look: [0, 1, 0], right: [1, 0, 0], up: [0, 0, 1] };
    const plane = (normal, at) => ({
        geometry: { kind: 'plane', normal, at: [0, 0, 0] },
        at: at || [0, 0, 0],
    });
    const nothing = { geometry: null };

    // Stands in for measurements.availableKinds, so this module stays free of
    // the one that knows about projection.
    const forms = (one, other) => (
        one.kind === 'plane' && other.kind === 'plane' ? ['projected_angle'] : []
    );

    it('says yes when the pair admits something', () => {
        expect(couldMeasure(plane([0, 0, 1]), plane([1, 0, 0]), AXES, forms).ok).toBe(true);
    });

    it('says no when the pair admits nothing', () => {
        const verdict = couldMeasure(plane([0, 0, 1]), { geometry: { kind: 'point' } }, AXES, forms);

        expect(verdict.ok).toBe(false);
        expect(verdict.reason).toBe('not-measurable');
    });

    it('a feature lying on no plane or line cannot be measured against', () => {
        // A cylinder's barrel, a lofted side: good to select, nothing to
        // measure to, and worth saying before the click rather than after.
        const verdict = couldMeasure(plane([0, 0, 1]), nothing, AXES, forms);

        expect(verdict.ok).toBe(false);
        expect(verdict.reason).toBe('not-measurable');
    });

    it('nothing held is nothing to compare against', () => {
        expect(couldMeasure(null, plane([0, 0, 1]), AXES, forms).reason).toBe('nothing-held');
    });

    it('a pair that measures nothing is refused', () => {
        // Two things in line with each other in this view are a good pair
        // whose distance is zero, and a dimension reading zero says nothing
        // while covering what it is drawn over.
        const value = () => 0;

        const verdict = couldMeasure(
            plane([0, 0, 1], [0, 0, 0]), plane([1, 0, 0], [0, 0, 0]), AXES, forms, value);

        expect(verdict.ok).toBe(false);
        expect(verdict.reason).toBe('degenerate');
    });

    it('a pair that measures something is allowed', () => {
        const value = () => 0.05;

        expect(couldMeasure(
            plane([0, 0, 1], [0, 0, 0]), plane([1, 0, 0], [1, 0, 0]), AXES, forms, value,
        ).ok).toBe(true);
    });

    it('without positions it cannot tell, and does not pretend to', () => {
        // No anchor on one of them: the pair is judged on what it admits and
        // nothing more.
        const value = () => 0;

        expect(couldMeasure(
            { geometry: { kind: 'plane', normal: [0, 0, 1] } },
            plane([1, 0, 0]), AXES, forms, value,
        ).ok).toBe(true);
    });
});
