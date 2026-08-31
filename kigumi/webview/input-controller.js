(function (globalScope) {
    'use strict';
    // Turning pointer events into things the viewer can act on.
    //
    // The part that matters for drawings is where a pointer is: with one
    // viewport filling the canvas, a click's normalized coordinates are the
    // canvas's own, and every raycast in the viewer assumed that. With several
    // viewports the same click means different things depending which one it
    // landed in, so the viewport has to be resolved first and the coordinates
    // taken relative to it.

    /**
     * A canvas point in normalized device coordinates *within* a viewport.
     *
     * Not within the canvas: a click halfway across a quarter-width viewport is
     * at its centre, however far across the window it is.
     */
    function viewportNdc(rect, pointX, pointY, pageRect) {
        const [x, y, width, height] = rect;
        const left = pageRect.x + x * pageRect.width;
        const top = pageRect.y + y * pageRect.height;
        const pixelWidth = Math.max(1, width * pageRect.width);
        const pixelHeight = Math.max(1, height * pageRect.height);
        return {
            x: ((pointX - left) / pixelWidth) * 2 - 1,
            // Measured up from the bottom rather than negating the distance
            // down: the same numbers, without a negative zero at the centre.
            y: (1 - (pointY - top) / pixelHeight) * 2 - 1,
        };
    }

    /** Whether a point is inside a viewport's rect, in canvas pixels. */
    function rectContains(rect, pointX, pointY, pageRect) {
        const [x, y, width, height] = rect;
        const left = pageRect.x + x * pageRect.width;
        const top = pageRect.y + y * pageRect.height;
        return pointX >= left && pointX <= left + width * pageRect.width
            && pointY >= top && pointY <= top + height * pageRect.height;
    }

    /**
     * Every viewport a canvas point falls in, topmost first.
     *
     * Usually one. It is a list because viewports may overlap and a drawing's
     * viewports draw on nothing, so where the one on top is empty the thing
     * under the cursor belongs to the one beneath -- the caller decides by
     * asking each in turn what it actually hit. Empty for a point outside every
     * viewport, which is a miss rather than the first one.
     */
    function resolvePointers(viewports, pointX, pointY, pageRect) {
        const found = [];
        for (let index = viewports.length - 1; index >= 0; index -= 1) {
            const viewport = viewports[index];
            const rect = viewport.spec ? viewport.spec.rect : viewport.rect;
            if (rectContains(rect, pointX, pointY, pageRect)) {
                found.push({ viewport, ndc: viewportNdc(rect, pointX, pointY, pageRect) });
            }
        }
        return found;
    }

    /**
     * The topmost viewport a canvas point is in, and where within it.
     *
     * What the camera controls act on, where "what is under the cursor" is the
     * rect and not its contents. Picking wants resolvePointers instead.
     */
    function resolvePointer(viewports, pointX, pointY, pageRect) {
        return resolvePointers(viewports, pointX, pointY, pageRect)[0] || null;
    }

    /** What holding a mouse button down means for the camera, or nothing. */
    function actionForButton(button, leftDragRotates) {
        if (button === 2 || (button === 0 && leftDragRotates)) {
            return 'orbit';
        }
        if (button === 1) {
            return 'pan';
        }
        return null;
    }

    // Below this a drag is a click that wobbled, not a drag. Kept here so the
    // press, the move and the release all agree on it.
    const DRAG_SLOP_PX = 2;

    /**
     * One press-move-release, and whether it turned out to be a drag.
     *
     * The viewer used to keep this in six fields that had to be set and cleared
     * together in three handlers, which is the kind of state that goes stale
     * when a new exit path is added.
     */
    class PointerDrag {
        constructor() {
            this.reset();
        }

        reset() {
            this.action = null;
            this.button = null;
            this.target = null;
            this.moved = false;
            this.lastX = 0;
            this.lastY = 0;
        }

        get isDragging() {
            return this.action !== null;
        }

        begin({ action, button, target, x, y }) {
            this.action = action;
            this.button = button;
            this.target = target;
            this.moved = false;
            this.lastX = x;
            this.lastY = y;
        }

        /** How far the pointer moved since last asked, or null if idle. */
        move({ x, y }) {
            if (!this.isDragging) {
                return null;
            }
            const dx = x - this.lastX;
            const dy = y - this.lastY;
            if (Math.abs(dx) + Math.abs(dy) > DRAG_SLOP_PX) {
                this.moved = true;
            }
            const fromX = this.lastX;
            const fromY = this.lastY;
            this.lastX = x;
            this.lastY = y;
            return { dx, dy, fromX, fromY, toX: x, toY: y, action: this.action };
        }

        /** What just finished, and clear it. */
        end() {
            const finished = {
                action: this.action,
                button: this.button,
                target: this.target,
                moved: this.moved,
            };
            this.reset();
            return finished;
        }
    }

    const KigumiInput = {
        viewportNdc,
        rectContains,
        resolvePointer,
        resolvePointers,
        actionForButton,
        PointerDrag,
        DRAG_SLOP_PX,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiInput;
    }
    globalScope.KigumiInput = KigumiInput;
})(typeof window !== 'undefined' ? window : globalThis);
