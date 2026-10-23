/**
 * The context menus: a member's (right-click in 3D or the layers list), a layer's and a feature's.
 *
 * A mixin of the viewer (viewer-app.js): its methods run as the viewer's.
 */

import { html } from 'lit';
import { t, vscode } from './viewer-shared.js';

export const MenusMixin = (Base) => class extends Base {
    onMemberContextMenuRequest(event) {
        const detail = event && event.detail;
        if (!detail || typeof detail.memberKey !== 'string') {
            return;
        }
        this.showMemberContextMenu(detail.memberKey, detail.clientX, detail.clientY);
    }

    showMemberContextMenu(memberKey, clientX, clientY) {
        if (!memberKey) {
            return;
        }
        const meta = this.memberMetadataByKey.get(memberKey);
        const item = { kind: 'member', member: this.selectionPanel.memberForCopy(memberKey) };
        this.contextMenu.open({
            x: clientX,
            y: clientY,
            title: (meta && meta.name) || memberKey,
            items: [
                ...this._copyMenuItems(),
                { id: 'stl', label: t('viewer.contextMenu.exportStl') },
                { id: 'step', label: t('viewer.contextMenu.exportStep') },
            ],
            onChoose: (id) => (this._copyFromMenu(id, item) || this.exportMember(memberKey, id)),
        });
        this.requestUpdate();
    }

    onLayerContextMenuRequest(event) {
        const detail = event && event.detail;
        if (detail && detail.item) {
            this.showLayerContextMenu(detail.item, detail.clientX, detail.clientY);
        }
    }

    /** A right click on a row of the layers tree: a CSG node, a joint or a tag. */
    showLayerContextMenu(row, clientX, clientY) {
        const name = (key) => (this.memberMetadataByKey.get(key) || {}).name || key;
        let item = null;
        if (row.kind === 'csg') {
            item = { kind: 'csg', timberName: name(row.memberKey), memberKey: row.memberKey,
                path: (row.node && row.node.path) || [], node: row.node };
        } else if (row.kind === 'joint') {
            item = { kind: 'joint', name: row.name, timbers: (row.timberKeys || []).map(name) };
        } else if (row.kind === 'tag') {
            item = { kind: 'tag', tagKind: row.tagKind, name: row.name, members: (row.memberKeys || []).map(name) };
        }
        if (!item) {
            return;
        }
        this.contextMenu.open({
            x: clientX,
            y: clientY,
            title: item.kind === 'csg' ? (row.node && (row.node.label || row.node.displayName)) || item.timberName : item.name,
            items: this._copyMenuItems(),
            onChoose: (id) => this._copyFromMenu(id, item),
        });
        this.requestUpdate();
    }

    _copyMenuItems() {
        return [
            { id: 'copyForAI', label: t('viewer.contextMenu.copyForAI') },
            { id: 'copyForAIDetailed', label: t('viewer.contextMenu.copyForAIDetailed') },
        ];
    }

    /** Copies `item` (see selection-copy.js) if `id` is a copy row; false otherwise. */
    _copyFromMenu(id, item) {
        if (id !== 'copyForAI' && id !== 'copyForAIDetailed') {
            return false;
        }
        this.copySelectionForAI({
            frameName: (this.currentFrameData && this.currentFrameData.name) || null,
            item,
            detailed: id === 'copyForAIDetailed',
        });
        return true;
    }

    /**
     * Offer the features under the pointer, by name.
     *
     * The same choice Tab steps through, said out loud. Tab is quicker once you
     * know what is there; this is how you find out -- a face seen edge-on is
     * never the best answer where it lies, so without being told it is on offer
     * there is no reason to expect it.
     */
    showFeatureContextMenu(clientX, clientY) {
        const hovered = this._hover && this._hover.feature;
        const candidates = (hovered && hovered.candidates) || [];
        if (candidates.length < 2) {
            // One feature under the pointer is not a choice.
            return false;
        }
        // Held where it is for as long as the menu is up. Reaching a row means
        // moving the pointer off the canvas, which would otherwise clear the
        // hover and forget the cycled choice -- so the menu would be naming
        // features of something that was no longer there, which is exactly what
        // it did: every row did nothing at all.
        if (!this._hover.pin()) {
            return false;
        }
        const opened = this.contextMenu.open({
            x: clientX,
            y: clientY,
            kind: 'feature',
            title: t('viewer.contextMenu.features'),
            // No `checked`: which row is current is not a fact to copy in here
            // and then keep up to date. It is derived at render time from the
            // answer on screen, so the row marked and the feature lit cannot
            // come to disagree. See _featureMenuActiveId.
            items: candidates.map((candidate, index) => ({
                id: String(index),
                label: candidate.label,
                // Under the pointer but not seen there: listed, so you know it is there, not taken.
                disabled: Boolean(candidate.hidden),
                // Where it is declared, so two named alike (a dovetail_wide_face on each of two
                // dovetails) can be told apart.
                note: [(candidate.type || '').toLowerCase(), ...(candidate.path || []).slice(-2),
                    candidate.hidden ? t('viewer.contextMenu.hidden') : null]
                    .filter(Boolean).join(' \u00b7 '),
            })),
            // A row is the feature it names: choosing one is the click that
            // would have taken it in the view.
            onChoose: (id, item, event) => this._takeFeatureFromMenu(id, event),
        });
        if (!opened) {
            this._hover.unpin();
            return false;
        }
        this.requestUpdate();
        return true;
    }

    /**
     * Light the feature a menu row names, as hovering it in the view would.
     *
     * The place does not change and the question does, which is what askAgain
     * is for. Everything else follows: the runner answers, the hover draws it,
     * and the menu marks the row that answer came from.
     */
    _showFeatureFromMenu(id) {
        if (!this._hover || !this._hover.pinned) {
            return;
        }
        const index = Number(id);
        if (this._hover.asking === index) {
            return;
        }
        this._hover.choose(index);
        this._hover.askAgain();
    }

    /**
     * Take the feature a menu row names, as clicking it in the view would.
     *
     * The same pick a click makes, at the point the menu was opened at, rather
     * than a second copy of that decision: handleCanvasClick already sends
     * whatever the hover is asking for, and drilling, selecting and taking a
     * measurement end are all its job to tell apart.
     */
    _takeFeatureFromMenu(id, event) {
        const at = this._hover && this._hover.at;
        if (!at) {
            return;
        }
        const index = Number(id);
        this._hover.choose(index);
        this.emitViewerLog('measure-cycle', {
            index, of: (this._hover.feature && this._hover.feature.candidateCount) || 0,
            from: 'menu',
        });
        // Unpinned before the pick, not after: what follows is an ordinary
        // click, and it must see a hover the pointer owns again.
        this._hover.unpin();
        this.handleCanvasClick({
            clientX: at.x,
            clientY: at.y,
            shiftKey: Boolean(event && event.shiftKey),
            ctrlKey: Boolean(event && event.ctrlKey),
            metaKey: Boolean(event && event.metaKey),
        });
    }

    /**
     * Which row the menu should mark: the one the view is lighting.
     *
     * Read off the answer on screen rather than off what was asked for, and
     * only for the feature menu. The runner says which candidate it settled on
     * -- it does not always get one named, since with nothing cycled it picks
     * whichever can finish the measurement in hand -- so this is the only way
     * to mark the right row before anything has been cycled.
     *
     * Derived every render, which is what keeps it in step with the highlight:
     * one fact, read twice, rather than two copies kept in agreement.
     */
    _featureMenuActiveId() {
        const state = this.contextMenu.state;
        if (!state || state.kind !== 'feature') {
            return null;
        }
        const drawn = this._hover && this._hover.drawn;
        const index = drawn ? drawn.candidateIndex : null;
        return index === null || index === undefined ? null : String(index);
    }

    closeMemberContextMenu() {
        // Unconditional: the menu may already be closed -- choosing a row closes
        // it before onChoose runs -- and the pin has to go either way.
        if (this._hover) {
            this._hover.unpin();
        }
        if (this.contextMenu.close()) {
            this.requestUpdate();
        }
    }

    onWindowContextMenuDismiss(event) {
        if (!this.contextMenu.isOpen) {
            return;
        }
        const menuEl = this.renderRoot.querySelector('#member-context-menu');
        if (menuEl && event.target && menuEl.contains(event.target)) {
            return;
        }
        this.closeMemberContextMenu();
    }

    exportMember(memberKey, format) {
        this.closeMemberContextMenu();
        if (!memberKey || (format !== 'stl' && format !== 'step')) {
            return;
        }
        if (typeof vscode !== 'undefined') {
            vscode.postMessage({ type: 'requestExportMember', memberKey, format });
        }
    }

    /**
     * Whatever menu is open, from the one description of a menu.
     *
     * One template rather than one per menu: exporting a member and choosing a
     * feature differ only in what they list, and a second template is a second
     * place for dismissing and positioning to go quietly wrong.
     */
    renderMemberContextMenu() {
        const state = this.contextMenu.state;
        if (!state) {
            return '';
        }
        // Which row the view is lighting, asked every render rather than stored
        // when it changed. Tab moves it without the pointer moving, so the mark
        // cannot ride on a mouseover.
        const isFeatureMenu = state.kind === 'feature';
        // Bound on every row of every menu: _showFeatureFromMenu answers only
        // for a PINNED hover, which only the feature menu takes -- so exporting
        // a member cannot reach it, and there is no conditional listener to get
        // wrong.
        const activeId = this._featureMenuActiveId();
        return html`
            <div
                id="member-context-menu"
                class="context-menu"
                data-x=${state.x}
                data-y=${state.y}
                @mousedown=${(event) => event.stopPropagation()}
                @contextmenu=${(event) => event.preventDefault()}
            >
                ${state.title
                    ? html`<div class="context-menu-title">${state.title}</div>`
                    : ''}
                ${state.items.map((item) => html`
                    <button
                        type="button"
                        class="context-menu-item${
                            item.checked || item.id === activeId
                                ? ' context-menu-checked' : ''}"
                        ?disabled=${Boolean(item.disabled)}
                        @mouseenter=${() => {
                            // A disabled button still gets mouseenter; a hidden feature is not shown.
                            if (!item.disabled) {
                                this._showFeatureFromMenu(item.id);
                            }
                        }}
                        @click=${(event) => {
                            this.contextMenu.choose(item.id, event);
                            this.requestUpdate();
                        }}
                    >${item.label}${item.note
                        ? html`<span class="context-menu-note">${item.note}</span>`
                        : ''}</button>
                `)}
                ${isFeatureMenu
                    ? html`<div class="context-menu-hint">${t('viewer.contextMenu.tabToCycle')}</div>`
                    : ''}
            </div>
        `;
    }
};
