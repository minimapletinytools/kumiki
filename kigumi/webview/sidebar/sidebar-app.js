import { LitElement, html, nothing } from 'lit';

// The Kigumi explorer page. Renders the tree the host posts (sidebar-model.js)
// and sends back what the user does. Row logic lives in sidebar-tree.js.

const { visibleRows, highlightParts, collapseAll, keyAction } = window.KigumiSidebarTree;
const { ContextMenu, menuPosition } = window.KigumiContextMenu;
const payload = window.__KIGUMI_INITIAL_PAYLOAD__ || {};
const t = window.KigumiI18n.createTranslator(payload.i18n && payload.i18n.strings);
const ROW_ACTIONS = payload.rowActions || {};
const STATUS_TYPES = new Set(['projectStatusAction', 'kumikiVersionAction', 'kumikiWebsiteAction']);

const hostApi = window.__kigumiVsCode
    || (typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : null);

function post(message) {
    if (hostApi) {
        hostApi.postMessage(message);
    }
}

function loadSavedState() {
    const saved = hostApi && typeof hostApi.getState === 'function' ? hostApi.getState() : null;
    return saved && typeof saved === 'object' ? saved : {};
}

function icon(name, spin = false) {
    if (!name) {
        return html`<span class="codicon codicon-blank"></span>`;
    }
    return html`<span class="codicon codicon-${name}${spin ? ' codicon-modifier-spin' : ''}"></span>`;
}

class KigumiSidebar extends LitElement {
    static properties = {
        tree: { state: true },
        groupByPatternbook: { state: true },
        isScanning: { state: true },
        filter: { state: true },
        overrides: { state: true },
        focusedKey: { state: true },
        selectedKey: { state: true },
        menuState: { state: true },
    };

    constructor() {
        super();
        const saved = loadSavedState();
        this.tree = [];
        this.groupByPatternbook = true;
        this.isScanning = false;
        this.filter = typeof saved.filter === 'string' ? saved.filter : '';
        this.overrides = new Map(Array.isArray(saved.overrides) ? saved.overrides : []);
        this.selectedKey = saved.selectedKey || null;
        this.focusedKey = this.selectedKey;
        this.menuState = null;
        this.contextMenu = new ContextMenu();
        this.onWindowMessage = this.onWindowMessage.bind(this);
        this.onWindowPointerDown = this.onWindowPointerDown.bind(this);
    }

    createRenderRoot() {
        return this;
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('message', this.onWindowMessage);
        window.addEventListener('pointerdown', this.onWindowPointerDown);
        post({ type: 'sidebarReady' });
    }

    disconnectedCallback() {
        window.removeEventListener('message', this.onWindowMessage);
        window.removeEventListener('pointerdown', this.onWindowPointerDown);
        super.disconnectedCallback();
    }

    onWindowMessage(event) {
        const message = event.data;
        if (message && message.type === 'sidebarState') {
            this.tree = Array.isArray(message.tree) ? message.tree : [];
            this.groupByPatternbook = message.groupByPatternbook !== false;
            this.isScanning = !!message.isScanning;
        }
    }

    onWindowPointerDown(event) {
        if (this.contextMenu.isOpen && !event.target.closest('.ks-menu')) {
            this.closeMenu();
        }
    }

    saveState() {
        if (hostApi && typeof hostApi.setState === 'function') {
            hostApi.setState({
                filter: this.filter,
                overrides: [...this.overrides.entries()],
                selectedKey: this.selectedKey,
            });
        }
    }

    get statusNodes() {
        return this.tree.filter((node) => STATUS_TYPES.has(node.type));
    }

    get treeNodes() {
        return this.tree.filter((node) => !STATUS_TYPES.has(node.type));
    }

    rows() {
        return visibleRows(this.treeNodes, { overrides: this.overrides, filter: this.filter });
    }

    toggle(key) {
        const row = this.rows().find((one) => one.node.key === key);
        if (!row || !row.isContainer) {
            return;
        }
        const overrides = new Map(this.overrides);
        overrides.set(key, !row.isExpanded);
        this.overrides = overrides;
        this.saveState();
    }

    select(key) {
        this.selectedKey = key;
        this.focusedKey = key;
        post({ type: 'sidebarSelect', key });
        this.saveState();
    }

    activate(row) {
        this.select(row.node.key);
        if (row.isContainer) {
            this.toggle(row.node.key);
        }
        if (row.node.action) {
            post({ type: 'sidebarRun', key: row.node.key });
        }
    }

    runRowAction(node, actionId) {
        this.select(node.key);
        post({ type: 'sidebarRun', key: node.key, actionId });
    }

    openMenu(node, x, y) {
        const items = (node.rowActions || [])
            .filter((id) => ROW_ACTIONS[id])
            .map((id) => ({ id, label: t(ROW_ACTIONS[id].labelKey), icon: ROW_ACTIONS[id].icon }));
        this.select(node.key);
        const opened = this.contextMenu.open({
            x,
            y,
            items,
            onChoose: (id) => this.runRowAction(node, id),
        });
        this.menuState = opened ? this.contextMenu.state : null;
    }

    closeMenu() {
        this.contextMenu.close();
        this.menuState = null;
    }

    onTreeKeyDown(event) {
        if (this.contextMenu.isOpen) {
            if (event.key === 'Escape') {
                event.preventDefault();
                this.closeMenu();
            }
            return;
        }
        const rows = this.rows();
        if ((event.key === 'F10' && event.shiftKey) || event.key === 'ContextMenu') {
            const row = rows.find((one) => one.node.key === this.focusedKey);
            const element = row && this.querySelector(`[data-key="${CSS.escape(row.node.key)}"]`);
            if (row && element) {
                event.preventDefault();
                const box = element.getBoundingClientRect();
                this.openMenu(row.node, box.left + 24, box.bottom);
            }
            return;
        }
        const result = keyAction(rows, this.focusedKey, event.key);
        if (!result) {
            return;
        }
        event.preventDefault();
        if (result.focus) {
            this.focusedKey = result.focus;
        } else if (result.toggle) {
            this.toggle(result.toggle);
        } else if (result.run) {
            const row = rows.find((one) => one.node.key === result.run);
            if (row) {
                this.activate(row);
            }
        }
    }

    onFilterInput(event) {
        this.filter = event.target.value;
        this.saveState();
    }

    onFilterKeyDown(event) {
        if (event.key === 'Escape' && this.filter) {
            event.preventDefault();
            this.clearFilter();
        } else if (event.key === 'ArrowDown') {
            event.preventDefault();
            const rows = this.rows();
            if (rows.length > 0) {
                this.focusedKey = rows[0].node.key;
                this.querySelector('.ks-tree').focus();
            }
        }
    }

    clearFilter() {
        this.filter = '';
        this.saveState();
        this.querySelector('.ks-filter input').focus();
    }

    collapseAll() {
        this.overrides = collapseAll(this.treeNodes);
        this.saveState();
    }

    updated() {
        if (this.menuState) {
            const menu = this.querySelector('.ks-menu');
            if (menu) {
                const at = menuPosition(
                    { x: this.menuState.x, y: this.menuState.y },
                    { width: menu.offsetWidth, height: menu.offsetHeight },
                    { width: window.innerWidth, height: window.innerHeight },
                );
                menu.style.left = `${at.x}px`;
                menu.style.top = `${at.y}px`;
            }
        }
        const focused = this.focusedKey && this.querySelector(`[data-key="${CSS.escape(this.focusedKey)}"]`);
        if (focused && this.querySelector('.ks-tree') === document.activeElement) {
            focused.scrollIntoView({ block: 'nearest' });
        }
    }

    renderStatus() {
        return html`
            <div class="ks-status">
                ${this.statusNodes.map((node) => {
                    const body = html`
                        ${icon(node.icon, node.spin)}
                        <span class="ks-status-text">
                            <span class="ks-status-label">${node.label}</span>
                            ${node.description ? html`<span class="ks-description">${node.description}</span>` : nothing}
                        </span>`;
                    return node.action
                        ? html`<button class="ks-status-row ks-status-action" title=${node.tooltip || node.label}
                            @click=${() => post({ type: 'sidebarRun', key: node.key })}>${body}</button>`
                        : html`<div class="ks-status-row" title=${node.tooltip || node.label}>${body}</div>`;
                })}
            </div>`;
    }

    renderToolbar() {
        return html`
            <div class="ks-toolbar">
                <label class="ks-filter">
                    ${icon('filter')}
                    <input type="search" .value=${this.filter} placeholder=${t('sidebar.ui.filterPlaceholder')}
                        aria-label=${t('sidebar.ui.filterPlaceholder')}
                        @input=${this.onFilterInput} @keydown=${this.onFilterKeyDown}>
                    ${this.filter ? html`<button class="ks-icon-button" title=${t('sidebar.ui.clearFilter')}
                        aria-label=${t('sidebar.ui.clearFilter')} @click=${this.clearFilter}>${icon('close')}</button>` : nothing}
                </label>
                <button class="ks-icon-button ${this.groupByPatternbook ? 'is-on' : ''}"
                    title=${t('sidebar.ui.groupByPatternbook')} aria-label=${t('sidebar.ui.groupByPatternbook')}
                    aria-pressed=${this.groupByPatternbook ? 'true' : 'false'}
                    @click=${() => post({ type: 'sidebarToggleGroup' })}>${icon('list-tree')}</button>
                <button class="ks-icon-button" title=${t('sidebar.ui.collapseAll')} aria-label=${t('sidebar.ui.collapseAll')}
                    @click=${this.collapseAll}>${icon('collapse-all')}</button>
                <button class="ks-icon-button" title=${t('sidebar.ui.refresh')} aria-label=${t('sidebar.ui.refresh')}
                    ?disabled=${this.isScanning}
                    @click=${() => post({ type: 'sidebarRefresh' })}>${icon('refresh', this.isScanning)}</button>
            </div>`;
    }

    renderRow(row, index) {
        const { node } = row;
        const [before, match, after] = highlightParts(node.label, this.filter);
        const inlineActions = (node.rowActions || []).filter((id) => ROW_ACTIONS[id] && ROW_ACTIONS[id].inline);
        const classes = [
            'ks-row',
            node.key === this.selectedKey ? 'is-selected' : '',
            node.key === this.focusedKey ? 'is-focused' : '',
            node.type === 'placeholder' || node.type === 'loading' ? 'is-muted' : '',
        ].join(' ');
        return html`
            <div class=${classes} id=${`ks-row-${index}`} data-key=${node.key} role="treeitem"
                aria-level=${row.depth + 1} aria-selected=${node.key === this.selectedKey ? 'true' : 'false'}
                aria-expanded=${row.isContainer ? String(row.isExpanded) : nothing}
                .style=${`--ks-depth: ${row.depth}`} title=${node.tooltip || node.label}
                @click=${() => this.activate(row)}
                @contextmenu=${(event) => { event.preventDefault(); this.openMenu(node, event.clientX, event.clientY); }}>
                <span class="ks-twistie codicon ${row.isContainer ? (row.isExpanded ? 'codicon-chevron-down' : 'codicon-chevron-right') : 'codicon-blank'}"
                    @click=${(event) => { event.stopPropagation(); this.select(node.key); this.toggle(node.key); }}></span>
                ${icon(node.icon, node.spin)}
                <span class="ks-label">${before}${match ? html`<mark>${match}</mark>` : nothing}${after}</span>
                ${node.description ? html`<span class="ks-description">${node.description}</span>` : nothing}
                ${inlineActions.length > 0 ? html`
                    <span class="ks-row-actions">
                        ${inlineActions.map((id) => html`
                            <button class="ks-icon-button" tabindex="-1" title=${t(ROW_ACTIONS[id].labelKey)}
                                aria-label=${t(ROW_ACTIONS[id].labelKey)}
                                @click=${(event) => { event.stopPropagation(); this.runRowAction(node, id); }}>${icon(ROW_ACTIONS[id].icon)}</button>`)}
                    </span>` : nothing}
            </div>`;
    }

    renderMenu() {
        if (!this.menuState) {
            return nothing;
        }
        return html`
            <div class="ks-menu" role="menu">
                ${this.menuState.items.map((item) => html`
                    <button class="ks-menu-item" role="menuitem"
                        @click=${(event) => { this.contextMenu.choose(item.id, event); this.menuState = null; }}>
                        ${icon(item.icon)}<span>${item.label}</span>
                    </button>`)}
            </div>`;
    }

    render() {
        const rows = this.rows();
        const focusedIndex = rows.findIndex((row) => row.node.key === this.focusedKey);
        return html`
            ${this.renderStatus()}
            ${this.renderToolbar()}
            <div class="ks-tree" role="tree" tabindex="0" aria-label=${t('sidebar.ui.treeLabel')}
                aria-activedescendant=${focusedIndex === -1 ? nothing : `ks-row-${focusedIndex}`}
                @keydown=${this.onTreeKeyDown}
                @focus=${() => { if (focusedIndex === -1 && rows.length > 0) this.focusedKey = rows[0].node.key; }}>
                ${rows.map((row, index) => this.renderRow(row, index))}
                ${this.filter && rows.length === 0
                    ? html`<div class="ks-empty">${t('sidebar.ui.noMatches', { filter: this.filter })}</div>`
                    : nothing}
            </div>
            ${this.renderMenu()}`;
    }
}

customElements.define('kigumi-sidebar', KigumiSidebar);
