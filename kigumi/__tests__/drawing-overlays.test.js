const fs = require('fs');
const path = require('path');
const { DrawingOverlays, anchoredLineDistances, drawnFacing, outlineShade, roundDashShader } = require('../webview/drawing-overlays');

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

    test('where measured, only a line a dimension in the view goes to', () => {
        const overlays = Object.create(DrawingOverlays.prototype);
        overlays._look = look;
        const camera = { getWorldDirection: () => look };
        const line = (measuredAs) => ({ option: 'showDrawingPerfectFaces', normal: vector(1, 0, 0), measuredAs,
            object: { visible: false } });
        const front = line('post#0|ptw.front'), back = line('post#0|ptw.back');
        const bundles = [{ drawingLines: [front, back] }];
        const options = { showDrawingPerfectFaces: 'measured' };

        overlays.showFor(bundles, camera, { inDrawing: true, options, measured: new Set(['post#0|ptw.front']) });
        expect([front.object.visible, back.object.visible]).toEqual([true, false]);
        overlays.showFor(bundles, camera, { inDrawing: true, options: { showDrawingPerfectFaces: 'on' }, measured: new Set() });
        expect([front.object.visible, back.object.visible]).toEqual([true, true]);
        overlays.showFor(bundles, camera, { inDrawing: true, options: { showDrawingPerfectFaces: 'off' },
            measured: new Set(['post#0|ptw.front']) });
        expect([front.object.visible, back.object.visible]).toEqual([false, false]);
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

describe('round dots', () => {
    // The vendored LineMaterial's fragment shader, as its file holds it.
    const vendored = fs.readFileSync(path.join(__dirname, '..', 'webview', 'vendor', 'LineMaterial.js'), 'utf8');
    const fragment = vendored.slice(vendored.indexOf('fragmentShader: `') + 'fragmentShader: `'.length);
    const shader = fragment.slice(0, fragment.indexOf('`'));

    test('the square dash test is replaced by round-ended dashes as wide as the line is drawn, measured in pixels', () => {
        const round = roundDashShader(shader);
        expect(round).not.toContain('> dashSize ) discard');
        expect(round).toContain('dFdx( vUv.x )');
        expect(round).toContain('float dashPeriod = 12.00 * dashRadius;');
        expect(round).toContain('abs( dashAlong ) - 3.00 * dashRadius');
    });

    test('a shader with no dash test to replace is refused, not drawn square', () => {
        expect(() => roundDashShader('void main() {}')).toThrow(/no dash test/);
    });
});

describe('a reference face\'s outline', () => {
    class Geometry { setPositions(positions) { this.positions = positions; } }
    class Line { constructor(geometry, material) { this.geometry = geometry; this.material = material; } }
    const THREE = {
        LineSegmentsGeometry: Geometry,
        LineSegments2: Line,
        Color: class { constructor(value) { this.value = value; } },
        Vector3: class { constructor(x, y, z) { Object.assign(this, vector(x, y, z)); } },
    };
    const overlays = Object.create(DrawingOverlays.prototype);
    overlays.THREE = THREE;
    overlays.memberIds = null;
    overlays.materials = { reference: { clone: () => ({ uniforms: { diffuse: { value: null }, resolution: {} } }), uniforms: { resolution: {} } } };

    // A unit square on z = 0 in two triangles, and one triangle standing off it.
    const vertices = [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1];
    const indices = [0, 1, 2, 0, 2, 3, 0, 1, 4];

    test('is its edges that only one of its triangles has, in its colour', () => {
        const [line, ...rest] = overlays.referenceOutlinesFor(vertices, indices, [{ normal: [0, 0, 1], offset: 0, color: '#cfdfec' }], 'post#0');

        expect(rest).toEqual([]);
        expect(line.object.geometry.positions.length).toBe(4 * 6);  // the square's sides, not its diagonal
        expect(line.object.material.uniforms.diffuse.value.value).toBe(outlineShade('#cfdfec'));
        expect(line.option).toBe('highlightReferenceEdges');
    });

    test('is drawn face-on too, as the reference edges are', () => {
        const [line] = overlays.referenceOutlinesFor(vertices, indices, [{ normal: [0, 0, 1], offset: 0, color: '#9cc' }], 'post#0');
        line.object.visible = false;
        overlays._look = vector(0, 0, -1);
        const camera = { getWorldDirection: () => overlays._look };

        expect(overlays.showFor([{ drawingLines: [line] }], camera, { inDrawing: true, options: { highlightReferenceEdges: true } })).toBe(true);
        expect(overlays.showFor([{ drawingLines: [line] }], camera, { inDrawing: true, options: { highlightReferenceEdges: false } })).toBe(false);
    });
});

test('a reference face\'s outline is its tint deepened, keeping its hue', () => {
    const hue = (hex) => {
        const [r, g, b] = [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16));
        return Math.atan2(Math.sqrt(3) * (g - b), 2 * r - g - b);
    };
    for (const tint of ['#cfdfec', '#f4d6c4']) {
        const shade = outlineShade(tint);
        expect(hue(shade)).toBeCloseTo(hue(tint), 1);
        expect(parseInt(shade.slice(1), 16)).toBeLessThan(parseInt(tint.slice(1), 16));
    }
});
