/**
 * The core's side of the app shell (webview/shell/): panels, the two center tab
 * groups and the quick pick, kept in step with the shell page over a transport.
 * Each panel is a surface (see ../host.js). Host-neutral: a host supplies the transport.
 *
 * The groups are linked by file: bringing a tab forward brings forward the tab
 * for the same file in the other group, so a frame's source and its view show together.
 *
 * Core → shell: shell:state, panel:message, quickpick:show
 * Shell → core: shell:ready, shell:command, tab:activate, tab:close, layout:toggle,
 *               panel:message, panel:state, panel:loaded, quickpick:result
 */

const { TabList } = require('./tab-list');
const { GROUPS, panelType } = require('./panel-registry');

class PanelSurface {
    constructor(connection, { id, type, title, filePath }) {
        this.connection = connection;
        this.id = id;
        this.type = type;
        this.slot = panelType(type).slot;
        this.group = panelType(type).group || null;
        this.filePath = filePath || null;
        this.url = null;
        this.state = undefined;
        this.loads = 0;
        this._title = title || '';
        this._messageListeners = new Set();
        this._disposeListeners = new Set();
        this._disposed = false;
    }

    // `kind` is what hosts and tests used before panels had types.
    get kind() { return this.type; }

    get title() { return this._title; }

    set title(value) {
        this._title = value;
        if (this.group) {
            this.connection.groups[this.group].update(this.id, { title: value });
        }
        this.connection.pushState();
    }

    get visible() { return this.connection.isShowing(this); }
    get active() { return this.visible && this.connection.isFocused(); }
    get cspSource() { return this.connection.pages.origin; }

    resourceUri(absPath) {
        return this.connection.pages.resourceUri(absPath);
    }

    setHtml(html) {
        this.connection.pages.release(this.url);
        this.loadUrl(this.connection.pages.serve(html));
    }

    loadUrl(url) {
        this.url = url;
        this.loads = 0;
        this.connection.pushState();
    }

    postMessage(message) {
        if (this._disposed) {
            return Promise.resolve(false);
        }
        this.connection.send({ type: 'panel:message', id: this.id, message });
        return Promise.resolve(true);
    }

    onMessage(callback) {
        this._messageListeners.add(callback);
        return { dispose: () => this._messageListeners.delete(callback) };
    }

    onDispose(callback) {
        this._disposeListeners.add(callback);
        return { dispose: () => this._disposeListeners.delete(callback) };
    }

    deliver(message) {
        for (const listener of [...this._messageListeners]) {
            listener(message);
        }
    }

    reveal() {
        this.connection.activate(this.id);
    }

    dispose() {
        this.connection.closePanel(this.id);
    }

    // The shell finished loading this panel's page.
    _loaded() {
        this.loads += 1;
        // A page loaded again (the shell reloaded) starts empty; have its owner redraw it.
        if (this.loads > 1 && panelType(this.type).redrawAfterReload) {
            this.deliver({ type: 'requestRefresh' });
        }
    }

    _destroyed() {
        if (this._disposed) {
            return;
        }
        this._disposed = true;
        this.connection.pages.release(this.url);
        for (const listener of [...this._disposeListeners]) {
            listener();
        }
    }
}

class ShellConnection {
    /**
     * @param {object} options
     * @param {{send: (message: object) => void, onMessage: (callback: (message: object) => void) => void}} options.transport
     * @param {import('./page-store').PageStore} options.pages
     * @param {() => object} [options.status]  extra state for the shell page
     * @param {(command: string, ...args: any[]) => void} [options.onCommand]
     * @param {() => boolean} [options.isFocused]
     * @param {(line: string) => void} [options.log]
     */
    constructor({ transport, pages, status = () => ({}), onCommand = () => {}, isFocused = () => true, log = () => {}, closeRequest = null }) {
        this.transport = transport;
        this.pages = pages;
        this.status = status;
        this.onCommand = onCommand;
        this.isFocused = isFocused;
        this.log = log;
        this.closeRequest = closeRequest;
        this.panels = new Map();
        this.groups = Object.fromEntries(GROUPS.map((group) => [group, new TabList()]));
        // The group last used: where the active panel is, and what closing a tab acts on.
        this.focusedGroup = 'view';
        this.sides = { left: null, bottom: null, right: null };
        // The layout, as data: whether each side slot is shown. A hidden side keeps its panel,
        // and what that panel holds (the agent's conversation, the explorer's state).
        this.layout = { left: true, bottom: true, right: true };
        this._changeListeners = new Set();
        this.nextPanel = 1;
        this.pendingPicks = new Map();
        this.nextPick = 1;
        transport.onMessage((message) => this.receive(message));
    }

    send(message) {
        this.transport.send(message);
    }

    createPanel(type, { title, filePath } = {}) {
        const id = `${type}-${this.nextPanel++}`;
        const panel = new PanelSurface(this, { id, type, title, filePath });
        this.panels.set(id, panel);
        if (panel.group) {
            this.groups[panel.group].add(id, { title: panel.title, kind: type });
            this.focusedGroup = panel.group;
            this._bringPartnerForward(panel);
        } else {
            const previous = this.sides[panel.slot];
            this.sides[panel.slot] = id;
            if (previous) this.closePanel(previous);
        }
        this.pushState();
        return panel;
    }

    findPanel(predicate) {
        for (const panel of this.panels.values()) {
            if (predicate(panel)) return panel;
        }
        return null;
    }

    /** Every center tab, code group first. */
    get tabs() {
        return GROUPS.flatMap((group) => this.groups[group].tabs);
    }

    /** The active tab of the focused group, else of the other one. */
    get activePanel() {
        const order = [this.focusedGroup, ...GROUPS.filter((group) => group !== this.focusedGroup)];
        const id = order.map((group) => this.groups[group].activeId).find(Boolean);
        return id ? this.panels.get(id) : null;
    }

    /** The tab showing in a group. */
    shownIn(group) {
        const id = this.groups[group] && this.groups[group].activeId;
        return id ? this.panels.get(id) : null;
    }

    isShowing(panel) {
        return panel.group ? this.groups[panel.group].activeId === panel.id : this.layout[panel.slot];
    }

    /** Called after any change to what is open or showing. */
    onDidChange(callback) {
        this._changeListeners.add(callback);
        return { dispose: () => this._changeListeners.delete(callback) };
    }

    // The tab for the same file in the other group comes forward too, without taking focus.
    _bringPartnerForward(panel) {
        if (!panel.filePath) {
            return;
        }
        for (const group of GROUPS.filter((other) => other !== panel.group)) {
            const partner = this.groups[group].tabs
                .map((tab) => this.panels.get(tab.id))
                .find((other) => other && other.filePath === panel.filePath);
            if (partner) this.groups[group].activate(partner.id);
        }
    }

    /** Show or hide a side slot, keeping its panel. */
    setSideShown(side, shown) {
        if (!(side in this.layout) || this.layout[side] === Boolean(shown)) {
            return;
        }
        this.layout[side] = Boolean(shown);
        this.pushState();
    }

    activate(id) {
        const panel = this.panels.get(id);
        if (!panel) {
            return;
        }
        if (panel.group) {
            this.groups[panel.group].activate(id);
            this.focusedGroup = panel.group;
            this._bringPartnerForward(panel);
        } else {
            this.layout[panel.slot] = true;
        }
        this.pushState();
    }

    closePanel(id) {
        const panel = this.panels.get(id);
        if (!panel) {
            return;
        }
        this.panels.delete(id);
        if (panel.group) {
            this.groups[panel.group].remove(id);
            if (this.groups[panel.group].tabs.length === 0) {
                this.focusedGroup = GROUPS.find((group) => this.groups[group].tabs.length > 0) || this.focusedGroup;
            }
        }
        if (this.sides[panel.slot] === id) this.sides[panel.slot] = null;
        panel._destroyed();
        this.pushState();
    }

    pushState() {
        const ordered = [
            this.sides.left,
            ...this.tabs.map((tab) => tab.id),
            this.sides.bottom,
            this.sides.right,
        ].filter(Boolean).map((id) => this.panels.get(id)).filter(Boolean);
        const active = this.activePanel;
        this.send({
            type: 'shell:state',
            activeId: active ? active.id : null,
            shown: Object.fromEntries(GROUPS.map((group) => [group, this.groups[group].activeId])),
            focusedGroup: this.focusedGroup,
            layout: { ...this.layout },
            panels: ordered.map((panel) => ({
                id: panel.id,
                type: panel.type,
                slot: panel.slot,
                group: panel.group,
                icon: panelType(panel.type).icon,
                title: panel.title,
                url: panel.url,
                state: panel.state,
            })),
            ...this.status(),
        });
        for (const listener of [...this._changeListeners]) {
            listener();
        }
    }

    // Shows the quick pick; resolves with the chosen item, or undefined.
    pick(items, placeholder) {
        const requestId = this.nextPick++;
        return new Promise((resolve) => {
            this.pendingPicks.set(requestId, { items, resolve });
            this.send({
                type: 'quickpick:show',
                requestId,
                placeholder: placeholder || '',
                items: items.map(({ label, description, detail, separator }) => ({ label, description, detail, separator: !!separator })),
            });
        });
    }

    receive(message) {
        if (!message || typeof message.type !== 'string') {
            return;
        }
        const panel = message.id ? this.panels.get(message.id) : null;
        switch (message.type) {
            case 'shell:ready':
                this.pushState();
                break;
            case 'shell:command':
                this.onCommand(message.command, ...(message.args || []));
                break;
            case 'tab:activate':
                this.activate(message.id);
                break;
            case 'layout:toggle':
                this.setSideShown(message.side, !this.layout[message.side]);
                break;
            case 'tab:close':
                if (this.closeRequest) {
                    Promise.resolve(this.closeRequest(message.id)).then((shouldClose) => {
                        if (shouldClose !== false) this.closePanel(message.id);
                    });
                } else {
                    this.closePanel(message.id);
                }
                break;
            case 'panel:message':
                if (panel) panel.deliver(message.message);
                break;
            case 'panel:state':
                if (panel) panel.state = message.state;
                break;
            case 'panel:loaded':
                if (panel) panel._loaded();
                break;
            case 'quickpick:result': {
                const pending = this.pendingPicks.get(message.requestId);
                if (pending) {
                    this.pendingPicks.delete(message.requestId);
                    pending.resolve(Number.isInteger(message.index) ? pending.items[message.index] : undefined);
                }
                break;
            }
            default:
                this.log(`[shell] ignored message ${message.type}`);
        }
    }

    dispose() {
        for (const panel of [...this.panels.values()]) {
            panel._destroyed();
        }
        this.panels.clear();
        this._changeListeners.clear();
        for (const pending of this.pendingPicks.values()) {
            pending.resolve(undefined);
        }
        this.pendingPicks.clear();
    }
}

module.exports = { ShellConnection, PanelSurface };
