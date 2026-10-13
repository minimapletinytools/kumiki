/**
 * Every open panel an agent can ask about: the app's views, and whatever else the host shows.
 *
 * Host-neutral. Views come from the app's sessions; a host with panels of its own (the
 * standalone app's editor and log tabs) adds them through two optional methods:
 *
 *   host.listPanels()        -> [{ id, kind, title, filePath?, active, visible, central }]
 *   host.describePanel(id)   -> Promise<object|null>, what that panel holds and has selected
 *
 * A panel's description always says its `kind`; a viewer's carries `selection` (see
 * webview/selection-copy.js), an editor's the selected text.
 */

const path = require('path');

/**
 * @param {object} options
 * @param {() => Iterable<{id: string, session: object}>} options.views  open view sessions by panel id
 * @param {object} options.host
 */
function createPanelDirectory({ views, host }) {
    function liveViews() {
        return [...views()].filter(({ session }) => session && !session.isDisposed);
    }

    function viewEntry({ id, session }) {
        const panel = session.panel || null;
        return {
            id,
            kind: 'viewer',
            title: (panel && panel.title) || path.basename(session.filePath || ''),
            filePath: session.filePath || null,
            active: Boolean(panel && panel.active),
            visible: Boolean(panel && panel.visible),
            central: true,
        };
    }

    /** Every open panel, views first. */
    function list() {
        const own = liveViews().map(viewEntry);
        const others = typeof host.listPanels === 'function' ? host.listPanels() || [] : [];
        return [...own, ...others];
    }

    /** The main panel with focus; else, with the window not focused (an agent outside asking),
     *  the main panel showing; else nothing. Side panels (the explorer) are never it. */
    function active() {
        const central = list().filter((panel) => panel.central);
        return central.find((panel) => panel.active)
            || central.find((panel) => panel.visible)
            || null;
    }

    /** The view session behind a panel id, or the active view's when none is given. */
    function viewSession(id) {
        const target = id || (active() || {}).id;
        const found = liveViews().find((view) => view.id === target)
            || (id ? null : liveViews()[0]);
        return found ? found.session : null;
    }

    /** What a panel holds and has selected; the active panel when no id is given. */
    async function describe(id) {
        const target = id || (active() || {}).id;
        if (!target) {
            return null;
        }
        const view = liveViews().find((entry) => entry.id === target);
        if (view) {
            return { id: target, ...(await view.session.describePanel()) };
        }
        if (typeof host.describePanel === 'function') {
            const described = await host.describePanel(target);
            return described ? { id: target, ...described } : null;
        }
        return null;
    }

    /** The view session drawing into a surface, if any. */
    function sessionForSurface(surface) {
        const found = surface ? liveViews().find(({ session }) => session.panel === surface) : null;
        return found ? found.session : null;
    }

    return { list, active, describe, viewSession, sessionForSurface };
}

module.exports = { createPanelDirectory };
