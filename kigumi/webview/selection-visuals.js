(function (globalScope) {
    'use strict';
    // How a selection decides what every timber looks like.
    //
    // Pure, and now in a file that can be imported: it was written inside
    // viewer-app.js with a comment saying the decision is "pure and
    // independently testable", and then never tested -- because viewer-app.js
    // pulls in lit and defines a custom element, so nothing in node can load
    // it. Five states and a fallback went unchecked for that reason alone.
    //
    // Two halves. WHICH state the selection is in, from a plain snapshot; and
    // what that state does to the opacities. Neither touches the scene: the
    // caller walks the members and applies what this returns.

    const SELECTION_VISUAL_STATES = Object.freeze({
        NOTHING_SELECTED: 'nothing_selected',
        TIMBER_SELECTED_NO_SUB: 'timber_selected_no_sub',
        TAGGED_CSG_SELECTED_NO_SUB: 'tagged_csg_selected_no_sub',
        TAGGED_CSG_SELECTED_WITH_SUB: 'tagged_csg_selected_with_sub',
        FEATURE_SELECTED: 'feature_selected',
    });

    // Classify the current selection into one of SELECTION_VISUAL_STATES from a
    // plain snapshot (list of selected timber keys + the csg focus), so the
    // decision is pure and independently testable.
    function computeSelectionVisualContext(selectedTimbers, csgFocus) {
        const selectedTimberSet = new Set(selectedTimbers);
        if (selectedTimberSet.size === 0) {
            return {
                state: SELECTION_VISUAL_STATES.NOTHING_SELECTED,
                selectedTimberSet,
                hasSubselection: false,
                subselectionTimberKey: null,
            };
        }

        const csg = csgFocus;
        const path = csg && Array.isArray(csg.path) ? csg.path : [];
        const featureLabel = csg && csg.featureLabel ? csg.featureLabel : null;
        const csgTimberKey = csg && csg.timberKey ? csg.timberKey : null;
        const hasSubselection = !!csg && (path.length > 0 || !!featureLabel);
        if (!hasSubselection) {
            return {
                state: SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB,
                selectedTimberSet,
                hasSubselection: false,
                subselectionTimberKey: null,
            };
        }

        const subselectionTimberKey = csgTimberKey
            || (selectedTimbers.length === 1 ? selectedTimbers[0] : null);

        let state;
        if (featureLabel) {
            state = SELECTION_VISUAL_STATES.FEATURE_SELECTED;
        } else if (path.length >= 2) {
            state = SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_WITH_SUB;
        } else {
            // hasSubselection with no featureLabel guarantees path.length > 0, so
            // the only remaining case here is path.length === 1.
            state = SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB;
        }

        return { state, selectedTimberSet, hasSubselection: true, subselectionTimberKey };
    }

    // Opacity/highlight policy per selection state. dimmedOpacity depends on the
    // user's base unselected opacity, so each entry is a small factory.
    const SELECTION_VISUAL_POLICIES = {
        [SELECTION_VISUAL_STATES.NOTHING_SELECTED]: () => ({
            selectedTimberOpacity: 1.0,
            dimmedOpacity: 1.0,
            csgHighlightOpacity: 0.7,
            parentHighlightOpacity: 0.35,
            featureHighlightOpacity: 0.85,
        }),
        [SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB]: (base) => ({
            selectedTimberOpacity: 1.0,
            dimmedOpacity: base,
            csgHighlightOpacity: 0.7,
            parentHighlightOpacity: 0.35,
            featureHighlightOpacity: 0.85,
        }),
        [SELECTION_VISUAL_STATES.FEATURE_SELECTED]: (base) => ({
            selectedTimberOpacity: 0.62,
            dimmedOpacity: Math.min(base, 0.18),
            csgHighlightOpacity: 0.9,
            parentHighlightOpacity: 0.35,
            featureHighlightOpacity: 0.9,
        }),
        [SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_WITH_SUB]: (base) => ({
            selectedTimberOpacity: 0.66,
            dimmedOpacity: Math.min(base, 0.2),
            csgHighlightOpacity: 0.8,
            parentHighlightOpacity: 0.3,
            featureHighlightOpacity: 0.85,
        }),
        [SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB]: (base) => ({
            selectedTimberOpacity: 0.72,
            dimmedOpacity: Math.min(base, 0.25),
            csgHighlightOpacity: 0.72,
            parentHighlightOpacity: 0.35,
            featureHighlightOpacity: 0.85,
        }),
    };

    function selectionVisualPolicy(state, baseUnselectedOpacity) {
        const factory = SELECTION_VISUAL_POLICIES[state]
            || SELECTION_VISUAL_POLICIES[SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB];
        return factory(baseUnselectedOpacity);
    }

    const KigumiSelectionVisuals = {
        SELECTION_VISUAL_STATES,
        SELECTION_VISUAL_POLICIES,
        computeSelectionVisualContext,
        selectionVisualPolicy,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiSelectionVisuals;
    }
    globalScope.KigumiSelectionVisuals = KigumiSelectionVisuals;
})(typeof window !== 'undefined' ? window : globalThis);
