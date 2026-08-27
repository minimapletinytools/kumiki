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
    test('is the rendered Difference, with the body as an ordinary child', () => {
        // The body must stay reachable as its own node: hanging the cuts off
        // it would bury the very faces you open the tree to find.
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        expect(root.kind).toBe('Difference');
        expect(root.children.map((c) => [c.kind, c.role])).toEqual([
            ['RectangularPrism', 'base'],
            ['SolidUnion', 'cut'],
        ]);
    });

    test('the body keeps its own features rather than the cuts', () => {
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        const body = root.children[0];
        expect(body.features.map((f) => f.name)).toEqual(['rough.top']);
        expect(body.children).toEqual([]);
    });

    test('an uncut timber is its body, with no Difference wrapping it', () => {
        const bare = {
            tree: {
                kind: 'RectangularPrism', label: null, path: [], role: null,
                features: [], children: [],
            },
        };
        const root = CsgTreeView.timberTree(bare, 'T1');
        expect(root.kind).toBe('RectangularPrism');
        expect(root.children).toEqual([]);
    });

    test('shows every cutting, each keeping its own joint attribution', () => {
        const root = CsgTreeView.timberTree(twoCutPayload(), 'T1');
        const cuts = root.children.filter((c) => c.role === 'cut');
        expect(cuts.map((c) => [c.label, c.jointId, c.cutIndex])).toEqual([
            ['lap', '7', 0],
            ['peg', '9', 1],
        ]);
    });

    test('renders a nested Difference as explicit base and cut children', () => {
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        const nested = root.children[1].children[0];
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
    test('is the timber as this one cutting alone would leave it', () => {
        const root = CsgTreeView.jointCuttingTree(twoCutPayload(), 'T1', '9', 1);
        expect(root.kind).toBe('Difference');
        expect(root.children.map((c) => [c.role, c.label])).toEqual([
            ['base', null],
            ['cut', 'peg'],
        ]);
    });

    test('the body is there in full, so a cutting reads against what it cuts', () => {
        const root = CsgTreeView.jointCuttingTree(buttTimberPayload(), 'T1', '3', 0);
        const body = root.children[0];
        expect(body.kind).toBe('RectangularPrism');
        expect(body.features.map((f) => f.name)).toEqual(['rough.top']);
    });

    test('a cutting that is not on this timber yields the body alone', () => {
        const root = CsgTreeView.jointCuttingTree(twoCutPayload(), 'T1', '9', 42);
        expect(root.kind).toBe('RectangularPrism');
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
        expect(rows.map((r) => r.depth)).toEqual([0, 1, 1]);
        expect(rows[1].role).toBe('base');
        expect(rows[2].label).toBe('mortise_and_tenon');
    });

    test('leaves report no children so they get no chevron', () => {
        const root = CsgTreeView.timberTree(twoCutPayload(), 'T1');
        const rows = CsgTreeView.flatten(root, new Set([root.id]));
        expect(rows.slice(1).every((r) => r.hasChildren === false)).toBe(true);
    });

    test('accepts an array of expanded ids as well as a Set', () => {
        const root = CsgTreeView.timberTree(twoCutPayload(), 'T1');
        // root + body + two cuts
        expect(CsgTreeView.flatten(root, [root.id])).toHaveLength(4);
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

    test('an empty path resolves to the tree root', () => {
        // Shallowest-wins is justified by label ownership, and an empty path
        // owns no label -- it means the pick found no labelled ancestor at
        // all. The root is then the honest answer: the path alone cannot say
        // which unlabelled node was hit, and it is what find_csg_by_path
        // resolves to, so the 3D highlight agrees.
        const root = CsgTreeView.timberTree(buttTimberPayload(), 'T1');
        expect(CsgTreeView.findByPath(root, [])).toBe(root);
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
        expect(CsgTreeView.describeNode(
            { kind: 'RectangularPrism', displayName: 'prism', label: 'tenon' },
        )).toBe('prism · tenon');
    });

    test('an untagged node shows just its type', () => {
        expect(CsgTreeView.describeNode(
            { kind: 'HalfSpace', displayName: 'half-space', label: null },
        )).toBe('half-space');
    });

    test('falls back to the class name when no display name came through', () => {
        expect(CsgTreeView.describeNode({ kind: 'HalfSpace', label: null })).toBe('HalfSpace');
    });

    test('a missing node describes as empty rather than throwing', () => {
        expect(CsgTreeView.describeNode(null)).toBe('');
    });
});

describe('describePickTail', () => {
    const NOUNS = { FACE: 'face', EDGE: 'edge', POINT: 'point' };

    test('a picked face names itself as a face', () => {
        expect(CsgTreeView.describePickTail(
            { featureLabel: 'tenon_back', featureType: 'FACE', nodeKind: 'RectangularPrism' },
            NOUNS,
        )).toBe('face (tenon_back)');
    });

    test('a picked edge is an edge, not a face', () => {
        // The wording used to be hardcoded, so an arris read as a face.
        expect(CsgTreeView.describePickTail(
            { featureLabel: 'rough.front×rough.right', featureType: 'EDGE', nodeKind: 'RectangularPrism' },
            NOUNS,
        )).toBe('edge (rough.front×rough.right)');
    });

    test('a whole node says what it is instead of naming a face', () => {
        // Regression: an ordinary click descends one level at a time and
        // selects compounds on the way down. Those reported a descendant's
        // face while the highlight lit the entire union.
        expect(CsgTreeView.describePickTail(
            { featureLabel: null, featureType: null, nodeKind: 'SolidUnion',
              nodeDisplayName: 'union' },
            NOUNS,
        )).toBe('union');
    });

    test('a named node gives its kind and its name together', () => {
        expect(CsgTreeView.describePickTail(
            { featureLabel: null, nodeDisplayName: 'difference', nodeLabel: 'tenon_waste' },
            NOUNS,
        )).toBe('difference (tenon_waste)');
    });

    test('a feature is named by the feature, not by the node it sits on', () => {
        expect(CsgTreeView.describePickTail(
            { featureLabel: 'tenon_back', featureType: 'FACE',
              nodeDisplayName: 'prism', nodeLabel: 'tenon' },
            NOUNS,
        )).toBe('face (tenon_back)');
    });

    test('an older runner without a display name still reads as something', () => {
        expect(CsgTreeView.describePickTail(
            { featureLabel: null, nodeKind: 'SolidUnion' }, NOUNS,
        )).toBe('SolidUnion');
    });

    test('an unknown feature type still reads as something', () => {
        expect(CsgTreeView.describePickTail(
            { featureLabel: 'x', featureType: 'WHAT', nodeKind: 'Cylinder' }, NOUNS,
        )).toBe('feature (x)');
    });

    test('the nouns are optional', () => {
        expect(CsgTreeView.describePickTail({ featureLabel: 'x', featureType: 'FACE' }))
            .toBe('feature (x)');
    });

    test('nothing picked describes as nothing', () => {
        expect(CsgTreeView.describePickTail(null, NOUNS)).toBeNull();
        expect(CsgTreeView.describePickTail({}, NOUNS)).toBeNull();
    });
});

describe('breadcrumbSegments', () => {
    const NOUNS = { FACE: 'face', EDGE: 'edge', POINT: 'point' };

    test('a selected node appears once, not as label then kind', () => {
        // Regression: the path already ends with the node's own label, so
        // appending its kind rendered one node as two levels --
        // "mortise_and_tenon > union" for a single union.
        expect(CsgTreeView.breadcrumbSegments('post', ['mortise_and_tenon'], {
            featureLabel: null, nodeDisplayName: 'union', nodeLabel: 'mortise_and_tenon',
        }, NOUNS)).toEqual(['post', 'union (mortise_and_tenon)']);
    });

    test('ancestors stay in the trail', () => {
        expect(CsgTreeView.breadcrumbSegments(
            'post', ['mortise_and_tenon', 'tenon_waste'],
            { featureLabel: null, nodeDisplayName: 'difference', nodeLabel: 'tenon_waste' },
            NOUNS,
        )).toEqual(['post', 'mortise_and_tenon', 'difference (tenon_waste)']);
    });

    test('a picked feature keeps the node it sits on in the trail', () => {
        // Folding here would lose the tenon entirely: the node is a real
        // ancestor of the face, not the thing selected.
        expect(CsgTreeView.breadcrumbSegments(
            'post', ['mortise_and_tenon', 'tenon_waste', 'tenon'],
            { featureLabel: 'tenon_back', featureType: 'FACE',
              nodeDisplayName: 'prism', nodeLabel: 'tenon' },
            NOUNS,
        )).toEqual(['post', 'mortise_and_tenon', 'tenon_waste', 'tenon', 'face (tenon_back)']);
    });

    test('an unlabelled node leaves its parent trail alone', () => {
        expect(CsgTreeView.breadcrumbSegments('post', ['miter_cut'], {
            featureLabel: null, nodeDisplayName: 'half-space', nodeLabel: null,
        }, NOUNS)).toEqual(['post', 'miter_cut', 'half-space']);
    });

    test('a label that matches an ancestor rather than the node is not dropped', () => {
        // Only the LAST segment can be the selected node's own label.
        expect(CsgTreeView.breadcrumbSegments('post', ['lap_cut', 'other'], {
            featureLabel: null, nodeDisplayName: 'prism', nodeLabel: 'lap_cut',
        }, NOUNS)).toEqual(['post', 'lap_cut', 'other', 'prism (lap_cut)']);
    });

    test('just the timber when nothing is picked', () => {
        expect(CsgTreeView.breadcrumbSegments('post', [], null, NOUNS)).toEqual(['post']);
    });
});

describe('describeOutwardNormal', () => {
    const PHRASE = 'approximately facing {face}';

    test('shows the exact normal and the face it approximates', () => {
        expect(CsgTreeView.describeOutwardNormal([0, 0, 1], 'top', PHRASE))
            .toBe('0.000, 0.000, 1.000 (approximately facing top)');
    });

    test('an off-axis normal shows how far off it is', () => {
        // The whole reason both are shown: rounding to the nearest of six
        // would hide that this is 45 degrees off either face.
        expect(CsgTreeView.describeOutwardNormal([0, 0.7071, 0.7071], 'front', PHRASE))
            .toBe('0.000, 0.707, 0.707 (approximately facing front)');
    });

    test('negative zero reads as zero', () => {
        expect(CsgTreeView.describeOutwardNormal([-0, -1e-9, 1], 'top', PHRASE))
            .toBe('0.000, 0.000, 1.000 (approximately facing top)');
    });

    test('a sign is kept when it is real', () => {
        expect(CsgTreeView.describeOutwardNormal([-1, 0, 0], 'left', PHRASE))
            .toBe('-1.000, 0.000, 0.000 (approximately facing left)');
    });

    test('without a face name it is just the vector', () => {
        expect(CsgTreeView.describeOutwardNormal([0, 0, 1], null, PHRASE))
            .toBe('0.000, 0.000, 1.000');
    });

    test('no normal describes as nothing', () => {
        expect(CsgTreeView.describeOutwardNormal(null, 'top', PHRASE)).toBeNull();
        expect(CsgTreeView.describeOutwardNormal([0, 1], 'top', PHRASE)).toBeNull();
    });
});

describe('an undeclared feature is not given a name', () => {
    const NOUNS = { FACE: 'face', EDGE: 'edge', POINT: 'point' };

    test('a guessed direction is not printed as the feature name', () => {
        // Regression: this read "feature (top)", where "top" was
        // _detect_face_label's guess at the direction -- not a name, and not
        // sign-corrected either, so it could name the opposite face.
        expect(CsgTreeView.describePickTail(
            { featureLabel: 'top', featureType: null, nodeDisplayName: 'prism' }, NOUNS,
        )).toBe('feature');
    });

    test('a declared feature still shows its name', () => {
        expect(CsgTreeView.describePickTail(
            { featureLabel: 'tenon_back', featureType: 'FACE', nodeDisplayName: 'prism' }, NOUNS,
        )).toBe('face (tenon_back)');
    });

    test('the breadcrumb keeps the node trail either way', () => {
        expect(CsgTreeView.breadcrumbSegments('post', ['lap_cut'], {
            featureLabel: 'top', featureType: null, nodeDisplayName: 'prism', nodeLabel: 'lap_cut',
        }, NOUNS)).toEqual(['post', 'lap_cut', 'feature']);
    });
});
