/**
 * The inspector: a panel outside the views that shows the current view's member list and log,
 * following whichever view is showing. Host-neutral; the host gives it a surface to draw in and
 * says which view session is current (see hosts/electron/main.js).
 *
 * The view's page publishes what it shows as `viewState` (viewer-app.js, publishViewState); its
 * session keeps that and the recent log (frame-view-session.js). This relays both to the
 * inspector's page, and what the user does there back to the view. The view's options and
 * parameters panels are drawn there too, against a stand-in for the view (webview/viewer-panels.js).
 *
 *   here -> page:  inspector:view {view: {title, filePath}|null, log, state, strings},
 *                  inspector:log {line}, inspector:state {state}
 *   page -> here:  inspector:ready, inspector:select {memberKeys, additive}, inspector:clearLog,
 *                  inspector:call {method, args, seq}
 *
 * Two paths, on purpose for now: under VS Code the view still draws its own options, parameters,
 * member list and log; only the app moves them here. The options and parameters are one code
 * path (viewer-panels.js); the member table and the log list are drawn twice (here and in the
 * view). What can break quietly is viewer-panels.js's SNAPSHOT_PROPS and PANEL_ACTIONS: a viewer
 * property or method the panels use but those lists omit works in VS Code and is dead here.
 * Showing this page in VS Code too (a webview panel) would make it one path.
 */

const path = require('path');
const { loadCatalog } = require('./i18n');

class ViewInspector {
    /**
     * @param {object} options
     * @param {{postMessage: (message: object) => any, onMessage: (callback: (message: object) => void) => any}} options.surface
     * @param {() => object|null} options.currentSession  the view session showing, if any
     * @param {string} [options.locale]  for the panels' strings
     */
    constructor({ surface, currentSession, locale = 'en' }) {
        this.surface = surface;
        this.currentSession = currentSession;
        this.strings = loadCatalog(locale);
        this.session = null;
        this.subscriptions = [];
        surface.onMessage((message) => this.handle(message));
    }

    post(message) {
        void this.surface.postMessage(message);
    }

    /** Follow the view showing now. Cheap when it has not changed. */
    sync() {
        const session = this.currentSession() || null;
        if (session === this.session) {
            return;
        }
        this._bind(session);
    }

    _bind(session) {
        for (const subscription of this.subscriptions) {
            subscription.dispose();
        }
        this.subscriptions = [];
        this.session = session;
        if (!session) {
            this.post({ type: 'inspector:view', view: null, log: [], state: null, strings: this.strings });
            return;
        }
        this.post({
            type: 'inspector:view',
            view: {
                title: (session.panel && session.panel.title) || path.basename(session.filePath),
                filePath: session.filePath,
            },
            log: session.logLines,
            state: session.viewState,
            strings: this.strings,
        });
        this.subscriptions.push(
            session.onLogLine((line) => this.post({ type: 'inspector:log', line })),
            session.onViewState((state) => this.post({ type: 'inspector:state', state })),
        );
    }

    handle(message) {
        if (!message) return;
        if (message.type === 'inspector:ready') {
            // A page (re)loaded: send it everything again.
            this._bind(this.currentSession() || null);
        } else if (message.type === 'inspector:select' && this.session) {
            this.session.selectMembers(message.memberKeys || [], { additive: message.additive === true });
        } else if (message.type === 'inspector:call' && this.session && typeof message.method === 'string') {
            this.session.callViewPanel(message.method, message.args || [], message.seq);
        } else if (message.type === 'inspector:clearLog' && this.session) {
            this.session.clearLogLines();
        }
    }

    dispose() {
        this._bind(null);
    }
}

module.exports = { ViewInspector };
