(function (globalScope) {
    'use strict';
    // How close a click has to be to count as hitting an edge or a vertex.
    //
    // A FACE is clicked directly, so the only slack it needs is the gap between
    // the analytic surface and the triangulated mesh the ray actually struck.
    // That is a fixed distance and has nothing to do with the view.
    //
    // An EDGE or a VERTEX cannot be clicked exactly at all. Selecting one means
    // snapping to it, the way any CAD package works, and how much slack that
    // wants is a matter of what the eye can see: a millimetre is generous on a
    // timber filling the screen and unusable on a whole frame zoomed out. So it
    // is specified in PIXELS and converted here, which is why this needs the
    // camera. Fixed world distances kept being tuned to whichever zoom level
    // somebody happened to be at.

    /** Pixels from an edge that still counts as clicking it. */
    const EDGE_PICK_PIXELS = 6;

    /** Pixels from a vertex. Larger: a point is smaller to aim at than a line. */
    const POINT_PICK_PIXELS = 10;

    /**
     * How much world distance one screen pixel covers at `point`.
     *
     * Both camera kinds come down to the height of the visible world divided by
     * the height of the canvas. A perspective camera's visible height depends on
     * how far away the point is; an orthographic camera's does not, but does
     * depend on its zoom.
     *
     * Zero when it cannot be worked out, which callers read as "no scaled
     * tolerance" rather than as a tolerance of nothing.
     */
    function worldUnitsPerPixel(camera, canvasHeight, point) {
        if (!camera || !(canvasHeight > 0)) {
            return 0;
        }
        if (camera.isOrthographicCamera) {
            const zoom = camera.zoom || 1;
            return ((camera.top - camera.bottom) / zoom) / canvasHeight;
        }
        if (camera.isPerspectiveCamera && Array.isArray(point)) {
            const dx = camera.position.x - point[0];
            const dy = camera.position.y - point[1];
            const dz = camera.position.z - point[2];
            const away = Math.sqrt(dx * dx + dy * dy + dz * dz);
            const height = 2 * away * Math.tan((camera.fov * Math.PI / 180) / 2);
            return height / canvasHeight;
        }
        return 0;
    }

    /**
     * The edge and point tolerances for a click at `point`, in world units.
     *
     * Null when the view cannot say, so the runner keeps its own defaults
     * rather than being handed a number made up here.
     */
    function pickTolerances(camera, canvasHeight, point) {
        const perPixel = worldUnitsPerPixel(camera, canvasHeight, point);
        if (!(perPixel > 0)) {
            return null;
        }
        return {
            edge: perPixel * EDGE_PICK_PIXELS,
            point: perPixel * POINT_PICK_PIXELS,
        };
    }

    const KigumiPickTolerances = {
        worldUnitsPerPixel, pickTolerances, EDGE_PICK_PIXELS, POINT_PICK_PIXELS,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiPickTolerances;
    }
    globalScope.KigumiPickTolerances = KigumiPickTolerances;
})(typeof window !== 'undefined' ? window : globalThis);
