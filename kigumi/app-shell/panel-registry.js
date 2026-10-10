/**
 * The kinds of panel the app shell can show, and the layout slot each lives in.
 * The layout is fixed: `left` (one panel), `center` (tabs), `right` (one panel).
 */

const SLOTS = Object.freeze(['left', 'center', 'right']);

const PANEL_TYPES = Object.freeze({
    explorer: { slot: 'left', icon: 'files' },
    viewer: { slot: 'center', icon: 'fish2-very-sad', redrawAfterReload: true },
    log: { slot: 'center', icon: 'output' },
    editor: { slot: 'center', icon: 'file-code' },
});

function panelType(type) {
    const spec = PANEL_TYPES[type];
    if (!spec) {
        throw new Error(`Unknown panel type "${type}". Known: ${Object.keys(PANEL_TYPES).join(', ')}`);
    }
    return spec;
}

module.exports = { SLOTS, PANEL_TYPES, panelType };
