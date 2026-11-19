// The view's own controls in the phone layout: a menu at the top left named for the frame (its
// parameters, options and drawings), the sidebar's pages opened from it as a sheet, and a chip naming
// what is selected. In a drawing the menu gives way to Back to 3D (viewer-app.js).
//
// The pages are the same ones the desktop sidebar shows (view-sidebar.js, in its sheet form): only
// where they open differs.

import { THREE_D_MEASUREMENTS_ID } from './viewer-shared.js';

export class CompactChrome {
    /**
     * @param {object} app  the viewer (viewer-app.js)
     * @param {{html: Function, nothing: any, t: Function}} runtime
     */
    constructor(app, { html, nothing, t }) {
        this.app = app;
        this.html = html;
        this.nothing = nothing;
        this.t = t;
        this.menuOpen = false;
        /** The sidebar page open as a sheet, or null. */
        this.sheet = null;
    }

    toggleMenu() {
        this.menuOpen = !this.menuOpen;
        this.app.requestUpdate();
    }

    closeMenu() {
        if (!this.menuOpen) return;
        this.menuOpen = false;
        this.app.requestUpdate();
    }

    openSheet(tab) {
        this.menuOpen = false;
        this.sheet = tab;
        this.app.sidebar.show(tab);
        this.app.requestUpdate();
    }

    closeSheet() {
        this.sheet = null;
        this.app.requestUpdate();
    }

    openDrawing(id) {
        this.menuOpen = false;
        this.sheet = null;
        this.app.setActiveScene(id);
    }

    /** The selected timbers' names: the first, and how many more. */
    selectionLabel() {
        const app = this.app;
        const keys = app.selectionManager.getSelectedTimbers();
        if (keys.length === 0) return null;
        const name = (app.memberMetadataByKey.get(keys[0]) || {}).name || keys[0];
        return keys.length === 1 ? name : `${name} +${keys.length - 1}`;
    }

    render() {
        const { app, html, nothing, t } = this;
        const frameName = (app.currentFrameData && app.currentFrameData.name) || app.fileName || t('viewer.compact.frame');
        const drawings = app.sceneStore.drawings().filter((drawing) => drawing.id !== THREE_D_MEASUREMENTS_ID);
        const hasKiwari = (app.kiwariSections || []).length > 0;
        const selected = app.isInDrawing ? null : this.selectionLabel();
        const item = (label, onClick, id) => html`<button class="compact-menu-item" type="button" role="menuitem"
            data-item=${id} @click=${onClick}>${label}</button>`;
        return html`
            ${app.isInDrawing ? nothing : html`
                <button id="compact-menu-btn" type="button" aria-haspopup="menu" aria-expanded=${this.menuOpen ? 'true' : 'false'}
                    @click=${() => this.toggleMenu()}>
                    <span class="compact-menu-name">${frameName}</span><span aria-hidden="true">▾</span>
                </button>`}
            ${this.menuOpen ? html`
                <div id="compact-menu-backdrop" @click=${() => this.closeMenu()}></div>
                <div id="compact-menu" role="menu">
                    ${hasKiwari ? item(t('viewer.compact.parameters'), () => this.openSheet('parameters'), 'parameters') : nothing}
                    ${item(t('viewer.compact.options'), () => this.openSheet('options'), 'options')}
                    ${drawings.length > 0 ? html`
                        <div class="compact-menu-heading">${t('viewer.compact.drawings')}</div>
                        ${drawings.map((drawing) => item(drawing.name || drawing.id, () => this.openDrawing(drawing.id), `drawing:${drawing.id}`))}`
                    : nothing}
                </div>` : nothing}
            ${this.sheet ? html`<button id="compact-sheet-close" type="button" aria-label=${t('viewer.compact.close')}
                @click=${() => this.closeSheet()}>✕</button>` : nothing}
            ${selected ? html`<button id="compact-selection-chip" type="button" title=${t('viewer.compact.focusSelection')}
                @click=${() => app.focusSelection()}>${selected}</button>` : nothing}`;
    }
}
