const {
    worldUnitsPerPixel, pickTolerances, EDGE_PICK_PIXELS, POINT_PICK_PIXELS,
} = require('../webview/pick-tolerances.js');

function perspective({ fov = 45, at = [0, 0, 0] } = {}) {
    return {
        isPerspectiveCamera: true,
        fov,
        position: { x: at[0], y: at[1], z: at[2] },
    };
}

function orthographic({ top = 1, bottom = -1, zoom = 1 } = {}) {
    return { isOrthographicCamera: true, top, bottom, zoom };
}

describe('what a screen pixel is worth in the model', () => {
    it('an orthographic view scales with zoom, and not with distance', () => {
        const wide = worldUnitsPerPixel(orthographic({ zoom: 1 }), 800, [0, 0, 0]);
        const close = worldUnitsPerPixel(orthographic({ zoom: 4 }), 800, [0, 0, 0]);

        expect(close).toBeCloseTo(wide / 4, 12);
        // Distance is not in the answer at all: a parallel projection does not
        // make far things smaller.
        expect(worldUnitsPerPixel(orthographic(), 800, [0, 0, 500]))
            .toBeCloseTo(wide, 12);
    });

    it('a perspective view scales with how far away the point is', () => {
        const camera = perspective();
        const near = worldUnitsPerPixel(camera, 800, [0, 0, 1]);
        const far = worldUnitsPerPixel(camera, 800, [0, 0, 4]);

        expect(far).toBeCloseTo(near * 4, 12);
    });

    it('a taller canvas puts more world in the same pixel count', () => {
        const camera = perspective();
        const short = worldUnitsPerPixel(camera, 400, [0, 0, 1]);
        const tall = worldUnitsPerPixel(camera, 800, [0, 0, 1]);

        expect(tall).toBeCloseTo(short / 2, 12);
    });

    it('it says nothing rather than guessing when it cannot tell', () => {
        expect(worldUnitsPerPixel(null, 800, [0, 0, 1])).toBe(0);
        expect(worldUnitsPerPixel(perspective(), 0, [0, 0, 1])).toBe(0);
        // A perspective camera with no point to measure to.
        expect(worldUnitsPerPixel(perspective(), 800, null)).toBe(0);
        // Something that is neither kind of camera.
        expect(worldUnitsPerPixel({ position: { x: 0, y: 0, z: 0 } }, 800, [0, 0, 1])).toBe(0);
    });
});

describe('the tolerances a pick is judged by', () => {
    it('a vertex is more forgiving than an edge, which is more than a face', () => {
        // A point is smaller to aim at than a line, so it gets more slack.
        expect(POINT_PICK_PIXELS).toBeGreaterThan(EDGE_PICK_PIXELS);
    });

    it('both are the pixel counts converted at that point', () => {
        const camera = perspective();
        const perPixel = worldUnitsPerPixel(camera, 800, [0, 0, 2]);

        const tolerances = pickTolerances(camera, 800, [0, 0, 2]);

        expect(tolerances.edge).toBeCloseTo(perPixel * EDGE_PICK_PIXELS, 12);
        expect(tolerances.point).toBeCloseTo(perPixel * POINT_PICK_PIXELS, 12);
    });

    it('zooming out makes the same click more forgiving in model units', () => {
        // The whole point. Fixed millimetres were unusable on a whole frame.
        const camera = perspective();
        const zoomedIn = pickTolerances(camera, 800, [0, 0, 1]);
        const zoomedOut = pickTolerances(camera, 800, [0, 0, 20]);

        expect(zoomedOut.edge).toBeGreaterThan(zoomedIn.edge * 15);
    });

    it('null when the view cannot say, so the runner keeps its own defaults', () => {
        expect(pickTolerances(null, 800, [0, 0, 1])).toBeNull();
        expect(pickTolerances(perspective(), 0, [0, 0, 1])).toBeNull();
    });
});
