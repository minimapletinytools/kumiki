const {
    MeasureDraft, STATES, sameReference, anchorIsMeasurable,
} = require('../webview/measure-draft.js');

const PLANE = { at: [0, 0, 0], normal: [0, 1, 0] };

function anchor(feature, extra = {}) {
    return {
        reference: { timber: 'post#0', csgPath: ['cut'], feature, type: 'FACE' },
        geometry: { kind: 'plane', normal: [0, 0, 1], at: [0, 0, 0] },
        at: [0, 0, 0],
        ...extra,
    };
}

const PARENT_X = { csgPath: ['cut'], feature: 'x' };
const PARENT_Y = { csgPath: ['body'], feature: 'y' };

// Whole parents, so swapping them is what the swap actually means. Swapping
// only the names leaves each path where it was, which is a different edge.
function edgeAnchor(first, second) {
    return {
        reference: { kind: 'edge', timber: 'post#0', a: first, b: second },
        geometry: { kind: 'line', direction: [1, 0, 0], at: [0, 0, 0] },
        at: [0, 0, 0],
    };
}

describe('making a measurement', () => {
    test('it starts idle, holding nothing', () => {
        const draft = new MeasureDraft();

        expect(draft.state).toBe(STATES.IDLE);
        expect(draft.isActive).toBe(false);
        expect(draft.pending).toBeNull();
    });

    test('holding the first feature does not make a measurement yet', () => {
        const draft = new MeasureDraft();

        expect(draft.hold(anchor('a')).action).toBe('holding');
        expect(draft.state).toBe(STATES.HOLDING);
        expect(draft.pending).toBeNull();
    });

    test('the second feature makes one, in the viewport it was picked in', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));

        const result = draft.pick(anchor('b', { plane: PLANE }), 'front');

        expect(result.action).toBe('pending');
        expect(result.pending.a.feature).toBe('a');
        expect(result.pending.b.feature).toBe('b');
        expect(result.pending.viewportId).toBe('front');
    });

    test('the plane comes back with the second anchor', () => {
        // Worked out by the runner from both ends and the camera. Deriving it
        // here as well would be a second copy of a rule.
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));

        draft.pick(anchor('b', { plane: PLANE }), 'front');

        expect(draft.pending.plane).toEqual(PLANE);
    });

    test('no plane is allowed, and means the viewport decides', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));

        draft.pick(anchor('b'), 'front');

        expect(draft.pending.plane).toBeNull();
    });

    test('a third pick corrects the second rather than making another', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));
        draft.pick(anchor('b'), 'front');

        const result = draft.pick(anchor('c'), 'top');

        expect(result.action).toBe('replaced');
        expect(draft.pending.b.feature).toBe('c');
        expect(draft.pending.viewportId).toBe('top');
    });
});

describe('what is refused', () => {
    test('picking before anything is held', () => {
        expect(new MeasureDraft().pick(anchor('a'), 'front').reason).toBe('nothing-held');
    });

    test('the end already held -- it would measure nothing', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));

        expect(draft.pick(anchor('a'), 'front').reason).toBe('same-feature');
    });

    test('a feature nobody declared, which could not be saved', () => {
        const draft = new MeasureDraft();

        expect(draft.hold({ geometry: {}, reference: null }).reason).toBe('no-reference');
    });

    test('a feature lying on no plane or line, which has nothing to measure to', () => {
        const draft = new MeasureDraft();

        expect(draft.hold({ reference: { timber: 't' }, geometry: null }).reason)
            .toBe('not-measurable');
    });

    test('a refused hold leaves the draft as it was', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));

        draft.hold({ reference: null });

        expect(draft.state).toBe(STATES.HOLDING);
        expect(draft.held.reference.feature).toBe('a');
    });

    test('confirming with nothing pending', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));

        expect(draft.confirm().reason).toBe('nothing-pending');
    });
});

describe('escape releases one end at a time', () => {
    // Two presses to leave a half-made measurement. One press throwing away
    // both is the same keystroke doing a small thing and a large one depending
    // on state you cannot see.
    test('the first press releases the second end', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));
        draft.pick(anchor('b'), 'front');

        expect(draft.escape().action).toBe('released-second');
        expect(draft.state).toBe(STATES.HOLDING);
        expect(draft.held.reference.feature).toBe('a');
    });

    test('and forgets which viewport it was going in', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));
        draft.pick(anchor('b', { plane: PLANE }), 'front');

        draft.escape();

        expect(draft.viewportId).toBeNull();
        expect(draft.plane).toBeNull();
    });

    test('the second press leaves the flow', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));
        draft.pick(anchor('b'), 'front');
        draft.escape();

        expect(draft.escape().action).toBe('left');
        expect(draft.isActive).toBe(false);
    });

    test('escaping when nothing is held does nothing', () => {
        expect(new MeasureDraft().escape().action).toBe('none');
    });
});

describe('confirming', () => {
    test('hands back what to write', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));
        draft.pick(anchor('b', { plane: PLANE }), 'front');

        const result = draft.confirm();

        expect(result.action).toBe('confirmed');
        expect(result.measurement.a.feature).toBe('a');
        expect(result.measurement.b.feature).toBe('b');
        expect(result.measurement.plane).toEqual(PLANE);
    });

    test('and leaves nothing behind', () => {
        // Nothing outside the viewer knew it was being made, so there is
        // nothing to tidy up either.
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));
        draft.pick(anchor('b'), 'front');

        draft.confirm();

        expect(draft.state).toBe(STATES.IDLE);
        expect(draft.pending).toBeNull();
        expect(draft.held).toBeNull();
    });

    test('leaving mid-flow says whether anything was held', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('a'));

        expect(draft.leave().action).toBe('left');
        expect(new MeasureDraft().leave().action).toBe('none');
    });
});

describe('comparing references', () => {
    test('the same feature written twice is one feature', () => {
        expect(sameReference(anchor('a').reference, anchor('a').reference)).toBe(true);
    });

    test('different features are not', () => {
        expect(sameReference(anchor('a').reference, anchor('b').reference)).toBe(false);
    });

    test('an edge is the same edge written either way round', () => {
        // The rule DerivedFeaturePath applies when it sorts its parents.
        expect(sameReference(
            edgeAnchor(PARENT_X, PARENT_Y).reference,
            edgeAnchor(PARENT_Y, PARENT_X).reference,
        )).toBe(true);
    });

    test('an edge and a face that share a name are not the same thing', () => {
        expect(sameReference(
            edgeAnchor(PARENT_X, PARENT_Y).reference, anchor('x').reference,
        )).toBe(false);
    });

    test('nothing is never the same as anything', () => {
        expect(sameReference(null, anchor('a').reference)).toBe(false);
    });
});

describe('anchorIsMeasurable', () => {
    test('says yes to a declared feature with geometry', () => {
        expect(anchorIsMeasurable(anchor('a')).ok).toBe(true);
    });

    test('and no, with a reason, to each way of failing', () => {
        expect(anchorIsMeasurable(null).reason).toBe('no-reference');
        expect(anchorIsMeasurable({ reference: null, geometry: {} }).reason)
            .toBe('no-reference');
        expect(anchorIsMeasurable({ reference: { timber: 't' }, geometry: null }).reason)
            .toBe('not-measurable');
    });
});
