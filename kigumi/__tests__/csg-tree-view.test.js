const { CsgTreeView } = require('../webview/csg-tree-view.js');

// Mirrors the real payload for a mortise-and-tenon butt timber, as dumped from
// runner.serialize_cut_csg_tree. The shape matters: three nodes share the path
// ['mortise_and_tenon'] because untagged nodes inherit their parent's path.
function buttTimberPayload() {
    const cut = (extra) => Object.assign({ jointName: 'joint-a', jointId: '3', cutIndex: 0 }, extra);
    return {
        tree: {
            kind: 'Difference',
            label: null,
            path: [],
            role: null,
            jointName: null,
            jointId: null,
            cutIndex: null,
            features: [],
            children: [
                {
                    kind: 'RectangularPrism',
                    label: null,
                    path: [],
                    role: 'base',
                    jointName: null,
                    jointId: null,
                    cutIndex: null,
                    features: [{ name: 'rough.top', type: 'FACE', group: 'B2', real: true }],
                    children: [],
                },
                cut({
                    kind: 'SolidUnion',
                    label: 'mortise_and_tenon',
                    path: ['mortise_and_tenon'],
                    role: 'subtract',
                    features: [],
                    children: [
                        cut({
                            kind: 'Difference',
                            label: null,
                            path: ['mortise_and_tenon'],
                            role: 'child',
                            features: [],
                            children: [
                                cut({
                                    kind: 'HalfSpace',
                                    label: 'shoulder',
                                    path: ['mortise_and_tenon', 'shoulder'],
                                    role: 'base',
                                    features: [],
                                    children: [],
                                }),
                                cut({
                                    kind: 'RectangularPrism',
                                    label: 'tenon',
                                    path: ['mortise_and_tenon', 'tenon'],
                                    role: 'subtract',
                                    features: [],
                                    children: [],
                                }),
                            ],
                        }),
                        cut({
                            kind: 'HalfSpace',
                            label: null,
                            path: ['mortise_and_tenon'],
                            role: 'child',
                            features: [],
                            children: [],
                        }),
                    ],
                }),
            ],
        },
    };
}

/** A timber cut by two different joints. */
function twoCutPayload() {
    const body = {
        kind: 'RectangularPrism', label: null, path: [], role: 'base',
        jointName: null, jointId: null, cutIndex: null, features: [], children: [],
    };
    const cutNode = (label, jointId, cutIndex) => ({
        kind: 'RectangularPrism', label, path: [label], role: 'subtract',
        jointName: 'joint-' + jointId, jointId, cutIndex, features: [], children: [],
    });
    return {
        tree: {
            kind: 'Difference', label: null, path: [], role: null,
            jointName: null, jointId: null, cutIndex: null, features: [],
            children: [body, cutNode('lap', '7', 0), cutNode('peg', '9', 1)],
        },
    };
}

function allNodes(root) {
    const out = [];
    (function walk(node) {
        out.push(node);
        (node.children || []).forEach(walk);
    })(root);
    return out;
}

describe('splitBodyAndCuts', () => {
    test('unwraps the rendered Difference into body and cuttings', () => {
        const split = CsgTreeView.splitBodyAndCuts(buttTimberPayload().tree);
        expect(split.body.kind).toBe('RectangularPrism');
        expect(split.cuts.map((c) => c.label)).toEqual(['mortise_and_tenon']);
    });

    test('a timber with no cuts is its own body', () => {
        const bare = { kind: 'RectangularPrism', label: null, path: [], children: [] };
        const split = CsgTreeView.splitBodyAndCuts(bare);
        expect(split.body).toBe(bare);
        expect(split.cuts).toEqual([]);
    });

    test('null payload splits to null rather than throwing', () => {
        expect(CsgTreeView.splitBodyAndCuts(null)).toBeNull();
    });
});

describe('timberTree', () => {
    test('is rooted at the body, with cuttings beneath it', () => {
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        expect(root.kind).toBe('RectangularPrism');
        expect(root.role).toBe('body');
        expect(root.children).toHaveLength(1);
        expect(root.children[0].label).toBe('mortise_and_tenon');
        expect(root.children[0].role).toBe('cut');
    });

    test('shows every cutting, each keeping its own joint attribution', () => {
        const root = CsgTreeView.timberTree(twoCutPayload(), 'T1');
        expect(root.children.map((c) => [c.label, c.jointId, c.cutIndex])).toEqual([
            ['lap', '7', 0],
            ['peg', '9', 1],
        ]);
    });

    test('renders a nested Difference as explicit base and cut children', () => {
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        const nested = root.children[0].children[0];
        expect(nested.kind).toBe('Difference');
        expect(nested.children.map((c) => [c.label, c.role])).toEqual([
            ['shoulder', 'base'],
            ['tenon', 'cut'],
        ]);
    });

    test('ids are unique across the whole tree', () => {
        const ids = allNodes(CsgTreeView.timberTree(buttTimberPayload(), 'T1')).map((n) => n.id);
        expect(new Set(ids).size).toBe(ids.length);
    });

    test('ids are namespaced by timber, so two timbers never collide', () => {
        const a = allNodes(CsgTreeView.timberTree(buttTimberPayload(), 'T1')).map((n) => n.id);
        const b = allNodes(CsgTreeView.timberTree(buttTimberPayload(), 'T2')).map((n) => n.id);
        expect(a.filter((id) => b.includes(id))).toEqual([]);
    });
});

describe('jointCuttingTree', () => {
    test('shows the body plus only the cutting asked for', () => {
        const root = CsgTreeView.jointCuttingTree(twoCutPayload(), 'T1', '9', 1);
        expect(root.role).toBe('body');
        expect(root.children.map((c) => c.label)).toEqual(['peg']);
    });

    test('starts at the timber body, so a cutting reads against what it cuts', () => {
        const root = CsgTreeView.jointCuttingTree(buttTimberPayload(), 'T1', '3', 0);
        expect(root.kind).toBe('RectangularPrism');
        expect(root.features.map((f) => f.name)).toEqual(['rough.top']);
    });

    test('a cutting that is not on this timber yields a body with no cuts', () => {
        const root = CsgTreeView.jointCuttingTree(twoCutPayload(), 'T1', '9', 42);
        expect(root.children).toEqual([]);
    });

    test('ids do not collide with the same node under the timber section', () => {
        const payload = twoCutPayload();
        const inTimber = allNodes(CsgTreeView.timberTree(payload, 'T1')).map((n) => n.id);
        const inJoint = allNodes(CsgTreeView.jointCuttingTree(payload, 'T1', '9', 1)).map((n) => n.id);
        expect(inTimber.filter((id) => inJoint.includes(id))).toEqual([]);
    });

    test('two joints on one timber get separate ids', () => {
        const payload = twoCutPayload();
        const first = allNodes(CsgTreeView.jointCuttingTree(payload, 'T1', '7', 0)).map((n) => n.id);
        const second = allNodes(CsgTreeView.jointCuttingTree(payload, 'T1', '9', 1)).map((n) => n.id);
        expect(first.filter((id) => second.includes(id))).toEqual([]);
    });
});

describe('flatten', () => {
    test('a collapsed root is a single row', () => {
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        const rows = CsgTreeView.flatten(root, new Set());
        expect(rows).toHaveLength(1);
        expect(rows[0].hasChildren).toBe(true);
        expect(rows[0].expanded).toBe(false);
    });

    test('expanding a node reveals its children one level down', () => {
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        const rows = CsgTreeView.flatten(root, new Set([root.id]));
        expect(rows.map((r) => r.depth)).toEqual([0, 1]);
        expect(rows[1].label).toBe('mortise_and_tenon');
    });

    test('leaves report no children so they get no chevron', () => {
        const root = CsgTreeView.timberTree(twoCutPayload(), 'T1');
        const rows = CsgTreeView.flatten(root, new Set([root.id]));
        expect(rows.slice(1).every((r) => r.hasChildren === false)).toBe(true);
    });

    test('accepts an array of expanded ids as well as a Set', () => {
        const root = CsgTreeView.timberTree(twoCutPayload(), 'T1');
        expect(CsgTreeView.flatten(root, [root.id])).toHaveLength(3);
    });
});

describe('findByPath', () => {
    test('resolves to the node that owns the label, not an untagged descendant', () => {
        // Three nodes carry ['mortise_and_tenon']; the SolidUnion owns it, and
        // it is what find_csg_by_path resolves to on the python side.
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        const found = CsgTreeView.findByPath(root, ['mortise_and_tenon']);
        expect(found.kind).toBe('SolidUnion');
        expect(found.label).toBe('mortise_and_tenon');
    });

    test('distinguishes a deeper label from its parent', () => {
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        expect(CsgTreeView.findByPath(root, ['mortise_and_tenon', 'tenon']).label).toBe('tenon');
    });

    test('an empty path is the timber body', () => {
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        expect(CsgTreeView.findByPath(root, []).role).toBe('body');
    });

    test('returns null when no node matches', () => {
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        expect(CsgTreeView.findByPath(root, ['nope'])).toBeNull();
    });
});

describe('cutIndexForPath', () => {
    test('reads the cutting off the picked node', () => {
        expect(CsgTreeView.cutIndexForPath(twoCutPayload(), ['peg'])).toBe(1);
    });

    test('a body pick belongs to no cutting', () => {
        expect(CsgTreeView.cutIndexForPath(buttTimberPayload(), [])).toBeNull();
    });

    test('a path deep inside a cutting still reports that cutting', () => {
        expect(CsgTreeView.cutIndexForPath(buttTimberPayload(), ['mortise_and_tenon', 'tenon'])).toBe(0);
    });

    test('an unknown path reports no cutting rather than throwing', () => {
        expect(CsgTreeView.cutIndexForPath(buttTimberPayload(), ['nope'])).toBeNull();
    });
});

describe('ancestorIds', () => {
    test('is the chain from the root down to the node itself', () => {
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        const tenon = CsgTreeView.findByPath(root, ['mortise_and_tenon', 'tenon']);
        const chain = CsgTreeView.ancestorIds(root, tenon.id);
        expect(chain[0]).toBe(root.id);
        expect(chain[chain.length - 1]).toBe(tenon.id);
        expect(chain).toHaveLength(4); // body > union > difference > tenon
    });

    test('an unknown id has no chain', () => {
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        expect(CsgTreeView.ancestorIds(root, 'nope')).toEqual([]);
    });
});

describe('revealTarget', () => {
    const jointFocus = {
        timberKey: 'T1',
        context: { section: 'joints', jointId: '9', cutIndex: 1 },
    };

    test('a pick with no focus reveals in the timber section', () => {
        expect(CsgTreeView.revealTarget(null, { timberKey: 'T1', cutIndex: 0 }))
            .toEqual({ section: 'timbers', timberKey: 'T1' });
    });

    test('a pick while focused in the timber section stays there', () => {
        const focus = { timberKey: 'T1', context: { section: 'timbers' } };
        expect(CsgTreeView.revealTarget(focus, { timberKey: 'T1', cutIndex: 1 }).section)
            .toBe('timbers');
    });

    test('picking the same cutting you are focused on stays in the joint section', () => {
        expect(CsgTreeView.revealTarget(jointFocus, { timberKey: 'T1', cutIndex: 1 })).toEqual({
            section: 'joints', jointId: '9', cutIndex: 1, timberKey: 'T1',
        });
    });

    test('picking the body stays put, since the joint tree shows the body too', () => {
        expect(CsgTreeView.revealTarget(jointFocus, { timberKey: 'T1', cutIndex: null }).section)
            .toBe('joints');
    });

    test('picking a different cutting leaves for the timber section', () => {
        expect(CsgTreeView.revealTarget(jointFocus, { timberKey: 'T1', cutIndex: 0 }).section)
            .toBe('timbers');
    });

    test('picking a different timber leaves for the timber section', () => {
        expect(CsgTreeView.revealTarget(jointFocus, { timberKey: 'T2', cutIndex: 1 }).section)
            .toBe('timbers');
    });
});

describe('describeNode', () => {
    test('shows the base type and the tag together', () => {
        expect(CsgTreeView.describeNode({ kind: 'RectangularPrism', label: 'tenon' }))
            .toBe('RectangularPrism · tenon');
    });

    test('an untagged node shows just its type', () => {
        expect(CsgTreeView.describeNode({ kind: 'HalfSpace', label: null })).toBe('HalfSpace');
    });

    test('a missing node describes as empty rather than throwing', () => {
        expect(CsgTreeView.describeNode(null)).toBe('');
    });
});
