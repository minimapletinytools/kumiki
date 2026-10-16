const { MAX_MEMBERS, canCopy, describeSelection } = require('../webview/selection-copy.js');

describe('when there is something to copy', () => {
    test('a feature, however many members', () => {
        expect(canCopy(0, true)).toBe(true);
        expect(canCopy(9, true)).toBe(true);
    });

    test('one to four members', () => {
        expect(canCopy(1, false)).toBe(true);
        expect(canCopy(MAX_MEMBERS, false)).toBe(true);
    });

    test('not nothing, and not more than four', () => {
        expect(canCopy(0, false)).toBe(false);
        expect(canCopy(MAX_MEMBERS + 1, false)).toBe(false);
    });
});

describe('what is copied', () => {
    const post = {
        key: 'Left Post#0', name: 'Left Post', type: 'timber',
        width: 0.09, height: 0.09, length: 2.4,
        placement: { bottom_position: [0, 0, 0], length_direction: [0, 0, 1], width_direction: [1, 0, 0] },
        tags: [{ kind: 'member', name: 'post' }],
    };

    test('a member: its name, key, size, placement and tags, in metres', () => {
        const text = describeSelection({ sourceFile: 'frame.py', frameName: 'Shed', members: [post] });

        expect(text).toContain('frame "Shed" in frame.py');
        expect(text).toContain('Timber "Left Post" (member key Left Post#0)');
        expect(text).toContain('size: 0.09 x 0.09 m, length 2.4 m');
        expect(text).toContain('bottom position: [0, 0, 0]');
        expect(text).toContain('length direction: [0, 0, 1]');
        expect(text).toContain('tags: member:post');
    });

    test('a feature: where it is, and the reference that finds it again', () => {
        const reference = { timber: 'Left Post#0', csgPath: ['timber (rough, extended)'], feature: 'rptw.front', type: 'FACE' };
        const text = describeSelection({
            members: [post],
            feature: {
                timberName: 'Left Post', memberKey: 'Left Post#0', path: 'timber (rough, extended)',
                featureLabel: 'rptw.front', featureType: 'FACE', jointName: null,
                geometry: { kind: 'plane', at: [0, 0.045, 1.2], normal: [0, 1, 0] },
                reference,
            },
        });

        expect(text).toContain('Feature "rptw.front" (face) on timber "Left Post"');
        expect(text).toContain('plane: at [0, 0.045, 1.2], normal [0, 1, 0]');
        expect(text).toContain(`reference: ${JSON.stringify(reference)}`);
        // The feature is the selection; the timber it is on is not listed again.
        expect(text).not.toContain('size:');
    });

    test('an accessory has no placement to give', () => {
        const text = describeSelection({
            members: [{ key: 'accessory:Peg#0', name: 'Peg 1', type: 'accessory', width: null, height: null,
                length: null, placement: null, tags: [] }],
        });

        expect(text).toContain('Accessory "Peg 1"');
        expect(text).not.toContain('position');
    });

    describe('a row of the layers tree', () => {
        const node = {
            path: ['free_dovetail#3', 'dovetail'], kind: 'ConvexPolygonSimpleLoft', displayName: 'loft',
            label: 'dovetail', role: 'cut', jointName: 'free_dovetail',
            features: [{ name: 'dovetail_neck', type: 'FACE' }, { name: 'dovetail_neck×dovetail_right_flank', type: 'EDGE' }],
        };
        const csg = { kind: 'csg', timberName: 'beam', memberKey: 'beam#0', path: node.path, node };

        test('is copied as its fully qualified name', () => {
            expect(describeSelection({ sourceFile: 'patterns/sawhorse.py', item: csg }))
                .toBe('patterns/sawhorse.py \u203a beam \u203a free_dovetail#3 \u203a dovetail\n');
            expect(describeSelection({ item: { kind: 'joint', name: 'free_dovetail#3', timbers: ['beam'] } }))
                .toBe('joint free_dovetail#3\n');
        });

        test('or with details: what the node is and what made it, but not every feature it names', () => {
            const text = describeSelection({ sourceFile: 'patterns/sawhorse.py', frameName: 'Sawhorse', item: csg, detailed: true });

            expect(text).toContain('frame "Sawhorse" in patterns/sawhorse.py');
            expect(text).toContain('- "dovetail" (loft) on timber "beam" (member key beam#0)');
            expect(text).toContain('path: beam \u203a free_dovetail#3 \u203a dovetail');
            expect(text).toContain('joint: free_dovetail');
            expect(text).not.toContain('dovetail_neck×dovetail_right_flank');
        });

        test('a measurement names its drawing and ends, and in detail what each end refers to', () => {
            const measurement = {
                kind: 'measurement', drawing: '3D', viewport: null, between: 'rptw.front / dovetail_neck',
                anchors: [
                    { describes: 'beam > rptw.front', reference: { timber: 'beam', csgPath: [], feature: 'rptw.front' } },
                    { describes: 'beam > free_dovetail#3 > dovetail > dovetail_neck', reference: null },
                ],
                measureKind: 'distance', value: '0.0254 m', origin: 'file', refused: null,
            };

            expect(describeSelection({ sourceFile: 'sawhorse.py', item: measurement }))
                .toBe('sawhorse.py \u203a drawing 3D \u203a measurement rptw.front / dovetail_neck\n');
            const text = describeSelection({ item: measurement, detailed: true });
            expect(text).toContain('value: 0.0254 m');
            expect(text).toContain('from: beam > rptw.front');
            expect(text).toContain('reference: {"timber":"beam","csgPath":[],"feature":"rptw.front"}');
            expect(text).toContain('to: beam > free_dovetail#3 > dovetail > dovetail_neck');
        });

        test('a tag lists who wears it', () => {
            const text = describeSelection({
                item: { kind: 'tag', tagKind: 'generic', name: 'wonky', members: ['beam', 'leg'] }, detailed: true,
            });

            expect(text).toContain('- Tag generic:wonky');
            expect(text).toContain('members: beam, leg');
        });
    });
});
