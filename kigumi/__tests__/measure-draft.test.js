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
        expect(draft.heldEnd).toBeNull();
    });

    test('holding the first feature does not make a measurement yet', () => {
        const draft = new MeasureDraft();

        expect(draft.hold(anchor('front'))).toEqual({ action: 'holding' });
        expect(draft.state).toBe(STATES.HOLDING);
    });

    test('there is no state between holding and written', () => {
        // The pending measurement is gone: what is under the pointer IS the
        // measurement, and clicking writes it. See docs/measuring-states.md.
        expect(Object.keys(STATES).sort()).toEqual(['HOLDING', 'IDLE']);
    });

    test('the second feature writes one, and the draft goes idle', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('front'));

        const result = draft.confirm(anchor('back', { plane: PLANE }), 'front-elevation');

        expect(result.action).toBe('confirmed');
        expect(result.measurement.a.feature).toBe('front');
        expect(result.measurement.b.feature).toBe('back');
        expect(result.measurement.viewportId).toBe('front-elevation');
        expect(draft.state).toBe(STATES.IDLE);
    });

    test('the plane comes back with the second end', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('front'));

        const result = draft.confirm(anchor('back', { plane: PLANE }), 'v1');

        expect(result.measurement.plane).toEqual(PLANE);
    });

    test('no plane is allowed, and means the viewport decides', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('front'));

        expect(draft.confirm(anchor('back'), 'v1').measurement.plane).toBeNull();
    });

    test('and nothing is held afterwards', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('front'));
        draft.confirm(anchor('back'), 'v1');

        expect(draft.isActive).toBe(false);
        expect(draft.heldEnd).toBeNull();
    });
});

describe('the end that stays held', () => {
    test('nothing is held to begin with', () => {
        expect(new MeasureDraft().heldEnd).toBeNull();
    });

    test('the first feature, once held', () => {
        const draft = new MeasureDraft();
        const first = anchor('front');
        draft.hold(first);

        expect(draft.heldEnd).toBe(first);
    });

    test('through any number of candidates that are only looked at', () => {
        // Hovering is not picking. The held end has to survive the focus
        // moving to whatever the pointer is over.
        const draft = new MeasureDraft();
        const first = anchor('front');
        draft.hold(first);

        expect(draft.canTake(anchor('back')).ok).toBe(true);
        expect(draft.canTake(anchor('left')).ok).toBe(true);
        expect(draft.heldEnd).toBe(first);
        expect(draft.state).toBe(STATES.HOLDING);
    });

    test('and nothing once the measurement is written', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('front'));
        draft.confirm(anchor('back'), 'v1');

        expect(draft.heldEnd).toBeNull();
    });

    test('holding again starts over rather than adding an end', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('front'));
        const second = anchor('back');
        draft.hold(second);

        expect(draft.heldEnd).toBe(second);
    });
});

describe('what can be taken, and what is refused', () => {
    // canTake answers for the PREVIEW and confirm answers for the CLICK, and
    // they are the same answer -- so what is drawn under the pointer is what
    // clicking takes, by construction.
    const reasons = (draft, candidate) => [
        draft.canTake(candidate).reason,
        draft.confirm(candidate, 'v1').reason,
    ];

    test('nothing can be taken before an end is held', () => {
        const draft = new MeasureDraft();

        expect(reasons(draft, anchor('back'))).toEqual(['nothing-held', 'nothing-held']);
    });

    test('the end already held -- it would measure nothing', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('front'));

        expect(reasons(draft, anchor('front'))).toEqual(['same-feature', 'same-feature']);
    });

    test('a feature nobody declared, which could not be saved', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('front'));

        expect(reasons(draft, { geometry: {}, reference: null }))
            .toEqual(['no-reference', 'no-reference']);
    });

    test('a feature with no line or plane of its own', () => {
        const draft = new MeasureDraft();
        draft.hold(anchor('front'));
        const barrel = { reference: { timber: 'post#0', feature: 'barrel' }, geometry: null };

        expect(reasons(draft, barrel)).toEqual(['not-measurable', 'not-measurable']);
    });

    test('a refusal leaves the held end exactly where it was', () => {
        // The first end is not lost because the second was wrong.
        const draft = new MeasureDraft();
        const first = anchor('front');
        draft.hold(first);

        draft.confirm(anchor('front'), 'v1');

        expect(draft.state).toBe(STATES.HOLDING);
        expect(draft.heldEnd).toBe(first);
    });

    test('an edge written either way round is the same edge', () => {
        const draft = new MeasureDraft();
        draft.hold(edgeAnchor(PARENT_X, PARENT_Y));

        expect(draft.canTake(edgeAnchor(PARENT_Y, PARENT_X)).reason).toBe('same-feature');
    });
});

describe('escape', () => {
    test('releases the held end and leaves', () => {
        // One level now: there is no second end to release separately.
        const draft = new MeasureDraft();
        draft.hold(anchor('front'));

        expect(draft.escape()).toEqual({ action: 'left' });
        expect(draft.state).toBe(STATES.IDLE);
        expect(draft.heldEnd).toBeNull();
    });

    test('and does nothing when nothing is being measured', () => {
        expect(new MeasureDraft().escape()).toEqual({ action: 'none' });
    });
});

describe('leaving', () => {
    test('says whether anything was held', () => {
        const draft = new MeasureDraft();

        expect(draft.leave()).toEqual({ action: 'none' });
        draft.hold(anchor('front'));
        expect(draft.leave()).toEqual({ action: 'left' });
        expect(draft.isActive).toBe(false);
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

describe('the comparable form of a reference', () => {
    // Load-bearing twice over: it decides whether a pick is the end already
    // held, and it is what the held HIGHLIGHT is keyed by, so two references
    // that compare equal must key equal too.
    const { referenceKey } = require('../webview/measure-draft.js');
    const key = (reference) => JSON.stringify(referenceKey(reference));

    test('a plain feature is its timber, path, name and type', () => {
        expect(referenceKey({
            timber: 'post#0', csgPath: ['cut'], feature: 'front', type: 'FACE',
        })).toEqual(['post#0', 'single', 'cut', 'front', 'FACE']);
    });

    test('the same feature on another timber keys differently', () => {
        expect(key({ timber: 'post#0', csgPath: [], feature: 'front' }))
            .not.toBe(key({ timber: 'girt#0', csgPath: [], feature: 'front' }));
    });

    test('and the same name at a different depth does too', () => {
        expect(key({ timber: 'post#0', csgPath: ['cut'], feature: 'front' }))
            .not.toBe(key({ timber: 'post#0', csgPath: ['cut', 'deeper'], feature: 'front' }));
    });

    test('an edge keys the same written either way round', () => {
        // The same two faces make the same edge, and python sorts its parents
        // for exactly this reason.
        const one = { kind: 'edge', timber: 'post#0', a: PARENT_X, b: PARENT_Y };
        const other = { kind: 'edge', timber: 'post#0', a: PARENT_Y, b: PARENT_X };

        expect(key(one)).toBe(key(other));
    });

    test('but two different edges do not', () => {
        const one = { kind: 'edge', timber: 'post#0', a: PARENT_X, b: PARENT_Y };
        const other = {
            kind: 'edge', timber: 'post#0',
            a: PARENT_X, b: { csgPath: ['body'], feature: 'z' },
        };

        expect(key(one)).not.toBe(key(other));
    });

    test('an edge and a plain feature are never the same thing', () => {
        expect(key({ kind: 'edge', timber: 'post#0', a: PARENT_X, b: PARENT_Y }))
            .not.toBe(key({ timber: 'post#0', csgPath: ['cut'], feature: 'x' }));
    });

    test('a parent with nothing in it still keys', () => {
        // References come off the wire; a missing half must not throw where it
        // is used, which is on every frame that draws a held end.
        expect(() => referenceKey({ kind: 'edge', timber: 'post#0', a: null, b: PARENT_Y }))
            .not.toThrow();
    });
});
