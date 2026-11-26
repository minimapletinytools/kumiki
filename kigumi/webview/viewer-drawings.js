/**
 * Scenes and drawings: switching scenes, entering and leaving a drawing, its options, and panning and zooming the page.
 *
 * A mixin of the viewer (viewer-app.js): its methods run as the viewer's.
 */

import { DEFAULT_SCENE_ID, DrawingPanel, THREE_D_MEASUREMENTS_ID, KigumiMeasurements, anchorName, describeAnchor, measurementKey, pageScreenRect, panPage, rectAspect, sceneMembers, vscode, zoomPageAt } from './viewer-shared.js';
import { SELECTION_MODES } from './selection-store.js';
import { composeDrawingPng, drawingFileName, previewImage, standaloneSvg } from './drawing-export.js';

// The exported page's longer side, in pixels; less where the GPU can't draw that large.
const EXPORT_LONG_SIDE_PX = 3000;

/** The drawing options that take 'off', 'measured' or 'on' rather than on or off. */
const LINE_OPTIONS = ['showDrawingPerfectFaces', 'showDrawingCenterplanes'];

export const DrawingsMixin = (Base) => class extends Base {
    /** The members this scene is about, or null when it is about all of them. */
    get activeSceneMembers() {
        return sceneMembers(this.sceneStore.activeScene());
    }

    /** The sheet this scene is laid out on, or null when the canvas is it. */
    get activePage() {
        return this.sceneStore.activeScene().page;
    }

    /** The canvas size the page transform is computed against. */
    _canvasSize() {
        const element = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#viewport')
            : null;
        return element && element.offsetHeight
            ? { width: element.offsetWidth, height: element.offsetHeight }
            : null;
    }

    /**
     * Move the sheet under the cursor.
     *
     * Pan and zoom belong to the page, not to a camera: a drawing's views each
     * hold a declared scale, and zooming one of them would change what 1:20
     * means rather than bringing the reader closer to the paper.
     */
    panPageBy(dx, dy) {
        const size = this._canvasSize();
        if (!this.activePage || !size) {
            return;
        }
        this.pageView = panPage(this.activePage, this.pageView, size.width, size.height, dx, dy);
        this.requestUpdate();
    }

    zoomPageToward(clientX, clientY, factor) {
        const size = this._canvasSize();
        const canvas = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#c')
            : null;
        if (!this.activePage || !size || !canvas) {
            return;
        }
        const bounds = canvas.getBoundingClientRect();
        this.pageView = zoomPageAt(
            this.activePage,
            this.pageView,
            size.width,
            size.height,
            clientX - bounds.left,
            clientY - bounds.top,
            factor,
        );
        this.requestUpdate();
    }

    /**
     * Where the active scene's sheet sits on the canvas, in pixels.
     *
     * A scene with no page is the canvas, so this is the whole of it and the
     * 3D scene behaves exactly as it did.
     */
    pageScreenRect(canvasWidth, canvasHeight) {
        return pageScreenRect(
            this.sceneStore.activeScene().page,
            canvasWidth,
            canvasHeight,
            this.pageView,
        );
    }

    /**
     * A viewport's aspect: its share of the page, times the page's own.
     *
     * Measured against the page rather than the canvas, so on a real sheet the
     * window's shape does not enter into it and a resize cannot leave a camera
     * holding a stale aspect. With no page the page is the canvas, which is the
     * behaviour this had before.
     */
    viewportAspect(viewport) {
        const element = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#viewport')
            : null;
        if (!element || !element.offsetHeight) {
            return 1;
        }
        const pageRect = this.pageScreenRect(element.offsetWidth, element.offsetHeight);
        return rectAspect(viewport.spec.rect, pageRect.width, pageRect.height);
    }

    // Keeps both cameras' aspect/frustum in sync with the current viewport size --
    // called on resize and when toggling projection mode (the camera that just became
    // inactive should still be correctly sized if the viewport changes while it's idle).
    syncCameraProjection() {
        // Reached from rebuildViewports, which runs in the constructor, so
        // there is not always a DOM to measure yet.
        const element = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#viewport')
            : null;
        if (!element || !element.offsetHeight) {
            return;
        }
        for (const viewport of this.viewports) {
            viewport.perspectiveCamera.aspect = this.viewportAspect(viewport);
            viewport.perspectiveCamera.updateProjectionMatrix();
        }
        this.updateOrthographicFrustum();
    }

    /** Switch scenes: new viewports, and whatever camera controls it asks for. */
    setActiveScene(sceneId) {
        if (!this.sceneStore.setActiveScene(sceneId)) {
            return;
        }
        // Nothing carries across. A feature selected in the model means nothing
        // in a drawing, a half-made measurement means nothing outside the one it
        // was being made in, and either left behind is something the new mode
        // cannot act on. The store drops the selection; this drops the draft.
        this.clearMeasureDraft();
        this.cancelLayoutDrag();
        this._layoutDraft = null;
        this.layoutEditing = false;
        this._layoutSelected = null;
        // Before clearHover, which a menu holding the hover pinned would refuse.
        this.closeMemberContextMenu();
        this.clearHover();
        this.selectionManager.setMode(
            this.isInDrawing
                ? SELECTION_MODES.DRAWING
                : SELECTION_MODES.MODEL);
        // A drawing is of the frame assembled. Scrubbed apart in 3D, it goes
        // back together on the way in, and stays so when you come back out.
        if (this.isInDrawing) {
            this.setAssemblyScrubValue(0);
        }
        this._lastPickAnchor = null;
        this.rebuildViewports();
        this.syncCameraControls();
        this.applyFootprintVisibility();
        this._layersDrawingsChanged();
        this._syncDrawingPanel();
        // What is ghosted follows the scene: a drawing dims everything it is
        // not about, and leaving one puts the frame back.
        this.updateCamera();
        this.requestUpdate();
    }

    /**
     * Draw the current selection: ask python for a sheet and go to it.
     *
     * The layout is python's to decide -- one timber becomes its four long
     * faces, which needs the timber's own axes -- so this sends the selection
     * and renders whatever comes back.
     */
    drawSelection() {
        if (!vscode) {
            return;
        }
        vscode.postMessage({
            type: 'requestDrawingFromSelection',
            memberKeys: this.selectionManager.getSelectedTimbers(),
        });
    }

    /**
     * Whether a drawing shows the timbers it is not about.
     *
     * On, they sit far back so the piece can be placed among its neighbours;
     * off, the sheet holds only what is drawn.
     */
    /** Light a selected feature's parent node as well as the feature. */
    setShowFeatureParent(enabled) {
        if (this.displayOptions.set('showFeatureParent', Boolean(enabled))) {
            this.requestUpdate();
        }
    }

    setDrawingXray(mode) {
        if (this.displayOptions.set('drawingXray', mode)) {
            this._hover?.askAgain();
            this.requestUpdate();
        }
    }

    /** Return whether this camera shows the hidden anchors of a committed dimension. */
    showsXrayMeasure(viewport, measure) {
        for (const end of [measure.a, measure.b]) {
            if (!end?.xray) continue;
            if (this.drawingXray === 'off' || !viewport.camera.isOrthographicCamera) return false;
            const look = viewport.camera.getWorldDirection(this._viewportLook);
            const [x, y, z] = end.xray;
            if (look.x * x + look.y * y + look.z * z < 1 - 1e-8) return false;
        }
        return true;
    }

    /** Return the features this viewport's dimensions go to, as `memberKey|feature` (both of a derived one's). */
    measuredFeatures(viewport) {
        const measured = new Set();
        for (const measure of viewport?.spec.measurements || []) {
            if (KigumiMeasurements.isDeleted(measure)) continue;
            for (const end of [measure.a, measure.b]) {
                if (!end || !end.timber) continue;
                for (const part of [end, end.a, end.b]) {
                    if (part && part.feature) measured.add(end.timber + '|' + part.feature);
                }
            }
        }
        return measured;
    }

    /** Return members whose authored X-ray strokes this drawing viewport can show. */
    xrayMembers(viewport) {
        if (!this.isInDrawing || !viewport?.camera.isOrthographicCamera || this.drawingXray === 'off'
                || this.edgeMode === 'none' || this.viewerOptions?.geometryMode?.endsWith('NoJoints')) {
            return new Set();
        }
        const drawn = this.activeSceneMembers;
        if (this.drawingXray === 'on') {
            return drawn || new Set(this.memberMetadataByKey.keys());
        }
        const members = new Set();
        for (const measure of viewport.spec.measurements || []) {
            if (KigumiMeasurements.isDeleted(measure)) continue;
            for (const end of [measure.a, measure.b]) {
                if (end?.xray) members.add(end.timber);
            }
        }
        if (!this._exportingDrawing && this.selectionManager.scope === viewport.id) {
            const focus = this.selectionManager.csgFocus;
            if (focus?.featureLabel) members.add(focus.timberKey);
            const held = this.measureDraft?.heldEnd?.reference;
            if (held?.timber) members.add(held.timber);
        }
        return drawn ? new Set([...members].filter((key) => drawn.has(key))) : members;
    }

    setDrawingOption(option, enabled) {
        // The reference lines take 'off', 'measured' or 'on'; the rest are on or off.
        const value = LINE_OPTIONS.includes(option) ? enabled : Boolean(enabled);
        if (this.displayOptions.set(option, value)) {
            if (option === 'colorReferenceFaces') {
                for (const bundle of this.sceneManager.bundles()) {
                    this.applyReferenceFaceOption(bundle.mesh);
                }
            }
            this.requestUpdate();
        }
    }

    setDrawingGhostsVisible(enabled) {
        if (!this.displayOptions.set('showDrawingGhosts', Boolean(enabled))) {
            return;
        }
        this.requestUpdate();
    }

    onEnterDrawingRequested(event) {
        const sceneId = event && event.detail ? event.detail.sceneId : null;
        if (sceneId) {
            this.enterDrawing(sceneId);
        }
    }

    onSaveDrawingsRequested() {
        this.saveDrawings();
    }

    /** Ask python for the drawings, without going to any of them. */
    requestDrawings() {
        if (vscode) {
            vscode.postMessage({ type: 'requestDrawings' });
        }
    }

    /** Save every drawing the file is responsible for. */
    saveDrawings() {
        if (vscode) {
            vscode.postMessage({ type: 'requestSaveDrawings' });
        }
    }

    /**
     * Return the open drawing's page as a PNG data URL, as printed: fitted whole, drawn at
     * EXPORT_LONG_SIDE_PX, with its dimensions and without the selection, hovers or a measurement
     * being made. Raises the renderer's pixel ratio for it, so lines and dimensions scale together.
     */
    async renderDrawingPng() {
        const savedView = this.pageView;
        const savedRatio = this.renderer.getPixelRatio();
        this.pageView = { zoom: 1, offsetX: 0, offsetY: 0 };
        this._exportingDrawing = true;
        try {
            const size = this.renderer.getSize(new THREE.Vector2());
            const pageRect = this.pageScreenRect(size.x, size.y);
            const gl = this.renderer.getContext();
            const largest = Math.min(gl.getParameter(gl.MAX_RENDERBUFFER_SIZE), gl.getParameter(gl.MAX_TEXTURE_SIZE));
            const scale = Math.min(EXPORT_LONG_SIDE_PX / Math.max(pageRect.width, pageRect.height), largest / Math.max(size.x, size.y));
            this.renderer.setPixelRatio(scale);
            this.renderViewports();
            return await composeDrawingPng({
                canvas: this.renderer.domElement,
                overlay: this.renderRoot.querySelector('#measurement-overlay'),
                pageRect, cssWidth: size.x, cssHeight: size.y, scale,
            });
        } finally {
            this._exportingDrawing = false;
            this.pageView = savedView;
            this.renderer.setPixelRatio(savedRatio);
            this.renderViewports();
        }
    }

    /** Capture the fitted sheet, live cameras, preview images, and printable dimension overlay. */
    exportDrawingSvg() {
        if (!vscode || !this.isInDrawing || !this.renderer || !this.activePage) return;
        const scene = this.sceneStore.activeScene();
        const fileName = drawingFileName(scene.name || scene.id, 'svg');
        const saved = this.pageView;
        this.pageView = { zoom: 1, offsetX: 0, offsetY: 0 };
        this._exportingDrawing = true;
        try {
            const size = this.renderer.getSize(new THREE.Vector2());
            const page = this.pageScreenRect(size.x, size.y);
            const views = [];
            this.renderViewports((viewport, rect) => {
                const spec = { id: viewport.id, rect: viewport.spec.rect, xrayMembers: [...this.xrayMembers(viewport)],
                    measured: [...this.measuredFeatures(viewport)] };
                const camera = viewport.camera;
                if (camera.isOrthographicCamera) {
                    const axis = (x, y) => new THREE.Vector3(x, y, 0).transformDirection(camera.matrixWorld).toArray();
                    spec.camera = {
                        center: new THREE.Vector3(0, 0, 0).unproject(camera).toArray(),
                        right: axis(1, 0), up: axis(0, 1),
                        width: 2 / camera.projectionMatrix.elements[0], height: 2 / camera.projectionMatrix.elements[5],
                    };
                } else {
                    spec.image = previewImage(this.renderer.domElement, rect, this.renderer.getPixelRatio(), size.y);
                }
                views.push(spec);
            });
            const visible = [], ghosts = [], appearances = Object.create(null);
            for (const [key, bundle] of this.sceneManager.entries()) {
                if (!bundle.mesh.visible) continue;
                visible.push(key);
                appearances[key] = {
                    edge: '#' + bundle.edges.material.color.getHexString(),
                    width: bundle.edges.material.linewidth,
                    edgeOpacity: bundle.edges.visible ? bundle.edges.material.opacity : 0,
                    surface: '#' + bundle.mesh.material.color.getHexString(),
                    opacity: bundle.mesh.material.opacity,
                };
                if (bundle.idMesh && !bundle.idMesh.visible) ghosts.push(key);
            }
            const overlay = this.renderRoot.querySelector('#measurement-overlay');
            vscode.postMessage({ type: 'exportDrawingSvg', fileName, sheet: {
                page, paper: this.activePage, views, visible, ghosts, appearances, edgeMode: this.edgeMode,
                geometryMode: this.viewerOptions?.geometryMode || 'actual',
                dimensions: standaloneSvg(overlay, size.x, size.y),
                styles: { centerlines: this.showDrawingCenterplanes, perfect_faces: this.showDrawingPerfectFaces,
                    references: this.highlightReferenceEdges,
                    reference_faces: this.colorReferenceFaces },
            } });
        } catch (error) {
            vscode.postMessage({ type: 'exportDrawingSvg', fileName, error: String(error) });
        } finally {
            this.pageView = saved;
            this._exportingDrawing = false;
            this.renderViewports();
        }
    }

    /** Render the open drawing to a PNG and send it to be saved with the frame's exports. */
    async exportDrawingPng() {
        const scene = this.sceneStore.activeScene();
        if (!vscode || !this.isInDrawing || !this.renderer) {
            return;
        }
        try {
            const dataUrl = await this.renderDrawingPng();
            vscode.postMessage({ type: 'exportDrawingPng', fileName: drawingFileName(scene.name || scene.id), dataUrl });
        } catch (error) {
            vscode.postMessage({ type: 'exportDrawingPng', fileName: drawingFileName(scene.name || scene.id),
                error: (error && error.message) || String(error) });
        }
    }

    /**
     * The frame's drawings and the one open, for an agent; `open` (a drawing's id or name, or '3d')
     * goes there first. Where each came from: 'code', 'file', or 'overridden' (code, with the file's
     * dimensions).
     */
    agentDrawings(open) {
        const drawings = this.sceneStore.drawings().filter((drawing) => drawing.id !== THREE_D_MEASUREMENTS_ID);
        if (open === '3d') {
            this.leaveDrawing();
        } else if (open) {
            const target = drawings.find((drawing) => drawing.id === open)
                || drawings.find((drawing) => drawing.name === open);
            if (!target) {
                throw new Error(`No drawing ${JSON.stringify(open)}. These are: ${drawings.map((drawing) => drawing.name || drawing.id).join(', ') || 'none'}.`);
            }
            this.enterDrawing(target.id);
        }
        const active = this.sceneStore.activeScene();
        return {
            open: this.isInDrawing ? (active.name || active.id) : '3d',
            drawings: drawings.map((drawing) => ({ id: drawing.id, name: drawing.name || drawing.id, origin: drawing.origin, unsaved: drawing.dirty })),
        };
    }

    /** Enter a drawing by id, from the layers panel. */
    enterDrawing(sceneId) {
        this.setActiveScene(sceneId);
    }

    /**
     * Keep the drawing's own tree in step with the scene.
     *
     * Mounted only while a drawing is open, and taken down on the way out, so
     * the rail carries nothing about a drawing when there is not one.
     */
    _syncDrawingPanel() {
        const host = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#drawing-panel-host')
            : null;
        if (!host) {
            return;
        }
        const scene = this.sceneStore.activeScene();
        if (!this.isInDrawing) {
            if (this._drawingPanel) {
                this._drawingPanel.unmount();
                this._drawingPanel = null;
            }
            return;
        }
        if (!this._drawingPanel) {
            this._drawingPanel = new DrawingPanel(this.selectionManager);
            this._drawingPanel.mount(host);
        }
        // The host outlives each panel, so its listeners go on once: added again on every
        // entry, one click on export png ran two exports.
        if (!host.dataset.bound) {
            host.dataset.bound = 'true';
            host.addEventListener('kigumi-save-drawings', () => this.saveDrawings());
            host.addEventListener('kigumi-export-drawing-svg', () => this.exportDrawingSvg());
            host.addEventListener('kigumi-export-drawing-png', () => void this.exportDrawingPng());
            host.addEventListener('kigumi-focus-measurement', (event) => {
                this._focusMeasurementFrom(event.detail);
            });
            host.addEventListener('kigumi-select-viewport', (event) => {
                this.selectDrawingViewport(event.detail.viewportId);
            });
            host.addEventListener('kigumi-edit-layout', () => {
                if (this.layoutEditing) this.exitLayoutEditing();
                else this.enterLayoutEditing();
            });
            host.addEventListener('kigumi-measurement-contextmenu', (event) => {
                this.showMeasurementContextMenu(event.detail || {});
            });
            host.addEventListener('kigumi-member-contextmenu', this.onMemberContextMenuRequest);
            // No browser menu (cut, copy, paste) over the panel: its rows open their own.
            host.addEventListener('contextmenu', (event) => event.preventDefault());
            host.addEventListener('kigumi-select-drawing-member', (event) => {
                this.selectionManager.selectTimber(
                    event.detail.memberKey, event.detail.addToSelection,
                );
            });
        }
        // A drawing about everything names no members, which used to leave the
        // section empty -- the one case where you most want to know what is on
        // the sheet. Fall back to every timber there is, and say which of the
        // two lists this is.
        const drawnMembers = this.activeSceneMembers;
        const keys = drawnMembers
            ? Array.from(drawnMembers)
            : Array.from(this.memberMetadataByKey.keys());
        this._drawingPanel.setDrawing({
            drawing: scene,
            layoutEditing: this.layoutEditing ? true : (scene.layout ? false : null),
            viewports: this.viewports.map((viewport) => this._measurementRows(viewport)),
            members: keys.map((key) => ({
                key,
                name: (this.memberMetadataByKey.get(key) || {}).name || key,
            })),
            // Python names the slice; the drawing's own name is what it sends.
            slice: drawnMembers ? (scene.sliceName || scene.name || null) : null,
        });
    }

    /** One viewport's measurements, judged and described for the list. */
    _measurementRows(viewport) {
        const axes = this.viewportAxes(viewport);
        const projection = this.viewportProjection(viewport);
        return {
            id: viewport.id,
            measurements: (viewport.spec.measurements || []).map((measure) => {
                const status = KigumiMeasurements.measurementStatus(
                    measure, axes, projection);
                const named = anchorName;
                return {
                    key: measurementKey(measure),
                    origin: measure.origin,
                    between: `${named(measure.a)} / ${named(measure.b)}`,
                    describes: [measure.a, measure.b]
                        .map((anchor) => describeAnchor(anchor)).join('  \u2194  '),
                    status,
                    formatted: status.drawable
                        ? KigumiMeasurements.formatMeasureLabel(measure.label, status.value.unit === 'angle'
                            ? `${status.value.value.toFixed(1)}\u00b0`
                            : this.fmt(status.value.value))
                        : '',
                };
            }),
        };
    }

    /** Hand the drawings to the layers panel, which lists them. */
    _layersDrawingsChanged() {
        if (this._layersView && typeof this._layersView.setDrawings === 'function') {
            this._layersView.setDrawings(
                this.sceneStore.drawings(), this.sceneStore.activeSceneId,
                { inDrawing: this.isInDrawing, measurementsHidden: this.measurementsHidden });
        }
    }

    /** Back to the 3D scene, leaving the drawing where it was. */
    leaveDrawing() {
        this.setActiveScene(DEFAULT_SCENE_ID);
    }

    /** Whether the viewer is currently looking at a drawing rather than the model. */
    get isInDrawing() {
        return this.sceneStore.activeSceneId !== DEFAULT_SCENE_ID;
    }

    setProjectionMode(isOrthographic) {
        const viewport = this.activeViewport;
        const next = Boolean(isOrthographic);
        // A locked viewport is orthographic by declaration; a drawing hides the
        // projection control, and this keeps a stray call from undoing it.
        if (!viewport || viewport.spec.locked || viewport.isOrthographic === next) {
            return;
        }
        // The projection belongs to the viewport, not the viewer: a drawing
        // holds locked orthographic elevations beside a perspective preview.
        viewport.isOrthographic = next;
        this.syncCameraProjection();
        this.updateCamera();
        this.requestUpdate();
    }

    /**
     * Redraw the scene already on screen, after its contents changed.
     *
     * Deliberately not setActiveScene: nothing about the mode has changed, so
     * the held end of a half-made measurement, the hover and the focus all stay
     * where they are, and the cameras are kept the way a rebuild of the same
     * scene always keeps them.
     */
    refreshActiveScene() {
        this.rebuildViewports();
        this._syncDrawingPanel();
        this.renderMeasurements();
        this.requestUpdate();
    }
};
