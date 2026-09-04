const { MeasureMode, sameReference, STATES } = require('../webview/measure-mode.js');

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

    it('the measurement belongs to the viewport the first pick was in', () => {
        const mode = new MeasureMode();
        mode.pick(face('a').pick, 'front');
        mode.pick(face('b').pick, 'top');

        expect(mode.measurement.viewportId).toBe('front');
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
