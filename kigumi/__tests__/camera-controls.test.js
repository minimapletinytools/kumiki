const {
    GIZMO_FACES, faceTextExtent, fitFaceFontSize, faceNormalToAxis,
} = require('../webview/camera-controls.js');

// Text measurement is the browser's, so the fitter is driven with a stand-in
// whose widths are proportional to the font size, which is all it relies on.
function measuringContext(widthPerCharPerPx = 0.55) {
    return {
        font: '',
        measureText(text) {
            const size = Number(/(\d+(?:\.\d+)?)px/.exec(this.font)[1]);
            return { width: text.length * size * widthPerCharPerPx };
        },
    };
}

describe('the cube faces', () => {
    test('every side face says which way it is three ways', () => {
        const sides = GIZMO_FACES.filter((face) => face.lines.length === 3);
        expect(sides).toHaveLength(4);
        expect(sides.map((face) => face.lines[2])).toEqual(['+x', '-x', '+y', '-y']);
    });

    test("north is on the back, following kumiki's own axes", () => {
        // rule.py: +X east, +Y north. BoxGeometry's material order is
        // +X, -X, +Y, -Y, so back is +Y and must read north.
        const [right, left, back, front] = GIZMO_FACES;
        expect(right.lines.slice(1)).toEqual(['east', '+x']);
        expect(left.lines.slice(1)).toEqual(['west', '-x']);
        expect(back.lines.slice(1)).toEqual(['north', '+y']);
        expect(front.lines.slice(1)).toEqual(['south', '-y']);
    });

    test('top and bottom have no bearing, only an axis', () => {
        expect(GIZMO_FACES[4].lines).toEqual(['top', '+z']);
        expect(GIZMO_FACES[5].lines).toEqual(['bottom', '-z']);
    });
});

describe('fitting the face text', () => {
    test('one size fits every face inside its frame', () => {
        const context = measuringContext();
        const size = fitFaceFontSize(context, GIZMO_FACES);
        const available = faceTextExtent();

        for (const face of GIZMO_FACES) {
            context.font = `600 ${size}px Segoe UI`;
            const widest = Math.max(...face.lines.map((line) => context.measureText(line).width));
            expect(widest).toBeLessThanOrEqual(available);
            expect(face.lines.length * size * 1.12).toBeLessThanOrEqual(available);
        }
    });

    test('the widest label is what holds the size down', () => {
        // Sharing one size across the cube means the longest word governs.
        const context = measuringContext();
        const shared = fitFaceFontSize(context, GIZMO_FACES);
        const withLonger = fitFaceFontSize(context, [
            ...GIZMO_FACES, { lines: ['an-extremely-long-label'], background: '#fff' },
        ]);
        expect(withLonger).toBeLessThan(shared);
    });

    test('a narrower font means a larger size, never an overflowing one', () => {
        const narrow = fitFaceFontSize(measuringContext(0.4), GIZMO_FACES);
        const wide = fitFaceFontSize(measuringContext(0.8), GIZMO_FACES);
        expect(narrow).toBeGreaterThan(wide);
    });
});

describe('picking a cube face', () => {
    test('a face normal becomes the axis it points along', () => {
        expect(faceNormalToAxis({ x: 1, y: 0, z: 0 })).toEqual({ x: 1, y: 0, z: 0 });
        expect(faceNormalToAxis({ x: 0, y: -1, z: 0 })).toEqual({ x: 0, y: -1, z: 0 });
        expect(faceNormalToAxis({ x: 0, y: 0, z: -1 })).toEqual({ x: 0, y: 0, z: -1 });
    });

    test('a normal that is nearly axis-aligned still snaps to one axis', () => {
        expect(faceNormalToAxis({ x: 0.98, y: 0.14, z: 0.02 })).toEqual({ x: 1, y: 0, z: 0 });
    });
});
