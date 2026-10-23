import { LitElement, html } from 'lit';
import { MemberListPanel } from './member-list-panel.js';
import { SelectionPanel } from './selection-panel.js';
import { ViewSidebar, useSidebarRuntime } from './view-sidebar.js';
import { EXPORT_FORMATS, EXPORT_FORMAT_PROP, ViewerKiwariPanel, ViewerSettingsPanel, usePanelRuntime } from './viewer-panels.js';
import { ASSEMBLY_PREVIEW_ENABLED, AssemblyTimeline, CameraController, CsgTreeView, DEFAULT_AXIS_ORBIT_SPEED, DEFAULT_FOOTPRINT_COLOR, DRAWING_BETA_ENABLED, DisplayOptionsStore, FEATURE_FLAGS, FEATURE_TYPE_NOUNS, FOOTPRINT_COLOR_IDS, GeometryMode, INITIAL_PAYLOAD, KigumiKiwariValues, KigumiTags, KigumiUnits, MAX_TILT_RADIANS, PAINT_WAIT_FALLBACK_MS, PAPER_COLOR, PointerDrag, RENDER_PROFILES, SELECTION_ECHO_OPACITY, SceneManager, SceneStore, SelectionStore, THEMES, TILT_ORBIT_SPEED, VIEWER_APP_VERSION, ViewerPhase, ViewerViewport, _isTypingTarget, accumulateBounds, actionForButton, boundsFromAccumulator, choosePickAction, createBoundsAccumulator, createInitialViewState, firstLoadCameraPlan, normalizeViewerOptions, resolvePointers, t, vscode } from './viewer-shared.js';
import { PickingMixin } from './viewer-picking.js';
import { MeasuringMixin } from './viewer-measuring.js';
import { MenusMixin } from './viewer-menus.js';
import { SelectionVisualsMixin } from './viewer-selection-visuals.js';
import { CameraMixin } from './viewer-camera.js';
import { RenderingMixin } from './viewer-rendering.js';
import { AssemblyMixin } from './viewer-assembly.js';
import { DrawingsMixin } from './viewer-drawings.js';

usePanelRuntime({ t, KigumiUnits: window.KigumiUnits, KigumiKiwariValues: window.KigumiKiwariValues });
useSidebarRuntime({ html, t });

class KigumiViewerApp extends DrawingsMixin(AssemblyMixin(RenderingMixin(CameraMixin(SelectionVisualsMixin(MenusMixin(MeasuringMixin(PickingMixin(LitElement)))))))) {
    constructor() {
        super();
        // Members on screen, and the only thing that knows what draws them.
        // The scene arrives in setupScene; until then it registers nothing.
        this.sceneManager = new SceneManager({ THREE, scene: null });
        this.lastBounds = { minX: -1, minY: -1, minZ: -1, maxX: 1, maxY: 1, maxZ: 1 };

        this.focusedCx = 0;
        this.focusedCy = 0;
        this.focusedCz = 0;
        // A scene owns its viewports, and a viewport owns its camera. The 3D
        // view is the scene the viewer starts in: one full-canvas viewport
        // with a free camera, so it runs the same path a drawing will.
        this.sceneStore = new SceneStore();
        // Before the viewports: the selection is kept in one of them.
        this.selectionManager = new SelectionStore();
        this.viewports = [];
        this.activeViewportId = null;
        // Built here rather than in setupScene: a viewport is cameras and data,
        // and the template reads the active one's camera controller on its
        // first render, which happens before the scene exists.
        this.rebuildViewports();

        // How the frame is drawn. The store owns the values and the rules for
        // taking them; the setters below keep the half that applies one to the
        // scene. Read through the forwarding properties defined further down.
        this.displayOptions = new DisplayOptionsStore({ themeIds: Object.keys(THEMES) });

        // Read display options off the store by their old names, so templates
        // and the hundred readers of this.edgeMode stay as they are. Getters
        // only: every write goes through a setter, which is what keeps the
        // store the one place a value can come from.
        for (const key of this.displayOptions.keys()) {
            Object.defineProperty(this, key, {
                get() { return this.displayOptions.get(key); },
                configurable: true,
            });
        }

        this.pointerDrag = new PointerDrag();

        // Making a measurement, and what could be taken back. Both are per
        // viewer; the stacks key themselves by frame and drawing.
        this.measureDraft = new window.KigumiMeasureDraft.MeasureDraft();
        this.undoStacks = new window.KigumiUndoStacks.UndoStacks();
        /** Lines drawn for the feature a measurement is being taken from. */
        // The eyeball on the 3D measurements node. About looking rather than
        // about the drawing, so deliberately not on the undo stack.
        this.measurementsHidden = false;

        this.showCenterGizmo = true;
        this.footprintObjects = [];
        this.debugEnabled = false;
        this.cameraPanelCollapsed = false;
        this.leftClickDragRotatesCamera = true;
        // What a right-click is offering. One menu for every kind of menu --
        // dismissing, choosing and where it sits are solved once.
        this.contextMenu = new window.KigumiContextMenu.ContextMenu();
        this.showAssemblyTimeline = true;
        this.disassemblyMultiplier = 1.5;
        this.assemblyData = null;
        this.assemblySolving = false;
        this.assemblyScrubValue = 0;
        this._assemblyOffsetsByKey = new Map();
        this._assemblyRotationsByKey = new Map();
        this.logFilterText = '';

        this.lightAzimuth = 0;
        this.lightElevation = 0.8;
        this.lightDistance = 16;
        this.lightDialDragging = false;

        this.shadowSize = 60;
        this.groundZ = -1.0005;

        this.gizmoDragging = false;
        this.gizmoMoved = false;
        this.gizmoLastX = 0;
        this.gizmoLastY = 0;
        // Built by syncCameraControls, and only when the scene asks for them.
        this.cameraCube = null;
        this.orbitGizmo = null;
        this.gizmoRaycaster = new THREE.Raycaster();
        this.gizmoPointer = new THREE.Vector2();
        this.navigationRaycaster = new THREE.Raycaster();
        this.navigationPointer = new THREE.Vector2();
        this.focalPlane = new THREE.Plane();
        this.tempOrbitCenter = new THREE.Vector3();
        this.tempViewDirection = new THREE.Vector3();
        this.tempPlaneHit = new THREE.Vector3();

        this.sun = null;
        this.ambient = null;
        this.fill = null;
        this.viewLight = null;
        this.shadowCatcher = null;
        this.orbitCenterGizmo = null;

        this.memberMetadataByKey = new Map(); // member key -> { name, type }
        /** The last state the frame was drawn for. See visualSignature. */
        this._visualSignature = null;
        /**
         * What is lit, by id. See highlights.js: the pass asks what SHOULD be
         * lit and reconciles this against it, so no overlay outlives the state
         * that wanted it and none has a lifetime of its own.
         */
        this._highlightObjects = new Map();
        /** Pointer gestures running now, by name. See _beginPointerGesture. */
        this._pointerGestures = new Map();
        /**
         * The geometry the runner sent for the current selection, kept so the
         * overlay can be re-derived rather than built once on arrival. Only
         * used while the focus still names the same thing -- a message from
         * before the focus moved lights nothing.
         */
        this._csgHighlightSource = null;
        this.renderProfiles = RENDER_PROFILES;
        this.memberRenderProfileByType = {
            timber: 'timber-default',
            accessory: 'accessory-cute',
        };

        this.animationHandle = null;
        this.viewState = createInitialViewState();
        this.currentFrameData = {};
        // Testing scaffolding; see setDebugDrawingEnabled.
        this.debugDrawingEnabled = false;
        // Where the reader has moved and scaled the sheet. Viewer-local: it is
        // how you look at the drawing, not part of it, and never goes back.
        this.pageView = { zoom: 1, offsetX: 0, offsetY: 0 };
        this.csgTreesByKey = new Map();  // memberKey -> { memberKey, tree }
        this.csgTreeRequests = new Set();// memberKeys already asked for
        this.lastPickDetail = null;      // featureType / jointName / facesToward
        this.viewerOptions = normalizeViewerOptions(INITIAL_PAYLOAD.viewerOptions);
        this.cadqueryOcpInstalled = null;
        this.installingCadqueryOcp = false;
        this.exportFormatStlEnabled = true;
        this.exportFormat3mfEnabled = false;
        this.exportFormatObjEnabled = false;
        this.exportFormatStepEnabled = false;
        this.exportCombinedEnabled = true;
        this.exportIndividualsEnabled = false;
        this.exportAccessoriesEnabled = true;
        this.settingsPanel = new ViewerSettingsPanel(this);
        // What the frame on screen may be adjusted by, or null when it takes
        // nothing. The shape is kiwari-values.js's, not this file's.
        this.kiwariSections = [];
        // Highlights for features nobody is pointing at. See _highlightState.
        this._referenceFeaturesByMember = new Map();
        this._measurementEndHighlights = new Map();
        this._measurementEndAsked = new Set();
        this.kiwariPanel = new ViewerKiwariPanel(this);
        this.memberListPanel = new MemberListPanel(this, { t });
        // Kigumi's MCP server as the host last said it is (frame-view-session.js), or null.
        this.mcpState = null;
        this.sidebar = new ViewSidebar({ requestUpdate: () => this.requestUpdate(), store: vscode });
        this.selectionPanel = new SelectionPanel(this, {
            t,
            csgTreeView: CsgTreeView,
            featureTypeNouns: FEATURE_TYPE_NOUNS,
        });
        this.activeRefreshToken = 0;
        this.onWindowMessage = this.onWindowMessage.bind(this);
        this.onWindowScroll = this.onWindowScroll.bind(this);
        this.onWindowMouseUp = this.onWindowMouseUp.bind(this);
        this.onWindowMouseMove = this.onWindowMouseMove.bind(this);
        this.onWindowResize = this.onWindowResize.bind(this);
        this.onGizmoPointerMove = this.onGizmoPointerMove.bind(this);
        this.onGizmoPointerUp = this.onGizmoPointerUp.bind(this);
        this.onLightDialPointerMove = this.onLightDialPointerMove.bind(this);
        this.onLightDialPointerUp = this.onLightDialPointerUp.bind(this);
        this.onWindowKeyDown = this.onWindowKeyDown.bind(this);
        this.onWindowKeyUp = this.onWindowKeyUp.bind(this);
        this.onWindowBlur = this.onWindowBlur.bind(this);
        // Whether shift is held: it switches the selection mode, which hover has to follow
        // while the pointer rests. See pickMode in selection-store.js.
        this._shiftHeld = false;
        this.onLayerStateChanged = this.onLayerStateChanged.bind(this);
        this.onMemberContextMenuRequest = this.onMemberContextMenuRequest.bind(this);
        this.onLayerContextMenuRequest = this.onLayerContextMenuRequest.bind(this);
        this.onCsgTreeRequested = this.onCsgTreeRequested.bind(this);
        this.onCsgByPathRequested = this.onCsgByPathRequested.bind(this);
        this.onEnterDrawingRequested = this.onEnterDrawingRequested.bind(this);
        this.onSaveDrawingsRequested = this.onSaveDrawingsRequested.bind(this);
        this.onWindowContextMenuDismiss = this.onWindowContextMenuDismiss.bind(this);
    }

    // ------------------------------------------------------------------
    // The page: rendering, the sidebar's pages, lifecycle and wiring
    // ------------------------------------------------------------------

    createRenderRoot() {
        return this;
    }

    render() {
        const cameraMode = this.cameraController.getCameraMode();
        const hasPendingChanges = this.viewState.sourceHasPendingChanges;
        const navigationHint = this.leftClickDragRotatesCamera
            ? t('viewer.chrome.navHint.leftClick')
            : t('viewer.chrome.navHint.rightClick');
        return html`
            <button id="to-v3d" title=${t('viewer.chrome.toV3d.title')}>${t('viewer.chrome.toV3d')}</button>
            <div id="view-layout">
            ${this.sidebar.render(this.sidebarPages())}
            <div id="viewport">
                ${hasPendingChanges
                    ? html`<button
                        id="top-center-refresh-btn"
                        type="button"
                        title=${t('viewer.refresh.title')}
                        @click=${() => this.requestRefresh()}>
                            <span class="top-center-refresh-primary">${t('viewer.refresh')}</span>
                            <span class="top-center-refresh-secondary">${t('viewer.refresh.changesDetected')}</span>
                        </button>`
                    : ''}
                <canvas id="c"></canvas>
                <!-- Dimensions are drawn on the sheet rather than in the scene:
                     they belong to the page, not to any camera. -->
                <svg id="measurement-overlay" aria-hidden="true"></svg>
                <div id="loading-overlay" class=${this.overlayClasses()}>
                    <div id="loading-text">${this.viewState.loadingText}</div>
                    <button id="output-btn" type="button" title=${t('viewer.chrome.viewOutput.title')} style="display: ${this.viewState.showOutputLink ? 'block' : 'none'}">${t('viewer.chrome.viewOutput')}</button>
                </div>
                <div id="gizmo-panel" class=${this.cameraPanelCollapsed ? 'is-collapsed' : ''}
                     aria-label=${t('viewer.chrome.gizmoPanel.ariaLabel')}>
                    <!-- The same header as the panels on the left (overlay-header.js), the
                         arrow after the name on this side. -->
                    <div class="ov-header ov-header-right" role="button"
                         aria-expanded=${this.cameraPanelCollapsed ? 'false' : 'true'}
                         @click=${() => this.toggleCameraPanel()}>
                        <span class="ov-title">${t('viewer.chrome.gizmo.camera')}</span>
                        <span class="ov-chev">${window.KigumiOverlay.ARROWS.right[this.cameraPanelCollapsed ? 'collapsed' : 'open']}</span>
                    </div>
                    <div class="gizmo-body">
                        <canvas id="gizmo-cube-c"></canvas>
                        <button id="focus-btn" type="button" title=${t('viewer.chrome.gizmo.focus.title')}>${t('viewer.chrome.gizmo.focus')}</button>
                        <button
                            id="camera-mode-btn"
                            type="button"
                            title=${t('viewer.chrome.gizmo.cameraMode.title')}
                        >📷 ${cameraMode === 'standard' ? t('viewer.chrome.gizmo.cameraMode.standard') : t('viewer.chrome.gizmo.cameraMode.free')}</button>
                        <button
                            id="projection-mode-btn"
                            type="button"
                            title=${t('viewer.chrome.gizmo.projectionMode.title')}
                        >${this.isOrthographic ? '⬛' : '📐'} ${this.isOrthographic ? t('viewer.chrome.gizmo.projectionMode.orthographic') : t('viewer.chrome.gizmo.projectionMode.perspective')}</button>
                        <div class="gizmo-title">${t('viewer.chrome.gizmo.light')}</div>
                        <canvas id="light-dial-c"></canvas>
                    </div>
                </div>
                <div id="debug"></div>
                <div id="hint">${navigationHint}</div>
                ${this.renderAssemblyTimeline()}
                ${this.renderMemberContextMenu()}
            </div>
            </div>
        `;
    }

    /** The sidebar's pages (view-sidebar.js): the tree, options, parameters, members and log. */
    sidebarPages() {
        const geometry = this._lastGeometryData;
        const memberCount = geometry && Array.isArray(geometry.meshes) ? geometry.meshes.length : 0;
        return [
            {
                id: 'tree',
                label: t('viewer.sidebar.tab.tree'),
                heading: html`<span class="vsb-mark" title=${t('viewer.sidebar.treeMark')}>🏠</span>`,
                // Its sections share the height, each collapsing to give the others room.
                fill: true,
                // What is selected, then the drawing it is in, then everything there is.
                // Narrowest first: the panel you came to read is the one about what you just clicked.
                content: html`
                    ${this.selectionPanel.render()}
                    <div id="drawing-panel-host"></div>
                    <kigumi-layers-view id="layers-view"></kigumi-layers-view>`,
            },
            { id: 'options', label: t('viewer.sidebar.tab.options'), content: this.settingsPanel.render() },
            {
                id: 'parameters',
                label: t('viewer.sidebar.tab.parameters'),
                content: this.kiwariPanel.render() || html`<div class="vsb-empty">${t('viewer.sidebar.noParameters')}</div>`,
            },
            { id: 'members', label: t('viewer.sidebar.tab.members'), badge: memberCount || '', content: this.memberListPanel.render() },
            {
                id: 'log',
                label: t('viewer.sidebar.tab.log'),
                content: html`
                    <div id="log-panel-box" class="panel-box">
                        <div class="panel-title">
                            ${t('viewer.log.title')}
                            <div id="log-panel-toolbar">
                                <input id="log-filter" type="text" placeholder=${t('viewer.log.filter.placeholder')}>
                                <button id="log-clear-btn" type="button">${t('viewer.log.clear')}</button>
                                <button id="log-open-output-btn" type="button">${t('viewer.log.openOutput')}</button>
                            </div>
                        </div>
                        <div id="log-output"></div>
                    </div>
                    <div class="panel-box">
                        <div class="panel-title">${t('viewer.rawOutput.title')}</div>
                        <pre id="raw-output"></pre>
                    </div>`,
            },
        ];
    }

    firstUpdated() {
        this.setupUiEvents();
        this.setupThreeScene();
        window.addEventListener('message', this.onWindowMessage);
        this.applyPersistedViewerSettings(INITIAL_PAYLOAD.viewerSettings || null);
        this.setViewerOptions(INITIAL_PAYLOAD.viewerOptions);
        this.setViewPhase(ViewerPhase.WAITING_FOR_RUNNER, t('viewer.chrome.loading.raisingFrame'), { refreshToken: 0 });
        void this.beginPayloadApplication(INITIAL_PAYLOAD);
        if (INITIAL_PAYLOAD.mcpAvailable && vscode) {
            vscode.postMessage({ type: 'requestMcpState' });
        }
        
        // Setup selection listener
        this.selectionManager.onSelectionChanged((event) => {
            // Nothing is focused, so there is no CSG highlight to draw. The
            // guard is the whole condition: when layers-view sets the focus and
            // pulls its timber into the selection, csgFocus is set, so this
            // leaves the highlight it just asked for alone. Listing the event
            // types as well only ever missed a cleanup -- selecting a joint,
            // or clearing the focus outright, left a stale mesh behind.
            if (!this.selectionManager.csgFocus) {
                this._csgHighlightSource = null;
            }
            // A measurement is made in one view: selecting in another lets go of it.
            if (event.type === 'scope' && this.measureDraft.isActive) {
                this.escapeMeasurement();
            }
            this.selectionPanel.updateInfo(this.currentFrameData);
            this.memberListPanel.syncSelection();
        });

        // Attach Layers panel to selection store + extension messaging.
        const layersView = this.renderRoot.querySelector('#layers-view');
        if (layersView && typeof layersView.attach === 'function') {
            layersView.attach(this.selectionManager, vscode);
        }
        this._layersView = layersView;
        if (this._layersView) {
            this._layersView.addEventListener('layer-state-changed', this.onLayerStateChanged);
            this._layersView.addEventListener('kigumi-member-contextmenu', this.onMemberContextMenuRequest);
            this._layersView.addEventListener('kigumi-layer-contextmenu', this.onLayerContextMenuRequest);
            this._layersView.addEventListener('kigumi-request-csg-tree', this.onCsgTreeRequested);
            this._layersView.addEventListener('kigumi-request-csg-by-path', this.onCsgByPathRequested);
            this._layersView.addEventListener('kigumi-enter-drawing', this.onEnterDrawingRequested);
            this._layersView.addEventListener('kigumi-save-drawings', this.onSaveDrawingsRequested);
            this._layersView.addEventListener('kigumi-focus-measurement', (event) => {
                this._focusMeasurementFrom(event.detail);
            });
            this._layersView.addEventListener('kigumi-measurement-contextmenu', (event) => {
                this.showMeasurementContextMenu(event.detail || {});
            });
            this._layersView.addEventListener('kigumi-toggle-measurements', (event) => {
                this.setMeasurementsHidden(event.detail && event.detail.hidden);
                this._layersDrawingsChanged();
            });
            this._layersView.setDrawingsEnabled(this.drawingBetaEnabled);
            if (this.drawingBetaEnabled) {
                // The list is python's; ask for it once there is somewhere to
                // show it.
                this.requestDrawings();
            }
        }
        // Layers tree (and any background assembly solve) data arrives
        // unprompted, pushed by the extension host once it's actually ready
        // (either from a completed refresh, or immediately from cache on a
        // panel reopen) -- no need to request it here.

        this.emitViewerLog('viewer-ready', {});
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener('message', this.onWindowMessage);
        window.removeEventListener('scroll', this.onWindowScroll);
        window.removeEventListener('mouseup', this.onWindowMouseUp);
        window.removeEventListener('mousemove', this.onWindowMouseMove);
        window.removeEventListener('mousedown', this.onWindowContextMenuDismiss);
        window.removeEventListener('resize', this.onWindowResize);
        if (this._viewportObserver) {
            this._viewportObserver.disconnect();
        }
        window.removeEventListener('keydown', this.onWindowKeyDown);
        window.removeEventListener('keyup', this.onWindowKeyUp);
        window.removeEventListener('blur', this.onWindowBlur);
        window.removeEventListener('pointermove', this.onGizmoPointerMove);
        window.removeEventListener('pointerup', this.onGizmoPointerUp);
        window.removeEventListener('pointermove', this.onLightDialPointerMove);
        window.removeEventListener('pointerup', this.onLightDialPointerUp);
        // Whatever is mid-drag, whether or not anything is: the rail being
        // resized, a dimension being moved. This is what a NAME buys -- the
        // measurement drag used closures nothing here could refer to.
        this._endAllPointerGestures();
        if (this.animationHandle) {
            cancelAnimationFrame(this.animationHandle);
            this.animationHandle = null;
        }
        if (this._layersView) {
            this._layersView.removeEventListener('layer-state-changed', this.onLayerStateChanged);
            this._layersView.removeEventListener('kigumi-member-contextmenu', this.onMemberContextMenuRequest);
            this._layersView.removeEventListener('kigumi-layer-contextmenu', this.onLayerContextMenuRequest);
            this._layersView.removeEventListener('kigumi-request-csg-tree', this.onCsgTreeRequested);
            this._layersView.removeEventListener('kigumi-request-csg-by-path', this.onCsgByPathRequested);
            this._layersView.removeEventListener('kigumi-enter-drawing', this.onEnterDrawingRequested);
            this._layersView.removeEventListener('kigumi-save-drawings', this.onSaveDrawingsRequested);
        }
        if (this.cameraCube) {
            this.cameraCube.dispose();
            this.cameraCube = null;
        }
        if (this.shadowCatcher) {
            this.scene.remove(this.shadowCatcher);
            this.shadowCatcher.geometry.dispose();
            this.shadowCatcher.material.dispose();
            this.shadowCatcher = null;
        }
        if (this.orbitGizmo) {
            this.scene.remove(this.orbitGizmo.object3d);
            this.orbitGizmo.dispose();
            this.orbitGizmo = null;
            this.orbitCenterGizmo = null;
        }
        this.sceneManager.disposeAll();
        this.memberMetadataByKey.clear();
    }

    onLayerStateChanged(event) {
        const detail = event && event.detail ? event.detail : {};
        const key = detail.key;
        if (typeof key !== 'string' || key.length === 0) {
            return;
        }
        // The only thing left here, and it is an EFFECT: it changes the state
        // rather than describing it, so it cannot be derived and has to happen
        // when it happens. What a locked member LOOKS like is derived, and the
        // frame loop works that out by asking.
        if (detail.prop === 'locked' && detail.value === true
                && this.selectionManager.isTimberSelected(key)) {
            this._dropCsgFocus();
            this.selectionManager.deselectTimber(key);
        }
    }

    /**
     * Whether a member is hidden or locked, ASKED of the one copy.
     *
     * There used to be a mirror here -- a Map on the app, kept in step with the
     * panel's store by events. Two copies of one fact, the second stale exactly
     * when an event goes missing, and the frame drawn from the stale one.
     */
    isMemberHidden(memberKey) {
        const layers = this._layersView && this._layersView.layerState;
        return Boolean(layers && layers.isHidden(memberKey));
    }

    isMemberLocked(memberKey) {
        const layers = this._layersView && this._layersView.layerState;
        return Boolean(layers && layers.isLocked(memberKey));
    }

    setupUiEvents() {
        const toV3d = this.renderRoot.querySelector('#to-v3d');
        const canvas = this.renderRoot.querySelector('#c');
        const viewport = this.renderRoot.querySelector('#viewport');
        const gizmoCanvas = this.renderRoot.querySelector('#gizmo-cube-c');
        const focusButton = this.renderRoot.querySelector('#focus-btn');
        const cameraModeButton = this.renderRoot.querySelector('#camera-mode-btn');
        const projectionModeButton = this.renderRoot.querySelector('#projection-mode-btn');
        const lightDialCanvas = this.renderRoot.querySelector('#light-dial-c');

        toV3d.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });

        canvas.addEventListener('pointermove', (event) => {
            this.handleCanvasHover(event);
        });
        canvas.addEventListener('pointerleave', () => {
            // clearHover refuses while the feature menu holds the hover pinned:
            // reaching one of its rows means leaving the canvas.
            this.clearHover();
        });

        canvas.addEventListener('mousedown', (event) => {
            const action = actionForButton(event.button, this.leftClickDragRotatesCamera);
            if (!action) {
                return;
            }
            // Dragging acts on the viewport it started in, so a press makes
            // that one active before the camera moves.
            this.focusViewportAt(event.clientX, event.clientY);
            if (action === 'orbit') {
                this.cameraController.captureOrbitDragFrame();
            }
            event.preventDefault();
            this.pointerDrag.begin({
                action,
                button: event.button,
                target: event.target,
                x: event.clientX,
                y: event.clientY,
            });
            this.cameraController.cancelAnimation();
        });

        canvas.addEventListener('contextmenu', (event) => {
            event.preventDefault();
        });

        viewport.addEventListener('wheel', (event) => {
            if (window.scrollY > 0) {
                return;
            }
            event.preventDefault();
            // Calculate adaptive zoom factor based on current distance
            // This makes zoom speed feel consistent across all scales
            const adaptiveZoomFactor = this.getAdaptiveZoomFactor(event.deltaY > 0);
            // On a sheet the wheel moves the page, and only the page. No
            // viewport zooms: a drawing's cameras are what python declared, and
            // a view that has been zoomed is no longer at the scale the drawing
            // says it is. Letting the preview zoom itself also zoomed whichever
            // viewport was last clicked, since a camera zoom acts on the active
            // one rather than the one under the pointer.
            if (this.activePage) {
                // Inverted on purpose: the factor scales an orbit distance,
                // where bigger means further away, and a page scale, where
                // bigger means closer. Passing it straight through is what made
                // the wheel work backwards on a sheet.
                this.zoomPageToward(event.clientX, event.clientY, 1 / adaptiveZoomFactor);
                return;
            }
            this.zoomTowardPointer(event.clientX, event.clientY, adaptiveZoomFactor);
        }, { passive: false });

        gizmoCanvas.addEventListener('pointerdown', (event) => {
            event.preventDefault();
            this.gizmoDragging = true;
            this.gizmoMoved = false;
            this.gizmoLastX = event.clientX;
            this.gizmoLastY = event.clientY;
            this.cameraController.captureOrbitDragFrame();
            gizmoCanvas.setPointerCapture(event.pointerId);
        });

        focusButton.addEventListener('click', () => {
            this.focusSelection();
        });

        cameraModeButton.addEventListener('click', () => {
            const nextMode = this.cameraController.getCameraMode() === 'standard' ? 'free' : 'standard';
            this.setCameraMode(nextMode);
        });

        projectionModeButton.addEventListener('click', () => {
            this.setProjectionMode(!this.isOrthographic);
        });

        const outputBtn = this.renderRoot.querySelector('#output-btn');
        if (outputBtn) {
            outputBtn.addEventListener('click', () => {
                if (vscode) { vscode.postMessage({ type: 'openKigumiOutput' }); }
            });
        }

        lightDialCanvas.addEventListener('pointerdown', (event) => {
            event.preventDefault();
            this.lightDialDragging = true;
            lightDialCanvas.setPointerCapture(event.pointerId);
            this.applyLightDialFromPointer(event);
        });

        this.settingsPanel.bindEvents(this.renderRoot);

        const logClearBtn = this.renderRoot.querySelector('#log-clear-btn');
        const logFilterInput = this.renderRoot.querySelector('#log-filter');
        const logOpenOutputBtn = this.renderRoot.querySelector('#log-open-output-btn');

        logClearBtn.addEventListener('click', () => { this.clearLog(); });
        logFilterInput.addEventListener('input', (event) => { this.applyLogFilter(event.target.value); });
        logOpenOutputBtn.addEventListener('click', () => {
            if (vscode) { vscode.postMessage({ type: 'openOutputChannel' }); }
        });

        this.memberListPanel.bindEvents(this.renderRoot);
        this.memberListPanel.applyOptionVisibility();

        window.addEventListener('scroll', this.onWindowScroll);
        window.addEventListener('mouseup', this.onWindowMouseUp);
        window.addEventListener('mousemove', this.onWindowMouseMove);
        window.addEventListener('mousedown', this.onWindowContextMenuDismiss);
        window.addEventListener('pointermove', this.onGizmoPointerMove);
        window.addEventListener('pointerup', this.onGizmoPointerUp);
        window.addEventListener('pointermove', this.onLightDialPointerMove);
        window.addEventListener('pointerup', this.onLightDialPointerUp);
        window.addEventListener('resize', this.onWindowResize);
        window.addEventListener('keydown', this.onWindowKeyDown);
        window.addEventListener('keyup', this.onWindowKeyUp);
        window.addEventListener('blur', this.onWindowBlur);
    }

    setupThreeScene() {
        const viewport = this.renderRoot.querySelector('#viewport');
        const canvas = this.renderRoot.querySelector('#c');

        this.renderer = new THREE.WebGLRenderer({
            canvas: canvas,
            antialias: true,
            logarithmicDepthBuffer: true,
            preserveDrawingBuffer: true,
        });
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.setSize(viewport.offsetWidth, viewport.offsetHeight, false);
        // The sidebar beside it changes its width as well as the window does.
        this._viewportObserver = new window.ResizeObserver(() => this.onWindowResize());
        this._viewportObserver.observe(viewport);
        this.renderer.outputEncoding = THREE.sRGBEncoding;
        // Which member is frontmost at each pixel: what clips a drawing's dotted lines to their own
        // timber. See member-id-buffer.js.
        this.memberIds = new window.KigumiMemberIdBuffer.MemberIdBuffer({ THREE, renderer: this.renderer });
        // A drawing's dotted perfect faces and centerlines, clipped by the id pass. See drawing-overlays.js.
        this.drawingOverlays = new window.KigumiDrawingOverlays.DrawingOverlays({
            THREE, memberIds: this.memberIds, resolution: this._getRendererResolution() });
        this.renderer.shadowMap.enabled = false;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

        this.scene = new THREE.Scene();
        this.sceneManager.setScene(this.scene);
        this.setTheme(this.activeTheme);

        this.rebuildViewports();

        // Intensities are not set here: applyRenderMode writes all four every
        // frame, so whatever they are built with is overwritten before the
        // first paint. Setting them twice would only invite the two to drift.
        this.ambient = new THREE.AmbientLight(0xffffff, 0);
        this.scene.add(this.ambient);
        this.sun = new THREE.DirectionalLight(0xffffff, 0);
        this.sun.position.set(2, 1, 18);
        this.sun.castShadow = true;
        this.sun.shadow.bias = -0.00008;
        this.sun.shadow.mapSize.set(2048, 2048);
        this.scene.add(this.sun);
        this.fill = new THREE.DirectionalLight(0xd8e3f5, 0);
        this.fill.position.set(-4, 3, -6);
        this.scene.add(this.fill);

        // The sheet's light. Added once and dimmed rather than added and
        // removed, because three.js keys its shader programs on how many lights
        // of each kind a scene has: taking one out recompiles every material in
        // the viewer, and switching between the model and a sheet would do it
        // each way.
        this.viewLight = new THREE.DirectionalLight(0xffffff, 0);
        this.viewLight.castShadow = false;
        this.scene.add(this.viewLight);
        this.scene.add(this.viewLight.target);
        this._viewLightAim = new THREE.Vector3();

        this.createOrUpdateShadowCatcher(this.lastBounds);
        this.syncCameraControls();
        this.syncLightAnglesFromSun();
        this.drawLightDial();
        this.setCenterGizmoEnabled(this.showCenterGizmo);
        this.setShadowsEnabled(this.shadowsEnabled);
        this.setReflectionsEnabled(this.reflectionsEnabled);
        this.setFootprintColor(this.footprintColor);

        this.updateCamera();
        const animate = () => {
            this.animationHandle = requestAnimationFrame(animate);
            this.stepCameraAnimation();
            this.renderCameraControls();
            this.updateCylinderSilhouettes();
            // Asked from here rather than a timer: a hover cannot outlive the
            // viewer, and nothing is asked while the tab is not drawing.
            //
            // Guarded because this runs inside the frame: a throw here would
            // stop renderViewports below it and freeze the view, which is a
            // spectacular way for a hover to fail.
            try {
                this.pumpHover();
            } catch (error) {
                if (!this._hoverBroken) {
                    this._hoverBroken = true;
                    this.emitViewerLog('hover-error', { message: String(error && error.message || error) });
                }
            }
            // Pulled, not pushed: what is drawn follows the state because the
            // state is asked, every frame, rather than because something
            // remembered to say it had changed.
            this.applyDerivedVisuals();
            this.renderViewports();
        };
        animate();
    }

    // ------------------------------------------------------------------
    // Viewports, cameras and the sheet
    // ------------------------------------------------------------------

    // The viewport the camera controls act on. With one viewport this is the
    // only one; with several it is the one last interacted with, which is what
    // the cube and the orbit gizmo describe.
    get activeViewport() {
        if (this.viewports.length === 0) {
            return null;
        }
        return this.viewports.find((viewport) => viewport.id === this.activeViewportId)
            || this.viewports[0];
    }

    get cameraController() {
        const viewport = this.activeViewport;
        return viewport ? viewport.cameraController : null;
    }

    /**
     * Orbit the active viewport, or tilt it if the scene locked its angle.
     *
     * A locked elevation is only an elevation while it points where the drawing
     * says, so a drag there is a bounded nudge rather than a free orbit: enough
     * to read the depth of what is drawn, not enough to become a different
     * view, and it springs back to the declared angle on release.
     */
    orbitActiveViewport(dx, dy) {
        const viewport = this.activeViewport;
        if (!viewport) {
            return;
        }
        const controller = viewport.cameraController;
        if (!viewport.spec.locked) {
            const orbit = viewport.spec.orbit;
            if (orbit && orbit.mode === 'axis') {
                // Only the sideways part of the drag: dragging up and down
                // would tumble the piece out of the attitude it is drawn in,
                // which is the whole thing this mode exists to prevent.
                controller.orbitAboutAxis(dx, DEFAULT_AXIS_ORBIT_SPEED, {
                    x: orbit.axis[0], y: orbit.axis[1], z: orbit.axis[2],
                });
                return;
            }
            controller.applyOrbitDelta(dx, dy);
            return;
        }
        controller.nudgeWithinCone(
            dx, dy, TILT_ORBIT_SPEED, viewport.declaredOffsetDir, MAX_TILT_RADIANS,
        );
    }

    /** Return a tilted viewport to the angle its drawing declared. */
    releaseTilt() {
        const viewport = this.activeViewport;
        if (!viewport || !viewport.spec.locked || !viewport.declaredOffsetDir) {
            return;
        }
        if (viewport.cameraController.cameraOffsetDir.equals(viewport.declaredOffsetDir)) {
            return;
        }
        this.animateCameraTo(
            viewport.declaredOffsetDir.clone(),
            viewport.cameraController.orbitDist,
            220,
            viewport.declaredUpVector ? viewport.declaredUpVector.clone() : null,
        );
    }

    get camera() {
        const viewport = this.activeViewport;
        return viewport ? viewport.camera : null;
    }

    get perspectiveCamera() {
        const viewport = this.activeViewport;
        return viewport ? viewport.perspectiveCamera : null;
    }

    get orthographicCamera() {
        const viewport = this.activeViewport;
        return viewport ? viewport.orthographicCamera : null;
    }

    get isOrthographic() {
        const viewport = this.activeViewport;
        return viewport ? viewport.isOrthographic : false;
    }

    /**
     * Build the runtime viewports for the active scene.
     *
     * Camera state is carried across by viewport id where the ids match, so
     * switching scenes and back does not throw away where you were looking.
     */
    rebuildViewports() {
        // Cameras are kept across a rebuild of the same scene, so a redraw does
        // not throw away where the reader had got to. They are *not* kept
        // across a change of scene: every drawing has a viewport called
        // 'front', and handing one drawing's front camera to another's is how a
        // drawing came up at the angle the last one was left at -- and never
        // learned the angle it was supposed to be at, since that is set when a
        // camera is first pointed.
        const sceneId = this.sceneStore.activeSceneId;
        const sameScene = this._viewportsBuiltFor === sceneId;
        const previous = sameScene
            ? new Map(this.viewports.map((viewport) => [viewport.id, viewport.cameraController]))
            : new Map();
        this._viewportsBuiltFor = sceneId;
        this.viewports = this.sceneStore.activeViewports().map((spec) => {
            const reused = previous.get(spec.id);
            const viewport = new ViewerViewport(spec, reused || new CameraController({ THREE }));
            // The declared angle is the spec's, so every viewport records it,
            // reused controller or not. Only POINTING the camera at it is
            // skipped on reuse -- that would throw away where the reader had
            // got to.
            viewport.rememberDeclaredCamera();
            if (!reused) {
                viewport.applySpecCamera();
            }
            return viewport;
        });
        if (!this.viewports.some((viewport) => viewport.id === this.activeViewportId)) {
            this.activeViewportId = this.viewports.length > 0 ? this.viewports[0].id : null;
        }
        this.selectionManager.keepScopeWithin(this.viewports.map((viewport) => viewport.id));
        // Cameras are built with a placeholder aspect, since a viewport can be
        // rebuilt before there is a canvas to measure. Give them the real one
        // now if there is; without this they keep 1 until the first resize and
        // the frame renders stretched to the canvas.
        this.syncCameraProjection();
        this.updateCamera();
    }

    /**
     * Draw every viewport of the active scene.
     *
     * On a sheet this composites: the page underneath, then each viewport over
     * it contributing only its geometry. Off a sheet -- the 3D scene -- it is
     * the single full-canvas render it always was.
     */
    /**
     * Which highlights a viewport draws. The selection, and a measurement's ends, belong to the
     * view they were made in; a hover to the view under the pointer; a reference to every view.
     * With one viewport there is nothing to choose.
     */
    _showHighlightsFor(viewportId) {
        const single = this.viewports.length < 2;
        for (const object of this._highlightObjects.values()) {
            const role = object.userData.role;
            const own = single || role === 'reference'
                || viewportId === (role === 'hover' ? this._hoverViewportId : this.selectionManager.scope);
            // The selection echoes softly in the other views, so it can be found there too.
            const echo = !own && role === 'selection';
            object.visible = own || echo;
            object.material.opacity = object.userData.opacity * (echo ? SELECTION_ECHO_OPACITY : 1);
        }
    }

    renderViewports() {
        if (!this.renderer || !this.scene) {
            return;
        }
        const size = this.renderer.getSize(new THREE.Vector2());
        const pageRect = this.pageScreenRect(size.x, size.y);
        // Before anything is drawn, and before onPaper is read: the mode is the
        // one answer to "sheet or model", so nothing below asks it again.
        const { onPaper } = this.applyRenderMode();
        if (onPaper) {
            this.paintSheet(pageRect, size.y);
        }
        // Depth is a different matter from colour (see the mode's autoClear)
        // and must still go per viewport, or one depth-tests against whatever
        // the last left and loses geometry behind a neighbour it has no
        // spatial relationship to.
        // Scissoring costs nothing to skip while one viewport covers the
        // canvas, which is the 3D scene and every session before drawings.
        const scissored = onPaper || this.viewports.length > 1;
        this.renderer.setScissorTest(scissored);
        for (const viewport of this.viewports) {
            this._showHighlightsFor(viewport.id);
            const anyDrawingLines = this.drawingOverlays.showFor(
                this.sceneManager.bundles(), viewport.camera, { inDrawing: this.isInDrawing, options: this });
            const rect = viewport.pixelRect(pageRect, size.y);
            if (anyDrawingLines && this.memberIds) {
                // Who is in front where, for the dotted lines to clip themselves by.
                const ratio = this.renderer.getPixelRatio();
                this.memberIds.render(this.scene, viewport.camera, viewport.id,
                    [rect.x * ratio, rect.y * ratio, rect.width * ratio, rect.height * ratio]);
            }
            this.renderer.setViewport(rect.x, rect.y, rect.width, rect.height);
            if (scissored) {
                this.renderer.setScissor(rect.x, rect.y, rect.width, rect.height);
            }
            if (onPaper) {
                this.renderer.clearDepth();
                // Per viewport, not per sheet: each view looks a different way,
                // and a light aimed down one of them would shade the others by
                // how far round they are from it -- the same thing the sun was
                // doing, just with a nearer sun.
                this.aimViewLight(viewport.camera);
            }
            this.renderer.render(this.scene, viewport.camera);
        }
        // After the scene, so dimensions sit over what they measure.
        this.renderMeasurements();
    }

    /**
     * Put the renderer into the mode the active scene wants. Every frame.
     *
     * Writes every property renderModeFor names, unconditionally, with no
     * check for whether it already holds that value. That is the whole point:
     * a guard is what lets a second writer drift, and a mode applied as a
     * difference from the one before it is a mode that depends on history.
     * Applied in full from a value derived only from the scene and the
     * reader's settings, nothing can carry over a switch.
     *
     * It reads the reader's settings and never writes them, so asking for
     * shadows while a sheet is open is remembered and takes effect on the way
     * back out.
     */
    applyRenderMode() {
        const mode = window.KigumiRenderMode.renderModeFor({
            page: this.sceneStore.activeScene().page,
            shadowsEnabled: this.shadowsEnabled,
            reflectionsEnabled: this.reflectionsEnabled,
        });
        if (this.ambient) {
            this.ambient.intensity = mode.lights.ambient;
            this.sun.intensity = mode.lights.sun;
            this.fill.intensity = mode.lights.fill;
            this.viewLight.intensity = mode.lights.viewLight;
            this.sun.castShadow = mode.sunCastsShadow;
        }
        if (this.shadowCatcher) {
            this.shadowCatcher.visible = mode.shadowCatcherVisible;
        }
        if (this.renderer) {
            this.renderer.shadowMap.enabled = mode.shadowMapEnabled;
            this.renderer.autoClear = mode.autoClear;
        }
        if (this.scene) {
            this.scene.background = mode.useThemeBackground
                ? (this._themeBackground || null)
                : null;
        }
        // Whether a reflection shows takes two answers -- the mode's, and
        // whether the member itself is hidden -- so it is written here, where
        // both are in hand, rather than half here and half in two other places
        // that each had to remember the mode. The loop costs what
        // updateCylinderSilhouettes already costs, which the frame pays anyway.
        for (const [memberKey, bundle] of this.sceneManager.entries()) {
            if (bundle.reflection) {
                bundle.reflection.visible =
                    mode.reflectionsVisible && !this.isMemberHidden(memberKey);
            }
        }
        return mode;
    }

    /**
     * Point the sheet's light exactly where *camera* points.
     *
     * A directional light is only a direction -- where it sits does not matter,
     * so this puts it at the camera and aims it one unit further along, which
     * is the shortest way to say "from the reader's eye".
     */
    aimViewLight(camera) {
        if (!this.viewLight) {
            return;
        }
        camera.getWorldDirection(this._viewLightAim);
        this.viewLight.position.copy(camera.position);
        this.viewLight.target.position.copy(camera.position).add(this._viewLightAim);
    }

    /**
     * The sheet, and the desk it lies on.
     *
     * Two scissored clears rather than any geometry: the page is a layer
     * beneath the viewports, not something a camera renders. A paper texture,
     * border or title block would go here, still beneath, still not a camera's
     * business.
     */
    paintSheet(pageRect, canvasHeight) {
        const colors = this.sheetColors();
        this.renderer.setScissorTest(false);
        this.renderer.setClearColor(colors.desk, 1);
        this.renderer.clear(true, true, false);

        this.renderer.setScissorTest(true);
        this.renderer.setScissor(
            Math.round(pageRect.x),
            Math.round(canvasHeight - (pageRect.y + pageRect.height)),
            Math.max(1, Math.round(pageRect.width)),
            Math.max(1, Math.round(pageRect.height)),
        );
        this.renderer.setClearColor(colors.paper, 1);
        this.renderer.clear(true, true, false);
    }

    /**
     * Paper and the desk under it, following the theme for now.
     *
     * The plan expects per-drawing overrides eventually, and this is where they
     * would land -- the sheet's appearance belongs to the page.
     */
    sheetColors() {
        if (!this._sheetColors) {
            const theme = THEMES[this.displayOptions.get('activeTheme')] || Object.values(THEMES)[0];
            this._sheetColors = {
                // Paper is paper. The theme tints the desk the sheet lies on,
                // not the sheet: a drawing tinted with the 3D scene's gradient
                // reads as a coloured panel rather than as something printed,
                // and every viewport on it looks like it has a background of
                // its own when what shows through is the page.
                paper: new THREE.Color(PAPER_COLOR),
                // Light enough to sit behind the paper rather than frame it,
                // while still leaving the sheet's edge visible.
                desk: new THREE.Color(theme.gradientBottom).multiplyScalar(0.94),
            };
        }
        return this._sheetColors;
    }

    // ------------------------------------------------------------------
    // The log
    // ------------------------------------------------------------------

    emitViewerLog(eventName, details = {}) {
        const payload = {
            type: 'viewerLog',
            event: eventName,
            source: 'viewer',
            level: 'info',
            version: VIEWER_APP_VERSION,
            details,
            timestamp: new Date().toISOString(),
        };
        if (vscode) {
            vscode.postMessage(payload);
            return;
        }
        console.info('[Kigumi]', payload);
    }

    appendLogLine(text) {
        const container = this.renderRoot.querySelector('#log-output');
        if (!container) { return; }
        const line = document.createElement('div');
        line.className = 'log-line';
        line.textContent = text;
        if (this.logFilterText && !text.toLowerCase().includes(this.logFilterText)) {
            line.classList.add('log-filtered-out');
        }
        container.appendChild(line);
        container.scrollTop = container.scrollHeight;
    }

    clearLog() {
        const container = this.renderRoot.querySelector('#log-output');
        if (container) { container.innerHTML = ''; }
    }

    applyLogFilter(filterText) {
        this.logFilterText = filterText.toLowerCase();
        const container = this.renderRoot.querySelector('#log-output');
        if (!container) { return; }
        for (const line of container.querySelectorAll('.log-line')) {
            const match = !this.logFilterText || line.textContent.toLowerCase().includes(this.logFilterText);
            line.classList.toggle('log-filtered-out', !match);
        }
    }

    // ------------------------------------------------------------------
    // Options, export choices and saved settings
    // ------------------------------------------------------------------

    setViewerOptions(nextPartial, options = {}) {
        const normalized = normalizeViewerOptions(nextPartial);
        this.viewerOptions = {
            ...this.viewerOptions,
            ...normalized,
        };

        if (this.renderRoot && this.renderRoot.querySelector) {
            this.settingsPanel.syncControls(this.renderRoot);
        }

        if (options.postMessage && vscode) {
            vscode.postMessage({
                type: 'setRefreshOptions',
                options: this.viewerOptions,
            });
        }
    }

    setUnselectedTransparencyPercent(nextPercent) {
        if (!this.displayOptions.set('unselectedTransparencyPercent', nextPercent)) {
            return;
        }
        this.requestUpdate();
    }

    setSelectedTransparencyPercent(nextPercent) {
        if (!this.displayOptions.set('selectedTransparencyPercent', nextPercent)) {
            return;
        }
        this.requestUpdate();
    }

    setEdgeLineVisibilityPercent(nextPercent) {
        if (!this.displayOptions.set('edgeLineVisibilityPercent', nextPercent)) {
            return;
        }
        this.requestUpdate();
    }

    // Set a boolean export-related flag, re-rendering only when it changes.
    _setExportFlag(prop, enabled) {
        const normalized = Boolean(enabled);
        if (this[prop] === normalized) {
            return;
        }
        this[prop] = normalized;
        this.requestUpdate();
    }

    setExportFormatEnabled(format, enabled) {
        const prop = EXPORT_FORMAT_PROP[format];
        if (prop) {
            this._setExportFlag(prop, enabled);
        }
    }

    setExportCombinedEnabled(enabled) {
        this._setExportFlag('exportCombinedEnabled', enabled);
    }

    setExportIndividualsEnabled(enabled) {
        this._setExportFlag('exportIndividualsEnabled', enabled);
    }

    setExportAccessoriesEnabled(enabled) {
        this._setExportFlag('exportAccessoriesEnabled', enabled);
    }

    getSelectedExportFormats() {
        return EXPORT_FORMATS.filter((format) => this[EXPORT_FORMAT_PROP[format]]);
    }

    collectViewerSettingsPayload() {
        return {
            version: 1,
            viewerOptions: { ...this.viewerOptions },
            ui: {
                // Everything the display options store owns, by its own account.
                ...this.displayOptions.toPayload(),
                showCenterGizmo: Boolean(this.showCenterGizmo),
                showAssemblyTimeline: Boolean(this.showAssemblyTimeline),
                disassemblyMultiplier: Number(this.disassemblyMultiplier),
                debugEnabled: Boolean(this.debugEnabled),
                leftClickDragRotatesCamera: Boolean(this.leftClickDragRotatesCamera),
                exportFormatStlEnabled: Boolean(this.exportFormatStlEnabled),
                exportFormat3mfEnabled: Boolean(this.exportFormat3mfEnabled),
                exportFormatObjEnabled: Boolean(this.exportFormatObjEnabled),
                exportFormatStepEnabled: Boolean(this.exportFormatStepEnabled),
                exportCombinedEnabled: Boolean(this.exportCombinedEnabled),
                exportIndividualsEnabled: Boolean(this.exportIndividualsEnabled),
                exportAccessoriesEnabled: Boolean(this.exportAccessoriesEnabled),
            },
        };
    }

    applyPersistedViewerSettings(settingsPayload) {
        if (!settingsPayload || typeof settingsPayload !== 'object') {
            return;
        }

        const viewerOptions = (settingsPayload.viewerOptions && typeof settingsPayload.viewerOptions === 'object')
            ? settingsPayload.viewerOptions
            : null;
        if (viewerOptions) {
            this.setViewerOptions(viewerOptions);
        }

        const ui = (settingsPayload.ui && typeof settingsPayload.ui === 'object')
            ? settingsPayload.ui
            : null;
        if (!ui) {
            return;
        }

        if (typeof ui.showCenterGizmo === 'boolean') {
            this.setCenterGizmoEnabled(ui.showCenterGizmo);
        }
        if (typeof ui.edgeMode === 'string') {
            this.setEdgeMode(ui.edgeMode);
        } else if (typeof ui.edgesEnabled === 'boolean') {
            // Back-compat for settings saved before edgeMode replaced the
            // edgesEnabled boolean.
            this.setEdgeMode(ui.edgesEnabled ? 'overlay' : 'none');
        }
        if (Number.isFinite(ui.edgeLineVisibilityPercent)) {
            this.setEdgeLineVisibilityPercent(Number(ui.edgeLineVisibilityPercent));
        }
        if (Number.isFinite(ui.edgeLineThicknessPx)) {
            this.setEdgeLineThicknessPx(Number(ui.edgeLineThicknessPx));
        }
        if (typeof ui.units === 'string') {
            this.setUnits(ui.units);
        }
        for (const system of KigumiUnits.UNIT_SYSTEMS) {
            if (typeof ui[`${system}Precision`] === 'string') {
                this.setUnitPrecision(ui[`${system}Precision`], system);
            }
        }
        if (typeof ui.shadowsEnabled === 'boolean') {
            this.setShadowsEnabled(ui.shadowsEnabled);
        }
        if (typeof ui.reflectionsEnabled === 'boolean') {
            this.setReflectionsEnabled(ui.reflectionsEnabled);
        }
        if (typeof ui.footprintColor === 'string') {
            this.setFootprintColor(ui.footprintColor);
        } else if (typeof ui.footprintsEnabled === 'boolean') {
            // Back-compat for settings saved before footprintColor replaced
            // the footprintsEnabled boolean.
            this.setFootprintColor(ui.footprintsEnabled ? DEFAULT_FOOTPRINT_COLOR : 'transparent');
        }
        if (ASSEMBLY_PREVIEW_ENABLED && typeof ui.showAssemblyTimeline === 'boolean') {
            this.setShowAssemblyTimeline(ui.showAssemblyTimeline);
        }
        if (ASSEMBLY_PREVIEW_ENABLED && Number.isFinite(ui.disassemblyMultiplier)) {
            this.setDisassemblyMultiplier(Number(ui.disassemblyMultiplier));
        }
        if (typeof ui.debugEnabled === 'boolean') {
            this.debugEnabled = ui.debugEnabled;
            const debugEl = this.renderRoot && this.renderRoot.querySelector
                ? this.renderRoot.querySelector('#debug')
                : null;
            if (debugEl) {
                debugEl.style.display = this.debugEnabled ? 'block' : 'none';
            }
        }
        if (typeof ui.leftClickDragRotatesCamera === 'boolean') {
            this.setLeftClickDragRotatesCameraEnabled(ui.leftClickDragRotatesCamera);
        }
        if (Number.isFinite(ui.unselectedTransparencyPercent)) {
            this.setUnselectedTransparencyPercent(Number(ui.unselectedTransparencyPercent));
        }
        if (Number.isFinite(ui.selectedTransparencyPercent)) {
            this.setSelectedTransparencyPercent(Number(ui.selectedTransparencyPercent));
        }
        if (typeof ui.activeTheme === 'string') {
            this.setTheme(ui.activeTheme);
        }
        if (typeof ui.exportFormatStlEnabled === 'boolean') {
            this.setExportFormatEnabled('stl', ui.exportFormatStlEnabled);
        }
        if (typeof ui.exportFormat3mfEnabled === 'boolean') {
            this.setExportFormatEnabled('3mf', ui.exportFormat3mfEnabled);
        }
        if (typeof ui.exportFormatObjEnabled === 'boolean') {
            this.setExportFormatEnabled('obj', ui.exportFormatObjEnabled);
        }
        if (typeof ui.exportFormatStepEnabled === 'boolean') {
            this.setExportFormatEnabled('step', ui.exportFormatStepEnabled);
        }
        if (typeof ui.exportCombinedEnabled === 'boolean') {
            this.setExportCombinedEnabled(ui.exportCombinedEnabled);
        }
        if (typeof ui.exportIndividualsEnabled === 'boolean') {
            this.setExportIndividualsEnabled(ui.exportIndividualsEnabled);
        }
        if (typeof ui.exportAccessoriesEnabled === 'boolean') {
            this.setExportAccessoriesEnabled(ui.exportAccessoriesEnabled);
        }

        if (this.settingsPanel && this.renderRoot && this.renderRoot.querySelector) {
            this.settingsPanel.syncControls(this.renderRoot);
        }
        this.requestUpdate();
    }

    // ------------------------------------------------------------------
    // Frame parameters (kiwari)
    // ------------------------------------------------------------------

    /** One section per kiwari the frames were built from. */
    setKiwariFromFrame(frameData) {
        this.kiwariSections = KigumiKiwariValues.sectionsFromPayload(frameData && frameData.kiwari, this.unitSystem());
        this.requestUpdate();
    }

    _changeKiwariSection(sectionId, change) {
        this.kiwariSections = KigumiKiwariValues.withSection(this.kiwariSections, sectionId, change);
        this.requestUpdate();
    }

    setKiwariDraft(sectionId, key, draft) {
        this._changeKiwariSection(sectionId, (state) => KigumiKiwariValues.withDraft(state, key, draft));
    }

    setKiwariEnabled(sectionId, key, on) {
        this._changeKiwariSection(sectionId, (state) => KigumiKiwariValues.withEnabled(state, key, on));
    }

    setKiwariAxisDraft(sectionId, key, axis, draft) {
        this._changeKiwariSection(sectionId, (state) => KigumiKiwariValues.withAxisDraft(state, key, axis, draft));
    }

    resetKiwariToDefaults() {
        this.kiwariSections = this.kiwariSections.map(
            (state) => KigumiKiwariValues.resetToDefaults(state, this.unitSystem()));
        this.requestUpdate();
    }

    /** What the boxes currently say, by section, or null if any of them does not read. */
    pendingKiwariValues() {
        if (!this.kiwariSections.length) {
            return null;
        }
        return KigumiKiwariValues.sectionsToWire(this.kiwariSections, this.units || KigumiUnits.DEFAULT_UNIT_SYSTEM);
    }

    saveKiwariToFile() {
        if (!vscode || !this.kiwariSections.some((state) => state.canSave)) {
            return;
        }
        vscode.postMessage({ type: 'saveParameters', kiwari: this.pendingKiwariValues() });
    }

    // ------------------------------------------------------------------
    // Messages from the host, and answers to its requests
    // ------------------------------------------------------------------

    requestRefresh() {
        if (!vscode) {
            return;
        }
        // A box that does not read sends nothing rather than a guess; the
        // build button is disabled in that state, so this is the belt to its
        // braces.
        const values = this.pendingKiwariValues();
        if (this.kiwariSections.length && values === null) {
            return;
        }
        vscode.postMessage({ type: 'requestRefresh', kiwari: values });
    }

    onWindowMessage(event) {
        const message = event.data || {};
        if (message.type === 'viewerState') {
            const uiState = this.normalizeUiState(message.uiState || null);
            if (message.viewerSettings && typeof message.viewerSettings === 'object') {
                this.applyPersistedViewerSettings(message.viewerSettings);
            }
            this.setViewerOptions(message.viewerOptions || null);
            const hasPayload = Object.prototype.hasOwnProperty.call(message, 'frame') ||
                Object.prototype.hasOwnProperty.call(message, 'geometry') ||
                Object.prototype.hasOwnProperty.call(message, 'profiling');

            if (!hasPayload) {
                this.setViewPhase(uiState.phase, uiState.loadingText, {
                    refreshToken: uiState.refreshToken,
                    error: uiState.error,
                });
                return;
            }

            this._frameLoaded();
            void this.beginPayloadApplication({
                frame: message.frame || {},
                geometry: message.geometry || { meshes: [] },
                profiling: message.profiling || null,
                uiState,
                viewerOptions: message.viewerOptions || null,
            });
            return;
        }

        if (message.type === 'captureScreenshotRequest') {
            this.handleCaptureScreenshotRequest(message);
            return;
        }

        if (message.type === 'capturePanelSnapshotRequest') {
            this.handleCapturePanelSnapshotRequest(message);
            return;
        }

        if (message.type === 'getCameraStateRequest') {
            this.handleGetCameraStateRequest(message);
            return;
        }

        if (message.type === 'mcpState') {
            this.mcpState = message.state || null;
            this.requestUpdate();
            return;
        }

        if (message.type === 'describePanelRequest') {
            this.respondToRequest(message, 'describePanelResult', () => this.describePanel(), 'Failed to describe the view');
            return;
        }

        if (message.type === 'setCameraStateRequest') {
            this.handleSetCameraStateRequest(message);
            return;
        }

        if (message.type === 'logEntry') {
            const text = typeof message.text === 'string' ? message.text : String(message.text);
            this.appendLogLine(text);
            return;
        }

        if (message.type === 'featureResult') {
            // Legacy stub — replaced by csgSelectionResult
            return;
        }

        if (message.type === 'hoverFeatureResult') {
            this.handleHoverResult(message);
            return;
        }

        if (message.type === 'featureHighlights') {
            this._setMeasurementEndHighlights(message);
            return;
        }

        if (message.type === 'csgSelectionResult') {
            this.handleCSGSelectionResult(message);
            return;
        }

        if (message.type === 'layersTree') {
            // The layers payload carries {pending: true} while the runner is
            // still solving the disassembly; the solved payload arrives later
            // in an 'assemblyData' message.
            const assemblyPayload = message.payload ? message.payload.assembly : null;
            if (ASSEMBLY_PREVIEW_ENABLED && assemblyPayload && assemblyPayload.pending === true) {
                this.assemblySolving = true;
                this.setAssemblyData(null);
            } else {
                this.assemblySolving = false;
                this.setAssemblyData(ASSEMBLY_PREVIEW_ENABLED
                    ? AssemblyTimeline.normalizeAssemblyPayload(assemblyPayload)
                    : null);
            }
            // Same reason the panel drops its copies: a refreshed frame can
            // have a different CSG, so cached trees must not outlive it.
            this.csgTreesByKey.clear();
            this.csgTreeRequests.clear();
            // A new frame: its reference features, and nothing kept from the last one.
            this._referenceFeaturesByMember = new Map(
                ((message.payload && message.payload.timbers) || [])
                    .filter((timber) => Array.isArray(timber.referenceFeatures) && timber.referenceFeatures.length)
                    .map((timber) => [timber.memberKey, timber.referenceFeatures]));
            this._measurementEndHighlights.clear();
            this._measurementEndAsked.clear();
            if (this._layersView && typeof this._layersView.setLayersPayload === 'function') {
                this._layersView.setLayersPayload(message.payload || {});
            }
            return;
        }

        if (message.type === 'scenes') {
            const payload = message.payload || {};
            // A dropped dimension was held until now: what came back has it where it was dropped.
            if (this._draggingMeasurement && this._draggingMeasurement.settling) {
                this._draggingMeasurement = null;
            }
            const ids = this.sceneStore.setScenes(payload.scenes);
            // Every drawing command answers with the whole set, so this is also
            // how the list refreshes -- entering is asked for separately, since
            // saving or listing should leave you where you are.
            const entering = payload.enterId && ids.includes(payload.enterId)
                ? payload.enterId
                : (payload.enter || this.debugDrawingEnabled ? ids[0] : null);
            if (entering) {
                this.setActiveScene(entering);
            } else {
                // Same scene, new contents. setActiveScene refuses the id it is
                // already on, so without this a measurement was written, came
                // back in this very message, and never appeared -- which is the
                // whole reason these commands answer with the full set.
                this.refreshActiveScene();
            }
            this._layersDrawingsChanged();
            this._applyPendingMeasurementFocus();
            return;
        }

        if (message.type === 'assemblyData') {
            this.assemblySolving = false;
            this.setAssemblyData(ASSEMBLY_PREVIEW_ENABLED
                ? AssemblyTimeline.normalizeAssemblyPayload(message.payload)
                : null);
            return;
        }

        if (message.type === 'csgTree') {
            const payload = message.payload || {};
            if (payload.tree) {
                this.onCsgTreeArrived(payload);
            }
            this.selectionPanel.updateInfo(this.currentFrameData);
            return;
        }

        if (message.type === 'dependencyStatus') {
            const payload = (message.payload && typeof message.payload === 'object') ? message.payload : {};
            if (typeof payload.cadqueryOcpInstalled === 'boolean') {
                this.cadqueryOcpInstalled = payload.cadqueryOcpInstalled;
                this.requestUpdate();
            }
            return;
        }

        if (message.type === 'dependencyInstallStatus') {
            const payload = (message.payload && typeof message.payload === 'object') ? message.payload : {};
            if (typeof payload.installingCadqueryOcp === 'boolean') {
                this.installingCadqueryOcp = payload.installingCadqueryOcp;
                this.requestUpdate();
            }
            return;
        }

        if (message.type === 'sourceChangeState') {
            const payload = (message.payload && typeof message.payload === 'object') ? message.payload : {};
            if (typeof payload.sourceHasPendingChanges === 'boolean') {
                this.setViewState({ sourceHasPendingChanges: payload.sourceHasPendingChanges });
                this.requestUpdate();
            }
            return;
        }

        if (message.type === 'viewerSettingsSaved') {
            if (message.ok !== false) {
                const pathText = typeof message.path === 'string' ? ` (${message.path})` : '';
                this.appendLogLine(`[settings] Saved viewer settings${pathText}`);
            }
            return;
        }
    }

    async handleCaptureScreenshotRequest(message) {
        const requestId = message && message.requestId;
        const canvas = this.renderRoot.querySelector('#c');

        if (!vscode || !requestId) {
            return;
        }

        if (!canvas) {
            vscode.postMessage({
                type: 'captureScreenshotResult',
                requestId,
                ok: false,
                error: 'Renderer canvas was not found',
            });
            return;
        }

        await this.waitForNextPaint();

        try {
            if (this.renderer && this.scene && this.camera) {
                this.renderViewports();
            }
            const dataUrl = canvas.toDataURL('image/png');
            vscode.postMessage({
                type: 'captureScreenshotResult',
                requestId,
                ok: true,
                dataUrl,
                width: canvas.width,
                height: canvas.height,
            });
        } catch (error) {
            vscode.postMessage({
                type: 'captureScreenshotResult',
                requestId,
                ok: false,
                error: error && error.message ? error.message : 'Unknown screenshot capture error',
            });
        }
    }

    handleCapturePanelSnapshotRequest(message) {
        const requestId = message && message.requestId;
        if (!vscode || !requestId) {
            return;
        }

        try {
            const titles = Array.from(this.renderRoot.querySelectorAll('#panels .panel-title'))
                .map((element) => (element.textContent || '').replace(/\s+/g, ' ').trim())
                .filter((label) => label.length > 0);
            const rawPanelIndex = titles.indexOf('Raw Python Output');
            const memberRowsElement = this.renderRoot.querySelector('#timber-rows');
            const memberRows = this.renderRoot.querySelectorAll('#timber-rows tr').length;
            const logText = this.renderRoot.querySelector('#log-output')
                ? this.renderRoot.querySelector('#log-output').textContent || ''
                : '';

            vscode.postMessage({
                type: 'capturePanelSnapshotResult',
                requestId,
                ok: true,
                snapshot: {
                    panelTitles: titles,
                    panelCount: titles.length,
                    hasMemberListPanel: titles.includes('Member List'),
                    hasMemberTableBody: Boolean(memberRowsElement),
                    hasLogOutputPanel: titles.some((label) => label.startsWith('Log Output')),
                    hasRawPythonOutputPanel: rawPanelIndex >= 0,
                    rawPythonOutputPanelIndex: rawPanelIndex,
                    isRawPythonOutputPanelLast: rawPanelIndex >= 0 && rawPanelIndex === titles.length - 1,
                    hasRenderControls: Boolean(this.renderRoot.querySelector('#render-controls')),
                    hasKiwariControls: Boolean(this.renderRoot.querySelector('#kiwari-controls')),
                    kiwariKeys: Array.from(this.renderRoot.querySelectorAll('#kiwari-controls .kiwari-key'))
                        .map((element) => (element.textContent || '').trim()),
                    kiwariChangedKeys: Array.from(
                        this.renderRoot.querySelectorAll('#kiwari-controls .kiwari-row-changed .kiwari-key'),
                    ).map((element) => (element.textContent || '').trim()),
                    kiwariOptionalKeys: Array.from(this.renderRoot.querySelectorAll('#kiwari-controls .kiwari-row'))
                        .filter((row) => row.querySelector('.kiwari-switch'))
                        .map((row) => (row.querySelector('.kiwari-key').textContent || '').trim()),
                    kiwariSwitchedOffKeys: Array.from(
                        this.renderRoot.querySelectorAll('#kiwari-controls .kiwari-row-off .kiwari-key'),
                    ).map((element) => (element.textContent || '').trim()),
                    kiwariBadKeys: Array.from(this.renderRoot.querySelectorAll('#kiwari-controls .kiwari-row'))
                        .filter((row) => row.querySelector('.kiwari-box-bad'))
                        .map((row) => (row.querySelector('.kiwari-key').textContent || '').trim()),
                    kiwariBuildDisabled: (() => {
                        const button = this.renderRoot.querySelector('#kiwari-build-btn');
                        return button ? button.disabled : null;
                    })(),
                    memberRowCount: memberRows,
                    logTextLength: logText.length,
                },
            });
        } catch (error) {
            vscode.postMessage({
                type: 'capturePanelSnapshotResult',
                requestId,
                ok: false,
                error: error && error.message ? error.message : 'Unknown panel snapshot error',
            });
        }
    }

    buildCameraStatePayload() {
        const cameraPosition = this.camera && this.camera.position
            ? {
                x: this.camera.position.x,
                y: this.camera.position.y,
                z: this.camera.position.z,
            }
            : null;
        const controllerPayload = this.cameraController.buildStatePayload();
        return {
            orbitCenter: controllerPayload.orbitCenter,
            focusCenter: {
                x: this.focusedCx,
                y: this.focusedCy,
                z: this.focusedCz,
            },
            orbit: controllerPayload.orbit,
            up: controllerPayload.up,
            cameraPosition,
        };
    }

    // Reply to a `${type}Request` message with a `${type}Result` carrying the
    // value returned by `produce()` (or ok:false with its error). Only for
    // handlers whose result is shaped `{ ok, payload }`; the capture handlers
    // use a different result shape and post directly.
    respondToRequest(message, resultType, produce, fallbackError = 'Request failed') {
        const requestId = message && message.requestId;
        if (!vscode || !requestId) {
            return;
        }
        try {
            const payload = produce();
            vscode.postMessage({ type: resultType, requestId, ok: true, payload });
        } catch (error) {
            vscode.postMessage({
                type: resultType,
                requestId,
                ok: false,
                error: error && error.message ? error.message : fallbackError,
            });
        }
    }

    // ------------------------------------------------------------------
    // What the options panel reads and calls
    // ------------------------------------------------------------------

    // What the options panel reads that lives elsewhere (viewer-panels.js).
    get themeChoices() {
        return Object.entries(THEMES).map(([id, theme]) => ({ id, labelKey: theme.labelKey }));
    }

    get footprintColorIds() {
        return FOOTPRINT_COLOR_IDS;
    }

    get panelFlags() {
        return {
            assemblyPreview: ASSEMBLY_PREVIEW_ENABLED,
            drawingBeta: DRAWING_BETA_ENABLED,
            // Whether the package lets assembly preview be turned on at all (feature-flags.js).
            assemblyPreviewAvailable: Boolean(FEATURE_FLAGS.assemblyPreview),
            // Whether the host runs Kigumi's MCP server; its state is `mcpState`.
            mcpAvailable: INITIAL_PAYLOAD.mcpAvailable === true,
        };
    }

    /** Put what adds Kigumi's MCP server to an agent (a setup id of `mcpState`) on the clipboard. */
    copyMcpSetup(clientId) {
        if (vscode) {
            vscode.postMessage({ type: 'copyMcpSetup', client: clientId });
        }
    }

    /** Turn a beta feature ('assemblyPreview' or 'drawingBeta') on or off: a setting, so the host reloads the views. */
    setBetaFeature(feature, enabled) {
        if (vscode) {
            vscode.postMessage({ type: 'setBetaFeature', feature, enabled: Boolean(enabled) });
        }
    }

    setDebugEnabled(enabled) {
        this.debugEnabled = Boolean(enabled);
        const debugEl = this.renderRoot.querySelector('#debug');
        if (debugEl) {
            debugEl.style.display = this.debugEnabled ? 'block' : 'none';
        }
    }

    saveViewerSettings() {
        if (vscode) {
            vscode.postMessage({ type: 'requestSaveViewerSettings', settings: this.collectViewerSettingsPayload() });
        }
    }

    exportFiles() {
        if (vscode) {
            vscode.postMessage({
                type: 'requestExportFiles',
                formats: this.getSelectedExportFormats(),
                includeCombined: this.exportCombinedEnabled,
                includeIndividuals: this.exportIndividualsEnabled,
                includeAccessories: this.exportAccessoriesEnabled,
            });
        }
    }

    installCadqueryOcp() {
        if (vscode) {
            vscode.postMessage({ type: 'requestInstallCadqueryOcp' });
        }
    }

    /** Select members, as a click on each would (the member list's rows). */
    selectMembers(memberKeys, additive) {
        const keys = (Array.isArray(memberKeys) ? memberKeys : []).filter((key) => this.sceneManager.has(key));
        this._dropCsgFocus();
        if (!additive) {
            this.selectionManager.clearTimberSelection();
        }
        for (const key of keys) {
            if (additive) this.selectionManager.toggleTimber(key);
            else this.selectionManager.selectTimber(key, true);
        }
    }

    /** What this view shows and what is selected in it, for an agent asking. See agent/panel-directory.js. */
    describePanel() {
        const scene = this.sceneStore.activeScene();
        const counts = (this.currentFrameData || {});
        return {
            kind: 'viewer',
            frameName: counts.name || null,
            view: this.isInDrawing ? 'drawing' : '3d',
            drawing: this.isInDrawing ? { id: scene.id, name: scene.name || scene.id } : null,
            timberCount: Number.isFinite(counts.timber_count) ? counts.timber_count : null,
            selection: this.selectionPanel.selectionForCopy(),
        };
    }

    handleGetCameraStateRequest(message) {
        this.respondToRequest(
            message,
            'getCameraStateResult',
            () => this.buildCameraStatePayload(),
            'Failed to read camera state',
        );
    }

    handleSetCameraStateRequest(message) {
        this.respondToRequest(
            message,
            'setCameraStateResult',
            () => {
                const cameraState = message && message.cameraState && typeof message.cameraState === 'object'
                    ? message.cameraState
                    : {};
                this.cameraController.applyStatePayload(cameraState);
                this.requestUpdate();
                this.updateCamera();
                return this.buildCameraStatePayload();
            },
            'Failed to set camera state',
        );
    }

    // ------------------------------------------------------------------
    // Window events: pointer, keyboard, resize; picking along a ray
    // ------------------------------------------------------------------

    onWindowScroll() {
        const toV3d = this.renderRoot.querySelector('#to-v3d');
        toV3d.style.display = window.scrollY > 260 ? 'block' : 'none';
    }

    onWindowMouseUp(event) {
        const finished = this.pointerDrag.end();
        const activeMouseAction = finished.action;
        const mouseDownButton = finished.button;
        const mouseDownTarget = finished.target;
        const mouseActionMoved = finished.moved;
        const canvas = this.renderRoot && this.renderRoot.querySelector ? this.renderRoot.querySelector('#c') : null;
        if (activeMouseAction === 'orbit' && mouseActionMoved) {
            // A tilted elevation goes back to its declared angle; a free orbit
            // stays where it was let go.
            this.releaseTilt();
        }
        if (!activeMouseAction && canvas && event.target === canvas) {
            this.handleCanvasClick(event);
            return;
        }
        if (
            activeMouseAction === 'orbit'
            && mouseDownButton === 0
            && mouseDownTarget === canvas
            && !mouseActionMoved
        ) {
            this.handleCanvasClick(event);
            return;
        }
        // Right button released without dragging (mousedown always starts an 'orbit'
        // drag for button 2 -- see the canvas mousedown handler -- so this is the only
        // way to tell a right-click from a right-drag-to-orbit): open the context menu
        // for whatever member is under the cursor, if any.
        if (
            activeMouseAction === 'orbit'
            && mouseDownButton === 2
            && mouseDownTarget === canvas
            && !mouseActionMoved
        ) {
            // While a feature is under the pointer, the useful question is
            // which feature you meant -- the same choice Tab steps through,
            // said out loud, since a face seen edge-on is never the best answer
            // where it lies and there is no reason to expect it is on offer.
            // Exporting the member is the answer when there is no such choice.
            if (!this.showFeatureContextMenu(event.clientX, event.clientY)) {
                const found = this._findMemberAtClientPoint(event.clientX, event.clientY);
                if (found) {
                    this.showMemberContextMenu(found.memberKey, event.clientX, event.clientY);
                }
            }
        }
    }

    onWindowMouseMove(event) {
        const drag = this.pointerDrag.move({ x: event.clientX, y: event.clientY });
        if (!drag) {
            return;
        }
        if (drag.action === 'orbit') {
            this.orbitActiveViewport(drag.dx, drag.dy);
        } else if (drag.action === 'pan') {
            if (this.activePage) {
                this.panPageBy(drag.toX - drag.fromX, drag.toY - drag.fromY);
            } else {
                this.panCameraInViewPlane(drag.fromX, drag.fromY, drag.toX, drag.toY);
            }
        }
        this.cameraController.cancelAnimation();
        this.updateCamera();
    }

    /** Shift pressed or released: the selection mode may have changed, so ask the hover again. */
    _setShiftHeld(held) {
        if (this._shiftHeld === held) {
            return;
        }
        this._shiftHeld = held;
        // A hover that found nothing to light has forgotten where it was, so it is
        // given the pointer again rather than asked again.
        if (this._hover && !this._hover.askAgain() && this._lastClientX !== undefined) {
            this._hover.pointerAt(this._lastClientX, this._lastClientY);
        }
    }

    onWindowKeyUp(event) {
        if (event.key === 'Shift') {
            this._setShiftHeld(false);
        }
    }

    /** A key released while the window is away is never heard, so let go of shift here. */
    onWindowBlur() {
        this._setShiftHeld(false);
    }

    onWindowKeyDown(event) {
        if (event.key === 'Shift') {
            this._setShiftHeld(true);
        }
        // Tab is checked BEFORE the defaultPrevented guard: it is the focus key,
        // so something else may well have claimed it, and this only acts while
        // the pointer is over a feature -- which is not a moment anyone is
        // tabbing between controls. The comment said this while the code did
        // the opposite, which disabled cycling wherever anything took Tab.
        if (event.key === 'Tab' && this._hover && this._hover.feature) {
            // A face seen edge-on is never the best answer where it lies -- the
            // edge formed with it wins, being the more specific one -- so
            // without this it cannot be reached at all. In an elevation it is
            // the face you most often want to measure to.
            event.preventDefault();
            const count = Math.max(1, this._hover.feature.candidateCount || 1);
            const index = this._hover.cycle(count);
            this.emitViewerLog('measure-cycle', {
                index, of: count,
                from: this._hover.feature.featureLabel,
            });
            // The place did not change, the question did: ask the same point
            // again so the hover shows what the next click would now take.
            this._hover.askAgain();
            return;
        }
        // Nothing below belongs to whatever has the caret. Delete in a search
        // box deletes text, and ctrl-Z there undoes typing -- taking those
        // would be the viewer reaching into a control it does not own.
        if (_isTypingTarget(event.target)) {
            return;
        }
        // Undo and redo are settled BEFORE the defaultPrevented guard, for the
        // same reason Tab is: the host claims them. VS Code forwards key events
        // from a webview to its own keybindings and marks ctrl-Z handled on the
        // way through, so by the time this listener runs the event is already
        // prevented -- and the guard below turned undo away every time, which
        // is exactly what "ctrl-Z does nothing" was. While the viewer has focus
        // and the caret is not in a control, these are the viewer's keys.
        //
        // They act on the drawing in front of you, which is what they are keyed
        // by. Refused while a measurement is half-made: there is nothing on the
        // stack for it, so undo would reach past the thing you are looking at
        // to something you are not.
        const accel = event.metaKey || event.ctrlKey;
        if (accel && (event.key === 'z' || event.key === 'Z')) {
            event.preventDefault();
            if (event.shiftKey) {
                this.redoMeasurementChange();
            } else {
                this.undoMeasurementChange();
            }
            return;
        }
        if (accel && (event.key === 'y' || event.key === 'Y')) {
            event.preventDefault();
            this.redoMeasurementChange();
            return;
        }
        if (event.defaultPrevented) {
            return;
        }
        if (event.key === 'Delete' || event.key === 'Backspace') {
            // Nothing to delete is not an error: a measurement the code asks
            // for is passed over, and the key simply does nothing.
            if (this.deleteMarkedMeasurements()) {
                event.preventDefault();
            }
            return;
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            if (this.contextMenu.isOpen) {
                this.closeMemberContextMenu();
            } else if (this.escapeMeasurement()) {
                // One end at a time, so leaving a half-made measurement takes
                // two presses: the second feature, then the first.
            } else if (this.selectionManager.csgFocus) {
                this._dropCsgFocus();
            } else {
                this.selectionManager.clearTimberSelection();
            }
            return;
        }
        if ((event.key === 'm' || event.key === 'M') && !accel && !event.altKey) {
            // Measure from this: the same as the button, when it would be offered.
            if (!this.measureDraft.isActive && this.canStartMeasurement) {
                event.preventDefault();
                this.startMeasurementFromFocus();
            }
            return;
        }
        if (event.key !== 'f' && event.key !== 'F') {
            return;
        }
        const activeTag = document.activeElement && document.activeElement.tagName;
        if (activeTag === 'INPUT' || activeTag === 'TEXTAREA') {
            return;
        }
        event.preventDefault();
        this.focusSelection();
    }

    onWindowResize() {
        const viewport = this.renderRoot.querySelector('#viewport');
        const width = viewport.offsetWidth;
        const height = viewport.offsetHeight;
        this.syncCameraProjection();
        this.renderer.setSize(width, height, false);
        if (this.cameraCube) {
            this.cameraCube.resize();
        }
        this.drawLightDial();
        // Fat-line (LineMaterial) edges compute their pixel thickness from
        // this resolution uniform -- keep it in sync or edges get thinner or
        // thicker than their configured linewidth as the viewport resizes.
        const resolution = this._getRendererResolution();
        for (const bundle of this.sceneManager.bundles()) {
            if (bundle.edges && bundle.edges.material) {
                bundle.edges.material.resolution = resolution;
            }
        }
        if (this.drawingOverlays) {
            this.drawingOverlays.setResolution(resolution);
        }
        // Every overlay, not only the selection's: the hover and held lines
        // had their own fields and were missed here, so they went thin on a
        // resize until something happened to rebuild them.
        for (const object of this._highlightObjects.values()) {
            if (object.material && object.material.resolution) {
                object.material.resolution = resolution;
            }
        }
    }

    // Raycasts from a client (screen) point and returns every visible, unlocked
    // member hit, nearest first. Shared by left-click selection and the
    // right-click context menu so both use identical hit-testing.
    /**
     * The viewport a screen point is over, and where it is within it.
     *
     * Null when the point is off the canvas, or in a gap between viewports.
     */
    _resolvePointer(clientX, clientY) {
        return this._resolvePointers(clientX, clientY)[0] || null;
    }

    /** Every viewport under a screen point, topmost first. */
    _resolvePointers(clientX, clientY) {
        const canvas = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#c')
            : null;
        if (!canvas) {
            return [];
        }
        const rect = canvas.getBoundingClientRect();
        if (clientX < rect.left || clientX > rect.right
            || clientY < rect.top || clientY > rect.bottom) {
            return [];
        }
        return resolvePointers(
            this.viewports,
            clientX - rect.left,
            clientY - rect.top,
            this.pageScreenRect(rect.width, rect.height),
        );
    }

    /** Make the viewport under a point the one the camera controls act on. */
    focusViewportAt(clientX, clientY) {
        const resolved = this._resolvePointer(clientX, clientY);
        if (resolved) {
            this.activeViewportId = resolved.viewport.id;
        }
        return resolved;
    }

    _findMembersAlongRay(clientX, clientY) {
        // A drawing's context timbers are not pickable: they are there to place
        // the piece, and clicking through to one would select something the
        // sheet is not about and cannot measure.
        const drawnMembers = this.activeSceneMembers;
        const isPickable = (memberKey) => !this.isMemberHidden(memberKey)
            && !this.isMemberLocked(memberKey)
            && (!drawnMembers || drawnMembers.has(memberKey));
        // Ask each viewport under the pointer in turn, topmost first, and take
        // the first that actually hits something. A drawing's viewports draw on
        // nothing, so where the one on top is empty you are looking straight
        // through it at the one beneath, and that is what the click means.
        // Through the topmost viewport when nothing is hit: a drawing still looks along that ray,
        // for features near it on no surface (choosePickAction, alongRay).
        let missed = null;
        for (const resolved of this._resolvePointers(clientX, clientY)) {
            // Through that viewport's own camera: the same screen point means
            // different things in each of a drawing's views.
            this.navigationPointer.set(resolved.ndc.x, resolved.ndc.y);
            this.navigationRaycaster.setFromCamera(this.navigationPointer, resolved.viewport.camera);
            const hits = this.sceneManager.memberAtRay(this.navigationRaycaster, { isPickable });
            if (!missed) {
                missed = {
                    hits: [],
                    camera: resolved.viewport.camera,
                    viewHeight: resolved.pixelHeight,
                    ray: {
                        origin: this.navigationRaycaster.ray.origin.toArray(),
                        direction: this.navigationRaycaster.ray.direction.clone().normalize().toArray(),
                    },
                };
            }
            if (hits.length > 0) {
                // The camera travels with the hits, and is not looked up again
                // later. A sheet has several viewports at different scales, and
                // the one the ray went through is not always the one the reader
                // last clicked in -- pick tolerances read from the active
                // viewport instead of this one were computed at the wrong scale
                // for every hover that had not been clicked in first.
                //
                // So does the RAY, copied out because the raycaster is reused
                // on the next pointer move. A hit point is on a surface, and a
                // feature in the void -- a bore's axis -- is nowhere near any
                // surface, so the runner needs the line the pointer went along
                // to find one at all.
                return {
                    hits,
                    camera: resolved.viewport.camera,
                    // How high that viewport is drawn: what a pixel of slack is measured against.
                    viewHeight: resolved.pixelHeight,
                    ray: {
                        origin: this.navigationRaycaster.ray.origin.toArray(),
                        direction: this.navigationRaycaster.ray.direction.clone().normalize().toArray(),
                    },
                };
            }
        }
        return missed || { hits: [], camera: this.camera, ray: null };
    }

    // The closest visible, unlocked member hit, or null. Used where only the
    // frontmost thing matters, such as the right-click context menu.
    _findMemberAtClientPoint(clientX, clientY) {
        return this._findMembersAlongRay(clientX, clientY).hits[0] || null;
    }

    /** Drop the CSG focus and everything that hangs off it. */
    _dropCsgFocus() {
        this.selectionManager.clearCsgFocus();
        this.lastPickDetail = null;
        this._csgHighlightSource = null;
    }

    // ------------------------------------------------------------------
    // Units
    // ------------------------------------------------------------------

    /** A length in metres, in whichever units the viewer is set to. */
    fmt(value) {
        return KigumiUnits.formatLength(value, this.units, this.unitPrecision());
    }

    unitSystem() {
        return this.units || KigumiUnits.DEFAULT_UNIT_SYSTEM;
    }

    /** What lengths are read to in the units the viewer is set to. */
    unitPrecision() {
        return this.displayOptions.get(`${this.unitSystem()}Precision`);
    }

    setUnits(units) {
        if (!this.displayOptions.set('units', units)) {
            return;
        }
        this.onLengthFormatChanged();
    }

    setUnitPrecision(precision, system = this.unitSystem()) {
        if (!this.displayOptions.set(`${system}Precision`, precision)) {
            return;
        }
        this.onLengthFormatChanged();
    }

    /** Redraw everything that has a length written on it. */
    onLengthFormatChanged() {
        this.kiwariSections = (this.kiwariSections || []).map(
            (state) => KigumiKiwariValues.withUnits(state, this.unitSystem()));
        this.memberListPanel.refresh();
        this.selectionPanel.updateInfo(this.currentFrameData);
        this.renderMeasurements();
        this._syncDrawingPanel();
        this.requestUpdate();
    }

    // ------------------------------------------------------------------
    // After each render
    // ------------------------------------------------------------------

    // The webview CSP blocks inline style attributes (style-src has no
    // 'unsafe-inline'), so lit style= bindings never reach the DOM. Setting
    // properties through the CSSOM is allowed: marks carry their position in
    // data-left and get placed here after every render.
    updated() {
        this.sidebar.sync(this);
        this.querySelectorAll('.assembly-timeline-mark[data-left]').forEach((mark) => {
            mark.style.left = `${mark.dataset.left}%`;
        });
        // Positioned via JS rather than a lit `style="..."` attribute binding: the webview's
        // CSP (style-src, no 'unsafe-inline') silently drops inline style attributes, but
        // script-driven element.style assignment is unaffected -- same reason the assembly
        // timeline marks above are positioned this way instead.
        const menu = this.querySelector('#member-context-menu');
        if (menu) {
            const at = window.KigumiContextMenu.menuPosition(
                { x: Number(menu.dataset.x), y: Number(menu.dataset.y) },
                { width: menu.offsetWidth, height: menu.offsetHeight },
                { width: window.innerWidth, height: window.innerHeight },
            );
            menu.style.left = `${at.x}px`;
            menu.style.top = `${at.y}px`;
        }
    }

    // ------------------------------------------------------------------
    // Pointer gestures
    // ------------------------------------------------------------------

    /**
     * Run a pointer gesture, owning its listeners for as long as it lasts.
     *
     * They go up when it starts and come down when it ends, in ONE place -- and
     * because the gesture has a name, teardown can end it. The measurement drag
     * put its handlers up as closures, which disconnectedCallback could not
     * name and so could not take down: leaving the viewer with the mouse still
     * held leaked both, holding the whole app with them.
     *
     * Only for gestures whose listeners live as long as the drag. The gizmo and
     * the light dial keep theirs for the life of the viewer and check a flag,
     * which has no pairing to get wrong and is left alone.
     */
    _beginPointerGesture(name, { onMove, onEnd }) {
        this._endPointerGesture(name);
        const move = (event) => onMove(event);
        const up = (event) => {
            // Taken down BEFORE the handler runs, so an end that throws still
            // leaves nothing listening.
            this._endPointerGesture(name);
            if (onEnd) {
                onEnd(event);
            }
        };
        this._pointerGestures.set(name, { move, up });
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', up);
    }

    /** Stop listening for one, whether or not it is running. */
    _endPointerGesture(name) {
        const gesture = this._pointerGestures.get(name);
        if (!gesture) {
            return false;
        }
        window.removeEventListener('pointermove', gesture.move);
        window.removeEventListener('pointerup', gesture.up);
        this._pointerGestures.delete(name);
        return true;
    }

    /** Leaving: nothing should still be listening for a pointer. */
    _endAllPointerGestures() {
        for (const name of Array.from(this._pointerGestures.keys())) {
            this._endPointerGesture(name);
        }
    }

    // ------------------------------------------------------------------
    // CSG trees: fetched here (the vscode channel lives in this component),
    // rendered by the layers panel.
    // ------------------------------------------------------------------

    /** The layers panel expanded a row and needs that timber's tree. */
    onCsgTreeRequested(event) {
        const detail = (event && event.detail) || {};
        this.requestCsgTree(detail.memberKey);
    }

    /** A CSG row was clicked; ask the runner to highlight it in 3D. */
    onCsgByPathRequested(event) {
        const detail = (event && event.detail) || {};
        if (!detail.memberKey || typeof vscode === 'undefined') {
            return;
        }
        vscode.postMessage({
            type: 'requestCSGByPath',
            memberKey: detail.memberKey,
            path: detail.path || [],
        });
    }

    /** Ask the runner for a timber's tree, once per timber. */
    requestCsgTree(memberKey) {
        if (!memberKey || this.csgTreesByKey.has(memberKey) || this.csgTreeRequests.has(memberKey)) {
            return;
        }
        this.csgTreeRequests.add(memberKey);
        if (typeof vscode !== 'undefined') {
            vscode.postMessage({ type: 'requestCSGTree', memberKey });
        }
    }

    /** Which cutting a pick landed on, or null if its tree is not in yet. */
    _cutIndexForPick(timberKey, path) {
        const payload = this.csgTreesByKey.get(timberKey);
        if (!payload) {
            return null;
        }
        return CsgTreeView.cutIndexForPath(payload, path);
    }

    /**
     * Show the focused node in the list, fetching the tree first if need be.
     * A pick can land before its tree arrives, in which case onCsgTreeArrived
     * finishes the job.
     */
    _revealCsgFocusInList(target, path) {
        this.requestCsgTree(target.timberKey);
        const view = this._layersView;
        if (view && typeof view.revealCsg === 'function') {
            view.revealCsg({ ...target, path });
        }
    }

    /** A requested tree came back. */
    onCsgTreeArrived(payload) {
        const memberKey = payload && payload.memberKey;
        if (!memberKey) {
            return;
        }
        this.csgTreeRequests.delete(memberKey);
        this.csgTreesByKey.set(memberKey, payload);

        const view = this._layersView;
        if (view && typeof view.setCsgTree === 'function') {
            view.setCsgTree(memberKey, payload);
        }

        // A pick that arrived before its tree could not work out its cutting,
        // and so could not be revealed. Now it can.
        const focus = this.selectionManager.csgFocus;
        if (focus && focus.timberKey === memberKey && focus.cutIndex === null) {
            const cutIndex = CsgTreeView.cutIndexForPath(payload, focus.path);
            if (cutIndex !== null) {
                focus.cutIndex = cutIndex;
            }
            const target = CsgTreeView.revealTarget(focus, { timberKey: memberKey, cutIndex });
            this._revealCsgFocusInList(target, focus.path);
        }
    }

    // ------------------------------------------------------------------
    // Debug info, loading the scene, and applying a payload
    // ------------------------------------------------------------------

    updateDebug(geometryData, profiling) {
        const meshes = (geometryData && geometryData.meshes) ? geometryData.meshes : [];
        const changedKeys = (geometryData && geometryData.changedKeys) ? geometryData.changedKeys : [];
        const removedKeys = (geometryData && geometryData.removedKeys) ? geometryData.removedKeys : [];
        const remeshMetrics = (geometryData && geometryData.remeshMetrics) ? geometryData.remeshMetrics : [];
        const rebuilt = changedKeys.length;
        const removed = removedKeys.length;
        const total = meshes.length;
        const reused = Math.max(0, total - rebuilt);

        let profilingHtml = '';
        if (profiling) {
            const parts = [];
            const timingBreakdown = profiling.timing && profiling.timing.breakdown_ms
                ? profiling.timing.breakdown_ms
                : null;
            if (typeof profiling.reload_s === 'number') {
                parts.push('refresh: ' + (profiling.reload_s * 1000).toFixed(0) + ' ms');
            }
            if (timingBreakdown && typeof timingBreakdown.frame_request === 'number') {
                parts.push('frame: ' + timingBreakdown.frame_request.toFixed(0) + ' ms');
            }
            if (typeof profiling.geometry_s === 'number') {
                parts.push('mesh (python): ' + (profiling.geometry_s * 1000).toFixed(0) + ' ms');
            }
            if (typeof profiling.webview_mesh_ms === 'number' && profiling.webview_mesh_ms > 0) {
                parts.push('mesh (three.js): ' + profiling.webview_mesh_ms.toFixed(0) + ' ms');
            }
            if (typeof profiling.refresh_total_s === 'number') {
                parts.push('total (extension): ' + (profiling.refresh_total_s * 1000).toFixed(0) + ' ms');
            }
            if (typeof profiling.webview_apply_ms === 'number') {
                parts.push('total (webview): ' + profiling.webview_apply_ms.toFixed(0) + ' ms');
            }

            if (parts.length > 0) {
                profilingHtml = '<br><strong>Profiling</strong><br>' + parts.join('<br>');
            }
        }

        let remeshHtml = '';
        if (remeshMetrics.length > 0) {
            const totalRemeshMs = remeshMetrics.reduce((sum, metric) => {
                if (typeof metric.remesh_s === 'number') {
                    return sum + metric.remesh_s * 1000;
                }
                return sum;
            }, 0);
            const maxCsgDepth = remeshMetrics.reduce((maxDepth, metric) => {
                if (typeof metric.csg_depth === 'number') {
                    return Math.max(maxDepth, metric.csg_depth);
                }
                return maxDepth;
            }, 0);
            remeshHtml = '<br><strong>Changed Timber Remesh</strong><br>' +
                'entries: ' + remeshMetrics.length + '<br>' +
                'remesh total: ' + totalRemeshMs.toFixed(0) + ' ms<br>' +
                'max CSG depth: ' + maxCsgDepth;
        }

        let milestonesHtml = '';
        if (profiling && Array.isArray(profiling.milestones) && profiling.milestones.length > 0) {
            milestonesHtml = '<br><strong>Script Milestones</strong><br>';
            for (const m of profiling.milestones) {
                const elapsed = typeof m.elapsed_ms === 'number' ? m.elapsed_ms.toFixed(0) : '?';
                const delta = typeof m.delta_ms === 'number' ? m.delta_ms.toFixed(0) : '?';
                milestonesHtml += m.name + ': ' + elapsed + ' ms (+' + delta + ' ms)<br>';
            }
        }

        this.renderRoot.querySelector('#debug').innerHTML =
            '<strong>Refresh Debug</strong><br>' +
            'total: ' + total + '<br>' +
            'rebuilt: ' + rebuilt + '<br>' +
            'reused: ' + reused + '<br>' +
            'removed: ' + removed +
            remeshHtml +
            milestonesHtml +
            profilingHtml;
    }

    async updateMeshScene(geometryData, refreshToken, onProgress) {
        // Cache the last geometry payload so we can re-run mesh building when the
        // user toggles geometryMode without round-tripping to Python.
        this._lastGeometryData = geometryData;
        const meshes = (geometryData && geometryData.meshes) ? geometryData.meshes : [];
        const geometryMode = (this.viewerOptions && this.viewerOptions.geometryMode) || 'actual';
        const total = meshes.length;
        let processed = 0;
        const nextKeys = new Set();
        let meshBuildMs = 0;

        const reportProgress = () => {
            if (typeof onProgress === 'function') {
                onProgress(processed, total);
            }
        };

        reportProgress();

        for (let index = 0; index < meshes.length; index += 1) {
            if (this.isRefreshStale(refreshToken)) {
                return false;
            }
            const mesh = meshes[index];
            const key = mesh.memberKey || mesh.timberKey || ('index-' + index);
            const memberType = mesh.memberType === 'accessory' ? 'accessory' : 'timber';
            const memberName = mesh.memberName || mesh.name || key;
            nextKeys.add(key);

            if (this.sceneManager.has(key)) {
                this.memberMetadataByKey.delete(key);
                this.sceneManager.disposeMember(key);
            }

            const meshT0 = performance.now();
            // Choose vertex/index arrays based on geometryMode. Accessories and
            // perfect timbers (which lack the alternate-mode payload fields) fall
            // back to the actual vertices/indices regardless of mode.
            const { vertices: vertexSource, indices: indexSource } = GeometryMode.selectMeshBuffers(mesh, memberType, geometryMode);
            const positions = new Float32Array(vertexSource);
            const indexedGeometry = new THREE.BufferGeometry();
            indexedGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
            indexedGeometry.setIndex(indexSource);

            const geometry = indexedGeometry.toNonIndexed();
            geometry.computeVertexNormals();
            geometry.computeBoundingSphere();
            indexedGeometry.dispose();

            const materialSet = this.createMaterialSetForMemberType(memberType);

            const solidMesh = new THREE.Mesh(geometry, materialSet.solid);
            // EdgesGeometry gives a flat, non-indexed position array (every
            // consecutive pair of vertices is one segment) -- exactly what
            // LineSegmentsGeometry.setPositions() expects, so it's used here
            // purely as a way to compute the sharp/boundary edge positions,
            // then thrown away in favor of the fat-line (LineSegments2)
            // geometry that actually gets rendered (supports real linewidth,
            // unlike plain THREE.LineSegments/LineBasicMaterial).
            const edgesSource = new THREE.EdgesGeometry(geometry, 25);
            const edgeGeometry = new THREE.LineSegmentsGeometry();
            edgeGeometry.setPositions(edgesSource.attributes.position.array);
            edgesSource.dispose();
            const edgeMesh = new THREE.LineSegments2(edgeGeometry, materialSet.edge);
            edgeMesh.computeLineDistances();
            const reflectionMesh = new THREE.Mesh(geometry, materialSet.reflection);
            solidMesh.renderOrder = 1;
            edgeMesh.renderOrder = 10;
            reflectionMesh.renderOrder = 0;
            solidMesh.castShadow = true;
            solidMesh.receiveShadow = true;
            edgeMesh.visible = this.edgeMode !== 'none';
            reflectionMesh.castShadow = false;
            reflectionMesh.receiveShadow = false;
            reflectionMesh.visible = false;   // applyRenderMode decides, next frame

            // Round accessories (pegs, dowels, ...) come with cylinderAxis: their
            // barrel is a faceted polygon under the hood, so EdgesGeometry's fixed
            // angle threshold above never catches the curved side (only the flat
            // end caps). Add the two true, camera-facing tangent lines instead,
            // parented under edgeMesh so they inherit its visibility/offset for
            // free; updateCylinderSilhouettes() recomputes them every frame.
            let cylinderSilhouette = null;
            if (mesh.cylinderAxis) {
                const axisStart = new THREE.Vector3(...mesh.cylinderAxis.axisStart);
                const axisEnd = new THREE.Vector3(...mesh.cylinderAxis.axisEnd);
                const radius = mesh.cylinderAxis.radius;
                const silhouetteGeometry = new THREE.LineSegmentsGeometry();
                const initialPositions = this._silhouetteLinePositions(axisStart, axisEnd, radius, this.camera.position)
                    || [...axisStart.toArray(), ...axisEnd.toArray(), ...axisStart.toArray(), ...axisEnd.toArray()];
                silhouetteGeometry.setPositions(initialPositions);
                const silhouetteLine = new THREE.LineSegments2(silhouetteGeometry, materialSet.edge);
                silhouetteLine.computeLineDistances();
                edgeMesh.add(silhouetteLine);
                cylinderSilhouette = { axisStart, axisEnd, radius, line: silhouetteLine };
            }

            // Parented like the silhouette, so they follow the member's visibility and offset.
            const drawingLines = this.drawingOverlays.linesFor(mesh, key);
            const idMesh = this.memberIds ? this.memberIds.attach(key, solidMesh) : null;
            for (const line of drawingLines) {
                edgeMesh.add(line.object);
            }

            this.scene.add(solidMesh);
            this.scene.add(edgeMesh);
            this.scene.add(reflectionMesh);
            this.memberMetadataByKey.set(key, {
                name: memberName,
                type: memberType,
                tags: KigumiTags.coerceTags(mesh.tags),
                mesh,
            });
            this.sceneManager.register(key, {
                memberType,
                profileId: materialSet.profileId,
                mesh: solidMesh,
                edges: edgeMesh,
                reflection: reflectionMesh,
                cylinderSilhouette,
                drawingLines,
                idMesh,
            });
            meshBuildMs += performance.now() - meshT0;
            processed += 1;
            reportProgress();
            if (index === 0 || index === meshes.length - 1 || index % 8 === 0) {
                await this.waitForNextPaint();
                if (this.isRefreshStale(refreshToken)) {
                    return false;
                }
            }
        }

        for (const existingKey of Array.from(this.sceneManager.keys())) {
            if (!nextKeys.has(existingKey)) {
                this.memberMetadataByKey.delete(existingKey);
                this.sceneManager.disposeMember(existingKey);
            }
        }

        this.rebuildFootprints(geometryData && geometryData.footprints);
        this.memberListPanel.rebuild(meshes);
        this.updateReflectionTransforms();
        // Rebuilt meshes come in at the origin; re-seat them at the current
        // scrub position so the assembly preview survives geometry refreshes.
        this.applyAssemblyOffsets();
        this._lastMeshBuildMs = meshBuildMs;
        return true;
    }

    normalizeUiState(uiState) {
        const next = uiState && typeof uiState === 'object' ? uiState : {};
        const phase = typeof next.phase === 'string' && next.phase
            ? next.phase
            : ViewerPhase.WAITING_FOR_RUNNER;
        const loadingText = typeof next.loadingText === 'string' && next.loadingText
            ? next.loadingText
            : this.defaultLoadingTextForPhase(phase);
        const refreshToken = Number.isFinite(next.refreshToken)
            ? next.refreshToken
            : this.activeRefreshToken;
        const error = typeof next.error === 'string' && next.error ? next.error : null;
        const showOutputLink = Boolean(next.showOutputLink);
        const sourceHasPendingChanges = Boolean(next.sourceHasPendingChanges);

        return {
            phase,
            loadingText,
            refreshToken,
            error,
            showOutputLink,
            sourceHasPendingChanges,
            keepLoading: Boolean(next.keepLoading),
        };
    }

    defaultLoadingTextForPhase(phase) {
        if (phase === ViewerPhase.BOOTING) {
            return t('viewer.chrome.loading.startingViewer');
        }
        if (phase === ViewerPhase.WAITING_FOR_RUNNER) {
            return t('viewer.chrome.loading.raisingFrame');
        }
        if (phase === ViewerPhase.APPLYING_GEOMETRY) {
            return t('viewer.chrome.loading.cuttingJoints', { processed: 0, total: 0 });
        }
        if (phase === ViewerPhase.ERROR) {
            return t('viewer.chrome.loading.viewerError');
        }
        return '';
    }

    isOverlayVisible() {
        return this.viewState.phase !== ViewerPhase.READY;
    }

    overlayClasses() {
        return [
            this.isOverlayVisible() ? 'visible' : '',
            this.viewState.phase === ViewerPhase.ERROR ? 'error' : '',
        ].filter(Boolean).join(' ');
    }

    setViewState(nextPartial) {
        this.viewState = {
            ...this.viewState,
            ...nextPartial,
        };
        // The overlay is bound in the template. viewState is a plain field, so
        // it schedules nothing on its own -- ask for a render rather than
        // pushing the values into the DOM by hand. Writing textContent over a
        // binding removes the markers Lit updates through, and every later
        // render of that part throws on the detached node.
        this.requestUpdate();
    }

    setViewPhase(phase, loadingText = null, extra = {}) {
        this.setViewState({
            phase,
            loadingText: loadingText || this.defaultLoadingTextForPhase(phase),
            ...extra,
        });
    }

    beginPayloadApplication(payload) {
        if (payload && Object.prototype.hasOwnProperty.call(payload, 'viewerOptions')) {
            this.setViewerOptions(payload.viewerOptions || null);
        }
        const uiState = this.normalizeUiState(payload && payload.uiState ? payload.uiState : null);
        const refreshToken = Number.isFinite(uiState.refreshToken)
            ? uiState.refreshToken
            : this.activeRefreshToken + 1;
        this.activeRefreshToken = Math.max(this.activeRefreshToken, refreshToken);
        return this.applyPayload(payload, refreshToken);
    }

    isRefreshStale(refreshToken) {
        return refreshToken !== this.activeRefreshToken;
    }

    /**
     * Yield until the next paint, or until a short timer fires -- whichever
     * comes first.
     *
     * requestAnimationFrame stops firing while the window is unfocused or the
     * panel is hidden, and this is awaited in a loop while geometry is applied
     * and again before a screenshot, so waiting on a frame alone lets an
     * unfocused window stall a frame load or a capture indefinitely.
     *
     * Concretely, this is what lets you alt-tab away from the extension-host
     * window while the automation tests run. Without the fallback those tests
     * hang for as long as the window is in the background -- the frame never
     * finishes loading and the capture never returns -- which reads as a flaky
     * suite rather than as the suspended-paint problem it is.
     *
     * The timer yields to the event loop the same way, without waiting for a
     * paint that may never come; when paints are happening it always wins the
     * race, so the healthy path is unchanged.
     */
    waitForNextPaint() {
        return new Promise((resolve) => {
            let settled = false;
            const finish = () => {
                if (settled) {
                    return;
                }
                settled = true;
                resolve();
            };
            requestAnimationFrame(() => {
                requestAnimationFrame(finish);
            });
            setTimeout(finish, PAINT_WAIT_FALLBACK_MS);
        });
    }

    getSceneBounds() {
        const acc = createBoundsAccumulator();
        // An iterator, not an array: older webviews have no Iterator.prototype.forEach.
        for (const bundle of this.sceneManager.bundles()) {
            accumulateBounds(acc, bundle.mesh.geometry.getAttribute('position').array);
        }

        if (!acc.hasAny) {
            return { minX: -1, minY: -1, minZ: -1, maxX: 1, maxY: 1, maxZ: 1 };
        }

        return boundsFromAccumulator(acc);
    }

    async applyPayload(payload, refreshToken) {
        const frameData = payload.frame || {};
        const geometryData = payload.geometry || { meshes: [] };
        const profiling = payload.profiling || null;
        const uiState = this.normalizeUiState(payload.uiState || null);
        const hadExistingScene = this.sceneManager.size > 0;

        this.setKiwariFromFrame(frameData);

        if (uiState.keepLoading) {
            this.setViewPhase(uiState.phase, uiState.loadingText, { refreshToken, error: uiState.error });
            this.selectionPanel.updateInfo(frameData);
            this.updateDebug(geometryData, profiling);
            this.renderRoot.querySelector('#raw-output').textContent = JSON.stringify({
                frame: frameData,
                geometry: geometryData,
            }, null, 2);
            return;
        }

        this.setViewPhase(ViewerPhase.APPLYING_GEOMETRY, uiState.loadingText || t('viewer.chrome.loading.raisingFrame'), {
            refreshToken,
            error: null,
        });
        await this.waitForNextPaint();
        if (this.isRefreshStale(refreshToken)) {
            return;
        }

        this.selectionPanel.updateInfo(frameData);
        const applyStartMs = performance.now();
        const completed = await this.updateMeshScene(geometryData, refreshToken, (processed, total) => {
            this.setViewPhase(ViewerPhase.APPLYING_GEOMETRY, t('viewer.chrome.loading.cuttingJoints', { processed, total }), {
                refreshToken,
                error: null,
            });
        });
        if (!completed || this.isRefreshStale(refreshToken)) {
            return;
        }
        const applyElapsedMs = performance.now() - applyStartMs;
        const enrichedProfiling = profiling
            ? { ...profiling, webview_apply_ms: applyElapsedMs, webview_mesh_ms: this._lastMeshBuildMs || 0 }
            : null;
        this.updateDebug(geometryData, enrichedProfiling);

        this.renderRoot.querySelector('#raw-output').textContent = JSON.stringify({
            frame: frameData,
            geometry: geometryData,
        }, null, 2);

        const bounds = this.getSceneBounds();
        this.lastBounds = bounds;
        this.createOrUpdateShadowCatcher(bounds);
        this.focusedCx = (bounds.minX + bounds.maxX) / 2;
        this.focusedCy = (bounds.minY + bounds.maxY) / 2;
        this.focusedCz = (bounds.minZ + bounds.maxZ) / 2;
        const dx = bounds.maxX - bounds.minX;
        const dy = bounds.maxY - bounds.minY;
        const dz = bounds.maxZ - bounds.minZ;
        const radius = Math.sqrt(dx * dx + dy * dy + dz * dz) / 2 || 5;
        // Who gets framed, and to what -- see firstLoadCameraPlan for the two
        // rules it encodes. Kept out of here because both were broken in ways
        // only a measured render showed.
        const plan = firstLoadCameraPlan(this.viewports.map((viewport) => viewport.spec), {
            center: { x: this.focusedCx, y: this.focusedCy, z: this.focusedCz },
            radius,
            fovDegrees: this.perspectiveCamera.fov,
        });
        this.viewports.forEach((viewport, index) => {
            const entry = plan[index];
            if (!entry) {
                return;
            }
            for (const camera of [viewport.perspectiveCamera, viewport.orthographicCamera]) {
                // An orthographic view sees all along each line wherever the camera sits, and
                // zooming in moves the camera closer -- into the frame, in the end. A near plane
                // ahead of it then cut away what it had passed, and rays started inside it, so
                // only what lay behind could be picked. Behind it instead, as far as far is ahead.
                camera.near = camera.isOrthographicCamera ? -entry.far : entry.near;
                camera.far = entry.far;
                camera.updateProjectionMatrix();
            }
            if (!entry.frame || hadExistingScene) {
                return;
            }
            const controller = viewport.cameraController;
            controller.cx = entry.frame.center.x;
            controller.cy = entry.frame.center.y;
            controller.cz = entry.frame.center.z;
            controller.orbitDist = entry.frame.orbitDist;
        });
        this.lightDistance = Math.max(12, radius * 4);
        this.updateCamera();
        this.updateLightFromAngles();
        this.drawLightDial();
        if (this.isRefreshStale(refreshToken)) {
            return;
        }
        this.setViewPhase(ViewerPhase.READY, '', { refreshToken, error: null });
    }

    // ------------------------------------------------------------------
    // The frame on screen: its key, and once it has loaded
    // ------------------------------------------------------------------



    /**
     * Which loaded frame the undo stacks are keyed by.
     *
     * A counter bumped on every load rather than the file's path, which the
     * viewer is never told. It answers the only question the key has to: a
     * reload is a different frame, so its stacks are different stacks. What a
     * stack holds names features and viewports the reloaded frame may not have,
     * and an undo that cannot be trusted to apply is worse than none.
     */
    get frameKey() {
        return String(this._frameGeneration || 0);
    }

    /** A frame arrived. Whatever could be undone was about the last one. */
    _frameLoaded() {
        this.undoStacks.purgeAll();
        this._frameGeneration = (this._frameGeneration || 0) + 1;
        this._lastPickAnchor = null;
        this.clearMeasureDraft();
    }
}

customElements.define('kigumi-app', KigumiViewerApp);
