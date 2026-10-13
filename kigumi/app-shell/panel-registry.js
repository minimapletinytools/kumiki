/**
 * The kinds of panel the app shell can show, and where each lives.
 *
 * The layout is fixed: `left` (one panel), `center` (two tab groups side by side: `code` for
 * sources, `view` for what they build), `bottom` (one panel, under the groups), `right` (one panel).
 */

const SLOTS = Object.freeze(['left', 'center', 'bottom', 'right']);
const GROUPS = Object.freeze(['code', 'view']);

const PANEL_TYPES = Object.freeze({
    explorer: { slot: 'left', icon: 'files' },
    viewer: { slot: 'center', group: 'view', icon: 'fish2-very-sad', redrawAfterReload: true },
    log: { slot: 'center', group: 'code', icon: 'output' },
    editor: { slot: 'center', group: 'code', icon: 'file-code' },
    inspector: { slot: 'bottom', icon: 'layout-panel' },
    agent: { slot: 'right', icon: 'sparkle' },
});

function panelType(type) {
    const spec = PANEL_TYPES[type];
    if (!spec) {
        throw new Error(`Unknown panel type "${type}". Known: ${Object.keys(PANEL_TYPES).join(', ')}`);
    }
    return spec;
}

module.exports = { SLOTS, GROUPS, PANEL_TYPES, panelType };
