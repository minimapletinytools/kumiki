/**
 * Editing a drawing's layout on the sheet, in a mode of its own: the views' outlines, the selected
 * view's handles and tools, the lines between a grid's cells, and where a dragged view will land.
 * Every edit sends the whole tree (setDrawingLayout) and draws itself at once; the runner's answer
 * replaces it. Measuring and hover are off while editing, and a click takes only a face.
 *
 * A mixin of the viewer (viewer-app.js): its methods run as the viewer's.
 */

import { html } from 'lit';
import { t, vscode } from './viewer-shared.js';
import * as Layout from './viewport-layout.js';

const SVG = 'http://www.w3.org/2000/svg';
// How far a press travels before it is a drag rather than a click, in pixels.
const DRAG_SLOP_PX = 3;
// Where a dragged view lands, each place meaning one thing: on a divider line, one more in that
// row or column; along the sheet's edge, a new row or column across it; near a view's edge, a
// split of that view (a quarter of it in, at most this many pixels).
const DROP_DIVIDER_PX = 12;
const DROP_SHEET_PX = 18;
const DROP_BAND_PX = 48;
const HANDLE_PX = 9;
const BUTTON_PX = 22;
// Held after a drop until the runner's answer redraws it, or for this long if none comes.
const SETTLE_MS = 3000;
// A wheel zoom or pan is saved once the wheel has been still this long.
const WHEEL_SETTLE_MS = 400;
const WHEEL_ZOOM_STEP = 1.15;

const RESIZE_HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

// kumiki's View.world.
const CAMERA_PRESETS = [
    ['front', [0, 1, 0], [0, 0, 1]],
    ['back', [0, -1, 0], [0, 0, 1]],
    ['left', [1, 0, 0], [0, 0, 1]],
    ['right', [-1, 0, 0], [0, 0, 1]],
    ['top', [0, 0, -1], [0, 1, 0]],
    ['bottom', [0, 0, 1], [0, 1, 0]],
];

function element(name, attributes, parent) {
    const made = document.createElementNS(SVG, name);
    for (const [key, value] of Object.entries(attributes)) made.setAttribute(key, value);
    if (parent) parent.appendChild(made);
    return made;
}

const add = (a, b, scale = 1) => a.map((value, index) => value + b[index] * scale);
const neg = (a) => a.map((value) => -value);

// The gizmo's buttons: where in its 3x3 grid, and the camera they turn to from (look, up, right).
// An orbit moves the camera around what it looks at; a roll turns the picture.
const TURNS = [
    { id: 'roll-left', glyph: '↺', key: 'viewer.layout.rollLeft', at: [0, 0], turn: (look, _up, right) => [look, right] },
    { id: 'orbit-up', glyph: '▲', key: 'viewer.layout.orbitUp', at: [1, 0], turn: (look, up) => [neg(up), look] },
    { id: 'roll-right', glyph: '↻', key: 'viewer.layout.rollRight', at: [2, 0], turn: (look, _up, right) => [look, neg(right)] },
    { id: 'orbit-left', glyph: '◀', key: 'viewer.layout.orbitLeft', at: [0, 1], turn: (_look, up, right) => [right, up] },
    { id: 'orbit-right', glyph: '▶', key: 'viewer.layout.orbitRight', at: [2, 1], turn: (_look, up, right) => [neg(right), up] },
    { id: 'orbit-down', glyph: '▼', key: 'viewer.layout.orbitDown', at: [1, 2], turn: (look, up) => [up, neg(look)] },
];
// Smaller than the tools: it sits on the drawing.
const GIZMO_BUTTON_PX = 17;
const GIZMO_CELL_PX = GIZMO_BUTTON_PX + 2;

export const LayoutEditingMixin = (Base) => class extends Base {
    /** Start editing the open drawing's layout. */
    enterLayoutEditing() {
        if (!this.isInDrawing || !this.sceneStore.activeScene().layout || this.layoutEditing) {
            return;
        }
        while (this.escapeMeasurement()) { /* one end at a time */ }
        this.clearHover();
        const focus = this.selectionManager.viewportFocus;
        this._layoutSelected = focus ? focus.viewportId : null;
        // Faces here, edges and points outside: neither selection means anything in the other.
        this._dropCsgFocus();
        this.selectionManager.clearTimberSelection();
        this.layoutEditing = true;
        this._syncDrawingPanel();
        this.requestUpdate();
    }

    exitLayoutEditing() {
        if (!this.layoutEditing) {
            return;
        }
        this.cancelLayoutDrag();
        this.layoutEditing = false;
        this._layoutSelected = null;
        this._layoutGestureView = null;
        this._dropCsgFocus();
        this.selectionManager.clearTimberSelection();
        this._syncDrawingPanel();
        this.requestUpdate();
    }

    /** The layout the sheet shows: a drag's while one is held, else the drawing's. Null when not editing. */
    get editableLayout() {
        if (!this.layoutEditing || !this.isInDrawing || !this.activePage || this._exportingDrawing) {
            return null;
        }
        if (this._layoutDraft) {
            return this._layoutDraft.layout;
        }
        return this.sceneStore.activeScene().layout || null;
    }

    /** The view picked out for editing, if the layout has it. */
    get layoutSelection() {
        const layout = this.editableLayout;
        const name = this._layoutSelected;
        return name && layout && Layout.findLeaf(layout, name) ? name : null;
    }

    /** Pick out a view for editing. */
    selectLayoutView(name) {
        if (this.layoutEditing) {
            this._layoutSelected = name;
        }
    }

    /** A click while editing picks out the view it is in (handleCanvasClick). */
    selectViewportForClick() {
        const id = this._clickViewportId;
        if (this.layoutEditing && id && this.viewports.some((one) => one.id === id)) {
            this._layoutSelected = id;
            return true;
        }
        return false;
    }

    /** The bar in the sheet's top right while editing: undo, redo, and done. */
    renderLayoutEditBar() {
        const drawingId = this.measurementDrawingId;
        const canUndo = this.undoStacks.canUndo(this.frameKey, drawingId);
        const canRedo = this.undoStacks.canRedo(this.frameKey, drawingId);
        const press = (act) => () => {
            act();
            this.requestUpdate();
        };
        return html`<div id="layout-edit-bar">
            <span class="leb-title">${t('viewer.layout.editing')}</span>
            <button type="button" class="leb-undo" title=${t('viewer.layout.undo')} ?disabled=${!canUndo}
                @click=${press(() => this.undoMeasurementChange())}>↶</button>
            <button type="button" class="leb-redo" title=${t('viewer.layout.redo')} ?disabled=${!canRedo}
                @click=${press(() => this.redoMeasurementChange())}>↷</button>
            <button type="button" class="leb-done" title=${t('viewer.layout.done.title')}
                @click=${() => this.exitLayoutEditing()}>${t('viewer.layout.done')}</button>
        </div>`;
    }

    /** A page fraction as overlay pixels, and back. */
    _pagePoint(x, y, pageRect) {
        return { x: pageRect.x + x * pageRect.width, y: pageRect.y + y * pageRect.height };
    }

    _pageFraction(event) {
        const host = this.renderRoot.querySelector('#viewport');
        const bounds = host.getBoundingClientRect();
        const pageRect = this.pageScreenRect(bounds.width, bounds.height);
        return {
            x: (event.clientX - bounds.left - pageRect.x) / pageRect.width,
            y: (event.clientY - bounds.top - pageRect.y) / pageRect.height,
            pageRect,
        };
    }

    /** Draw the layout's outlines and handles over the sheet (renderMeasurements, every frame). */
    _drawLayoutEditing(overlay, pageRect) {
        const layout = this.editableLayout;
        if (!layout) {
            return;
        }
        const selected = this.layoutSelection;
        const page = this.activePage;
        const group = element('g', { class: 'vp-edit' }, overlay);
        const toPixels = (rect) => {
            const at = this._pagePoint(rect[0], rect[1], pageRect);
            return { x: at.x, y: at.y, width: rect[2] * pageRect.width, height: rect[3] * pageRect.height };
        };
        const rects = Layout.resolveLayout(layout, page);
        for (const [name, rect] of rects) {
            if (name === selected) continue;
            const box = toPixels(rect);
            element('rect', { class: 'vp-outline', x: box.x, y: box.y, width: box.width, height: box.height }, group);
        }

        for (const divider of Layout.dividers(layout, page)) {
            const [x1, y1, x2, y2] = divider.line;
            const from = this._pagePoint(x1, y1, pageRect);
            const to = this._pagePoint(x2, y2, pageRect);
            const ends = { x1: from.x, y1: from.y, x2: to.x, y2: to.y };
            element('line', { class: 'vp-divider-line', ...ends }, group);
            // Drawn thin, grabbed wide.
            const line = element('line', { class: `vp-divider vp-divider-${divider.direction}`, ...ends }, group);
            line.addEventListener('pointerdown', (event) => this._beginLayoutDrag(event, { kind: 'divider', divider }));
        }

        const draft = this._layoutDraft;
        if (draft && draft.drop) {
            const drop = draft.drop;
            if (drop.line) {
                const [x1, y1, x2, y2] = drop.line;
                const from = this._pagePoint(x1, y1, pageRect);
                const to = this._pagePoint(x2, y2, pageRect);
                element('line', { class: 'vp-drop-line', x1: from.x, y1: from.y, x2: to.x, y2: to.y }, group);
            }
            const box = toPixels(drop.rect);
            element('rect', { class: `vp-drop vp-drop-${drop.kind}`, x: box.x, y: box.y, width: box.width, height: box.height }, group);
            element('text', { class: 'vp-drop-label', x: box.x + box.width / 2, y: box.y + box.height / 2 + 4,
                'text-anchor': 'middle' }, group).textContent = t(drop.label);
        }
        if (draft && draft.ghost) {
            const box = toPixels(draft.ghost);
            element('rect', { class: 'vp-ghost', x: box.x, y: box.y, width: box.width, height: box.height }, group);
        }
        if (!selected || (draft && !draft.settling)) {
            return;
        }

        const rect = rects.get(selected);
        if (!rect) {
            return;
        }
        const box = toPixels(rect);
        element('rect', { class: 'vp-selected', x: box.x, y: box.y, width: box.width, height: box.height }, group);
        const floating = Layout.isFloating(layout, selected);
        if (floating) {
            for (const handle of RESIZE_HANDLES) {
                const across = handle.includes('w') ? 0 : handle.includes('e') ? 1 : 0.5;
                const down = handle.includes('n') ? 0 : handle.includes('s') ? 1 : 0.5;
                const square = element('rect', {
                    class: `vp-handle vp-handle-${handle}`,
                    x: box.x + across * box.width - HANDLE_PX / 2,
                    y: box.y + down * box.height - HANDLE_PX / 2,
                    width: HANDLE_PX, height: HANDLE_PX,
                }, group);
                square.addEventListener('pointerdown', (event) => this._beginLayoutDrag(event, { kind: 'resize', handle, name: selected, rect }));
            }
        }
        const grip = element('g', { class: 'vp-grip', transform: `translate(${box.x + 4}, ${box.y + 4})` }, group);
        element('rect', { width: BUTTON_PX, height: BUTTON_PX, rx: 3 }, grip);
        element('text', { x: BUTTON_PX / 2, y: BUTTON_PX / 2 + 5, 'text-anchor': 'middle' }, grip).textContent = '✥';
        element('title', {}, grip).textContent = t('viewer.layout.move');
        grip.addEventListener('pointerdown', (event) => this._beginLayoutDrag(event, { kind: 'move', name: selected, rect, floating }));

        const only = Layout.leafNames(layout).length < 2;
        const buttons = [
            { id: 'split-across', glyph: '◫', key: 'viewer.layout.splitAcross', act: () => this._splitView(selected, 'columns') },
            { id: 'split-down', glyph: '⊟', key: 'viewer.layout.splitDown', act: () => this._splitView(selected, 'rows') },
            ...(floating ? [
                { id: 'to-front', glyph: '▲', key: 'viewer.layout.toFront', act: () => this._commitLayout(Layout.restack(layout, selected, true), 'bring view to front') },
                { id: 'to-back', glyph: '▼', key: 'viewer.layout.toBack', act: () => this._commitLayout(Layout.restack(layout, selected, false), 'send view to back') },
            ] : []),
            { id: 'fit', glyph: '⤢', key: 'viewer.layout.fit', act: () => this.fitLayoutView(selected) },
            { id: 'camera', glyph: '◎', key: 'viewer.layout.camera', act: (event) => this._openCameraMenu(selected, event) },
            { id: 'delete', glyph: '✕', key: only ? 'viewer.layout.deleteLast' : 'viewer.layout.delete', disabled: only,
                act: () => this._commitLayout(Layout.removeLeaf(layout, selected), 'delete view') },
        ];
        // Inside the view's top right, or above it where the view is too narrow to hold them past the grip.
        const inside = buttons.length * (BUTTON_PX + 3) + BUTTON_PX + 12 <= box.width;
        const top = inside ? box.y + 4 : box.y - BUTTON_PX - 4;
        buttons.forEach((button, index) => {
            const at = box.x + box.width - (inside ? 4 : 0) - (buttons.length - index) * (BUTTON_PX + 3);
            const tool = element('g', {
                class: `vp-tool vp-tool-${button.id}${button.disabled ? ' vp-tool-disabled' : ''}`,
                transform: `translate(${at}, ${top})`,
            }, group);
            element('rect', { width: BUTTON_PX, height: BUTTON_PX, rx: 3 }, tool);
            element('text', { x: BUTTON_PX / 2, y: BUTTON_PX / 2 + 5, 'text-anchor': 'middle' }, tool).textContent = button.glyph;
            element('title', {}, tool).textContent = t(button.key);
            // On the press: the overlay is drawn afresh every frame, so the element a click would
            // need to be released on is gone by then.
            tool.addEventListener('pointerdown', (event) => {
                event.preventDefault();
                event.stopPropagation();
                if (!button.disabled) button.act(event);
            });
        });
        this._drawTurnGizmo(group, box, selected);
    }

    /** The turning buttons, in the view's bottom right, or below it where the view is too small. */
    _drawTurnGizmo(group, box, name) {
        const size = 3 * GIZMO_CELL_PX;
        const inside = box.width >= size + 8 && box.height >= size + BUTTON_PX + 16;
        const left = box.x + box.width - size - (inside ? 4 : 0);
        const top = inside ? box.y + box.height - size - 4 : box.y + box.height + 4;
        const gizmo = element('g', { class: 'vp-turn', transform: `translate(${left}, ${top})` }, group);
        for (const turn of TURNS) {
            const tool = element('g', {
                class: `vp-tool vp-tool-${turn.id}`,
                transform: `translate(${turn.at[0] * GIZMO_CELL_PX}, ${turn.at[1] * GIZMO_CELL_PX})`,
            }, gizmo);
            element('rect', { width: GIZMO_BUTTON_PX, height: GIZMO_BUTTON_PX, rx: 3 }, tool);
            element('text', { x: GIZMO_BUTTON_PX / 2, y: GIZMO_BUTTON_PX / 2 + 4, 'text-anchor': 'middle' }, tool).textContent = turn.glyph;
            element('title', {}, tool).textContent = t(turn.key);
            tool.addEventListener('pointerdown', (event) => {
                event.preventDefault();
                event.stopPropagation();
                this.turnLayoutView(name, turn.id);
            });
        }
    }

    /** Turn a view's camera a quarter turn (TURNS), and fit it again. */
    turnLayoutView(name, id) {
        const layout = this.editableLayout;
        const turn = TURNS.find((one) => one.id === id);
        const viewport = this.viewports.find((one) => one.id === name);
        const camera = viewport && viewport.spec.camera;
        if (!layout || !turn || !camera || !camera.look || !camera.up) {
            return;
        }
        const { look, up } = camera;
        // look x up, as the runner builds it (frame_from_look_and_up).
        const right = camera.right || [
            look[1] * up[2] - look[2] * up[1], look[2] * up[0] - look[0] * up[2], look[0] * up[1] - look[1] * up[0]];
        const [newLook, newUp] = turn.turn(look, up, right);
        const was = Layout.leafCamera(layout, name);
        this._commitLayout(Layout.setLeafCamera(layout, name, {
            look: newLook, up: newUp, ...(was && was.projection ? { projection: was.projection } : {}),
        }), 'turn view');
    }

    /** Split a view's cell, the new half a copy of it, and pick out the copy once it comes back. */
    _splitView(name, direction) {
        const start = this.editableLayout;
        const { layout, made } = Layout.splitLeaf(start, name, direction);
        if (made) {
            this._selectOnArrival = made;
            this._commitLayout(this._fitMoved(start, layout), 'split view');
        }
    }

    /** The way a view looks now, from its viewport's camera. */
    _viewAxes(name) {
        const viewport = this.viewports.find((one) => one.id === name);
        const camera = viewport && viewport.spec.camera;
        return camera && camera.look && camera.up ? { look: [...camera.look], up: [...camera.up] } : null;
    }

    _leafNode(layout, path) {
        let node = layout.roots[path[0]];
        for (const index of path.slice(1)) node = node.split.portions[index].node;
        return node;
    }

    /**
     * `after` with each view it moves or resizes -- the one dragged and every one it pushes
     * aside -- fitted to what it draws: a camera the layout gives it loses its place and zoom, and
     * a view without one is given the way it looks now, since otherwise it keeps the zoom its
     * code or file gave it.
     */
    _fitMoved(before, after) {
        let fitted = after;
        for (const name of Layout.movedLeaves(before, after, this.activePage)) {
            const camera = Layout.leafCamera(fitted, name);
            if (camera) {
                const { target: _target, extent: _extent, ...rest } = camera;
                fitted = Layout.setLeafCamera(fitted, name, rest);
                continue;
            }
            const path = Layout.findLeaf(fitted, name);
            const copyOf = path && this._leafNode(fitted, path).copyOf;
            const axes = this._viewAxes(name) || this._viewAxes(copyOf);
            if (axes) fitted = Layout.setLeafCamera(fitted, name, axes);
        }
        return fitted;
    }

    /** Fit a view's camera to what it draws, keeping which way it looks. */
    fitLayoutView(name) {
        const layout = this.editableLayout;
        const axes = this._viewAxes(name);
        if (!layout || !axes) {
            return;
        }
        const was = Layout.leafCamera(layout, name);
        const camera = { ...axes, ...(was && was.projection ? { projection: was.projection } : {}) };
        this._commitLayout(Layout.setLeafCamera(layout, name, camera), 'fit view');
    }

    /** Point a view along `look` with `up`, square on and fitted. */
    aimLayoutView(name, look, up, label = 'turn view') {
        const layout = this.editableLayout;
        if (layout) {
            this._commitLayout(Layout.setLeafCamera(layout, name, { look, up, projection: 'orthographic' }), label);
        }
    }

    /** The selected face's way out, in the world, or null when no face is selected. */
    get selectedFaceNormal() {
        const detail = this.lastPickDetail;
        return this.layoutEditing && this.selectionManager.csgFocus && detail && detail.featureType === 'FACE'
            && Array.isArray(detail.worldNormal) ? detail.worldNormal : null;
    }

    /** The orthographic presets, and the selected face. */
    _openCameraMenu(name, event) {
        const normal = this.selectedFaceNormal;
        const items = [
            ...CAMERA_PRESETS.map(([id]) => ({ id, label: t(`viewer.layout.camera.${id}`) })),
            { id: 'divider', divider: true },
            { id: 'face', label: t('viewer.layout.camera.face'), disabled: !normal },
        ];
        this.contextMenu.open({
            x: event.clientX,
            y: event.clientY,
            title: t('viewer.layout.camera'),
            items,
            onChoose: (id) => {
                if (id === 'face') {
                    const look = normal.map((value) => -value);
                    const up = Math.abs(look[2]) > 0.9 ? [0, 1, 0] : [0, 0, 1];
                    this.aimLayoutView(name, look, up, 'look at face');
                    return;
                }
                const preset = CAMERA_PRESETS.find(([one]) => one === id);
                if (preset) this.aimLayoutView(name, preset[1], preset[2]);
            },
        });
        this.requestUpdate();
    }

    /** The selected view, if (clientX, clientY) is in it and it has a camera to move. */
    layoutViewAt(clientX, clientY) {
        const name = this.layoutSelection;
        if (!name || (this._layoutDraft && !this._layoutDraft.settling)) {
            return null;
        }
        const viewport = this.viewports.find((one) => one.id === name);
        const rect = Layout.resolveLayout(this.editableLayout, this.activePage).get(name);
        const at = this._pageFraction({ clientX, clientY });
        const inside = rect && at.x >= rect[0] && at.x <= rect[0] + rect[2] && at.y >= rect[1] && at.y <= rect[1] + rect[3];
        return inside && viewport && viewport.spec.camera && viewport.spec.camera.extent ? name : null;
    }

    /**
     * Move a view's camera by a wheel, drag or touch gesture (touch-navigation.js): a pan or a
     * one-finger drag pans it, a zoom zooms it about the pointer, a pinch does both. Saved once
     * the gesture stops. Returns whether it was taken.
     */
    layoutViewGesture(name, clientX, clientY, gesture) {
        const viewport = this.viewports.find((one) => one.id === name);
        const layout = this.editableLayout;
        const rect = layout && Layout.resolveLayout(layout, this.activePage).get(name);
        if (!viewport || !viewport.spec.camera || !rect) {
            return false;
        }
        const camera = { ...viewport.spec.camera };
        const right = camera.right || [1, 0, 0];
        const pageRect = this._pageFraction({ clientX, clientY }).pageRect;
        const heightPx = rect[3] * pageRect.height;
        const aspect = (rect[2] * pageRect.width) / heightPx;
        const pan = (dx, dy) => {
            const perPixel = (2 * camera.extent) / heightPx;
            camera.target = add(add(camera.target, right, -dx * perPixel), camera.up, dy * perPixel);
        };
        // The point under (x, y) stays there.
        const zoom = (factor, x, y) => {
            const at = this._pageFraction({ clientX: x, clientY: y });
            const u = ((at.x - rect[0]) / rect[2]) * 2 - 1;
            const v = 1 - ((at.y - rect[1]) / rect[3]) * 2;
            const extent = camera.extent * factor;
            const shift = camera.extent - extent;
            camera.target = add(add(camera.target, right, u * aspect * shift), camera.up, v * shift);
            camera.extent = extent;
        };
        if (gesture.kind === 'pan' || gesture.kind === 'orbit') {
            pan(gesture.dx, gesture.dy);
        } else if (gesture.kind === 'zoom') {
            zoom(gesture.factor, clientX, clientY);
        } else if (gesture.kind === 'zoomStep') {
            zoom(gesture.out ? WHEEL_ZOOM_STEP : 1 / WHEEL_ZOOM_STEP, clientX, clientY);
        } else if (gesture.kind === 'pinch') {
            zoom(gesture.factor, gesture.to.x, gesture.to.y);
            pan(gesture.to.x - gesture.from.x, gesture.to.y - gesture.from.y);
        } else {
            return false;
        }
        viewport.spec.camera = camera;
        viewport.applySpecCamera();
        this.syncCameraProjection();
        this._saveViewCameraSoon(name, camera);
        return true;
    }

    /** Save a view's camera once nothing has moved it for a moment and no drag or touch is held. */
    _saveViewCameraSoon(name, camera) {
        clearTimeout(this._wheelCommitTimer);
        const save = () => {
            if (this.pointerDrag.isDragging || this.touchGestures.active) {
                this._wheelCommitTimer = setTimeout(save, WHEEL_SETTLE_MS);
                return;
            }
            const layout = this.editableLayout;
            if (!layout || !Layout.findLeaf(layout, name)) return;
            const was = Layout.leafCamera(layout, name);
            this._commitLayout(Layout.setLeafCamera(layout, name, {
                look: camera.look, up: camera.up, target: camera.target, extent: camera.extent,
                ...(was && was.projection ? { projection: was.projection } : {}),
            }), 'zoom view');
        };
        this._wheelCommitTimer = setTimeout(save, WHEEL_SETTLE_MS);
    }

    /**
     * Follow a press on a handle: a divider shares space differently, a corner resizes a floating
     * view, and the grip moves a view -- floating it where it is let go, or beside the view whose
     * edge it is let go on. Escape lets go without changing anything.
     */
    _beginLayoutDrag(event, grab) {
        event.preventDefault();
        event.stopPropagation();
        const start = this.editableLayout;
        const page = this.activePage;
        const from = this._pageFraction(event);
        const startClient = { x: event.clientX, y: event.clientY };
        const originalRects = new Map(this.viewports.map((one) => [one.id, one.spec.rect]));
        let moved = false;

        const onMove = (moveEvent) => {
            if (!moved && Math.abs(moveEvent.clientX - startClient.x) + Math.abs(moveEvent.clientY - startClient.y) < DRAG_SLOP_PX) {
                return;
            }
            moved = true;
            const at = this._pageFraction(moveEvent);
            const dx = at.x - from.x;
            const dy = at.y - from.y;
            if (grab.kind === 'divider') {
                const along = grab.divider.direction === 'columns' ? at.x : at.y;
                this._showLayoutDraft({ layout: Layout.moveDivider(start, grab.divider.path, grab.divider.index, along, page) });
            } else if (grab.kind === 'resize') {
                this._showLayoutDraft({ layout: Layout.setFloatingRect(start, grab.name, this._resized(grab.rect, grab.handle, dx, dy)) });
            } else {
                const ghost = Layout.clampRect([grab.rect[0] + dx, grab.rect[1] + dy, grab.rect[2], grab.rect[3]]);
                const drop = this._dropAt(start, grab.name, at, page);
                this._showLayoutDraft({
                    // A floating view follows the pointer; a grid's stays put until it is let go.
                    layout: grab.floating && !drop ? Layout.setFloatingRect(start, grab.name, ghost) : start,
                    ghost: grab.floating && !drop ? null : ghost,
                    drop,
                });
            }
        };

        const onEnd = () => {
            this._layoutDragCancel = null;
            const draft = this._layoutDraft;
            if (!moved || !draft) {
                this._layoutDraft = null;
                return;
            }
            if (grab.kind === 'move') {
                const layout = draft.drop
                    ? draft.drop.result
                    : (grab.floating ? draft.layout : Layout.floatLeaf(start, grab.name, draft.ghost));
                this._commitLayout(this._fitMoved(start, layout), draft.drop ? 'dock view' : 'move view', originalRects);
            } else {
                this._commitLayout(this._fitMoved(start, draft.layout), grab.kind === 'divider' ? 'resize views' : 'resize view', originalRects);
            }
        };
        this._layoutDragCancel = () => {
            this._layoutDragCancel = null;
            this._endPointerGesture('layout-drag');
            this._layoutDraft = null;
            for (const viewport of this.viewports) {
                if (originalRects.has(viewport.id)) viewport.spec.rect = originalRects.get(viewport.id);
            }
            this.syncCameraProjection();
        };
        this._beginPointerGesture('layout-drag', { onMove, onEnd });
    }

    /** Let go of a drag in hand, changing nothing. Returns whether there was one. */
    cancelLayoutDrag() {
        if (!this._layoutDragCancel) {
            return false;
        }
        this._layoutDragCancel();
        return true;
    }

    /** `rect` with the edges `handle` names moved by (dx, dy). */
    _resized(rect, handle, dx, dy) {
        let [x, y, width, height] = rect;
        if (handle.includes('w')) {
            x += dx;
            width -= dx;
        }
        if (handle.includes('e')) width += dx;
        if (handle.includes('n')) {
            y += dy;
            height -= dy;
        }
        if (handle.includes('s')) height += dy;
        return [x, y, width, height];
    }

    /**
     * Where a view let go at `at` would go, or null to float: on a divider, into that row or
     * column there; along the sheet's edge, a new row or column; near a view's edge, splitting it.
     * The layout it makes, the rect it takes there, and what to call it.
     */
    _dropAt(layout, name, at, page) {
        const pageRect = at.pageRect;
        const made = (kind, label, result, extra = {}) => {
            const rect = Layout.resolveLayout(result, page).get(name);
            return rect ? { kind, label, result, rect, ...extra } : null;
        };
        const dividerPx = (divider) => {
            const [x1, y1, x2, y2] = divider.line;
            return divider.direction === 'columns'
                ? (at.y >= y1 && at.y <= y2 ? Math.abs(at.x - x1) * pageRect.width : Infinity)
                : (at.x >= x1 && at.x <= x2 ? Math.abs(at.y - y1) * pageRect.height : Infinity);
        };
        const nearest = Layout.dividers(layout, page)
            .map((divider) => ({ divider, px: dividerPx(divider) }))
            .filter((one) => one.px <= DROP_DIVIDER_PX)
            .sort((a, b) => a.px - b.px)[0];
        if (nearest) {
            const { divider } = nearest;
            return made('insert', divider.direction === 'columns' ? 'viewer.layout.dropSiblingRow' : 'viewer.layout.dropSiblingColumn',
                Layout.insertLeaf(layout, name, divider.path, divider.index + 1), { line: divider.line });
        }

        const sheet = [
            { side: 'left', px: at.x * pageRect.width },
            { side: 'right', px: (1 - at.x) * pageRect.width },
            { side: 'top', px: at.y * pageRect.height },
            { side: 'bottom', px: (1 - at.y) * pageRect.height },
        ].filter((edge) => edge.px >= 0 && edge.px <= DROP_SHEET_PX).sort((a, b) => a.px - b.px)[0];
        if (sheet) {
            const across = sheet.side === 'left' || sheet.side === 'right';
            return made('sheet', across ? 'viewer.layout.dropColumn' : 'viewer.layout.dropRow', Layout.edgeLeaf(layout, name, sheet.side));
        }

        const rects = Layout.resolveLayout(layout, page);
        // Topmost first: the scene's viewports are in draw order.
        for (const viewport of [...this.viewports].reverse()) {
            const rect = rects.get(viewport.id);
            if (!rect || viewport.id === name) continue;
            const [x, y, width, height] = rect;
            if (at.x < x || at.x > x + width || at.y < y || at.y > y + height) continue;
            const bandX = Math.min(width / 4, DROP_BAND_PX / pageRect.width);
            const bandY = Math.min(height / 4, DROP_BAND_PX / pageRect.height);
            const edge = [
                { side: 'left', inside: (at.x - x) / bandX },
                { side: 'right', inside: (x + width - at.x) / bandX },
                { side: 'top', inside: (at.y - y) / bandY },
                { side: 'bottom', inside: (y + height - at.y) / bandY },
            ].filter((one) => one.inside <= 1).sort((a, b) => a.inside - b.inside)[0];
            return edge ? made('split', 'viewer.layout.dropSplit', Layout.dockLeaf(layout, name, viewport.id, edge.side),
                { target: viewport.id, side: edge.side }) : null;
        }
        return null;
    }

    /** Draw `draft` at once: each view at its rect in the draft's layout. */
    _showLayoutDraft(draft) {
        this._layoutDraft = draft;
        const rects = Layout.resolveLayout(draft.layout, this.activePage);
        for (const viewport of this.viewports) {
            const rect = rects.get(viewport.id);
            if (rect) viewport.spec.rect = rect;
        }
        this.syncCameraProjection();
    }

    /**
     * Send `layout` with what undoes it, and hold it drawn until the runner's answer comes.
     * `originalRects` puts the views back if none does.
     */
    _commitLayout(layout, label, originalRects = new Map(this.viewports.map((one) => [one.id, one.spec.rect]))) {
        const scene = this.sceneStore.activeScene();
        const drawingId = scene.id;
        const was = scene.origin === 'file' || scene.layoutEdited ? scene.layout : null;
        const redo = { type: 'setDrawingLayout', drawingId, layout };
        this.undoStacks.push(this.frameKey, drawingId, { label, redo, undo: { ...redo, layout: was } });
        this.emitViewerLog('layout-edit', { label });
        if (layout) {
            this._showLayoutDraft({ layout });
        }
        const settling = { layout: layout || scene.layout, settling: true };
        this._layoutDraft = settling;
        setTimeout(() => {
            if (this._layoutDraft === settling) {
                this._layoutDraft = null;
                for (const viewport of this.viewports) {
                    if (originalRects.has(viewport.id)) viewport.spec.rect = originalRects.get(viewport.id);
                }
                this.syncCameraProjection();
            }
        }, SETTLE_MS);
        this.requestUpdate();
        if (vscode) {
            vscode.postMessage(redo);
        }
    }

    /** The drawings came back: the layout they carry is the one to show now. */
    _layoutArrived() {
        this._layoutDraft = null;
        const wanted = this._selectOnArrival;
        this._selectOnArrival = null;
        if (wanted && this.viewports.some((one) => one.id === wanted)) {
            this.selectLayoutView(wanted);
        }
        if (this.layoutEditing && !this.sceneStore.activeScene().layout) {
            this.exitLayoutEditing();
        }
        this.requestUpdate();
    }
};
