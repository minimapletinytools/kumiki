(function (globalScope) {
    'use strict';
    // What should be lit, given what is selected, hovered and held.
    //
    // A LIST, not seven lifetimes. Each overlay used to be built when the
    // message that caused it arrived and torn down by one of seven scattered
    // calls -- so there was no path from "the state is X" to "these overlays
    // should exist", and every state change that produced no message had to
    // remember to tear the right thing down by hand. Two bugs grew there: a
    // measurement preview erased a statement after it was drawn, and the record
    // of what was on screen nulled by a teardown in the middle of a redraw.
    //
    // This is pure. It answers what should exist; the caller reconciles what
    // does against what should, and nothing has to remember anything.
    //
    // IDENTITY vs APPEARANCE. `id` says WHICH thing is lit, and nothing else --
    // so an overlay that is still wanted is left alone rather than rebuilt.
    // Colour and opacity ride alongside and are applied every pass, which is
    // why a selection deepening now fades the highlight with it; the old code
    // froze that at the moment the message arrived.

    /** Selection: the tagged node, and the feature within it. */
    const CSG_COLORS = Object.freeze({ tagged: 0x29b6f6, feature: 0x0288d1 });

    /** The pointer, in another hue and drawn over the selection. */
    const HOVER_COLOR = 0xffa726;

    /** A pair the click will refuse. Red, and the click does refuse it. */
    const HOVER_REFUSED_COLOR = 0xef5350;

    /** The first end of a measurement: held, not selected, and green. */
    const HELD_COLOR = 0x66bb6a;

    const HOVER_OPACITY = 0.8;
    const HELD_OPACITY = 0.8;

    /** Over the selection, and over each other in this order. */
    const ORDER = Object.freeze({
        csgMesh: 999,
        csgEdges: 1000,
        hoverMesh: 1100,
        hoverEdges: 1101,
        // Above the hover: what is HELD is the more important of the two, and
        // they are the two most likely to overlap -- the pointer is usually
        // right beside the thing being held. They used to share 1101, which
        // left which one won undefined.
        heldMesh: 1102,
        heldEdges: 1103,
    });

    function hasMesh(mesh) {
        return Boolean(mesh && Array.isArray(mesh.vertices) && mesh.vertices.length > 0
            && Array.isArray(mesh.indices));
    }

    function hasEdges(positions) {
        return Array.isArray(positions) && positions.length > 0;
    }

    /**
     * Which overlays should exist, given the state.
     *
     * `csg`, `hover` and `held` are each null or
     * `{ key, mesh, parentMesh, edgePositions, featureLabel, refused }` -- the
     * geometry the runner sent, kept by the caller for as long as the state it
     * belongs to is still the state. `policy` carries the opacities the current
     * selection asks for.
     */
    function highlightsFor(state) {
        const found = state || {};
        const policy = found.policy || {};
        const out = [];

        const csg = found.csg;
        if (csg) {
            if (hasEdges(csg.edgePositions)) {
                // An edge is a line: shading the triangles beside it lit a
                // stray wedge that read as geometry rather than as a selection.
                out.push({
                    id: `csg-edges:${csg.key}`,
                    shape: 'edges',
                    positions: csg.edgePositions,
                    color: CSG_COLORS.feature,
                    opacity: 1,
                    renderOrder: ORDER.csgEdges,
                });
            }
            if (csg.featureLabel && hasMesh(csg.parentMesh)) {
                // A feature inside something: the parent dim, the feature
                // bright, so which is which is visible.
                out.push({
                    id: `csg-parent:${csg.key}`,
                    shape: 'mesh',
                    mesh: csg.parentMesh,
                    color: CSG_COLORS.tagged,
                    opacity: policy.parentHighlightOpacity,
                    renderOrder: ORDER.csgMesh,
                });
                if (hasMesh(csg.mesh)) {
                    out.push({
                        id: `csg-feature:${csg.key}`,
                        shape: 'mesh',
                        mesh: csg.mesh,
                        color: CSG_COLORS.feature,
                        opacity: policy.featureHighlightOpacity,
                        renderOrder: ORDER.csgMesh,
                    });
                }
            } else if (hasMesh(csg.mesh)) {
                out.push({
                    id: `csg-node:${csg.key}`,
                    shape: 'mesh',
                    mesh: csg.mesh,
                    color: CSG_COLORS.tagged,
                    opacity: policy.csgHighlightOpacity,
                    renderOrder: ORDER.csgMesh,
                });
            }
        }

        const hover = found.hover;
        if (hover) {
            // One colour decides both: what is drawn red is what the click
            // refuses, so they cannot disagree about the same feature.
            const color = hover.refused ? HOVER_REFUSED_COLOR : HOVER_COLOR;
            if (hasEdges(hover.edgePositions)) {
                out.push({
                    id: `hover-edges:${hover.key}`,
                    shape: 'edges',
                    positions: hover.edgePositions,
                    color,
                    opacity: 1,
                    renderOrder: ORDER.hoverEdges,
                });
            }
            if (hasMesh(hover.mesh)) {
                out.push({
                    id: `hover-mesh:${hover.key}`,
                    shape: 'mesh',
                    mesh: hover.mesh,
                    color,
                    opacity: HOVER_OPACITY,
                    renderOrder: ORDER.hoverMesh,
                });
            }
        }

        const held = found.held;
        if (held) {
            if (hasEdges(held.edgePositions)) {
                out.push({
                    id: `held-edges:${held.key}`,
                    shape: 'edges',
                    positions: held.edgePositions,
                    color: HELD_COLOR,
                    opacity: 1,
                    renderOrder: ORDER.heldEdges,
                });
            }
            if (hasMesh(held.mesh)) {
                out.push({
                    id: `held-mesh:${held.key}`,
                    shape: 'mesh',
                    mesh: held.mesh,
                    color: HELD_COLOR,
                    opacity: HELD_OPACITY,
                    renderOrder: ORDER.heldMesh,
                });
            }
        }

        return out;
    }

    const KigumiHighlights = {
        highlightsFor,
        CSG_COLORS,
        HOVER_COLOR,
        HOVER_REFUSED_COLOR,
        HELD_COLOR,
        HOVER_OPACITY,
        HELD_OPACITY,
        ORDER,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiHighlights;
    }
    globalScope.KigumiHighlights = KigumiHighlights;
})(typeof window !== 'undefined' ? window : globalThis);
