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
     * - selection: 'none' (nothing about it is selected), 'selected' (picked as
     *   a whole), 'drilledInto' (a node or feature inside it is picked), or
     *   'dimmed' (something else is).
     * - drawing: 'none' (no drawing open), 'subject' (the drawing names it), or
     *   'context' (a drawing is open and does not).
     */
    function memberStateFor(memberKey, { hidden = false, visualContext, drawnMembers = null } = {}) {
        let selection = 'none';
        if (visualContext && visualContext.state === SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB) {
            selection = visualContext.selectedTimberSet.has(memberKey) ? 'selected' : 'dimmed';
        } else if (visualContext && visualContext.hasSubselection) {
            selection = visualContext.subselectionTimberKey === memberKey ? 'drilledInto' : 'dimmed';
        }
        let drawing = 'none';
        if (drawnMembers) {
            drawing = drawnMembers.has(memberKey) ? 'subject' : 'context';
        }
        return { hidden: Boolean(hidden), selection, drawing };
    }

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
     *   3. then a drawing's context is ghosted (or hidden) and capped at
     *      `drawingContextOpacity`, faces and edges both, whatever the
     *      selection said.
     *
     * `settings`: baseSelectedOpacity, policy (selection-visuals), profile (the
     * member's render profile, or null), edgeLineVisibilityPercent, edgeMode,
     * showDrawingGhosts, drawingContextOpacity.
     */
    function appearanceFor(state, settings) {
        let look;
        let asContext = false;
        if (state.hidden) {
            look = { name: 'hidden', opacity: settings.baseSelectedOpacity };
        } else {
            look = SELECTION_LOOKS[state.selection](settings);
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
            * (asContext ? settings.drawingContextOpacity : 1);

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

    const KigumiMemberStates = { memberStateFor, appearanceFor, SELECTION_LOOKS };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiMemberStates;
    }
    globalScope.KigumiMemberStates = KigumiMemberStates;
})(typeof window !== 'undefined' ? window : globalThis);
