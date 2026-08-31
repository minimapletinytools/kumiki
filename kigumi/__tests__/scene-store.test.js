const {
    SceneStore, DEFAULT_SCENE_ID, defaultSceneSpec, normalizeScene,
    isOrthogonalFrame, orbitDistanceForExtent, firstLoadCameraPlan, pixelRect, viewportAspect, viewportAtPoint,
    normalizePage, normalizePageView, pageScreenRect, viewportScale, extentForScale,
    panPage, zoomPageAt, MAX_TILT_RADIANS,
} = require('../webview/scene-store.js');

describe('the default 3D scene', () => {
    test('is one full-canvas viewport with a free perspective camera', () => {
        const scene = defaultSceneSpec();
        expect(scene.viewports).toHaveLength(1);
        expect(scene.viewports[0].rect).toEqual([0, 0, 1, 1]);
        expect(scene.viewports[0].locked).toBe(false);
        expect(scene.viewports[0].projection).toBe('perspective');
    });

    test('asks for the camera controls a drawing will not', () => {
        expect(defaultSceneSpec().cameraControls).toEqual(
            expect.arrayContaining(['cube', 'orbitGizmo']));
        expect(normalizeScene({ id: 'a-drawing' }).cameraControls).toEqual([]);
    });
});

describe('normalizing a spec', () => {
    test('a scene with no viewports still has one', () => {
        expect(normalizeScene({ id: 'x' }).viewports).toHaveLength(1);
    });

    test('rects clamp into the canvas', () => {
        const scene = normalizeScene({ viewports: [{ rect: [-1, 0.5, 4, 0.25] }] });
        expect(scene.viewports[0].rect).toEqual([0, 0.5, 1, 0.25]);
    });

    test('a junk rect becomes the whole canvas rather than nothing', () => {
        expect(normalizeScene({ viewports: [{ rect: 'wide' }] }).viewports[0].rect)
            .toEqual([0, 0, 1, 1]);
    });

    test('an unknown projection falls back to perspective', () => {
        expect(normalizeScene({ viewports: [{ projection: 'fisheye' }] }).viewports[0].projection)
            .toBe('perspective');
    });

    test('members default to null, meaning the scene is about all of them', () => {
        const viewport = normalizeScene({ viewports: [{}] }).viewports[0];
        expect(viewport.members).toBeNull();
        expect(viewport.ghostOthers).toBe(true);
    });

    test('a camera frame that is not orthogonal is dropped, not trusted', () => {
        const scene = normalizeScene({ viewports: [{
            camera: { right: [1, 0, 0], up: [1, 1, 0], look: [0, 0, 1] },
        }] });
        expect(scene.viewports[0].camera).toBeNull();
    });

    test('an orthogonal frame is kept as given', () => {
        const camera = { right: [1, 0, 0], up: [0, 0, 1], look: [0, 1, 0], target: [0, 0, 0], extent: 1 };
        expect(normalizeScene({ viewports: [{ camera }] }).viewports[0].camera).toEqual(camera);
    });
});

describe('isOrthogonalFrame', () => {
    test('accepts perpendicular axes and rejects skewed ones', () => {
        expect(isOrthogonalFrame({ right: [1, 0, 0], up: [0, 1, 0], look: [0, 0, 1] })).toBe(true);
        expect(isOrthogonalFrame({ right: [1, 0, 0], up: [0.7, 0.7, 0], look: [0, 0, 1] })).toBe(false);
    });

    test('rejects a degenerate axis', () => {
        expect(isOrthogonalFrame({ right: [0, 0, 0], up: [0, 1, 0], look: [0, 0, 1] })).toBe(false);
    });

    test('rejects anything malformed', () => {
        expect(isOrthogonalFrame(null)).toBe(false);
        expect(isOrthogonalFrame({ right: [1, 0], up: [0, 1, 0], look: [0, 0, 1] })).toBe(false);
    });
});

const CANVAS = { x: 0, y: 0, width: 800, height: 600 };

describe('pixelRect', () => {
    test('a full-canvas rect covers the canvas', () => {
        expect(pixelRect([0, 0, 1, 1], CANVAS, 600)).toEqual({ x: 0, y: 0, width: 800, height: 600 });
    });

    test('rects are written top-down and flipped for WebGL', () => {
        // The top-left quarter is at the TOP of the canvas, so in GL's
        // bottom-left origin its y is the canvas height minus its own.
        expect(pixelRect([0, 0, 0.5, 0.5], CANVAS, 600))
            .toEqual({ x: 0, y: 300, width: 400, height: 300 });
        expect(pixelRect([0, 0.5, 0.5, 0.5], CANVAS, 600))
            .toEqual({ x: 0, y: 0, width: 400, height: 300 });
    });

    test('a rect is placed within the page, not the canvas', () => {
        // A sheet sits inset on the canvas, so the same rect lands somewhere
        // else -- this is what stops pan and zoom having to touch a camera.
        const sheet = { x: 100, y: 50, width: 400, height: 300 };
        expect(pixelRect([0, 0, 0.5, 0.5], sheet, 600))
            .toEqual({ x: 100, y: 400, width: 200, height: 150 });
    });

    test('a sliver still gets a pixel, so nothing divides by zero', () => {
        const rect = pixelRect([0, 0, 0.0001, 0.0001], CANVAS, 600);
        expect(rect.width).toBeGreaterThan(0);
        expect(rect.height).toBeGreaterThan(0);
    });
});

describe('viewportAspect', () => {
    test('a full-canvas viewport takes the canvas aspect', () => {
        expect(viewportAspect([0, 0, 1, 1], 800, 400)).toBe(2);
    });

    test('a half-width viewport is half as wide as the canvas, not as wide', () => {
        // Giving a camera the canvas aspect here is what renders a frame
        // stretched across its viewport.
        expect(viewportAspect([0, 0, 0.5, 1], 800, 400)).toBe(1);
    });

    test('a stacked elevation is taller than it is wide', () => {
        expect(viewportAspect([0, 0, 0.5, 0.25], 800, 400)).toBe(4);
    });

    test('a viewport with no height does not divide by zero', () => {
        expect(viewportAspect([0, 0, 1, 0], 800, 400)).toBe(1);
    });
});

describe('viewportAtPoint', () => {
    const viewports = [
        { id: 'left', rect: [0, 0, 0.5, 1] },
        { id: 'right', rect: [0.5, 0, 0.5, 1] },
    ];

    test('finds the viewport under a canvas point', () => {
        expect(viewportAtPoint(viewports, 100, 300, CANVAS).id).toBe('left');
        expect(viewportAtPoint(viewports, 700, 300, CANVAS).id).toBe('right');
    });

    test('later viewports win where they overlap', () => {
        const stacked = [{ id: 'under', rect: [0, 0, 1, 1] }, { id: 'over', rect: [0, 0, 0.5, 1] }];
        expect(viewportAtPoint(stacked, 100, 300, CANVAS).id).toBe('over');
    });

    test('a point off the canvas belongs to no viewport', () => {
        expect(viewportAtPoint(viewports, -5, 300, CANVAS)).toBeNull();
    });
});

describe('the store', () => {
    test('starts in the default 3D scene', () => {
        const store = new SceneStore();
        expect(store.activeSceneId).toBe(DEFAULT_SCENE_ID);
        expect(store.activeViewports()).toHaveLength(1);
    });

    test('taking scenes from python keeps the 3D scene alongside them', () => {
        const store = new SceneStore();
        store.setScenes([{ id: 'post_A', viewports: [{ rect: [0, 0, 0.5, 1] }] }]);
        expect(store.sceneIds()).toEqual([DEFAULT_SCENE_ID, 'post_A']);
    });

    test('switching scenes reports the change once', () => {
        const store = new SceneStore();
        store.setScenes([{ id: 'post_A' }]);
        const seen = [];
        store.onChanged((event) => seen.push(event.sceneId));
        expect(store.setActiveScene('post_A')).toBe(true);
        expect(store.setActiveScene('post_A')).toBe(false);
        expect(seen).toEqual(['post_A']);
    });

    test('switching to a scene that does not exist is refused', () => {
        const store = new SceneStore();
        expect(store.setActiveScene('nope')).toBe(false);
        expect(store.activeSceneId).toBe(DEFAULT_SCENE_ID);
    });

    test('a reload that drops the active scene falls back to the 3D scene', () => {
        const store = new SceneStore();
        store.setScenes([{ id: 'post_A' }]);
        store.setActiveScene('post_A');
        store.setScenes([{ id: 'post_B' }]);
        expect(store.activeSceneId).toBe(DEFAULT_SCENE_ID);
    });

    test('the 3D scene wants camera controls and a drawing does not', () => {
        const store = new SceneStore();
        expect(store.wantsCameraControl('cube')).toBe(true);
        store.setScenes([{ id: 'post_A' }]);
        store.setActiveScene('post_A');
        expect(store.wantsCameraControl('cube')).toBe(false);
    });
});

describe('orbitDistanceForExtent', () => {
    // The viewer sizes an orthographic frustum as orbitDist * tan(fov/2), so
    // this has to invert that exactly or a locked elevation frames the model
    // at the wrong scale.
    it('inverts the frustum sizing the viewer applies', () => {
        const distance = orbitDistanceForExtent(0.609, 45);
        expect(distance * Math.tan((45 * Math.PI) / 360)).toBeCloseTo(0.609, 9);
    });

    it('is further back for a taller view', () => {
        expect(orbitDistanceForExtent(2, 45)).toBeGreaterThan(orbitDistanceForExtent(1, 45));
    });

    it('is further back for a narrower lens', () => {
        expect(orbitDistanceForExtent(1, 20)).toBeGreaterThan(orbitDistanceForExtent(1, 45));
    });

    it('keeps a degenerate extent off the camera plane', () => {
        expect(orbitDistanceForExtent(0, 45)).toBeGreaterThan(0);
        expect(orbitDistanceForExtent(-5, 45)).toBeGreaterThan(0);
    });

    it('refuses a lens that has no angle', () => {
        expect(orbitDistanceForExtent(1, 0)).toBe(0);
        expect(orbitDistanceForExtent(1, undefined)).toBe(0);
    });
});

describe('normalizePage', () => {
    test('a sheet keeps its size in metres', () => {
        expect(normalizePage({ width: 0.42, height: 0.297 })).toEqual({ width: 0.42, height: 0.297 });
    });

    test('no page means the canvas is the page', () => {
        expect(normalizePage(null)).toBeNull();
        expect(normalizePage(undefined)).toBeNull();
    });

    test('a sheet with no area is not a sheet', () => {
        expect(normalizePage({ width: 0, height: 0.297 })).toBeNull();
        expect(normalizePage({ width: -1, height: 0.297 })).toBeNull();
        expect(normalizePage({ width: 'wide', height: 0.297 })).toBeNull();
    });
});

describe('normalizePageView', () => {
    test('the default view is the whole sheet, unmoved', () => {
        expect(normalizePageView(undefined)).toEqual({ zoom: 1, offsetX: 0, offsetY: 0 });
    });

    test('zoom is clamped rather than allowed to invert or vanish', () => {
        expect(normalizePageView({ zoom: 0 }).zoom).toBeGreaterThan(0);
        expect(normalizePageView({ zoom: -3 }).zoom).toBeGreaterThan(0);
        expect(normalizePageView({ zoom: 1e9 }).zoom).toBeLessThan(1e9);
    });
});

describe('pageScreenRect', () => {
    const page = { width: 0.42, height: 0.297 };

    test('no page means the whole canvas', () => {
        expect(pageScreenRect(null, 800, 600, { zoom: 4, offsetX: 90 }))
            .toEqual({ x: 0, y: 0, width: 800, height: 600 });
    });

    test('a sheet keeps its own aspect, so it letterboxes', () => {
        const rect = pageScreenRect(page, 800, 600, null);
        expect(rect.width / rect.height).toBeCloseTo(page.width / page.height, 9);
        expect(rect.width).toBeLessThanOrEqual(800);
        expect(rect.height).toBeLessThanOrEqual(600);
    });

    test('the sheet is centred, and pan moves it', () => {
        const centred = pageScreenRect(page, 800, 600, null);
        expect(centred.x + centred.width / 2).toBeCloseTo(400, 9);
        expect(centred.y + centred.height / 2).toBeCloseTo(300, 9);

        const panned = pageScreenRect(page, 800, 600, { offsetX: 30, offsetY: -20 });
        expect(panned.x).toBeCloseTo(centred.x + 30, 9);
        expect(panned.y).toBeCloseTo(centred.y - 20, 9);
    });

    test('zoom scales the sheet and leaves its aspect alone', () => {
        const once = pageScreenRect(page, 800, 600, { zoom: 1 });
        const twice = pageScreenRect(page, 800, 600, { zoom: 2 });
        expect(twice.width).toBeCloseTo(once.width * 2, 9);
        expect(twice.height).toBeCloseTo(once.height * 2, 9);
        expect(twice.width / twice.height).toBeCloseTo(once.width / once.height, 9);
    });

    test('a zoomed sheet leaves every viewport aspect untouched', () => {
        // The property the whole design rests on: zooming the page is rect
        // arithmetic, so no camera has to be told and none can drift.
        const rect = [0.1, 0.1, 0.4, 0.35];
        const at = (zoom) => {
            const sheet = pageScreenRect(page, 800, 600, { zoom });
            return viewportAspect(rect, sheet.width, sheet.height);
        };
        expect(at(3)).toBeCloseTo(at(1), 9);
        expect(at(0.25)).toBeCloseTo(at(1), 9);
    });
});

describe('viewportScale', () => {
    // A3 landscape, a view filling the top-left quarter: 148.5mm of paper.
    const page = { width: 0.42, height: 0.297 };
    const rect = [0, 0, 0.5, 0.5];

    test('scale follows from the extent, the rect and the page', () => {
        // 1.485m of world in 0.1485m of paper is 1:10.
        expect(viewportScale(0.7425, rect, page)).toBeCloseTo(10, 9);
    });

    test('it round-trips with the extent that satisfies it', () => {
        const extent = extentForScale(20, rect, page);
        expect(viewportScale(extent, rect, page)).toBeCloseTo(20, 9);
    });

    test('a bigger view on the same paper is a smaller scale', () => {
        expect(viewportScale(1, rect, page)).toBeGreaterThan(viewportScale(0.5, rect, page));
    });

    test('scale means nothing without a sheet', () => {
        expect(viewportScale(1, rect, null)).toBeNull();
        expect(extentForScale(20, rect, null)).toBeNull();
    });

    test('a nonsense scale is refused rather than guessed at', () => {
        expect(extentForScale(0, rect, page)).toBeNull();
        expect(extentForScale(-5, rect, page)).toBeNull();
        expect(extentForScale(NaN, rect, page)).toBeNull();
    });
});

describe('a scene with a page', () => {
    test('the page comes through normalization', () => {
        const scene = normalizeScene({ id: 'd', page: { width: 0.42, height: 0.297 }, viewports: [] });
        expect(scene.page).toEqual({ width: 0.42, height: 0.297 });
    });

    test('a viewport may state a scale instead of an extent', () => {
        const scene = normalizeScene({
            id: 'd',
            page: { width: 0.42, height: 0.297 },
            viewports: [{
                id: 'front',
                rect: [0, 0, 0.5, 0.5],
                camera: { right: [1, 0, 0], up: [0, 0, 1], look: [0, 1, 0], target: [0, 0, 0], scale: 20 },
            }],
        });
        expect(scene.viewports[0].camera.extent).toBeCloseTo(extentForScale(20, [0, 0, 0.5, 0.5], { width: 0.42, height: 0.297 }), 9);
    });

    test('a stated extent is left alone', () => {
        const scene = normalizeScene({
            id: 'd',
            page: { width: 0.42, height: 0.297 },
            viewports: [{
                id: 'front',
                rect: [0, 0, 0.5, 0.5],
                camera: { right: [1, 0, 0], up: [0, 0, 1], look: [0, 1, 0], target: [0, 0, 0], extent: 2, scale: 20 },
            }],
        });
        expect(scene.viewports[0].camera.extent).toBe(2);
    });

    test('a viewport draws on nothing unless it says otherwise', () => {
        const scene = normalizeScene({ id: 'd', viewports: [{ id: 'a' }] });
        expect(scene.viewports[0].background).toBeNull();
    });

    test('the default 3D scene has no page, so the canvas is the page', () => {
        expect(defaultSceneSpec().page).toBeNull();
    });
});

describe('firstLoadCameraPlan', () => {
    // Both rules here were shipped broken and only showed up when a rendered
    // sheet was measured against where its cameras said the model should be.
    const bounds = { center: { x: 1, y: 2, z: 3 }, radius: 4, fovDegrees: 45 };
    const drawing = [
        { id: 'front', locked: true },
        { id: 'top', locked: true },
        { id: 'preview', locked: false },
    ];

    it('leaves a locked viewport where the drawing put it', () => {
        // Fitting an elevation to the model replaces the view that was asked
        // for with a general view of everything, at the wrong scale.
        const plan = firstLoadCameraPlan(drawing, bounds);
        expect(plan[0].frame).toBeNull();
        expect(plan[1].frame).toBeNull();
    });

    it('frames the viewports that have nothing better to point at', () => {
        const preview = firstLoadCameraPlan(drawing, bounds)[2];
        expect(preview.frame).not.toBeNull();
        expect(preview.frame.center).toEqual({ x: 1, y: 2, z: 3 });
        expect(preview.frame.orbitDist).toBeGreaterThan(0);
    });

    it('gives near and far to every viewport, locked or not', () => {
        // Applying these to the active viewport alone leaves the rest of a
        // drawing on the placeholder range they were constructed with.
        const plan = firstLoadCameraPlan(drawing, bounds);
        expect(plan).toHaveLength(3);
        for (const entry of plan) {
            expect(entry.near).toBeGreaterThan(0);
            expect(entry.far).toBeGreaterThan(entry.near);
        }
        expect(new Set(plan.map((entry) => entry.near)).size).toBe(1);
        expect(new Set(plan.map((entry) => entry.far)).size).toBe(1);
    });

    it('keeps the order it was given, so entries pair with viewports', () => {
        expect(firstLoadCameraPlan(drawing, bounds).map((entry) => entry.id))
            .toEqual(['front', 'top', 'preview']);
    });

    it('frames the single viewport of the 3D scene', () => {
        const plan = firstLoadCameraPlan([{ id: 'main', locked: false }], bounds);
        expect(plan[0].frame.orbitDist).toBeGreaterThan(bounds.radius);
    });

    it('pushes the camera back further for a bigger model', () => {
        const near = firstLoadCameraPlan([{ id: 'main' }], { ...bounds, radius: 1 })[0];
        const far = firstLoadCameraPlan([{ id: 'main' }], { ...bounds, radius: 10 })[0];
        expect(far.frame.orbitDist).toBeGreaterThan(near.frame.orbitDist);
        expect(far.far).toBeGreaterThanOrEqual(near.far);
    });

    it('survives a frame with no size and an empty scene', () => {
        expect(firstLoadCameraPlan([], bounds)).toEqual([]);
        expect(firstLoadCameraPlan(null, bounds)).toEqual([]);
        const degenerate = firstLoadCameraPlan([{ id: 'main' }], { radius: 0 })[0];
        expect(degenerate.frame.orbitDist).toBeGreaterThan(0);
        expect(degenerate.near).toBeGreaterThan(0);
    });
});

describe('zoomPageAt', () => {
    const page = { width: 0.42, height: 0.297 };

    it('leaves whatever is under the cursor under the cursor', () => {
        // The whole point of zooming toward a pointer, and the thing that is
        // fiddly in world space and arithmetic here.
        const before = pageScreenRect(page, 800, 600, null);
        const pointX = before.x + before.width * 0.3;
        const pointY = before.y + before.height * 0.8;
        const after = pageScreenRect(page, 800, 600, zoomPageAt(page, null, 800, 600, pointX, pointY, 2));
        expect(after.x + after.width * 0.3).toBeCloseTo(pointX, 6);
        expect(after.y + after.height * 0.8).toBeCloseTo(pointY, 6);
    });

    it('zooms in and out about the same point consistently', () => {
        const view = zoomPageAt(page, null, 800, 600, 400, 300, 2.5);
        expect(view.zoom).toBeCloseTo(2.5, 9);
        const back = zoomPageAt(page, view, 800, 600, 400, 300, 1 / 2.5);
        expect(back.zoom).toBeCloseTo(1, 9);
    });

    it('refuses a nonsense factor rather than losing the sheet', () => {
        expect(zoomPageAt(page, null, 800, 600, 400, 300, 0).zoom).toBe(1);
        expect(zoomPageAt(page, null, 800, 600, 400, 300, -2).zoom).toBe(1);
        expect(zoomPageAt(page, null, 800, 600, 400, 300, NaN).zoom).toBe(1);
    });

    it('does nothing without a sheet, where the camera zooms instead', () => {
        expect(zoomPageAt(null, { zoom: 3 }, 800, 600, 400, 300, 2).zoom).toBe(3);
    });
});

describe('panPage', () => {
    const page = { width: 0.42, height: 0.297 };

    it('moves the sheet by the drag', () => {
        const view = panPage(page, null, 800, 600, 40, -25);
        const moved = pageScreenRect(page, 800, 600, view);
        const still = pageScreenRect(page, 800, 600, null);
        expect(moved.x).toBeCloseTo(still.x + 40, 6);
        expect(moved.y).toBeCloseTo(still.y - 25, 6);
    });

    it('keeps some of the sheet on the canvas, however hard it is thrown', () => {
        // Panning the paper out of the window with no way back is the one
        // outcome worth making impossible.
        let view = null;
        for (let i = 0; i < 40; i += 1) {
            view = panPage(page, view, 800, 600, 500, 500);
        }
        const rect = pageScreenRect(page, 800, 600, view);
        expect(rect.x).toBeLessThan(800);
        expect(rect.y).toBeLessThan(600);
        expect(rect.x + rect.width).toBeGreaterThan(0);
        expect(rect.y + rect.height).toBeGreaterThan(0);
    });

    it('leaves the zoom alone', () => {
        expect(panPage(page, { zoom: 2.5 }, 800, 600, 10, 10).zoom).toBeCloseTo(2.5, 9);
    });

    it('does nothing without a sheet', () => {
        expect(panPage(null, { offsetX: 5 }, 800, 600, 40, 40).offsetX).toBe(5);
    });
});
