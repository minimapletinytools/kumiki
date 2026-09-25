/**
 * Connects a SidebarModel to a sidebar page (a surface, see host.js): posts the
 * tree whenever it changes and runs what the page asks for through the host's
 * `runCommand`.
 */

const { ROW_ACTIONS } = require('./sidebar-model');
const { SIDEBAR_TO_HOST } = require('./message-types');
const { buildWebviewPage } = require('./webview-html');
const { resolveLocale, loadCatalog } = require('./i18n');
const { getHost } = require('./host');

// Template placeholder → file under webview/.
const SIDEBAR_ASSETS = [
    ['__CODICON_CSS_URI__', 'vendor/codicon.css'],
    ['__SIDEBAR_CSS_URI__', 'sidebar/sidebar.css'],
    ['__LIT_JS_URI__', 'vendor/lit.min.js'],
    ['__I18N_JS_URI__', 'i18n.js'],
    ['__CONTEXT_MENU_JS_URI__', 'context-menu.js'],
    ['__SIDEBAR_TREE_JS_URI__', 'sidebar/sidebar-tree.js'],
    ['__SIDEBAR_APP_JS_URI__', 'sidebar/sidebar-app.js'],
];

function renderSidebarPage(surface) {
    const locale = resolveLocale(getHost().locale);
    return buildWebviewPage(surface, {
        templateName: 'sidebar/sidebar.html',
        assets: SIDEBAR_ASSETS,
        locale,
        payload: {
            i18n: { locale, strings: loadCatalog(locale) },
            rowActions: ROW_ACTIONS,
        },
    });
}

function indexTree(nodes, byKey = new Map()) {
    for (const item of nodes) {
        byKey.set(item.key, item);
        if (item.children) {
            indexTree(item.children, byKey);
        }
    }
    return byKey;
}

class SidebarController {
    /**
     * @param {import('./sidebar-model').SidebarModel} model
     * @param {object} options
     * @param {(command: string, ...args: any[]) => Promise<any>} options.runCommand
     * @param {(line: string) => void} [options.log]
     */
    constructor(model, { runCommand, log = () => {} }) {
        this.model = model;
        this.runCommand = runCommand;
        this.log = log;
        this.surface = null;
        this._nodes = new Map();
        this._selected = null;
        this._subscriptions = [model.onDidChange(() => this.postState())];
    }

    attach(surface) {
        this.surface = surface;
        surface.setHtml(renderSidebarPage(surface));
        this._subscriptions.push(
            surface.onMessage((message) => {
                void this.handleMessage(message);
            }),
            surface.onDispose(() => {
                if (this.surface === surface) {
                    this.surface = null;
                }
            }),
        );
        this.model.ensureLoaded();
    }

    getSelectedElementData() {
        return this._selected;
    }

    postState() {
        const tree = this.model.getTree();
        this._nodes = indexTree(tree);
        if (this._selected && this._nodes.has(this._selected.key)) {
            this._selected = this._nodes.get(this._selected.key);
        }
        if (!this.surface) {
            return;
        }
        this.surface.postMessage({
            type: 'sidebarState',
            tree,
            groupByPatternbook: this.model.getGroupByPatternbook(),
            isScanning: this.model.state.isScanning,
        }).catch((error) => this.log(`[sidebar] post failed: ${error.message || error}`));
    }

    async handleMessage(message) {
        if (!message || !SIDEBAR_TO_HOST.includes(message.type)) {
            return;
        }
        try {
            if (message.type === 'sidebarReady') {
                this.postState();
            } else if (message.type === 'sidebarSelect') {
                this._selected = this._nodes.get(message.key) || null;
            } else if (message.type === 'sidebarRun') {
                await this.run(message.key, message.actionId);
            } else if (message.type === 'sidebarToggleGroup') {
                this.model.toggleGroupByPatternbook();
            } else if (message.type === 'sidebarRefresh') {
                await this.model.refresh(true);
            }
        } catch (error) {
            this.log(`[sidebar] ${message.type} failed: ${error.message || error}`);
        }
    }

    // Runs a row's click action, or one of its ROW_ACTIONS by id.
    async run(key, actionId) {
        const target = this._nodes.get(key);
        if (!target) {
            return;
        }
        if (actionId) {
            const rowAction = ROW_ACTIONS[actionId];
            if (rowAction && (target.rowActions || []).includes(actionId)) {
                await this.runCommand(rowAction.command, target);
            }
            return;
        }
        if (target.action) {
            await this.runCommand(target.action.command, ...(target.action.arguments || []));
        }
    }

    dispose() {
        for (const subscription of this._subscriptions) {
            subscription.dispose();
        }
        this._subscriptions = [];
        this.surface = null;
    }
}

module.exports = { SidebarController, SIDEBAR_ASSETS, renderSidebarPage };
