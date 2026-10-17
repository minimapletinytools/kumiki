(function (globalScope) {
    'use strict';
    // What state a member is in, and what that state looks like.
    //
    // Two halves, kept apart on purpose. memberStateFor says WHICH state a
    // member is in -- selected, dimmed, hidden, context in a drawing -- and
    // nothing about opacities. appearanceFor turns a state into the numbers a
    // material takes. A new state is a new field here and a row in the tables
    // below, rather than a branch threaded into one function.
    //
    // Both are pure; the caller walks the members and applies the result. See
    // .claude/plans/render-states.md.

    const { SELECTION_VISUAL_STATES } = (typeof module !== 'undefined' && module.exports)
        ? require('./selection-visuals.js')
        : globalScope.KigumiSelectionVisuals;

    /**
     * A member's state.
     *
     * - hidden: hidden from the layers panel.
     * - locked: locked from the layers panel, so it cannot be picked.
     * - selection: 'none' (nothing about it is selected), 'selected' (picked as
     *   a whole), 'drilledInto' (a node or feature inside it is picked), or
     *   'dimmed' (something else is). A drawing has no timber selection, so it
     *   is always 'none' there: picking a feature narrows the focus to its
     *   timber, but the drawing decides how that timber looks, not the
     *   selection.
     * - drawing: 'none' (no drawing open), 'subject' (the drawing is of it, or
     *   of everything), or 'context' (a drawing is open and is not about it).
     *
     * `inDrawing` is needed as well as `drawnMembers` because a drawing that
     * names no members is a drawing of the whole frame, which the member set
     * alone cannot tell apart from the 3D scene.
     */
    function memberStateFor(memberKey, { hidden = false, locked = false, visualContext, drawnMembers = null, inDrawing = false } = {}) {
        let selection = 'none';
        if (!inDrawing) {
            if (visualContext && visualContext.state === SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB) {
                selection = visualContext.selectedTimberSet.has(memberKey) ? 'selected' : 'dimmed';
            } else if (visualContext && visualContext.hasSubselection) {
                selection = visualContext.subselectionTimberKey === memberKey ? 'drilledInto' : 'dimmed';
            }
        }
        let drawing = 'none';
        if (drawnMembers) {
            drawing = drawnMembers.has(memberKey) ? 'subject' : 'context';
        } else if (inDrawing) {
            drawing = 'subject';
        }
        return { hidden: Boolean(hidden), locked: Boolean(locked), selection, drawing };
    }

    /** How much a locked member is faded, faces and edges. */
    const LOCKED_OPACITY_FACTOR = 0.5;

    /** How each selection state looks, before anything else is applied. */
    const SELECTION_LOOKS = Object.freeze({
        none: (settings) => ({ name: 'normal', opacity: settings.baseSelectedOpacity }),
        selected: (settings) => ({ name: 'selected', opacity: settings.baseSelectedOpacity }),
        drilledInto: (settings) => ({ name: 'selected', opacity: settings.policy.selectedTimberOpacity }),
        dimmed: (settings) => ({ name: 'ghost', opacity: settings.policy.dimmedOpacity }),
    });

    /**
     * What a state looks like, as the numbers setMemberAppearance writes.
     *
     * Precedence, in order:
     *   1. hidden wins outright;
     *   2. otherwise the selection decides the look (SELECTION_LOOKS);
     *   3. then a locked member is faded by `lockedOpacityFactor`, faces and
     *      edges both: it is there but cannot be picked;
     *   4. then a drawing's context is ghosted (or hidden) and capped at
     *      `drawingContextOpacity`, faces and edges both, whatever the
     *      selection said.
     *
     * `settings`: baseSelectedOpacity, policy (selection-visuals), profile (the
     * member's render profile, or null), edgeLineVisibilityPercent, edgeMode,
     * showDrawingGhosts, drawingContextOpacity, lockedOpacityFactor.
     */
    function appearanceFor(state, settings) {
        let look;
        let asContext = false;
        let edgeFactor = 1;
        if (state.hidden) {
            look = { name: 'hidden', opacity: settings.baseSelectedOpacity };
        } else {
            look = SELECTION_LOOKS[state.selection](settings);
            if (state.locked) {
                const factor = settings.lockedOpacityFactor ?? LOCKED_OPACITY_FACTOR;
                look = { name: 'locked', opacity: look.opacity * factor };
                edgeFactor = factor;
            }
            if (state.drawing === 'context') {
                // A drawing is about the members it names; the rest of the frame
                // is there for context and is ghosted whatever the selection says,
                // far fainter than a ghost in the 3D scene.
                asContext = true;
                look = {
                    name: settings.showDrawingGhosts ? 'ghost' : 'hidden',
                    opacity: Math.min(look.opacity, settings.drawingContextOpacity),
                };
            }
        }

        const profile = settings.profile;
        const edgeVisibility = settings.edgeLineVisibilityPercent / 100;
        // Edge opacity is independent of face opacity: a member with transparent
        // faces keeps its edges at full strength, relative to the edge slider.
        // A drawing's context is the exception -- faded faces behind crisp
        // outlines would read as another piece of the drawing.
        const edgeOpacity = (profile ? profile.edgeOpacity * edgeVisibility : edgeVisibility)
            * (asContext ? settings.drawingContextOpacity : 1) * edgeFactor;

        return {
            name: look.name,
            opacity: look.opacity,
            edgeOpacity,
            edgesVisible: settings.edgeMode !== 'none',
            // Reflections fade with the faces. Whether one shows at all is the
            // render mode's.
            reflectionOpacity: (profile ? profile.reflectionOpacity : 0.14) * look.opacity,
        };
    }

    const KigumiMemberStates = { memberStateFor, appearanceFor, SELECTION_LOOKS, LOCKED_OPACITY_FACTOR };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiMemberStates;
    }
    globalScope.KigumiMemberStates = KigumiMemberStates;
})(typeof window !== 'undefined' ? window : globalThis);
