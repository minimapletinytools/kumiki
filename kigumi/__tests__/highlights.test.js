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

describe('keeping the scene in step with the list', () => {
    // The decisions -- what is new, what is still wanted, what has gone -- with
    // the three.js half handed in. Untested until it was pulled out of
    // viewer-app.js, which no test can load.
    const { reconcile } = require('../webview/highlights.js');

    function spy() {
        const built = [];
        const updated = [];
        const dropped = [];
        return {
            built, updated, dropped,
            handlers: {
                build: (d) => { built.push(d.id); return { id: d.id, color: d.color }; },
                update: (object, d) => { updated.push(d.id); object.color = d.color; },
                drop: (object) => { dropped.push(object.id); },
            },
        };
    }

    const lit = (id, color = 1) => ({ id, color });

    test('what is new is built', () => {
        const watch = spy();
        const existing = new Map();

        reconcile(existing, [lit('a'), lit('b')], watch.handlers);

        expect(watch.built).toEqual(['a', 'b']);
        expect([...existing.keys()]).toEqual(['a', 'b']);
    });

    test('what is still wanted is updated, never rebuilt', () => {
        // Its geometry has not changed; rebuilding would throw away a mesh to
        // draw the same mesh.
        const watch = spy();
        const existing = new Map();
        reconcile(existing, [lit('a')], watch.handlers);
        watch.built.length = 0;

        reconcile(existing, [lit('a', 0xff0000)], watch.handlers);

        expect(watch.built).toEqual([]);
        expect(watch.updated).toEqual(['a', 'a']);
        expect(existing.get('a').color).toBe(0xff0000);
    });

    test('what has gone is dropped and forgotten', () => {
        const watch = spy();
        const existing = new Map();
        reconcile(existing, [lit('a'), lit('b')], watch.handlers);

        reconcile(existing, [lit('a')], watch.handlers);

        expect(watch.dropped).toEqual(['b']);
        expect([...existing.keys()]).toEqual(['a']);
    });

    test('an empty list drops everything', () => {
        // Nothing selected, nothing hovered, nothing held: the scene empties
        // because the list did, not because anything remembered to clear it.
        const watch = spy();
        const existing = new Map();
        reconcile(existing, [lit('a'), lit('b')], watch.handlers);

        reconcile(existing, [], watch.handlers);

        expect(watch.dropped.sort()).toEqual(['a', 'b']);
        expect(existing.size).toBe(0);
    });

    test('a descriptor nothing can be made of is skipped, not remembered', () => {
        // A source can arrive without the geometry to draw. Storing a null
        // would make the next pass think it was still there.
        const existing = new Map();
        const dropped = [];

        reconcile(existing, [lit('a')], {
            build: () => null,
            update: () => { throw new Error('should not update what was never built'); },
            drop: (object) => dropped.push(object),
        });

        expect(existing.size).toBe(0);
        expect(dropped).toEqual([]);
    });

    test('and it is not dropped on the next pass either', () => {
        const existing = new Map();
        const dropped = [];
        const handlers = { build: () => null, update: () => {}, drop: (o) => dropped.push(o) };

        reconcile(existing, [lit('a')], handlers);
        reconcile(existing, [lit('a')], handlers);

        expect(dropped).toEqual([]);
    });

    test('the same list twice changes nothing the second time', () => {
        const watch = spy();
        const existing = new Map();
        const list = [lit('a'), lit('b')];
        reconcile(existing, list, watch.handlers);
        watch.built.length = 0;
        watch.dropped.length = 0;

        reconcile(existing, list, watch.handlers);

        expect(watch.built).toEqual([]);
        expect(watch.dropped).toEqual([]);
    });

    test('missing handlers are tolerated rather than thrown at', () => {
        expect(() => reconcile(new Map(), [lit('a')], undefined)).not.toThrow();
    });
});

describe('a selection highlight outliving its selection', () => {
    const { sourceForFocus } = require('../webview/highlights.js');
    const source = { key: 'post#0|cut|front', mesh: {} };

    test('is offered while the focus still names it', () => {
        expect(sourceForFocus(source, 'post#0|cut|front')).toBe(source);
    });

    test('and not once the focus has moved', () => {
        // The geometry is kept so the overlay can be re-derived; a message from
        // before the focus moved describes a selection nobody has.
        expect(sourceForFocus(source, 'girt#0|cut|back')).toBeNull();
    });

    test('nor when there is no focus at all', () => {
        expect(sourceForFocus(source, null)).toBeNull();
    });

    test('and no source is no highlight', () => {
        expect(sourceForFocus(null, 'post#0|cut|front')).toBeNull();
    });
});
