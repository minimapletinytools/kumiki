const { TouchGestures, wheelGesture, TAP_SLOP } = require('../webview/touch-navigation');

describe('TouchGestures', () => {
    test('a finger that barely moves is a tap', () => {
        const touch = new TouchGestures();
        touch.down(1, 100, 100);
        expect(touch.move(1, 100 + TAP_SLOP - 2, 100)).toBeNull();
        expect(touch.up(1)).toBe(true);
    });

    test('one finger dragged orbits by how far it moved, and is not a tap', () => {
        const touch = new TouchGestures();
        touch.down(1, 100, 100);
        expect(touch.move(1, 120, 100)).toEqual({ kind: 'orbit', dx: 20, dy: 0 });
        expect(touch.move(1, 125, 90)).toEqual({ kind: 'orbit', dx: 5, dy: -10 });
        expect(touch.up(1)).toBe(false);
    });

    test('two fingers spreading zoom in toward their midpoint, and moving together pan', () => {
        const touch = new TouchGestures();
        touch.down(1, 100, 100);
        touch.down(2, 200, 100);
        const pinch = touch.move(2, 300, 100);
        expect(pinch.kind).toBe('pinch');
        expect(pinch.factor).toBeCloseTo(0.5);
        expect(pinch.from).toEqual({ x: 150, y: 100 });
        expect(pinch.to).toEqual({ x: 200, y: 100 });
        touch.up(2);
        // The finger left behind doesn't orbit, and lifting it isn't a tap.
        expect(touch.move(1, 140, 140)).toBeNull();
        expect(touch.up(1)).toBe(false);
    });

    test('a held finger stays still until it moves or is cancelled', () => {
        const touch = new TouchGestures();
        touch.down(1, 10, 10);
        expect(touch.stillHeld()).toBe(true);
        touch.cancel();
        expect(touch.stillHeld()).toBe(false);
    });
});

describe('wheelGesture', () => {
    const wheel = (fields) => ({ deltaX: 0, deltaY: 0, deltaMode: 0, ctrlKey: false, shiftKey: false, ...fields });

    test('a pinch zooms by how far it pinched, out for a positive delta', () => {
        const out = wheelGesture(wheel({ ctrlKey: true, deltaY: 10 }));
        const back = wheelGesture(wheel({ ctrlKey: true, deltaY: -10 }));
        expect(out.kind).toBe('zoom');
        expect(out.factor).toBeGreaterThan(1);
        expect(out.factor * back.factor).toBeCloseTo(1);
    });

    test('a scroll is a zoom step, unless two-finger scroll orbits; then shift pans', () => {
        expect(wheelGesture(wheel({ deltaY: 100 }))).toEqual({ kind: 'zoomStep', out: true });
        expect(wheelGesture(wheel({ deltaX: 4, deltaY: -6 }), { scrollOrbits: true })).toEqual({ kind: 'orbit', dx: -4, dy: 6 });
        expect(wheelGesture(wheel({ deltaY: 3, shiftKey: true }), { scrollOrbits: true })).toEqual({ kind: 'pan', dx: -0, dy: -3 });
    });
});
