(function (globalScope) {
    'use strict';
    // How the renderer should be set up, given what is being drawn.
    //
    // A sheet and the 3D model want different things from the same renderer and
    // the same scene, and the two used to be reached by toggling one property
    // here and another there on the way in and out. That is how state carries
    // over: each toggle is a separate promise to remember, and the one nobody
    // remembers is a ground plane left lying across an elevation.
    //
    // So the mode is computed rather than toggled. renderModeFor() takes what
    // is being drawn and what the reader has asked for, and returns EVERY
    // property that differs between the two -- always all of them, never a
    // difference from what is already set. The caller writes the lot
    // unconditionally on every frame, so nothing survives a switch that the
    // current mode did not ask for.
    //
    // Two rules keep it that way, and both are checked by the tests:
    //
    //   - the two modes describe the same set of properties, so a property
    //     added for one cannot be forgotten for the other;
    //   - nothing here reads the renderer. A mode is a function of the scene
    //     and the settings, so it cannot depend on the mode before it.
    //
    // What belongs here: anything whose right value differs between a sheet
    // and the model. What does not: anything per-viewport -- a sheet has
    // several and they differ from each other, so that is an argument to
    // whatever needs it, not a mode.

    /**
     * How a sheet is lit.
     *
     * Not by the sun. A drawing has already thrown away which way the piece
     * faces in the world -- that is what projecting it does -- so shading from
     * a light fixed in the world says nothing about the drawing, and changes
     * under the reader as the 3D view's light dial moves. A front elevation
     * would be bright in the morning and dark in the afternoon.
     *
     * The sheet gets its own light instead, aimed exactly where its viewport's
     * camera points. Mostly ambient, with enough of a directional term that a
     * face turned away from the viewer reads slightly darker than one square
     * to it -- information about the piece rather than about the sun. A face
     * seen edge-on keeps the full ambient and goes no darker, so nothing on a
     * sheet is ever black.
     *
     * For a completely flat sheet, set viewLight to 0 and ambient to 1.
     */
    const SHEET_LIGHTS = { ambient: 0.78, sun: 0, fill: 0, viewLight: 0.32 };

    /** How the model is lit: a sun the light dial moves, plus a cool fill. */
    const MODEL_LIGHTS = { ambient: 0.61, sun: 0.62, fill: 0.34, viewLight: 0 };

    /**
     * Everything that depends on which of the two is being drawn.
     *
     * `page` is the active scene's page, so truthy means a sheet. `settings`
     * carries what the reader has asked for -- the INTENT, which outlives a
     * trip to a sheet and back. Nothing here writes to those; a mode is
     * derived from them, so asking for shadows while on a sheet is remembered
     * and applied again on the way out.
     */
    function renderModeFor({ page, shadowsEnabled = false, reflectionsEnabled = false } = {}) {
        const onPaper = Boolean(page);
        return {
            onPaper,
            lights: onPaper ? { ...SHEET_LIGHTS } : { ...MODEL_LIGHTS },
            // A ground plane in an elevation is a grey band across the sheet.
            // It is there to catch the sun, and on paper there is no sun.
            shadowCatcherVisible: !onPaper && Boolean(shadowsEnabled),
            // The shadow pass is work for a light that contributes nothing on
            // a sheet, so it is not merely invisible there, it is not run.
            shadowMapEnabled: !onPaper && Boolean(shadowsEnabled),
            sunCastsShadow: !onPaper && Boolean(shadowsEnabled),
            // A reflection is the piece mirrored in the ground it is standing
            // on. A sheet has no ground -- it is a projection onto paper, and
            // there is nothing under the piece to catch one -- so a drawing
            // showing one is showing something that is not there.
            reflectionsVisible: !onPaper && Boolean(reflectionsEnabled),
            // three paints a scene background as a full pass inside the active
            // viewport whatever the clear flags say, so on a sheet it would
            // repaint the gradient over every neighbour and nothing would
            // float. The page paints the paper there instead.
            useThemeBackground: !onPaper,
            // A viewport on a sheet draws on nothing: clearing colour would
            // erase the paper and any neighbour it overlaps, which is exactly
            // what floating means.
            autoClear: !onPaper,
        };
    }

    /** The property names every mode describes. Exported for the caller's tests. */
    const RENDER_MODE_KEYS = Object.freeze(Object.keys(renderModeFor({ page: null })));
    const RENDER_MODE_LIGHT_KEYS = Object.freeze(Object.keys(MODEL_LIGHTS));

    const KigumiRenderMode = {
        renderModeFor, RENDER_MODE_KEYS, RENDER_MODE_LIGHT_KEYS,
        SHEET_LIGHTS, MODEL_LIGHTS,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiRenderMode;
    }
    globalScope.KigumiRenderMode = KigumiRenderMode;
})(typeof window !== 'undefined' ? window : globalThis);
