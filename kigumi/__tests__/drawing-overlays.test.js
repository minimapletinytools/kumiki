const { DrawingOverlays, drawnFacing } = require('../webview/drawing-overlays');

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
