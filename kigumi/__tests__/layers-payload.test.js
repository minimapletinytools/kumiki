const { KigumiLayersView } = require('../webview/layers-panel.js');

// _convertRunnerPayload joins the runner's kumiki ids to viewer member keys.
// It is a silent join: a mismatch produces an empty list rather than an error,
// so the joint section would just quietly show nothing.
function convert(payload) {
    const view = Object.create(KigumiLayersView.prototype);
    return view._convertRunnerPayload(payload);
}

const TIMBERS = [
    { kumikiEphemeralId: 1, memberKey: 'T1', name: 'post', tags: ['load'] },
    { kumikiEphemeralId: 2, memberKey: 'T2', name: 'beam' },
];

describe('layers payload conversion', () => {
    test('timbers keep their key, name and tags', () => {
        const { timbers } = convert({ timbers: TIMBERS });
        expect(timbers).toEqual([
            { key: 'T1', name: 'post', tags: ['load'] },
            { key: 'T2', name: 'beam', tags: [] },
        ]);
    });

    test('a joint lists one cutting per cut index', () => {
        // The joint section renders a row per cutting, so a member cut twice
        // by one joint has to survive as two entries, not one.
        const { joints } = convert({
            timbers: TIMBERS,
            joints: [{
                kumikiEphemeralId: 9,
                name: 'lap',
                members: [{ timberKumikiEphemeralId: 1, cutIndices: [0, 2] }],
            }],
        });
        expect(joints[0].cuttings).toEqual([
            { timberKey: 'T1', cutIndex: 0 },
            { timberKey: 'T1', cutIndex: 2 },
        ]);
    });

    test('cuttings span every member of the joint', () => {
        const { joints } = convert({
            timbers: TIMBERS,
            joints: [{
                kumikiEphemeralId: 9,
                name: 'lap',
                members: [
                    { timberKumikiEphemeralId: 1, cutIndices: [0] },
                    { timberKumikiEphemeralId: 2, cutIndices: [1] },
                ],
            }],
        });
        expect(joints[0].cuttings).toEqual([
            { timberKey: 'T1', cutIndex: 0 },
            { timberKey: 'T2', cutIndex: 1 },
        ]);
        expect(joints[0].timberKeys).toEqual(['T1', 'T2']);
    });

    test('a member the frame does not know about is dropped, not faked', () => {
        const { joints } = convert({
            timbers: TIMBERS,
            joints: [{
                kumikiEphemeralId: 9,
                name: 'lap',
                members: [{ timberKumikiEphemeralId: 404, cutIndices: [0] }],
            }],
        });
        expect(joints[0].cuttings).toEqual([]);
    });

    test('a member with no cut indices contributes no cuttings', () => {
        const { joints } = convert({
            timbers: TIMBERS,
            joints: [{ kumikiEphemeralId: 9, name: 'lap', members: [{ timberKumikiEphemeralId: 1 }] }],
        });
        expect(joints[0].cuttings).toEqual([]);
        expect(joints[0].timberKeys).toEqual(['T1']);
    });

    test('an empty payload converts to empty lists rather than throwing', () => {
        expect(convert({})).toEqual({ timbers: [], joints: [] });
    });
});
