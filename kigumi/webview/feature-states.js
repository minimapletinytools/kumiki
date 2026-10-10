(function (globalScope) {
    'use strict';
    // What state each lit feature is in.
    //
    // A feature can be lit for several reasons at once: it is the selection,
    // the pointer is over it, and it is the held end of a measurement. Each
    // reason used to be its own source with its own key, so there was no one
    // answer to "what is this feature doing". Here the sources are merged by one
    // feature key into a FeatureState: { key, roles }, where each role keeps
    // the geometry its source sent.
    //
    // Pure. highlights.js draws from these. See .claude/plans/render-states.md.

    /** The roles a feature can have, in the order their overlays are listed. */
    const ROLES = Object.freeze(['selection', 'hover', 'held']);

    /**
     * One key for a feature, whichever source names it: member, CSG path and
     * feature label, as a selection focus and a hover answer both carry them.
     * A node with no feature is keyed by its path alone.
     */
    function featureKeyOf({ memberKey, timberKey, path, featureLabel } = {}) {
        return `${memberKey || timberKey || ''}|${(path || []).join('/')}|${featureLabel || ''}`;
    }

    /**
     * The lit features, merged by key.
     *
     * `sources` maps a role to null or a source with a `key` (from featureKeyOf)
     * and the geometry to draw. Returns FeatureStates in the order their keys
     * first appear, taking the roles in ROLES order.
     */
    function featureStatesFor(sources) {
        const found = sources || {};
        const states = new Map();
        for (const role of ROLES) {
            const source = found[role];
            if (!source || !source.key) {
                continue;
            }
            if (!states.has(source.key)) {
                states.set(source.key, { key: source.key, roles: {} });
            }
            states.get(source.key).roles[role] = source;
        }
        return Array.from(states.values());
    }

    /**
     * A FeatureState as plain comparable data: which feature, which roles, and
     * whether the hover is refused. Geometry is left out -- it follows the key.
     */
    function featureStateSummary(state) {
        const roles = state.roles || {};
        return [
            state.key,
            ROLES.filter((role) => roles[role]),
            Boolean(roles.hover && roles.hover.refused),
        ];
    }

    const KigumiFeatureStates = { ROLES, featureKeyOf, featureStatesFor, featureStateSummary };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiFeatureStates;
    }
    globalScope.KigumiFeatureStates = KigumiFeatureStates;
})(typeof window !== 'undefined' ? window : globalThis);
