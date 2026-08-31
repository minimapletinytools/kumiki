const {
    viewportNdc, resolvePointer, actionForButton, PointerDrag, DRAG_SLOP_PX,
} = require('../webview/input-controller.js');

describe('normalized coordinates within a viewport', () => {
    test('the centre of a full-canvas viewport is the origin', () => {
        expect(viewportNdc([0, 0, 1, 1], 400, 300, 800, 600)).toEqual({ x: 0, y: 0 });
    });

    test('a point is measured against its own viewport, not the canvas', () => {
        // Halfway across a quarter-width viewport is its centre, however far
        // across the window that is. Measuring against the canvas is what made
        // every raycast wrong the moment there was more than one viewport.
        expect(viewportNdc([0.5, 0, 0.5, 1], 600, 300, 800, 600)).toEqual({ x: 0, y: 0 });
    });

    test('the corners come out at the corners', () => {
        const rect = [0, 0, 0.5, 0.5];
        expect(viewportNdc(rect, 0, 0, 800, 600)).toEqual({ x: -1, y: 1 });
        expect(viewportNdc(rect, 400, 300, 800, 600)).toEqual({ x: 1, y: -1 });
    });

    test('y is flipped, since the screen counts down and NDC counts up', () => {
        expect(viewportNdc([0, 0, 1, 1], 400, 0, 800, 600).y).toBe(1);
        expect(viewportNdc([0, 0, 1, 1], 400, 600, 800, 600).y).toBe(-1);
    });
});

describe('resolving which viewport a pointer is in', () => {
    const viewports = [
        { id: 'left', spec: { rect: [0, 0, 0.5, 1] } },
        { id: 'right', spec: { rect: [0.5, 0, 0.5, 1] } },
    ];

    test('a point lands in the viewport it is over', () => {
        expect(resolvePointer(viewports, 100, 300, 800, 600).viewport.id).toBe('left');
        expect(resolvePointer(viewports, 700, 300, 800, 600).viewport.id).toBe('right');
    });

    test('the coordinates come back relative to that viewport', () => {
        const resolved = resolvePointer(viewports, 600, 300, 800, 600);
        expect(resolved.ndc).toEqual({ x: 0, y: 0 });
    });

    test('a point outside every viewport is a miss, not the first one', () => {
        const inset = [{ id: 'inset', spec: { rect: [0.25, 0.25, 0.5, 0.5] } }];
        expect(resolvePointer(inset, 10, 10, 800, 600)).toBeNull();
    });

    test('later viewports win where they overlap, matching what is drawn last', () => {
        const stacked = [
            { id: 'under', spec: { rect: [0, 0, 1, 1] } },
            { id: 'over', spec: { rect: [0, 0, 0.5, 1] } },
        ];
        expect(resolvePointer(stacked, 100, 300, 800, 600).viewport.id).toBe('over');
    });

    test('a bare rect works as well as a runtime viewport', () => {
        expect(resolvePointer([{ id: 'plain', rect: [0, 0, 1, 1] }], 10, 10, 800, 600).viewport.id)
            .toBe('plain');
    });
});

describe('what a button press means', () => {
    test('right drag orbits and middle drag pans', () => {
        expect(actionForButton(2, false)).toBe('orbit');
        expect(actionForButton(1, false)).toBe('pan');
    });

    test('left drag orbits only when that is switched on', () => {
        expect(actionForButton(0, false)).toBeNull();
        expect(actionForButton(0, true)).toBe('orbit');
    });
});

describe('a press, a move and a release', () => {
    test('moving reports how far, and from where', () => {
        const drag = new PointerDrag();
        drag.begin({ action: 'orbit', button: 2, target: 'canvas', x: 100, y: 100 });

        expect(drag.move({ x: 110, y: 120 })).toMatchObject({
            dx: 10, dy: 20, fromX: 100, fromY: 100, toX: 110, toY: 120, action: 'orbit',
        });
        // and the next move is measured from there, not from the press
        expect(drag.move({ x: 115, y: 120 })).toMatchObject({ dx: 5, dy: 0 });
    });

    test('moving while nothing is held reports nothing', () => {
        expect(new PointerDrag().move({ x: 10, y: 10 })).toBeNull();
    });

    test('a wobble is still a click, a real drag is not', () => {
        const wobbled = new PointerDrag();
        wobbled.begin({ action: 'orbit', button: 2, x: 0, y: 0 });
        wobbled.move({ x: DRAG_SLOP_PX, y: 0 });
        expect(wobbled.end().moved).toBe(false);

        const dragged = new PointerDrag();
        dragged.begin({ action: 'orbit', button: 2, x: 0, y: 0 });
        dragged.move({ x: DRAG_SLOP_PX + 5, y: 0 });
        expect(dragged.end().moved).toBe(true);
    });

    test('releasing says what finished and leaves nothing behind', () => {
        const drag = new PointerDrag();
        drag.begin({ action: 'pan', button: 1, target: 'canvas', x: 5, y: 5 });

        expect(drag.end()).toEqual({ action: 'pan', button: 1, target: 'canvas', moved: false });
        expect(drag.isDragging).toBe(false);
        // The six fields this replaced had to be cleared together in three
        // handlers; ending twice must not resurrect the last one.
        expect(drag.end().action).toBeNull();
    });
});
