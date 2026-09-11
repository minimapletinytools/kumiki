const {
    renderModeFor,
    RENDER_MODE_KEYS,
    RENDER_MODE_LIGHT_KEYS,
} = require('../webview/render-mode.js');

const SHEET = { page: { width: 297, height: 210 } };
const MODEL = { page: null };

describe('what a mode describes', () => {
    // The reason this module exists. A sheet and the model are reached by
    // writing the same set of properties, so a property added for one cannot
    // be quietly missing from the other and left holding whatever the previous
    // mode set -- which is how a ground plane ends up lying across an
    // elevation.
    it('both modes describe exactly the same properties', () => {
        expect(Object.keys(renderModeFor(SHEET)).sort())
            .toEqual(Object.keys(renderModeFor(MODEL)).sort());
    });

    it('both modes set every light', () => {
        for (const scene of [SHEET, MODEL]) {
            expect(Object.keys(renderModeFor(scene).lights).sort())
                .toEqual([...RENDER_MODE_LIGHT_KEYS].sort());
        }
    });

    it('every property is decided, never left undefined', () => {
        for (const scene of [SHEET, MODEL]) {
            const mode = renderModeFor(scene);
            for (const key of RENDER_MODE_KEYS) {
                expect(mode[key]).toBeDefined();
            }
            for (const light of Object.values(mode.lights)) {
                expect(Number.isFinite(light)).toBe(true);
            }
        }
    });

    it('a mode is a function of its inputs and nothing else', () => {
        // No memory between calls, in either direction, so a mode can never
        // depend on the one before it.
        const first = renderModeFor(SHEET);
        renderModeFor(MODEL);
        renderModeFor(MODEL);
        expect(renderModeFor(SHEET)).toEqual(first);
    });

    it('a mode cannot be edited into the next one', () => {
        // Each call returns its own lights object rather than a shared
        // constant, so a caller that scales one is not scaling every later
        // mode as well.
        const mode = renderModeFor(MODEL);
        mode.lights.sun = 99;
        expect(renderModeFor(MODEL).lights.sun).not.toBe(99);
    });
});

describe('lighting a sheet', () => {
    it('the sun is off and the view light is on', () => {
        // A drawing has thrown away which way the piece faces in the world, so
        // a light fixed in the world tells the reader nothing and changes
        // under them as the 3D view's light dial moves.
        const lights = renderModeFor(SHEET).lights;

        expect(lights.sun).toBe(0);
        expect(lights.fill).toBe(0);
        expect(lights.viewLight).toBeGreaterThan(0);
    });

    it('ambient carries most of it, so nothing on the sheet is ever black', () => {
        // A face seen edge-on takes nothing from the view light and keeps the
        // ambient; it should still read as paler than the paper is dark.
        const lights = renderModeFor(SHEET).lights;

        expect(lights.ambient).toBeGreaterThan(lights.viewLight);
        expect(lights.ambient).toBeLessThan(1);
    });

    it('the model keeps its sun and fill, and no view light', () => {
        const lights = renderModeFor(MODEL).lights;

        expect(lights.sun).toBeGreaterThan(0);
        expect(lights.fill).toBeGreaterThan(0);
        expect(lights.viewLight).toBe(0);
    });
});

describe('shadows', () => {
    it('nothing to do with shadows happens on a sheet', () => {
        const mode = renderModeFor({ ...SHEET, shadowsEnabled: true });

        expect(mode.shadowCatcherVisible).toBe(false);
        expect(mode.sunCastsShadow).toBe(false);
        // Not merely invisible: the pass is work for a light contributing
        // nothing, so it does not run.
        expect(mode.shadowMapEnabled).toBe(false);
    });

    it('the ask survives a trip to a sheet and back', () => {
        // The mode reads the setting and never writes it, which is what lets
        // "shadows on" mean the same thing before and after a drawing.
        expect(renderModeFor({ ...MODEL, shadowsEnabled: true })
            .shadowCatcherVisible).toBe(true);
        expect(renderModeFor({ ...SHEET, shadowsEnabled: true })
            .shadowCatcherVisible).toBe(false);
        expect(renderModeFor({ ...MODEL, shadowsEnabled: true })
            .shadowCatcherVisible).toBe(true);
    });

    it('shadows off is off in the model too', () => {
        const mode = renderModeFor({ ...MODEL, shadowsEnabled: false });

        expect(mode.shadowCatcherVisible).toBe(false);
        expect(mode.shadowMapEnabled).toBe(false);
    });
});

describe('reflections', () => {
    it('a sheet never shows one, however the reader has it set', () => {
        // A reflection is the piece mirrored in the ground it stands on. A
        // sheet has no ground -- it is a projection onto paper -- so one there
        // is showing something that is not in front of the reader at all.
        expect(renderModeFor({ ...SHEET, reflectionsEnabled: true })
            .reflectionsVisible).toBe(false);
    });

    it('the ask survives a trip to a sheet and back', () => {
        expect(renderModeFor({ ...MODEL, reflectionsEnabled: true })
            .reflectionsVisible).toBe(true);
        expect(renderModeFor({ ...SHEET, reflectionsEnabled: true })
            .reflectionsVisible).toBe(false);
        expect(renderModeFor({ ...MODEL, reflectionsEnabled: true })
            .reflectionsVisible).toBe(true);
    });

    it('off is off in the model too', () => {
        expect(renderModeFor({ ...MODEL, reflectionsEnabled: false })
            .reflectionsVisible).toBe(false);
    });
});

describe('clearing and the background', () => {
    it('a sheet neither clears colour nor paints a background', () => {
        // A viewport on a sheet draws on nothing: clearing would erase the
        // paper and any neighbour it overlaps, and three paints a scene
        // background as a full pass inside the viewport whatever the clear
        // flags say -- so on a sheet it would repaint over every neighbour.
        const mode = renderModeFor(SHEET);

        expect(mode.autoClear).toBe(false);
        expect(mode.useThemeBackground).toBe(false);
    });

    it('the model does both', () => {
        const mode = renderModeFor(MODEL);

        expect(mode.autoClear).toBe(true);
        expect(mode.useThemeBackground).toBe(true);
    });
});

describe('what counts as a sheet', () => {
    it('any page is a sheet, and none is the model', () => {
        expect(renderModeFor(SHEET).onPaper).toBe(true);
        expect(renderModeFor(MODEL).onPaper).toBe(false);
        expect(renderModeFor({}).onPaper).toBe(false);
        expect(renderModeFor().onPaper).toBe(false);
    });
});
