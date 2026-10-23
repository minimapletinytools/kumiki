/**
 * The view's left sidebar: one page per tab (the tree, options, parameters, members, log), the
 * tabs along its bottom, a button that collapses it to a strip, its own scrolling, and a drag
 * handle for its width.
 *
 * Layout only. The pages are the view's panels, handed in as content each render, so the sidebar
 * could move out of the view (a docked tab) without them changing. Every page stays in the DOM
 * while hidden: the layers tree and the log keep what they hold.
 *
 * Its tab, collapsed state and width are kept in the webview's saved state.
 */

let html;
let t;

export function useSidebarRuntime(runtime) {
    ({ html, t } = runtime);
}

export const SIDEBAR_MIN_WIDTH_PX = 200;
export const SIDEBAR_MAX_WIDTH_PX = 720;
const DEFAULT_WIDTH_PX = 320;

function clampWidth(width) {
    return Math.max(SIDEBAR_MIN_WIDTH_PX, Math.min(SIDEBAR_MAX_WIDTH_PX, Math.round(width)));
}

export class ViewSidebar {
    /**
     * @param {object} options
     * @param {() => void} options.requestUpdate  redraw the page holding the sidebar
     * @param {() => void} [options.onLayoutChange]  after it collapses, expands or changes width
     * @param {{getState?: () => any, setState?: (state: any) => void}|null} [options.store]
     */
    constructor({ requestUpdate, onLayoutChange = () => {}, store = null }) {
        this.requestUpdate = requestUpdate;
        this.onLayoutChange = onLayoutChange;
        this.store = store;
        const saved = this._saved();
        this.tab = typeof saved.tab === 'string' ? saved.tab : 'tree';
        this.collapsed = saved.collapsed === true;
        this.width = Number.isFinite(saved.width) ? clampWidth(saved.width) : DEFAULT_WIDTH_PX;
        this._drag = null;
        this.onResizeStart = this.onResizeStart.bind(this);
    }

    show(tab) {
        this.tab = tab;
        if (this.collapsed) {
            this.collapsed = false;
            this.onLayoutChange();
        }
        this._save();
        this.requestUpdate();
    }

    setCollapsed(collapsed) {
        this.collapsed = collapsed;
        this._save();
        this.requestUpdate();
        this.onLayoutChange();
    }

    /**
     * @param {Array<{id: string, label: string, badge?: string|number, content: any, fill?: boolean, heading?: any}>} pages
     *   `fill`: the page lays out its own height (the tree's sections share it), rather than scrolling.
     *   `heading`: drawn in the header instead of the label.
     */
    render(pages) {
        const active = pages.some((page) => page.id === this.tab) ? this.tab : pages[0].id;
        const activePage = pages.find((page) => page.id === active);
        return html`
            <aside id="view-sidebar" class=${this.collapsed ? 'is-collapsed' : ''}>
                <button class="vsb-expand" type="button" ?hidden=${!this.collapsed}
                    title=${t('viewer.sidebar.expand')} aria-label=${t('viewer.sidebar.expand')}
                    @click=${() => this.setCollapsed(false)}>›</button>
                <div class="vsb-frame" ?hidden=${this.collapsed}>
                    <div class="vsb-header">
                        <span class="vsb-title">${activePage.heading || activePage.label}</span>
                        <button class="vsb-collapse" type="button" title=${t('viewer.sidebar.collapse')}
                            aria-label=${t('viewer.sidebar.collapse')}
                            @click=${() => this.setCollapsed(true)}>‹</button>
                    </div>
                    ${pages.map((page) => html`
                        <div class="vsb-page ${page.fill ? 'is-fill' : ''}" data-tab=${page.id} role="tabpanel"
                            ?hidden=${page.id !== active}>${page.content}</div>`)}
                    <nav class="vsb-tabs" role="tablist">
                        ${pages.map((page) => html`
                            <button class="vsb-tab ${page.id === active ? 'is-active' : ''}" type="button" role="tab"
                                data-tab=${page.id} aria-selected=${page.id === active ? 'true' : 'false'}
                                @click=${() => this.show(page.id)}>
                                ${page.label}${page.badge !== undefined && page.badge !== ''
                                    ? html`<span class="vsb-badge">${page.badge}</span>` : ''}
                            </button>`)}
                    </nav>
                    <div class="vsb-resize" title=${t('viewer.sidebar.resize')} @pointerdown=${this.onResizeStart}></div>
                </div>
            </aside>`;
    }

    /**
     * Set its width, after each render of `root`: the webview's CSP keeps lit's style= bindings
     * from reaching the DOM, while the CSSOM is allowed.
     */
    sync(root) {
        const aside = root.querySelector('#view-sidebar');
        if (aside) {
            aside.style.width = this.collapsed ? '' : `${this.width}px`;
        }
    }

    onResizeStart(event) {
        if (event.button !== 0) {
            return;
        }
        event.preventDefault();
        const handle = event.currentTarget;
        this._drag = { startX: event.clientX, startWidth: this.width, handle };
        handle.classList.add('is-dragging');
        handle.setPointerCapture(event.pointerId);
        const onMove = (moveEvent) => {
            this.width = clampWidth(this._drag.startWidth + moveEvent.clientX - this._drag.startX);
            this.requestUpdate();
        };
        const onEnd = () => {
            handle.classList.remove('is-dragging');
            handle.removeEventListener('pointermove', onMove);
            handle.removeEventListener('pointerup', onEnd);
            handle.removeEventListener('pointercancel', onEnd);
            this._drag = null;
            this._save();
            this.onLayoutChange();
        };
        handle.addEventListener('pointermove', onMove);
        handle.addEventListener('pointerup', onEnd);
        handle.addEventListener('pointercancel', onEnd);
    }

    _saved() {
        try {
            const state = this.store && typeof this.store.getState === 'function' ? this.store.getState() : null;
            return state && typeof state.sidebar === 'object' && state.sidebar ? state.sidebar : {};
        } catch (_error) {
            return {};
        }
    }

    _save() {
        if (!this.store || typeof this.store.setState !== 'function') {
            return;
        }
        const state = (typeof this.store.getState === 'function' && this.store.getState()) || {};
        this.store.setState({ ...state, sidebar: { tab: this.tab, collapsed: this.collapsed, width: this.width } });
    }
}
