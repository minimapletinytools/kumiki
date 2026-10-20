const { DrawingOverlays, anchoredLineDistances, drawnFacing } = require('../webview/drawing-overlays');

const vector = (x, y, z) => ({ x, y, z, dot: (o) => x * o.x + y * o.y + z * o.z });

describe('which of a drawing\'s planes are drawn', () => {
    const look = vector(0, 0, -1);

    test('edge-on, and turned off square, but never face-on', () => {
        expect(drawnFacing(vector(1, 0, 0), look)).toBe(true);
        expect(drawnFacing(vector(Math.SQRT1_2, 0, Math.SQRT1_2), look)).toBe(true);
        expect(drawnFacing(vector(0, 0, 1), look)).toBe(false);
    });

    test('only in a drawing, only as its options say, and it says whether the id pass is needed', () => {
        const overlays = Object.create(DrawingOverlays.prototype);
        overlays._look = look;
        const camera = { getWorldDirection: () => look };
        const line = (option, normal) => ({ option, normal, object: { visible: true } });
        const face = line('showDrawingPerfectFaces', vector(1, 0, 0));
        const center = line('showDrawingCenterplanes', vector(0, 0, 1));
        const bundles = [{ drawingLines: [face, center] }, {}];

        expect(overlays.showFor(bundles, camera, {
            inDrawing: true, options: { showDrawingPerfectFaces: true, showDrawingCenterplanes: true } })).toBe(true);
        expect([face.object.visible, center.object.visible]).toEqual([true, false]);  // the centerplane is face-on

        expect(overlays.showFor(bundles, camera, {
            inDrawing: true, options: { showDrawingPerfectFaces: false, showDrawingCenterplanes: true } })).toBe(false);
        expect(overlays.showFor(bundles, camera, {
            inDrawing: false, options: { showDrawingPerfectFaces: true, showDrawingCenterplanes: true } })).toBe(false);
    });
});

describe('dots on one line fall in step', () => {
    const PERIOD = 0.0048;  // a dot and a gap
    const phase = (distance) => ((distance % PERIOD) + PERIOD) % PERIOD;

    test('a front and a back edge drawn on top of each other, run either way, dot alike', () => {
        // Along x at y = 0.3: the front edge at z = 0, the back one at z = -0.1, run the other way
        // and starting elsewhere.
        const [frontStart, frontEnd, backStart, backEnd] = anchoredLineDistances([
            0.1, 0.3, 0, 0.9, 0.3, 0,
            0.75, 0.3, -0.1, 0.2, 0.3, -0.1,
        ]);
        expect(frontEnd - frontStart).toBeCloseTo(0.8, 6);
        // The same x has the same distance on both, so the same place in the pattern.
        expect(phase(backStart)).toBeCloseTo(phase(0.75), 6);
        expect(phase(backEnd)).toBeCloseTo(phase(0.2), 6);
        expect(frontStart).toBeCloseTo(0.1, 6);
    });

    test('segments after the first do not inherit its length', () => {
        const [, , secondStart] = anchoredLineDistances([
            0, 0, 0, 0, 0, 5,
            0, 1, 0.2, 0, 1, 0.4,
        ]);
        expect(secondStart).toBeCloseTo(0.2, 6);
    });
});
