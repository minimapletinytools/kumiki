/**
 * The standalone window: a shell page (tab bar, status bar, welcome) with the
 * sidebar, one view per open tab, and a quick-pick overlay laid over it as
 * WebContentsViews. Each view is a surface (see ../../host.js).
 */

const path = require('path');
const { BrowserWindow, WebContentsView, ipcMain, shell: electronShell } = require('electron');
const { TabList } = require('./tab-list');

const PAGE_PRELOAD = path.join(__dirname, 'preload.js');
const SHELL_PRELOAD = path.join(__dirname, 'shell-preload.js');
const ORIGIN = 'kigumi://app';

// HTML handed to surfaces, served at kigumi://app/page/<id>.
const pages = new Map();
let nextPageId = 1;

function servePage(html) {
    const id = String(nextPageId++);
    pages.set(id, html);
    return `${ORIGIN}/page/${id}`;
}

function lockDown(webContents) {
    webContents.setWindowOpenHandler(({ url }) => {
        if (/^https?:/.test(url)) {
            void electronShell.openExternal(url);
        }
        return { action: 'deny' };
    });
    webContents.on('will-navigate', (event, url) => {
        if (!url.startsWith(ORIGIN)) {
            event.preventDefault();
        }
    });
}

class ViewSurface {
    constructor(shell, { id, kind, title, filePath }) {
        this.shell = shell;
        this.id = id;
        this.kind = kind;
        this.filePath = filePath || null;
        this._title = title || '';
        this._messageListeners = new Set();
        this._disposeListeners = new Set();
        this._queue = [];
        this._ready = false;
        this._disposed = false;
        this.state = undefined;
        this.view = new WebContentsView({
            webPreferences: { preload: PAGE_PRELOAD, contextIsolation: true, backgroundThrottling: false },
        });
        lockDown(this.view.webContents);
        this.view.webContents.on('did-finish-load', () => {
            this._ready = true;
            for (const message of this._queue.splice(0)) {
                this.view.webContents.send('kigumi:message', message);
            }
        });
    }

    get title() { return this._title; }

    set title(value) {
        this._title = value;
        this.shell.onSurfaceTitleChanged(this);
    }

    get visible() { return this.shell.isShowing(this); }
    get active() { return this.visible && this.shell.window.isFocused(); }
    get cspSource() { return ORIGIN; }

    resourceUri(absPath) {
        return this.shell.resourceUri(absPath);
    }

    setHtml(html) {
        this.loadUrl(servePage(html));
    }

    loadUrl(url) {
        this._ready = false;
        void this.view.webContents.loadURL(url);
    }

    postMessage(message) {
        if (this._disposed) {
            return Promise.resolve(false);
        }
        if (this._ready) {
            this.view.webContents.send('kigumi:message', message);
        } else {
            this._queue.push(message);
        }
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
        this.shell.activate(this.id);
    }

    dispose() {
        this.shell.closeTab(this.id);
    }

    // Called by the shell once the view is gone.
    _destroyed() {
        if (this._disposed) {
            return;
        }
        this._disposed = true;
        for (const listener of [...this._disposeListeners]) {
            listener();
        }
        if (!this.view.webContents.isDestroyed()) {
            this.view.webContents.close();
        }
    }
}

class Shell {
    /**
     * @param {object} options
     * @param {(absPath: string) => string} options.resourceUri
     * @param {() => object} options.status  extra state for the shell page
     * @param {(id: string, ...args: any[]) => void} options.onShellCommand
     */
    constructor({ resourceUri, status, onShellCommand }) {
        this.resourceUri = resourceUri;
        this.status = status;
        this.onShellCommand = onShellCommand;
        this.tabs = new TabList();
        this.surfaces = new Map();
        this.byWebContents = new Map();
        this.nextTabId = 1;
        this.layout = null;
        this.pendingPick = null;

        this.window = new BrowserWindow({
            width: 1400,
            height: 900,
            minWidth: 720,
            minHeight: 480,
            title: 'Kigumi',
            show: false,
            webPreferences: { preload: SHELL_PRELOAD, contextIsolation: true },
        });
        lockDown(this.window.webContents);
        // A scripted test run shouldn't take focus from whoever is at the keyboard.
        this.window.once('ready-to-show', () => (process.env.KIGUMI_TEST_SCRIPT ? this.window.showInactive() : this.window.show()));
        this.window.on('focus', () => this.pushState());

        this.sidebar = new ViewSurface(this, { id: 'sidebar', kind: 'sidebar' });
        this._track(this.sidebar);
        this.window.contentView.addChildView(this.sidebar.view);

        this.overlay = new WebContentsView({
            webPreferences: { preload: SHELL_PRELOAD, contextIsolation: true },
        });
        this.overlay.setBackgroundColor('#00000000');
        lockDown(this.overlay.webContents);

        this._ipc = [
            ['kigumi:post', (event, message) => {
                const surface = this.byWebContents.get(event.sender.id);
                if (surface) surface.deliver(message);
            }],
            ['kigumi:getState', (event) => {
                const surface = this.byWebContents.get(event.sender.id);
                event.returnValue = surface ? surface.state : undefined;
            }],
            ['kigumi:setState', (event, state) => {
                const surface = this.byWebContents.get(event.sender.id);
                if (surface) surface.state = state;
            }],
            ['shell:layout', (event, layout) => {
                if (event.sender === this.window.webContents) {
                    this.layout = layout;
                    this.applyLayout();
                }
            }],
            ['shell:ready', (event) => {
                if (event.sender === this.window.webContents) this.pushState();
            }],
            ['shell:activateTab', (_event, id) => this.activate(id)],
            ['shell:closeTab', (_event, id) => this.closeTab(id)],
            ['shell:command', (_event, id, ...args) => this.onShellCommand(id, ...args)],
            ['quickpick:result', (event, index) => {
                if (event.sender === this.overlay.webContents) this._finishPick(index);
            }],
        ];
        for (const [channel, handler] of this._ipc) {
            ipcMain.on(channel, handler);
        }
        this.window.on('resize', () => this.applyLayout());
        this.window.on('closed', () => this._teardown());

        void this.window.loadURL(`${ORIGIN}/shell/shell.html`);
    }

    _track(surface) {
        this.surfaces.set(surface.id, surface);
        this.byWebContents.set(surface.view.webContents.id, surface);
    }

    createTab({ kind = 'viewer', title, filePath }) {
        const id = `tab-${this.nextTabId++}`;
        const surface = new ViewSurface(this, { id, kind, title, filePath });
        this._track(surface);
        this.tabs.add(id, { title: title || '', kind });
        this.window.contentView.addChildView(surface.view);
        this.applyLayout();
        this.pushState();
        return surface;
    }

    findTab(predicate) {
        for (const tab of this.tabs.tabs) {
            const surface = this.surfaces.get(tab.id);
            if (surface && predicate(surface)) return surface;
        }
        return null;
    }

    get activeSurface() {
        const tab = this.tabs.active;
        return tab ? this.surfaces.get(tab.id) : null;
    }

    isShowing(surface) {
        return surface.id === 'sidebar' || this.tabs.activeId === surface.id;
    }

    activate(id) {
        this.tabs.activate(id);
        this.applyLayout();
        this.pushState();
        const surface = this.surfaces.get(id);
        if (surface) surface.view.webContents.focus();
    }

    closeTab(id) {
        const surface = this.surfaces.get(id);
        if (!surface || id === 'sidebar') {
            return;
        }
        this.tabs.remove(id);
        this.surfaces.delete(id);
        this.byWebContents.delete(surface.view.webContents.id);
        this.window.contentView.removeChildView(surface.view);
        surface._destroyed();
        this.applyLayout();
        this.pushState();
    }

    onSurfaceTitleChanged(surface) {
        this.tabs.update(surface.id, { title: surface.title });
        this.pushState();
    }

    applyLayout() {
        if (!this.layout || this.window.isDestroyed()) {
            return;
        }
        const round = (rect) => ({
            x: Math.round(rect.x), y: Math.round(rect.y),
            width: Math.max(0, Math.round(rect.width)), height: Math.max(0, Math.round(rect.height)),
        });
        this.sidebar.view.setBounds(round(this.layout.sidebar));
        for (const tab of this.tabs.tabs) {
            const surface = this.surfaces.get(tab.id);
            const showing = tab.id === this.tabs.activeId;
            surface.view.setVisible(showing);
            if (showing) surface.view.setBounds(round(this.layout.content));
        }
        const [width, height] = this.window.getContentSize();
        this.overlay.setBounds({ x: 0, y: 0, width, height });
    }

    pushState() {
        if (this.window.isDestroyed()) {
            return;
        }
        this.window.webContents.send('shell:state', { ...this.tabs.snapshot(), ...this.status() });
    }

    // Shows the quick-pick overlay; resolves with the chosen item or undefined.
    pick(items, placeholder) {
        if (this.pendingPick) {
            this._finishPick(null);
        }
        return new Promise((resolve) => {
            this.pendingPick = { items, resolve };
            this.window.contentView.addChildView(this.overlay);
            this.applyLayout();
            const send = () => this.overlay.webContents.send('quickpick:show', {
                placeholder: placeholder || '',
                items: items.map(({ label, description, detail, separator }) => ({ label, description, detail, separator: !!separator })),
            });
            if (this.overlay.webContents.getURL()) {
                send();
            } else {
                this.overlay.webContents.once('did-finish-load', send);
                void this.overlay.webContents.loadURL(`${ORIGIN}/shell/quickpick.html`);
            }
            this.overlay.webContents.focus();
        });
    }

    _finishPick(index) {
        const pending = this.pendingPick;
        if (!pending) return;
        this.pendingPick = null;
        this.window.contentView.removeChildView(this.overlay);
        pending.resolve(Number.isInteger(index) ? pending.items[index] : undefined);
    }

    _teardown() {
        for (const [channel, handler] of this._ipc) {
            ipcMain.removeListener(channel, handler);
        }
        for (const tab of [...this.tabs.tabs]) {
            const surface = this.surfaces.get(tab.id);
            if (surface) surface._destroyed();
        }
        this.sidebar._destroyed();
    }
}

module.exports = { Shell, pages, ORIGIN };
