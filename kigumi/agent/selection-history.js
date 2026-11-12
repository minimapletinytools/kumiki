/**
 * The user's recent selections in the views, newest last, kept in memory for an agent to ask about
 * (agent/tools.js get_selection_history). A selection is webview/selection-copy.js's
 * { frameName, members, feature }.
 */

const SELECTION_HISTORY_LIMIT = 20;

/** The member keys and feature that make a selection the same as another. */
function identity({ panelId, selection }) {
    const feature = selection.feature;
    return JSON.stringify([panelId, (selection.members || []).map((member) => member.key),
        feature ? [feature.memberKey, feature.path, feature.featureLabel] : null]);
}

function createSelectionHistory({ limit = SELECTION_HISTORY_LIMIT, now = () => new Date() } = {}) {
    const entries = [];

    return {
        /**
         * Keep `entry` ({ panelId, filePath, slotName?, view?, selection }); an empty selection, or
         * the same as the last one kept, is not kept.
         */
        record(entry) {
            const selection = entry && entry.selection;
            if (!selection || (!(selection.members || []).length && !selection.feature)) return;
            const last = entries[entries.length - 1];
            if (last && identity(last) === identity(entry)) return;
            entries.push({ at: now().toISOString(), ...entry });
            entries.splice(0, Math.max(0, entries.length - limit));
        },

        /** The last `count` selections, newest first. */
        list(count = limit) {
            return entries.slice(-Math.max(0, count)).reverse();
        },
    };
}

module.exports = { createSelectionHistory, SELECTION_HISTORY_LIMIT };
