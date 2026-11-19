// Touch and trackpad gestures as camera moves, kept apart from the DOM so they can be tested.

/** How far a finger may move, in pixels, and still count as a tap. */
const TAP_SLOP = 8;
/** How long a finger held still opens the context menu, in ms. */
const LONG_PRESS_MS = 550;
/** Pinch zoom per wheel delta unit: a trackpad pinch arrives as ctrl+wheel with small deltas. */
const PINCH_ZOOM_RATE = 0.01;

const midpoint = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/**
 * The fingers on the view. One finger drags to orbit; two pinch to zoom and move together to pan.
 * `move` returns what the camera should do, or null.
 */
class TouchGestures {
    constructor() {
        this.points = new Map();
        this.start = null;
        this.moved = false;
        this.multi = false;
    }

    get active() {
        return this.points.size > 0;
    }

    down(id, x, y) {
        this.points.set(id, { x, y });
        if (this.points.size === 1) {
            this.start = { x, y };
            this.moved = false;
            this.multi = false;
        } else {
            this.multi = true;
        }
    }

    /** Return {kind: 'orbit', dx, dy}, {kind: 'pinch', factor, from, to} (factor > 1 zooms out), or null. */
    move(id, x, y) {
        const before = this.points.get(id);
        if (!before) {
            return null;
        }
        if (this.points.size >= 2) {
            const [a, b] = [...this.points.values()];
            const fromMid = midpoint(a, b);
            const fromDistance = distance(a, b);
            this.points.set(id, { x, y });
            const [c, d] = [...this.points.values()];
            const toDistance = distance(c, d);
            this.moved = true;
            return {
                kind: 'pinch',
                factor: toDistance > 0 ? fromDistance / toDistance : 1,
                from: fromMid,
                to: midpoint(c, d),
            };
        }
        this.points.set(id, { x, y });
        if (!this.moved && distance(this.start, { x, y }) < TAP_SLOP) {
            return null;
        }
        this.moved = true;
        return this.multi ? null : { kind: 'orbit', dx: x - before.x, dy: y - before.y };
    }

    /** A finger lifted: true if the touch was a tap (one finger that barely moved). */
    up(id) {
        this.points.delete(id);
        const tapped = this.points.size === 0 && !this.moved && !this.multi;
        return tapped;
    }

    /** True while one finger has stayed still since it went down. */
    stillHeld() {
        return this.points.size === 1 && !this.moved && !this.multi;
    }

    cancel() {
        this.points.clear();
        this.moved = true;
    }
}

/**
 * What a wheel event does to the camera.
 * A pinch (ctrl+wheel) zooms by how far it pinched. With `scrollOrbits`, a two-finger scroll orbits,
 * or pans with shift; otherwise each wheel step zooms. Returns {kind: 'zoom', factor} (factor > 1
 * zooms out), {kind: 'zoomStep', out}, {kind: 'orbit', dx, dy} or {kind: 'pan', dx, dy}.
 */
function wheelGesture(event, { scrollOrbits = false } = {}) {
    const pixels = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 400 : 1;
    const dx = event.deltaX * pixels;
    const dy = event.deltaY * pixels;
    if (event.ctrlKey) {
        return { kind: 'zoom', factor: Math.exp(dy * PINCH_ZOOM_RATE) };
    }
    if (scrollOrbits) {
        return event.shiftKey ? { kind: 'pan', dx: -dx, dy: -dy } : { kind: 'orbit', dx: -dx, dy: -dy };
    }
    return { kind: 'zoomStep', out: event.deltaY > 0 };
}

export { TouchGestures, wheelGesture, LONG_PRESS_MS, TAP_SLOP };
