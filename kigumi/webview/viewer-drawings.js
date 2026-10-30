/**
 * Scenes and drawings: switching scenes, entering and leaving a drawing, its options, and panning and zooming the page.
 *
 * A mixin of the viewer (viewer-app.js): its methods run as the viewer's.
 */

import { DEBUG_DRAWING_SCENE_ID, DEFAULT_SCENE_ID, DrawingPanel, KigumiMeasurements, anchorName, describeAnchor, measurementKey, pageScreenRect, panPage, rectAspect, sceneMembers, vscode, zoomPageAt } from './viewer-shared.js';
import { SELECTION_MODES } from './selection-store.js';
import { composeDrawingPng, drawingFileName } from './drawing-export.js';

// The exported page's longer side, in pixels; less where the GPU can't draw that large.
const EXPORT_LONG_SIDE_PX = 3000;

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

    /** Where reference features are lit: 'drawings', 'always' or 'never'. */
    setReferenceFeatures(mode) {
        if (this.displayOptions.set('referenceFeatures', mode)) {
            this.requestUpdate();
        }
    }

    /** One of a drawing's on/off options: showDrawingPerfectFaces, -Centerplanes, -ReferenceFeatures. */
    setDrawingOption(option, enabled) {
        if (this.displayOptions.set(option, Boolean(enabled))) {
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
        if (!this.drawingBetaEnabled || !this.isInDrawing) {
            if (this._drawingPanel) {
                this._drawingPanel.unmount();
                this._drawingPanel = null;
            }
            return;
        }
        if (!this._drawingPanel) {
            this._drawingPanel = new DrawingPanel(this.selectionManager);
            this._drawingPanel.mount(host);
            host.addEventListener('kigumi-save-drawings', () => this.saveDrawings());
            host.addEventListener('kigumi-export-drawing-png', () => void this.exportDrawingPng());
            host.addEventListener('kigumi-focus-measurement', (event) => {
                this._focusMeasurementFrom(event.detail);
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
                        ? (status.value.unit === 'angle'
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
        this.debugDrawingEnabled = false;
        this.setActiveScene(DEFAULT_SCENE_ID);
    }

    /** Whether the viewer is currently looking at a drawing rather than the model. */
    get isInDrawing() {
        return this.sceneStore.activeSceneId !== DEFAULT_SCENE_ID;
    }

    /**
     * Testing scaffolding: swap between the 3D scene and the four-viewport
     * drawing python builds (get_default_drawing_for_debugging), so the
     * multi-viewport path has something to render until real drawings arrive.
     */
    /**
     * Go to the debug drawing, asking python to build it the first time.
     *
     * A button rather than a checkbox, because it is a place to go rather than
     * a state to be in: leaving is what the drawing's own control is for, and a
     * checkbox that ticks itself off when you leave by any other route is a
     * checkbox that lies about where you are.
     */
    openDebugDrawing() {
        this.debugDrawingEnabled = true;
        if (this.sceneStore.sceneIds().includes(DEBUG_DRAWING_SCENE_ID)) {
            this.setActiveScene(DEBUG_DRAWING_SCENE_ID);
            return;
        }
        if (vscode) {
            vscode.postMessage({ type: 'requestDebugDrawing' });
        }
    }

    setDebugDrawingEnabled(enabled) {
        if (enabled) {
            this.openDebugDrawing();
            return;
        }
        this.debugDrawingEnabled = false;
        this.setActiveScene(DEFAULT_SCENE_ID);
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
