const { highlightsFor, CSG_COLORS, HOVER_COLOR, HOVER_REFUSED_COLOR, HELD_COLOR, ORDER } =
    require('../webview/highlights.js');

// What should be lit, as a list. The old shape built each overlay when its
// message arrived and tore it down by one of seven scattered calls, so there was
// nothing to test: "should this exist" was never asked anywhere.

const MESH = { vertices: [0, 0, 0, 1, 0, 0, 0, 1, 0], indices: [0, 1, 2] };
const EDGES = [0, 0, 0, 1, 0, 0];
const POLICY = {
    csgHighlightOpacity: 0.7,
    parentHighlightOpacity: 0.35,
    featureHighlightOpacity: 0.9,
};

const ids = (list) => list.map((one) => one.id);
const byId = (list, prefix) => list.find((one) => one.id.startsWith(prefix));

describe('nothing is lit when nothing asks to be', () => {
    test('an empty state lights nothing', () => {
        expect(highlightsFor({})).toEqual([]);
    });

    test('and so does no state at all', () => {
        expect(highlightsFor(null)).toEqual([]);
    });

    test('a source with no geometry lights nothing', () => {
        // A cylinder's barrel is selectable and has no mesh to light.
        const lit = highlightsFor({
            csg: { key: 'post#0', mesh: null, parentMesh: null, edgePositions: [] },
            policy: POLICY,
        });

        expect(lit).toEqual([]);
    });
});

describe('what a selection lights', () => {
    test('a tagged node on its own is one mesh, in the tagged colour', () => {
        const lit = highlightsFor({
            csg: { key: 'post#0/cut', mesh: MESH, featureLabel: null }, policy: POLICY,
        });

        expect(ids(lit)).toEqual(['csg-node:post#0/cut']);
        expect(lit[0].color).toBe(CSG_COLORS.tagged);
        expect(lit[0].opacity).toBe(POLICY.csgHighlightOpacity);
    });

    test('a feature inside one lights both, the parent dim and the feature bright', () => {
        const lit = highlightsFor({
            csg: {
                key: 'post#0/cut/front', featureLabel: 'front',
                mesh: MESH, parentMesh: MESH,
            },
            policy: POLICY,
        });

        expect(ids(lit)).toEqual(['csg-parent:post#0/cut/front', 'csg-feature:post#0/cut/front']);
        expect(byId(lit, 'csg-parent').opacity).toBe(POLICY.parentHighlightOpacity);
        expect(byId(lit, 'csg-feature').opacity).toBe(POLICY.featureHighlightOpacity);
        expect(byId(lit, 'csg-feature').color).toBe(CSG_COLORS.feature);
    });

    test('a feature whose parent has no mesh falls back to the node rule', () => {
        const lit = highlightsFor({
            csg: { key: 'post#0/cut/front', featureLabel: 'front', mesh: MESH, parentMesh: null },
            policy: POLICY,
        });

        expect(ids(lit)).toEqual(['csg-node:post#0/cut/front']);
    });

    test('an edge is lit as a line, not as the triangles beside it', () => {
        // Shading those lit a stray wedge that read as geometry.
        const lit = highlightsFor({
            csg: { key: 'post#0/arris.1', edgePositions: EDGES, mesh: null }, policy: POLICY,
        });

        expect(ids(lit)).toEqual(['csg-edges:post#0/arris.1']);
        expect(lit[0].shape).toBe('edges');
    });
});

describe('what the pointer lights', () => {
    test('a candidate the click will take, in the hover colour', () => {
        const lit = highlightsFor({
            hover: { key: 'girt#0/back', mesh: MESH, refused: false }, policy: POLICY,
        });

        expect(byId(lit, 'hover-mesh').color).toBe(HOVER_COLOR);
    });

    test('and one it will refuse, in red', () => {
        const lit = highlightsFor({
            hover: { key: 'girt#0/back', mesh: MESH, refused: true }, policy: POLICY,
        });

        expect(byId(lit, 'hover-mesh').color).toBe(HOVER_REFUSED_COLOR);
    });

    test('the same feature keeps its id when the verdict changes', () => {
        // Identity is WHICH thing is lit. The colour rides alongside, so a
        // verdict changing under a resting pointer recolours rather than
        // rebuilds -- and cannot be missed, because the list is asked again.
        const allowed = highlightsFor({ hover: { key: 'girt#0/back', mesh: MESH }, policy: POLICY });
        const refused = highlightsFor({
            hover: { key: 'girt#0/back', mesh: MESH, refused: true }, policy: POLICY,
        });

        expect(ids(allowed)).toEqual(ids(refused));
        expect(byId(allowed, 'hover-mesh').color)
            .not.toBe(byId(refused, 'hover-mesh').color);
    });
});

describe('what a held end lights', () => {
    test('its own colour, so held does not read as selected', () => {
        const lit = highlightsFor({ held: { key: 'post#0/left', mesh: MESH }, policy: POLICY });

        expect(byId(lit, 'held-mesh').color).toBe(HELD_COLOR);
    });

    test('and it outlives the selection moving off it', () => {
        // The first end is HELD, not selected: picking the second moves the
        // focus away, and it has to survive that.
        const lit = highlightsFor({
            csg: { key: 'girt#0/front', featureLabel: 'front', mesh: MESH },
            held: { key: 'post#0/left', mesh: MESH },
            policy: POLICY,
        });

        expect(byId(lit, 'held-mesh')).toBeDefined();
        expect(byId(lit, 'csg-node')).toBeDefined();
    });
});

describe('what is drawn over what', () => {
    test('held over hover over selection', () => {
        const lit = highlightsFor({
            csg: { key: 'a', mesh: MESH },
            hover: { key: 'b', mesh: MESH },
            held: { key: 'c', mesh: MESH },
            policy: POLICY,
        });
        const order = (prefix) => byId(lit, prefix).renderOrder;

        expect(order('csg-node')).toBeLessThan(order('hover-mesh'));
        expect(order('hover-mesh')).toBeLessThan(order('held-mesh'));
    });

    test('and no two of them share an order', () => {
        // Held and the hover outline both sat at 1101, which left which one
        // won undefined -- and they are the two most likely to overlap, since
        // the pointer is usually beside the thing being held.
        const orders = Object.values(ORDER);

        expect(new Set(orders).size).toBe(orders.length);
    });

    test('an edge sits over the mesh it belongs to', () => {
        expect(ORDER.csgEdges).toBeGreaterThan(ORDER.csgMesh);
        expect(ORDER.hoverEdges).toBeGreaterThan(ORDER.hoverMesh);
        expect(ORDER.heldEdges).toBeGreaterThan(ORDER.heldMesh);
    });
});

describe('identity is what the reconciler keeps', () => {
    test('the same state asked twice gives the same ids', () => {
        const state = {
            csg: { key: 'post#0/cut/front', featureLabel: 'front', mesh: MESH, parentMesh: MESH },
            hover: { key: 'girt#0/back', mesh: MESH },
            held: { key: 'post#0/left', mesh: MESH },
            policy: POLICY,
        };

        expect(ids(highlightsFor(state))).toEqual(ids(highlightsFor(state)));
    });

    test('every id is unique, so nothing overwrites anything', () => {
        const lit = highlightsFor({
            csg: { key: 'k', featureLabel: 'front', mesh: MESH, parentMesh: MESH, edgePositions: EDGES },
            hover: { key: 'k', mesh: MESH, edgePositions: EDGES },
            held: { key: 'k', mesh: MESH, edgePositions: EDGES },
            policy: POLICY,
        });

        expect(new Set(ids(lit)).size).toBe(lit.length);
        expect(lit.length).toBe(7);
    });

    test('a different feature is a different id', () => {
        const one = highlightsFor({ hover: { key: 'girt#0/back', mesh: MESH } });
        const other = highlightsFor({ hover: { key: 'girt#0/front', mesh: MESH } });

        expect(ids(one)).not.toEqual(ids(other));
    });

    test('opacity is not part of identity', () => {
        // It follows the selection state, so folding it into the id would
        // rebuild the geometry every time the selection deepened.
        const dim = highlightsFor({ csg: { key: 'k', mesh: MESH }, policy: POLICY });
        const bright = highlightsFor({
            csg: { key: 'k', mesh: MESH }, policy: { ...POLICY, csgHighlightOpacity: 0.2 },
        });

        expect(ids(dim)).toEqual(ids(bright));
        expect(dim[0].opacity).not.toBe(bright[0].opacity);
    });
});
