/**
 * The inspector: a panel outside the views that shows the current view's member list and log,
 * following whichever view is showing. Host-neutral; the host gives it a surface to draw in and
 * says which view session is current (see hosts/electron/main.js).
 *
 * The view's page publishes what it shows as `viewState` (viewer-app.js, publishViewState); its
 * session keeps that and the recent log (frame-view-session.js). This relays both to the
 * inspector's page, and what the user does there back to the view.
 *
 *   here -> page:  inspector:view {view: {title, filePath}|null, log, state}, inspector:log {line},
 *                  inspector:state {state}
 *   page -> here:  inspector:ready, inspector:select {memberKeys, additive}, inspector:clearLog
 */

const path = require('path');

class ViewInspector {
    /**
     * @param {object} options
     * @param {{postMessage: (message: object) => any, onMessage: (callback: (message: object) => void) => any}} options.surface
     * @param {() => object|null} options.currentSession  the view session showing, if any
     */
    constructor({ surface, currentSession }) {
        this.surface = surface;
        this.currentSession = currentSession;
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
            this.post({ type: 'inspector:view', view: null, log: [], state: null });
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
        } else if (message.type === 'inspector:clearLog' && this.session) {
            this.session.clearLogLines();
        }
    }

    dispose() {
        this._bind(null);
    }
}

module.exports = { ViewInspector };
