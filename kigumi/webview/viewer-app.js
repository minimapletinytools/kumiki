import { LitElement, html } from 'https://unpkg.com/lit@3.2.0/index.js?module';

const ViewerPhase = Object.freeze({
    BOOTING: 'booting',
    WAITING_FOR_RUNNER: 'waiting_for_runner',
    APPLYING_GEOMETRY: 'applying_geometry',
    READY: 'ready',
    ERROR: 'error',
});

function normalizeViewerOptions(viewerOptions) {
    return {};
}

function createInitialViewState() {
    return {
        phase: ViewerPhase.BOOTING,
        loadingText: 'raising frame',
        refreshToken: 0,
        error: null,
    };
}

const INITIAL_PAYLOAD = window.__KIGUMI_INITIAL_PAYLOAD__ || {
    frame: {},
    geometry: { meshes: [] },
    uiState: {
        phase: ViewerPhase.WAITING_FOR_RUNNER,
        loadingText: 'raising frame',
        refreshToken: 0,
    },
    viewerOptions: {},
};
const vscode = typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : null;
const VIEWER_APP_VERSION = '2026.03.17.4';
const SelectionStore = window.SelectionStore;

const RENDER_PROFILES = Object.freeze({
    'timber-default': Object.freeze({
        label: 'Timber Default',
        solidColor: 0xafbccf,
        edgeColor: 0x5d6882,
        reflectionColor: 0xe7edf8,
        roughness: 0.68,
        metalness: 0.02,
        reflectionRoughness: 0.28,
        reflectionMetalness: 0.04,
        edgeOpacity: 0.42,
        reflectionOpacity: 0.14,
    }),
    'timber-warm': Object.freeze({
        label: 'Timber Warm',
        solidColor: 0xc3b08f,
        edgeColor: 0x6b5c49,
        reflectionColor: 0xe7d8c2,
        roughness: 0.73,
        metalness: 0.01,
        reflectionRoughness: 0.31,
        reflectionMetalness: 0.02,
        edgeOpacity: 0.45,
        reflectionOpacity: 0.12,
    }),
    'accessory-cute': Object.freeze({
        label: 'Accessory Cute Tint',
        solidColor: 0xffb3c7,
        edgeColor: 0x994f68,
        reflectionColor: 0xffd9e6,
        roughness: 0.54,
        metalness: 0.03,
        reflectionRoughness: 0.24,
        reflectionMetalness: 0.05,
        edgeOpacity: 0.5,
        reflectionOpacity: 0.17,
    }),
    'accessory-brass': Object.freeze({
        label: 'Accessory Brass',
        solidColor: 0xc8a64d,
        edgeColor: 0x5f4c1f,
        reflectionColor: 0xe8cd80,
        roughness: 0.42,
        metalness: 0.2,
        reflectionRoughness: 0.2,
        reflectionMetalness: 0.24,
        edgeOpacity: 0.48,
        reflectionOpacity: 0.18,
    }),
    'timber-dark': Object.freeze({
        label: 'Timber Dark',
        solidColor: 0x4a5468,
        edgeColor: 0x1c2232,
        reflectionColor: 0x6a7a92,
        roughness: 0.75,
        metalness: 0.03,
        reflectionRoughness: 0.32,
        reflectionMetalness: 0.04,
        edgeOpacity: 0.65,
        reflectionOpacity: 0.10,
    }),
});

const BACKGROUND_PRESETS = Object.freeze({
    'cream': Object.freeze({
        label: 'Cream',
        gradientTop: '#fff8dc',
        gradientBottom: '#ffeef4',
    }),
    'sky': Object.freeze({
        label: 'Sky',
        gradientTop: '#cde4ff',
        gradientBottom: '#e6f2ff',
    }),
    'forest': Object.freeze({
        label: 'Forest Mist',
        gradientTop: '#d4ead0',
        gradientBottom: '#e8f5ea',
    }),
    'warm-white': Object.freeze({
        label: 'Warm White',
        gradientTop: '#fdfaf5',
        gradientBottom: '#f8f4ee',
    }),
    'linen': Object.freeze({
        label: 'Linen',
        gradientTop: '#f5efe0',
        gradientBottom: '#ece6d5',
        pattern: 'linen',
    }),
    'slate': Object.freeze({
        label: 'Slate Night',
        gradientTop: '#1a2030',
        gradientBottom: '#2a3244',
    }),
    'blueprint': Object.freeze({
        label: 'Blueprint',
        gradientTop: '#0e1e3c',
        gradientBottom: '#152a50',
        pattern: 'grid',
    }),
});

if (!SelectionStore) {
    throw new Error('SelectionStore is not loaded. Ensure selection-store.js is included before viewer-app.js.');
}

class ViewerSettingsPanel {
    constructor(app) {
        this.app = app;
    }

    render() {
        return html`
            <section id="render-controls" aria-label="Viewer options">
                <button id="refresh-btn" type="button" title="Reload pattern">↻ refresh</button>
                <label>
                    <input id="center-gizmo-toggle" type="checkbox" ?checked=${this.app.showCenterGizmo}>
                    center gizmo
                </label>
                <label>
                    <input id="edges-toggle" type="checkbox" ?checked=${this.app.edgesEnabled}>
                    edges
                </label>
                <label>
                    <input id="shadows-toggle" type="checkbox" ?checked=${this.app.shadowsEnabled}>
                    shadows
                </label>
                <label>
                    <input id="reflections-toggle" type="checkbox" ?checked=${this.app.reflectionsEnabled}>
                    reflection
                </label>
                <label>
                    <input id="debug-toggle" type="checkbox" ?checked=${this.app.debugEnabled}>
                    debug info
                </label>
                <label>
                    unselected visibility (${100 - this.app.unselectedTransparencyPercent}%)
                    <input
                        id="unselected-transparency-slider"
                        type="range"
                        min="5"
                        max="100"
                        step="5"
                        .value=${String(100 - this.app.unselectedTransparencyPercent)}>
                </label>
                <label>
                    timber profile
                    <select id="timber-profile-select" .value=${this.app.memberRenderProfileByType.timber}>
                        ${Object.entries(this.app.renderProfiles).map(([profileId, profile]) => html`<option value=${profileId}>${profile.label}</option>`)}
                    </select>
                </label>
                <label>
                    accessory profile
                    <select id="accessory-profile-select" .value=${this.app.memberRenderProfileByType.accessory}>
                        ${Object.entries(this.app.renderProfiles).map(([profileId, profile]) => html`<option value=${profileId}>${profile.label}</option>`)}
                    </select>
                </label>
                <label>
                    background
                    <select id="background-select" .value=${this.app.activeBackground}>
                        ${Object.entries(BACKGROUND_PRESETS).map(([bgId, bg]) => html`<option value=${bgId}>${bg.label}</option>`)}
                    </select>
                </label>
            </section>
        `;
    }

    bindEvents(renderRoot) {
        const centerGizmoToggle = renderRoot.querySelector('#center-gizmo-toggle');
        const edgesToggle = renderRoot.querySelector('#edges-toggle');
        const shadowsToggle = renderRoot.querySelector('#shadows-toggle');
        const reflectionsToggle = renderRoot.querySelector('#reflections-toggle');
        const unselectedTransparencySlider = renderRoot.querySelector('#unselected-transparency-slider');
        const debugToggle = renderRoot.querySelector('#debug-toggle');
        const timberProfileSelect = renderRoot.querySelector('#timber-profile-select');
        const accessoryProfileSelect = renderRoot.querySelector('#accessory-profile-select');
        const refreshButton = renderRoot.querySelector('#refresh-btn');
        const backgroundSelect = renderRoot.querySelector('#background-select');

        centerGizmoToggle.addEventListener('change', (event) => {
            this.app.setCenterGizmoEnabled(event.target.checked);
        });

        edgesToggle.addEventListener('change', (event) => {
            this.app.setEdgesEnabled(event.target.checked);
        });

        debugToggle.addEventListener('change', (event) => {
            this.app.debugEnabled = event.target.checked;
            const debugEl = renderRoot.querySelector('#debug');
            if (debugEl) {
                debugEl.style.display = this.app.debugEnabled ? 'block' : 'none';
            }
        });

        shadowsToggle.addEventListener('change', (event) => {
            this.app.setShadowsEnabled(event.target.checked);
        });

        reflectionsToggle.addEventListener('change', (event) => {
            this.app.setReflectionsEnabled(event.target.checked);
        });

        unselectedTransparencySlider.addEventListener('input', (event) => {
            const rawVisibility = Number(event.target.value);
            const normalizedVisibility = Number.isFinite(rawVisibility)
                ? Math.max(5, Math.min(100, Math.round(rawVisibility / 5) * 5))
                : 60;
            this.app.setUnselectedTransparencyPercent(100 - normalizedVisibility);
        });

        timberProfileSelect.addEventListener('change', (event) => {
            this.app.setMemberRenderProfile('timber', event.target.value);
        });

        accessoryProfileSelect.addEventListener('change', (event) => {
            this.app.setMemberRenderProfile('accessory', event.target.value);
        });

        refreshButton.addEventListener('click', () => {
            if (vscode) {
                vscode.postMessage({ type: 'requestRefresh' });
            }
        });

        backgroundSelect.addEventListener('change', (event) => {
            this.app.setBackground(event.target.value);
        });
    }

    syncControls(renderRoot) {
        const unselectedTransparencySlider = renderRoot.querySelector('#unselected-transparency-slider');
        if (unselectedTransparencySlider) {
            unselectedTransparencySlider.value = String(100 - this.app.unselectedTransparencyPercent);
        }
    }
}

class KigumiViewerApp extends LitElement {
    constructor() {
        super();
        this.meshObjectsByKey = new Map();
        this.lastBounds = { minX: -1, minY: -1, minZ: -1, maxX: 1, maxY: 1, maxZ: 1 };

        this.focusedCx = 0;
        this.focusedCy = 0;
        this.focusedCz = 0;
        this.cx = 0;
        this.cy = 0;
        this.cz = 0;
        this.orbitDist = 10;
        this.theta = -Math.PI / 5;
        this.phi = Math.PI / 3;
        this.cameraUpVector = new THREE.Vector3(0, 0, 1);

        this.cameraAnimation = null;

        this.mouseAction = null;
        this.lastX = 0;
        this.lastY = 0;

        this.showCenterGizmo = true;
        this.edgesEnabled = true;
        this.shadowsEnabled = true;
        this.reflectionsEnabled = true;
        this.debugEnabled = false;
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
        this.gizmoRenderer = null;
        this.gizmoScene = null;
        this.gizmoCamera = null;
        this.gizmoCube = null;
        this.gizmoRaycaster = new THREE.Raycaster();
        this.gizmoPointer = new THREE.Vector2();
        this.navigationRaycaster = new THREE.Raycaster();
        this.navigationPointer = new THREE.Vector2();
        this.focalPlane = new THREE.Plane();
        this.tempOrbitCenter = new THREE.Vector3();
        this.tempViewDirection = new THREE.Vector3();
        this.tempPlaneHit = new THREE.Vector3();

        this.sun = null;
        this.shadowCatcher = null;
        this.orbitCenterGizmo = null;

        this.selectionManager = new SelectionStore();
        this._csgHighlightMesh = null;
        this._csgParentHighlightMesh = null;
        this.meshKeyMap = new Map(); // mesh object -> member key
        this.memberMetadataByKey = new Map(); // member key -> { name, type }
        this.renderProfiles = RENDER_PROFILES;
        this.memberRenderProfileByType = {
            timber: 'timber-default',
            accessory: 'accessory-cute',
        };
        this.unselectedTransparencyPercent = 40;
        this.activeBackground = 'cream';

        this.availablePatterns = [];  // [{name, groups, source_file, source}]
        this.patternsLoading = new Set();  // pattern names currently loading

        this.animationHandle = null;
        this.viewState = createInitialViewState();
        this.currentFrameData = {};
        this.viewerOptions = normalizeViewerOptions(INITIAL_PAYLOAD.viewerOptions);
        this.settingsPanel = new ViewerSettingsPanel(this);
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
    }

    createRenderRoot() {
        return this;
    }

    render() {
        return html`
            <button id="to-v3d" title="Jump back to 3D view">to v3d view</button>
            <div id="viewport">
                <canvas id="c"></canvas>
                <div id="loading-overlay" class=${this.isOverlayVisible() ? 'visible' : ''}>
                    <div id="loading-text">${this.viewState.loadingText}</div>
                    <button id="output-btn" type="button" title="Open Kigumi output channel" style="display: ${this.viewState.showOutputLink ? 'block' : 'none'}">view output</button>
                </div>
                <div id="info"></div>
                <div id="gizmo-panel" aria-label="Camera and light gizmos">
                    <div class="gizmo-block">
                        <div class="gizmo-title">camera</div>
                        <canvas id="gizmo-cube-c"></canvas>
                    </div>
                    <button id="focus-btn" type="button" title="Focus selection">focus</button>
                    <div class="gizmo-block">
                        <div class="gizmo-title">light</div>
                        <canvas id="light-dial-c"></canvas>
                    </div>
                </div>
                <div id="debug"></div>
                <div id="hint">right drag orbit • middle drag pan • scroll zoom • F focus</div>
            </div>
            ${this.settingsPanel.render()}
            <div id="panels">
                <div class="panel-box">
                    <div class="panel-title">Member List</div>
                    <div id="timber-panel">
                        <table>
                            <thead>
                                <tr>
                                    <th>#</th><th>Type</th><th>Name</th>
                                    <th>Length</th><th>Width</th><th>Height</th>
                                    <th>CSG</th><th>Feat</th>
                                </tr>
                            </thead>
                            <tbody id="timber-rows"></tbody>
                        </table>
                    </div>
                </div>
                <div class="panel-box">
                    <div class="panel-title">Raw Python Output</div>
                    <pre id="raw-output"></pre>
                </div>
                <div id="patterns-panel-box" class="panel-box">
                    <div class="panel-title">
                        Patterns
                        <div id="patterns-toolbar">
                            <button id="patterns-load-btn" type="button">load patterns</button>
                        </div>
                    </div>
                    <div id="patterns-panel">
                        <div id="patterns-empty" class="patterns-empty-msg">click “load patterns” to scan for available patterns</div>
                        <div id="patterns-list"></div>
                    </div>
                </div>
                <div id="log-panel-box" class="panel-box">
                    <div class="panel-title">
                        Log Output
                        <div id="log-panel-toolbar">
                            <input id="log-filter" type="text" placeholder="filter…">
                            <button id="log-clear-btn" type="button">clear</button>
                            <button id="log-open-output-btn" type="button">open VS Code output</button>
                        </div>
                    </div>
                    <div id="log-output"></div>
                </div>
            </div>
        `;
    }

    firstUpdated() {
        this.setupUiEvents();
        this.setupThreeScene();
        window.addEventListener('message', this.onWindowMessage);
        this.setViewerOptions(INITIAL_PAYLOAD.viewerOptions);
        this.setViewPhase(ViewerPhase.WAITING_FOR_RUNNER, 'raising frame', { refreshToken: 0 });
        void this.beginPayloadApplication(INITIAL_PAYLOAD);
        
        // Setup selection listener
        this.selectionManager.onSelectionChanged((event) => {
            if (event.type === 'clear-timbers' || event.type === 'timber-selected') {
                this.selectionManager.clearCSGSelection();
                this.removeCSGHighlight();
            }
            this.applySelectionOpacity();
            this.updateInfo(this.currentFrameData);
        });
        
        this.emitViewerLog('viewer-ready', {});
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener('message', this.onWindowMessage);
        window.removeEventListener('scroll', this.onWindowScroll);
        window.removeEventListener('mouseup', this.onWindowMouseUp);
        window.removeEventListener('mousemove', this.onWindowMouseMove);
        window.removeEventListener('resize', this.onWindowResize);
        window.removeEventListener('keydown', this.onWindowKeyDown);
        window.removeEventListener('pointermove', this.onGizmoPointerMove);
        window.removeEventListener('pointerup', this.onGizmoPointerUp);
        window.removeEventListener('pointermove', this.onLightDialPointerMove);
        window.removeEventListener('pointerup', this.onLightDialPointerUp);
        if (this.animationHandle) {
            cancelAnimationFrame(this.animationHandle);
            this.animationHandle = null;
        }
        if (this.gizmoRenderer) {
            this.gizmoRenderer.dispose();
            this.gizmoRenderer = null;
        }
        if (this.shadowCatcher) {
            this.scene.remove(this.shadowCatcher);
            this.shadowCatcher.geometry.dispose();
            this.shadowCatcher.material.dispose();
            this.shadowCatcher = null;
        }
        if (this.orbitCenterGizmo) {
            this.scene.remove(this.orbitCenterGizmo);
            this.orbitCenterGizmo.traverse((child) => {
                if (child.geometry) {
                    child.geometry.dispose();
                }
                if (child.material && typeof child.material.dispose === 'function') {
                    child.material.dispose();
                }
            });
            this.orbitCenterGizmo = null;
        }
        for (const bundle of this.meshObjectsByKey.values()) {
            this.disposeMeshBundle(bundle);
        }
        this.meshObjectsByKey.clear();
        this.meshKeyMap.clear();
        this.memberMetadataByKey.clear();
    }

    setupUiEvents() {
        const toV3d = this.renderRoot.querySelector('#to-v3d');
        const canvas = this.renderRoot.querySelector('#c');
        const viewport = this.renderRoot.querySelector('#viewport');
        const gizmoCanvas = this.renderRoot.querySelector('#gizmo-cube-c');
        const focusButton = this.renderRoot.querySelector('#focus-btn');
        const lightDialCanvas = this.renderRoot.querySelector('#light-dial-c');

        toV3d.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });

        canvas.addEventListener('mousedown', (event) => {
            if (event.button === 2) {
                this.mouseAction = 'orbit';
            } else if (event.button === 1) {
                this.mouseAction = 'pan';
            } else {
                return;
            }
            event.preventDefault();
            this.lastX = event.clientX;
            this.lastY = event.clientY;
            this.cameraAnimation = null;
        });

        canvas.addEventListener('contextmenu', (event) => {
            event.preventDefault();
        });

        viewport.addEventListener('wheel', (event) => {
            event.preventDefault();
            // Calculate adaptive zoom factor based on current distance
            // This makes zoom speed feel consistent across all scales
            const adaptiveZoomFactor = this.getAdaptiveZoomFactor(event.deltaY > 0);
            this.zoomTowardPointer(event.clientX, event.clientY, adaptiveZoomFactor);
        }, { passive: false });

        gizmoCanvas.addEventListener('pointerdown', (event) => {
            event.preventDefault();
            this.gizmoDragging = true;
            this.gizmoMoved = false;
            this.gizmoLastX = event.clientX;
            this.gizmoLastY = event.clientY;
            gizmoCanvas.setPointerCapture(event.pointerId);
        });

        focusButton.addEventListener('click', () => {
            this.focusSelection();
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

        const patternsLoadBtn = this.renderRoot.querySelector('#patterns-load-btn');
        if (patternsLoadBtn) {
            patternsLoadBtn.addEventListener('click', () => {
                this.requestLoadPatterns();
            });
        }

        window.addEventListener('scroll', this.onWindowScroll);
        window.addEventListener('mouseup', this.onWindowMouseUp);
        window.addEventListener('mousemove', this.onWindowMouseMove);
        window.addEventListener('pointermove', this.onGizmoPointerMove);
        window.addEventListener('pointerup', this.onGizmoPointerUp);
        window.addEventListener('pointermove', this.onLightDialPointerMove);
        window.addEventListener('pointerup', this.onLightDialPointerUp);
        window.addEventListener('resize', this.onWindowResize);
        window.addEventListener('keydown', this.onWindowKeyDown);
    }

    setupThreeScene() {
        const viewport = this.renderRoot.querySelector('#viewport');
        const canvas = this.renderRoot.querySelector('#c');

        this.renderer = new THREE.WebGLRenderer({
            canvas: canvas,
            antialias: true,
            logarithmicDepthBuffer: true,
        });
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.setSize(viewport.offsetWidth, viewport.offsetHeight, false);
        this.renderer.outputEncoding = THREE.sRGBEncoding;
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

        this.scene = new THREE.Scene();
        this.scene.background = this._buildBackgroundTexture(BACKGROUND_PRESETS['cream']);

        this.camera = new THREE.PerspectiveCamera(45, viewport.offsetWidth / viewport.offsetHeight, 0.01, 10000);
        this.camera.up.set(0, 0, 1);

        this.scene.add(new THREE.AmbientLight(0xffffff, 0.8));
        this.sun = new THREE.DirectionalLight(0xffffff, 0.75);
        this.sun.position.set(3, 2, 12);
        this.sun.castShadow = true;
        this.sun.shadow.bias = -0.00008;
        this.sun.shadow.mapSize.set(2048, 2048);
        this.scene.add(this.sun);
        const fill = new THREE.DirectionalLight(0xecf2ff, 0.45);
        fill.position.set(-4, 3, -6);
        this.scene.add(fill);

        this.createOrUpdateShadowCatcher(this.lastBounds);
        this.createOrbitCenterGizmo();
        this.setupCameraGizmoScene();
        this.syncLightAnglesFromSun();
        this.drawLightDial();
        this.setCenterGizmoEnabled(this.showCenterGizmo);
        this.setEdgesEnabled(this.edgesEnabled);
        this.setShadowsEnabled(this.shadowsEnabled);
        this.setReflectionsEnabled(this.reflectionsEnabled);

        this.updateCamera();
        const animate = () => {
            this.animationHandle = requestAnimationFrame(animate);
            this.stepCameraAnimation();
            this.renderCameraGizmo();
            this.renderer.render(this.scene, this.camera);
        };
        animate();
    }

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
        const normalizedPercent = Number.isFinite(nextPercent)
            ? Math.max(0, Math.min(95, Math.round(nextPercent / 5) * 5))
            : 40;
        if (this.unselectedTransparencyPercent === normalizedPercent) {
            return;
        }
        this.unselectedTransparencyPercent = normalizedPercent;
        this.requestUpdate();
        this.applySelectionOpacity();
    }

    updateStructureScreenBounds() {
        if (!this.camera || !this.lastBounds) {
            this.structureScreenBounds = null;
            return;
        }
        const viewport = this.renderRoot.querySelector('#viewport');
        if (!viewport) {
            this.structureScreenBounds = null;
            return;
        }
        const width = viewport.clientWidth;
        const height = viewport.clientHeight;
        if (width <= 0 || height <= 0) {
            this.structureScreenBounds = null;
            return;
        }

        const bounds = this.lastBounds;
        const corners = [
            [bounds.minX, bounds.minY, bounds.minZ],
            [bounds.minX, bounds.minY, bounds.maxZ],
            [bounds.minX, bounds.maxY, bounds.minZ],
            [bounds.minX, bounds.maxY, bounds.maxZ],
            [bounds.maxX, bounds.minY, bounds.minZ],
            [bounds.maxX, bounds.minY, bounds.maxZ],
            [bounds.maxX, bounds.maxY, bounds.minZ],
            [bounds.maxX, bounds.maxY, bounds.maxZ],
        ];

        let minX = Infinity;
        let maxX = -Infinity;
        let minY = Infinity;
        let maxY = -Infinity;
        let hasPoint = false;

        for (const corner of corners) {
            const projected = new THREE.Vector3(corner[0], corner[1], corner[2]).project(this.camera);
            if (!Number.isFinite(projected.x) || !Number.isFinite(projected.y)) {
                continue;
            }
            const sx = ((projected.x + 1) * 0.5) * width;
            const sy = ((1 - projected.y) * 0.5) * height;
            minX = Math.min(minX, sx);
            maxX = Math.max(maxX, sx);
            minY = Math.min(minY, sy);
            maxY = Math.max(maxY, sy);
            hasPoint = true;
        }

        if (!hasPoint) {
            this.structureScreenBounds = null;
            return;
        }

        this.structureScreenBounds = {
            minX: Math.max(0, minX),
            maxX: Math.min(width, maxX),
            minY: Math.max(0, minY),
            maxY: Math.min(height, maxY),
        };
    }

    onWindowMessage(event) {
        const message = event.data || {};
        if (message.type === 'viewerState') {
            const uiState = this.normalizeUiState(message.uiState || null);
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

        if (message.type === 'logEntry') {
            const text = typeof message.text === 'string' ? message.text : String(message.text);
            this.appendLogLine(text);
            return;
        }

        if (message.type === 'featureResult') {
            // Legacy stub — replaced by csgSelectionResult
            return;
        }

        if (message.type === 'csgSelectionResult') {
            this.handleCSGSelectionResult(message);
            return;
        }

        if (message.type === 'patternsAvailable') {
            this.handlePatternsAvailable(message);
            return;
        }

        if (message.type === 'patternLoadResult') {
            this.handlePatternLoadResult(message);
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

        await new Promise((resolve) => requestAnimationFrame(() => resolve()));

        try {
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

    onWindowScroll() {
        const toV3d = this.renderRoot.querySelector('#to-v3d');
        toV3d.style.display = window.scrollY > 260 ? 'block' : 'none';
    }

    onWindowMouseUp(event) {
        const activeMouseAction = this.mouseAction;
        this.mouseAction = null;
        const canvas = this.renderRoot && this.renderRoot.querySelector ? this.renderRoot.querySelector('#c') : null;
        if (!activeMouseAction && canvas && event.target === canvas) {
            this.handleCanvasClick(event);
        }
    }

    onWindowMouseMove(event) {
        if (!this.mouseAction) {
            return;
        }
        if (this.mouseAction === 'orbit') {
            this.cameraUpVector.set(0, 0, 1);
            this.theta -= (event.clientX - this.lastX) * 0.008;
            this.phi = this.clampPhi(this.phi - (event.clientY - this.lastY) * 0.008);
        } else if (this.mouseAction === 'pan') {
            this.panCameraInViewPlane(this.lastX, this.lastY, event.clientX, event.clientY);
        }
        this.lastX = event.clientX;
        this.lastY = event.clientY;
        this.cameraAnimation = null;
        this.updateCamera();
    }

    onWindowKeyDown(event) {
        if (event.defaultPrevented) {
            return;
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            if (this.selectionManager.csgSelection) {
                this.selectionManager.clearCSGSelection();
                this.removeCSGHighlight();
            } else {
                this.selectionManager.clearTimberSelection();
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
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height, false);
        this.resizeGizmoRenderer();
        this.drawLightDial();
        this.updateStructureScreenBounds();
    }

    handleCanvasClick(event) {
        const canvas = this.renderRoot.querySelector('#c');
        if (!canvas || !event) {
            return;
        }
        const rect = canvas.getBoundingClientRect();
        if (
            event.clientX < rect.left || event.clientX > rect.right ||
            event.clientY < rect.top || event.clientY > rect.bottom
        ) {
            return;
        }

        const normalizedX = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        const normalizedY = -(((event.clientY - rect.top) / rect.height) * 2 - 1);

        this.navigationPointer.set(normalizedX, normalizedY);
        this.navigationRaycaster.setFromCamera(this.navigationPointer, this.camera);

        const targetMeshes = Array.from(this.meshObjectsByKey.values()).map((bundle) => bundle.mesh);
        const intersects = this.navigationRaycaster.intersectObjects(targetMeshes, false);

        if (intersects.length === 0) {
            this.selectionManager.clearCSGSelection();
            this.removeCSGHighlight();
            this.selectionManager.clearTimberSelection();
            return;
        }

        // When a single timber is selected, find its hit among all intersects
        // (it may be behind unselected timbers). Otherwise use the closest hit.
        let hit = intersects[0];
        let memberKey = this.meshKeyMap.get(hit.object);

        const allHitKeys = intersects.map((h) => this.meshKeyMap.get(h.object)).filter(Boolean);
        const isTimberSelected = this.selectionManager.selectedTimbers.size === 1;
        console.log('[csg-nav] click: allHits=' + JSON.stringify(allHitKeys) +
            ', selectedTimbers=' + JSON.stringify(this.selectionManager.getSelectedTimbers()) +
            ', csgSelection=' + JSON.stringify(this.selectionManager.csgSelection));

        if (this.selectionManager.selectedTimbers.size === 1 && !event.shiftKey) {
            const selectedKey = this.selectionManager.getSelectedTimbers()[0];
            let foundSelected = false;
            for (const candidate of intersects) {
                const candidateKey = this.meshKeyMap.get(candidate.object);
                if (candidateKey === selectedKey) {
                    hit = candidate;
                    memberKey = candidateKey;
                    foundSelected = true;
                    break;
                }
            }
            console.log('[csg-nav] looking for selected timber "' + selectedKey + '" in hits: found=' + foundSelected);
        }

        if (!memberKey) {
            return;
        }

        if (event.shiftKey) {
            console.log('[csg-nav] action: shift-toggle');
            this.selectionManager.clearCSGSelection();
            this.removeCSGHighlight();
            this.selectionManager.toggleTimber(memberKey);
        } else if (this.selectionManager.isTimberSelected(memberKey) && this.selectionManager.selectedTimbers.size === 1) {
            // Already selected single timber — navigate CSG tree
            const point = [hit.point.x, hit.point.y, hit.point.z];
            const csg = this.selectionManager.csgSelection;
            const currentPath = (csg && csg.timberKey === memberKey) ? csg.path : [];
            console.log('[csg-nav] action: navigate CSG, memberKey=' + memberKey + ', point=' + JSON.stringify(point) + ', currentPath=' + JSON.stringify(currentPath));
            if (typeof vscode !== 'undefined') {
                vscode.postMessage({
                    type: 'findCSGAtPoint',
                    memberKey,
                    point,
                    currentPath,
                    ctrlClick: !!event.ctrlKey || !!event.metaKey,
                });
            }
        } else {
            console.log('[csg-nav] action: select new timber ' + memberKey);
            this.selectionManager.clearCSGSelection();
            this.removeCSGHighlight();
            this.selectionManager.selectTimber(memberKey, false);
        }

        this.emitViewerLog('selection-changed', {
            selectedTimbers: this.selectionManager.getSelectedTimbers(),
        });
    }

    handleCSGSelectionResult(message) {
        const path = Array.isArray(message.path) ? message.path : [];
        const featureLabel = message.featureLabel || null;
        const hlMesh = message.highlightMesh;
        const parentHlMesh = message.parentHighlightMesh || null;
        const stats = message.stats;

        console.log('[csg-nav] csgSelectionResult:', JSON.stringify({
            path,
            featureLabel,
            hlVerts: hlMesh ? hlMesh.vertices.length : 0,
            hlIdx: hlMesh ? hlMesh.indices.length : 0,
            parentHlVerts: parentHlMesh ? parentHlMesh.vertices.length : 0,
            stats,
        }));

        // Find which timber this applies to
        const csg = this.selectionManager.csgSelection;
        const timberKey = (csg && csg.timberKey) || (this.selectionManager.selectedTimbers.size === 1
            ? this.selectionManager.getSelectedTimbers()[0]
            : null);

        if (timberKey) {
            this.selectionManager.selectCSG(timberKey, path, featureLabel);
        }

        // Build highlight geometry
        this.removeCSGHighlight();
        if (featureLabel && parentHlMesh && Array.isArray(parentHlMesh.vertices) && parentHlMesh.vertices.length > 0) {
            // Feature selected: parent CSG gets dim highlight, feature face gets bright highlight
            this._buildHighlightMesh(parentHlMesh.vertices, parentHlMesh.indices, 0x4fc3f7, 0.35, '_csgParentHighlightMesh');
            if (hlMesh && Array.isArray(hlMesh.vertices) && hlMesh.vertices.length > 0) {
                this._buildHighlightMesh(hlMesh.vertices, hlMesh.indices, 0x80d8ff, 0.85, '_csgHighlightMesh');
            }
        } else if (hlMesh && Array.isArray(hlMesh.vertices) && hlMesh.vertices.length > 0 && Array.isArray(hlMesh.indices)) {
            // Tagged CSG selected (no feature): standard highlight
            this._buildHighlightMesh(hlMesh.vertices, hlMesh.indices, 0x4fc3f7, 0.7, '_csgHighlightMesh');
        }

        if (stats) {
            this.emitViewerLog('csg-selection', {
                path,
                featureLabel,
                meshWalkMs: stats.meshWalkMs,
                trianglesMatched: stats.trianglesMatched,
                totalTriangles: stats.totalTriangles,
            });
        }

        this.updateInfo(this.currentFrameData);
    }

    handlePatternsAvailable(message) {
        const sources = Array.isArray(message.sources) ? message.sources : [];
        const flat = [];
        for (const src of sources) {
            const sourceLabel = src.source || 'unknown';
            const patterns = Array.isArray(src.patterns) ? src.patterns : [];
            for (const p of patterns) {
                flat.push({
                    name: p.name,
                    groups: Array.isArray(p.groups) ? p.groups : [],
                    source_file: p.source_file || '',
                    source: sourceLabel,
                });
            }
        }
        this.availablePatterns = flat;
        this.patternsLoading.clear();
        const loadBtn = this.renderRoot.querySelector('#patterns-load-btn');
        if (loadBtn) {
            loadBtn.disabled = false;
            loadBtn.textContent = 'reload patterns';
        }
        this.renderPatternsList();
    }

    handlePatternLoadResult(message) {
        const patternName = message.patternName;
        if (patternName) {
            this.patternsLoading.delete(patternName);
        }
        const sourceFile = message.sourceFile;
        if (sourceFile) {
            this.patternsLoading.delete('book:' + sourceFile);
        }
        this.renderPatternsList();
    }

    onPatternClick(patternName, sourceFile) {
        if (this.patternsLoading.has(patternName)) {
            return;
        }
        this.patternsLoading.add(patternName);
        this.renderPatternsList();
        if (vscode) {
            vscode.postMessage({
                type: 'loadPattern',
                patternName,
                sourceFile,
            });
        }
    }

    onBookClick(sourceFile) {
        // Use the source_file as a loading key for the book
        const bookKey = 'book:' + sourceFile;
        if (this.patternsLoading.has(bookKey)) {
            return;
        }
        this.patternsLoading.add(bookKey);
        this.renderPatternsList();
        if (vscode) {
            vscode.postMessage({
                type: 'loadBook',
                sourceFile,
            });
        }
    }

    requestLoadPatterns() {
        const rescan = this.availablePatterns.length > 0;
        const loadBtn = this.renderRoot.querySelector('#patterns-load-btn');
        if (loadBtn) {
            loadBtn.disabled = true;
            loadBtn.textContent = 'scanning…';
        }
        const emptyEl = this.renderRoot.querySelector('#patterns-empty');
        if (emptyEl && this.availablePatterns.length === 0) {
            emptyEl.textContent = 'scanning for patterns…';
            emptyEl.style.display = 'block';
        }
        if (vscode) {
            vscode.postMessage({ type: 'requestLoadPatterns', rescan });
        }
    }

    renderPatternsList() {
        const listEl = this.renderRoot.querySelector('#patterns-list');
        const emptyEl = this.renderRoot.querySelector('#patterns-empty');
        if (!listEl || !emptyEl) {
            return;
        }

        if (this.availablePatterns.length === 0) {
            emptyEl.style.display = 'block';
            listEl.innerHTML = '';
            return;
        }
        emptyEl.style.display = 'none';

        // Group by source (shipped/local), then by book (source_file)
        const bySource = new Map();
        for (const p of this.availablePatterns) {
            const sourceKey = p.source === 'shipped' ? 'Shipped Library' : p.source === 'local' ? 'Local Project' : p.source;
            if (!bySource.has(sourceKey)) {
                bySource.set(sourceKey, new Map());
            }
            const books = bySource.get(sourceKey);
            if (!books.has(p.source_file)) {
                books.set(p.source_file, []);
            }
            books.get(p.source_file).push(p);
        }

        let html = '';
        let bookIdx = 0;
        for (const [sourceLabel, books] of bySource) {
            html += `<div class="patterns-source-label">${this._escapeHtml(sourceLabel)}</div>`;
            for (const [sourceFile, patterns] of books) {
                const bookName = sourceFile.replace(/\\/g, '/').split('/').pop().replace(/\.py$/, '');
                const bookLoading = this.patternsLoading.has('book:' + sourceFile);
                const anyPatternLoading = patterns.some(p => this.patternsLoading.has(p.name));
                const bookClass = bookLoading ? ' patterns-book-loading' : '';
                html += `<div class="patterns-book${bookClass}" data-book-idx="${bookIdx}">`;
                html += `<button class="patterns-book-header" data-book-idx="${bookIdx}" data-source-file="${this._escapeAttr(sourceFile)}" ${bookLoading ? 'disabled' : ''}>`;
                html += `<span class="patterns-book-name">${this._escapeHtml(bookName)}</span>`;
                html += `<span class="patterns-book-count">${patterns.length}</span>`;
                if (bookLoading || anyPatternLoading) {
                    html += ' <span class="patterns-item-spinner">…</span>';
                }
                html += '</button>';
                html += '<div class="patterns-book-items">';
                for (const p of patterns) {
                    const isLoading = this.patternsLoading.has(p.name);
                    const loadingClass = isLoading ? ' patterns-item-loading' : '';
                    html += `<button class="patterns-item${loadingClass}" data-pattern-name="${this._escapeAttr(p.name)}" data-source-file="${this._escapeAttr(p.source_file)}" ${isLoading ? 'disabled' : ''}>`;
                    html += `<span class="patterns-item-name">${this._escapeHtml(p.name)}</span>`;
                    if (isLoading) {
                        html += ' <span class="patterns-item-spinner">…</span>';
                    }
                    html += '</button>';
                }
                html += '</div></div>';
                bookIdx++;
            }
        }
        listEl.innerHTML = html;

        // Bind pattern click events
        const buttons = listEl.querySelectorAll('.patterns-item');
        for (const btn of buttons) {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const name = btn.getAttribute('data-pattern-name');
                const file = btn.getAttribute('data-source-file');
                if (name && file) {
                    this.onPatternClick(name, file);
                }
            });
        }

        // Bind book header click events (open all patterns in book)
        const bookHeaders = listEl.querySelectorAll('.patterns-book-header');
        for (const header of bookHeaders) {
            header.addEventListener('click', () => {
                const sourceFile = header.getAttribute('data-source-file');
                if (sourceFile) {
                    this.onBookClick(sourceFile);
                }
            });
        }
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    _escapeAttr(str) {
        return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    _buildHighlightMesh(vertices, indices, color, opacity, storeKey) {
        console.log('[csg-nav] _buildHighlightMesh:', storeKey, 'verts=' + vertices.length, 'idx=' + indices.length, 'color=0x' + color.toString(16), 'opacity=' + opacity);
        const geometry = new THREE.BufferGeometry();
        const posArray = new Float32Array(vertices);
        geometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
        geometry.setIndex(indices);
        geometry.computeVertexNormals();

        const material = new THREE.MeshBasicMaterial({
            color,
            transparent: true,
            opacity,
            depthTest: false,
            depthWrite: false,
            side: THREE.DoubleSide,
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.renderOrder = 999;
        mesh.castShadow = false;
        mesh.receiveShadow = false;
        this.scene.add(mesh);
        this[storeKey] = mesh;
    }

    removeCSGHighlight() {
        this._disposeHighlightMesh('_csgHighlightMesh');
        this._disposeHighlightMesh('_csgParentHighlightMesh');
    }

    _disposeHighlightMesh(storeKey) {
        const mesh = this[storeKey];
        if (mesh) {
            this.scene.remove(mesh);
            if (mesh.geometry) {
                mesh.geometry.dispose();
            }
            if (mesh.material) {
                mesh.material.dispose();
            }
            this[storeKey] = null;
        }
    }

    applySelectionOpacity() {
        const hasTimberSelection = this.selectionManager.selectedTimbers.size > 0;
        const unselectedOpacity = 1 - (this.unselectedTransparencyPercent / 100);
        for (const [name, bundle] of this.meshObjectsByKey) {
            const selected = this.selectionManager.isTimberSelected(name);
            const opacity = hasTimberSelection ? (selected ? 1.0 : unselectedOpacity) : 1.0;
            const isTransparent = opacity < 1.0;
            bundle.mesh.material.transparent = isTransparent;
            bundle.mesh.material.opacity = opacity;
            // Transparent unselected timbers should not cast shadows
            bundle.mesh.castShadow = !isTransparent;
            // Apply matching transparency to edges
            if (bundle.edges && bundle.edges.material) {
                const profile = this.resolveRenderProfile(bundle.profileId);
                const baseEdgeOpacity = profile ? profile.edgeOpacity : 1.0;
                bundle.edges.material.opacity = isTransparent
                    ? baseEdgeOpacity * unselectedOpacity
                    : baseEdgeOpacity;
            }
            // Apply matching transparency to reflections
            if (bundle.reflection && bundle.reflection.material) {
                const profile = this.resolveRenderProfile(bundle.profileId);
                const baseReflectionOpacity = profile ? profile.reflectionOpacity : 0.14;
                bundle.reflection.material.opacity = isTransparent
                    ? baseReflectionOpacity * unselectedOpacity
                    : baseReflectionOpacity;
            }
        }
    }

    onGizmoPointerMove(event) {
        if (!this.gizmoDragging) {
            return;
        }
        const dx = event.clientX - this.gizmoLastX;
        const dy = event.clientY - this.gizmoLastY;
        if (Math.abs(dx) + Math.abs(dy) > 1) {
            this.gizmoMoved = true;
        }
        this.cameraUpVector.set(0, 0, 1);
        this.theta -= dx * 0.008;
        this.phi = this.clampPhi(this.phi - dy * 0.008);
        this.gizmoLastX = event.clientX;
        this.gizmoLastY = event.clientY;
        this.cameraAnimation = null;
        this.updateCamera();
    }

    onGizmoPointerUp(event) {
        if (!this.gizmoDragging) {
            return;
        }
        this.gizmoDragging = false;
        if (this.gizmoMoved) {
            return;
        }
        const canvas = this.renderRoot.querySelector('#gizmo-cube-c');
        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        this.snapCameraFromGizmoFace(x, y);
    }

    onLightDialPointerMove(event) {
        if (!this.lightDialDragging) {
            return;
        }
        this.applyLightDialFromPointer(event);
    }

    onLightDialPointerUp() {
        this.lightDialDragging = false;
    }

    fmt(value) {
        return (value * 1000).toFixed(1) + ' mm';
    }

    clampPhi(value) {
        return Math.max(0.05, Math.min(Math.PI - 0.05, value));
    }

    normalizeAngle(value) {
        let out = value;
        while (out <= -Math.PI) {
            out += Math.PI * 2;
        }
        while (out > Math.PI) {
            out -= Math.PI * 2;
        }
        return out;
    }

    shortestAngleDelta(from, to) {
        return this.normalizeAngle(to - from);
    }

    directionToAngles(direction) {
        const length = Math.sqrt(direction.x * direction.x + direction.y * direction.y + direction.z * direction.z) || 1;
        const nx = direction.x / length;
        const ny = direction.y / length;
        const nz = direction.z / length;
        const theta = Math.atan2(ny, nx);
        const phi = this.clampPhi(Math.acos(Math.max(-1, Math.min(1, nz))));
        return { theta, phi };
    }

    animateCameraTo(targetTheta, targetPhi, targetOrbitDist, durationMs = 260, targetUpVector = null, targetCenter = null) {
        const nextUp = targetUpVector || { x: 0, y: 0, z: 1 };
        const nextCenter = targetCenter || { x: this.cx, y: this.cy, z: this.cz };
        this.cameraAnimation = {
            startedAt: performance.now(),
            durationMs,
            startTheta: this.theta,
            startPhi: this.phi,
            startDist: this.orbitDist,
            startCx: this.cx,
            startCy: this.cy,
            startCz: this.cz,
            startUpX: this.cameraUpVector.x,
            startUpY: this.cameraUpVector.y,
            startUpZ: this.cameraUpVector.z,
            deltaTheta: this.shortestAngleDelta(this.theta, targetTheta),
            deltaPhi: targetPhi - this.phi,
            deltaDist: targetOrbitDist - this.orbitDist,
            deltaCx: nextCenter.x - this.cx,
            deltaCy: nextCenter.y - this.cy,
            deltaCz: nextCenter.z - this.cz,
            targetUpX: nextUp.x,
            targetUpY: nextUp.y,
            targetUpZ: nextUp.z,
        };
    }

    stepCameraAnimation() {
        if (!this.cameraAnimation) {
            return;
        }
        const now = performance.now();
        const elapsed = now - this.cameraAnimation.startedAt;
        const t = Math.max(0, Math.min(1, elapsed / this.cameraAnimation.durationMs));
        const eased = 1 - Math.pow(1 - t, 3);

        this.theta = this.cameraAnimation.startTheta + this.cameraAnimation.deltaTheta * eased;
        this.phi = this.clampPhi(this.cameraAnimation.startPhi + this.cameraAnimation.deltaPhi * eased);
        this.orbitDist = Math.max(0.01, this.cameraAnimation.startDist + this.cameraAnimation.deltaDist * eased);
        this.cx = this.cameraAnimation.startCx + this.cameraAnimation.deltaCx * eased;
        this.cy = this.cameraAnimation.startCy + this.cameraAnimation.deltaCy * eased;
        this.cz = this.cameraAnimation.startCz + this.cameraAnimation.deltaCz * eased;
        this.cameraUpVector.set(
            this.cameraAnimation.startUpX + (this.cameraAnimation.targetUpX - this.cameraAnimation.startUpX) * eased,
            this.cameraAnimation.startUpY + (this.cameraAnimation.targetUpY - this.cameraAnimation.startUpY) * eased,
            this.cameraAnimation.startUpZ + (this.cameraAnimation.targetUpZ - this.cameraAnimation.startUpZ) * eased,
        ).normalize();
        this.updateCamera();

        if (t >= 1) {
            this.cameraAnimation = null;
        }
    }

    getSelectionBounds() {
        const selected = this.selectionManager.getSelectedTimbers();
        if (!selected.length) {
            return this.getSceneBounds();
        }

        let minX = Infinity;
        let minY = Infinity;
        let minZ = Infinity;
        let maxX = -Infinity;
        let maxY = -Infinity;
        let maxZ = -Infinity;
        let hasAny = false;

        for (const key of selected) {
            const bundle = this.meshObjectsByKey.get(key);
            if (!bundle || !bundle.mesh || !bundle.mesh.geometry) {
                continue;
            }
            const positions = bundle.mesh.geometry.getAttribute('position').array;
            for (let index = 0; index < positions.length; index += 3) {
                hasAny = true;
                const vx = positions[index];
                const vy = positions[index + 1];
                const vz = positions[index + 2];
                if (vx < minX) minX = vx;
                if (vx > maxX) maxX = vx;
                if (vy < minY) minY = vy;
                if (vy > maxY) maxY = vy;
                if (vz < minZ) minZ = vz;
                if (vz > maxZ) maxZ = vz;
            }
        }

        if (!hasAny) {
            return this.getSceneBounds();
        }

        return { minX, minY, minZ, maxX, maxY, maxZ };
    }

    setBackground(id) {
        const preset = BACKGROUND_PRESETS[id];
        if (!preset) {
            return;
        }
        this.activeBackground = id;
        if (this.scene) {
            const tex = this._buildBackgroundTexture(preset);
            if (this.scene.background && this.scene.background.isTexture) {
                this.scene.background.dispose();
            }
            this.scene.background = tex;
        }
        this.style.background = this._buildCssBg(preset);
        this.requestUpdate();
    }

    _buildBackgroundTexture(preset) {
        const w = preset.pattern ? 256 : 2;
        const h = 256;
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, h);
        gradient.addColorStop(0, preset.gradientTop);
        gradient.addColorStop(1, preset.gradientBottom);
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, w, h);
        if (preset.pattern === 'linen') {
            ctx.strokeStyle = 'rgba(160,140,100,0.07)';
            ctx.lineWidth = 1;
            for (let i = -h; i < w + h; i += 12) {
                ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + h, h); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(i + h, 0); ctx.lineTo(i, h); ctx.stroke();
            }
        } else if (preset.pattern === 'grid') {
            ctx.strokeStyle = 'rgba(80,140,220,0.12)';
            ctx.lineWidth = 1;
            const sp = 24;
            for (let x = 0; x < w; x += sp) {
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
            }
            for (let y = 0; y < h; y += sp) {
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
            }
        }
        const tex = new THREE.CanvasTexture(canvas);
        tex.needsUpdate = true;
        return tex;
    }

    _buildCssBg(preset) {
        if (preset.pattern === 'linen') {
            return `repeating-linear-gradient(45deg, rgba(160,140,100,0.07) 0, rgba(160,140,100,0.07) 1px, transparent 1px, transparent 12px), repeating-linear-gradient(-45deg, rgba(160,140,100,0.07) 0, rgba(160,140,100,0.07) 1px, transparent 1px, transparent 12px), linear-gradient(180deg, ${preset.gradientTop} 0%, ${preset.gradientBottom} 100%)`;
        }
        if (preset.pattern === 'grid') {
            return `linear-gradient(rgba(80,140,220,0.12) 0 1px, transparent 1px 24px) 0 0 / 24px 24px repeat, linear-gradient(90deg, rgba(80,140,220,0.12) 0 1px, transparent 1px 24px) 0 0 / 24px 24px repeat, linear-gradient(180deg, ${preset.gradientTop} 0%, ${preset.gradientBottom} 100%)`;
        }
        return `linear-gradient(180deg, ${preset.gradientTop} 0%, ${preset.gradientBottom} 100%)`;
    }

    focusSelection() {
        const bounds = this.getSelectionBounds();
        this.lastBounds = bounds;
        this.focusedCx = (bounds.minX + bounds.maxX) / 2;
        this.focusedCy = (bounds.minY + bounds.maxY) / 2;
        this.focusedCz = (bounds.minZ + bounds.maxZ) / 2;
        const dx = bounds.maxX - bounds.minX;
        const dy = bounds.maxY - bounds.minY;
        const dz = bounds.maxZ - bounds.minZ;
        const radius = Math.sqrt(dx * dx + dy * dy + dz * dz) / 2 || 5;
        const fovRad = this.camera.fov * Math.PI / 180;
        const targetDist = radius / Math.sin(fovRad / 2) * 1.3;
        this.animateCameraTo(
            -Math.PI / 2,
            Math.PI / 2,
            targetDist,
            280,
            { x: 0, y: 0, z: 1 },
            { x: this.focusedCx, y: this.focusedCy, z: this.focusedCz },
        );
        this.updateLightFromAngles();
    }

    getCameraCenterVector(target = null) {
        const out = target || new THREE.Vector3();
        return out.set(this.cx, this.cy, this.cz);
    }

    projectPointerToFocalPlane(clientX, clientY, planeCenter = null) {
        if (!this.camera) {
            return null;
        }
        const canvas = this.renderRoot.querySelector('#c');
        if (!canvas) {
            return null;
        }
        const rect = canvas.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) {
            return null;
        }

        this.navigationPointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
        this.navigationPointer.y = -(((clientY - rect.top) / rect.height) * 2 - 1);
        this.navigationRaycaster.setFromCamera(this.navigationPointer, this.camera);

        const focalCenter = planeCenter || this.getCameraCenterVector(this.tempOrbitCenter);
        const viewDirection = this.camera.getWorldDirection(this.tempViewDirection).normalize();
        this.focalPlane.setFromNormalAndCoplanarPoint(viewDirection, focalCenter);
        const hit = this.navigationRaycaster.ray.intersectPlane(this.focalPlane, this.tempPlaneHit);
        return hit ? hit.clone() : null;
    }

    panCameraInViewPlane(fromClientX, fromClientY, toClientX, toClientY) {
        const planeCenter = this.getCameraCenterVector(this.tempOrbitCenter);
        const fromPoint = this.projectPointerToFocalPlane(fromClientX, fromClientY, planeCenter);
        const toPoint = this.projectPointerToFocalPlane(toClientX, toClientY, planeCenter);
        if (!fromPoint || !toPoint) {
            return;
        }
        const delta = fromPoint.sub(toPoint);
        this.cx += delta.x;
        this.cy += delta.y;
        this.cz += delta.z;
    }

    getAdaptiveZoomFactor(isZoomingOut) {
        // Calculate zoom speed that scales with current camera distance.
        // This provides consistent zoom feel whether zoomed in close or far on large structures.
        // 
        // The formula uses a logarithmic scale: at small distances zoom is slow,
        // at large distances zoom is proportionally faster to cover the scaled geometry.
        const baseZoomFactor = isZoomingOut ? 0.8 : 1.2;
        
        if (this.orbitDist <= 0) {
            return baseZoomFactor;
        }
        
        // Calculate scale multiplier based on distance
        // Log scale ensures zoom speed is proportional to visible size
        const distanceScale = Math.max(0.8, Math.log(this.orbitDist + 1) / 3);
        
        // Apply adaptive scaling with 2x responsiveness by doubling the exponent.
        // This preserves the same curve shape while making each wheel step stronger.
        return Math.pow(baseZoomFactor, distanceScale * 2);
    }

    zoomTowardPointer(clientX, clientY, zoomFactor) {
        const oldDist = Math.max(0.01, this.orbitDist);
        const nextDist = Math.max(0.01, oldDist * zoomFactor);
        const planeCenter = this.getCameraCenterVector(this.tempOrbitCenter);
        const focalPoint = this.projectPointerToFocalPlane(clientX, clientY, planeCenter);
        let targetCenter = { x: this.cx, y: this.cy, z: this.cz };

        if (focalPoint) {
            const ratio = nextDist / oldDist;
            targetCenter = {
                x: this.cx + (focalPoint.x - planeCenter.x) * (1 - ratio),
                y: this.cy + (focalPoint.y - planeCenter.y) * (1 - ratio),
                z: this.cz + (focalPoint.z - planeCenter.z) * (1 - ratio),
            };
        }

        this.animateCameraTo(
            this.theta,
            this.phi,
            nextDist,
            140,
            { x: this.cameraUpVector.x, y: this.cameraUpVector.y, z: this.cameraUpVector.z },
            targetCenter,
        );
    }

    createOrbitCenterGizmo() {
        const group = new THREE.Group();

        const orb = new THREE.Mesh(
            new THREE.SphereGeometry(1, 20, 20),
            new THREE.MeshBasicMaterial({ color: 0xffd8a8, transparent: true, opacity: 0.96 })
        );
        group.add(orb);

        const ringConfigs = [
            { color: 0xff8fa3, rotation: [0, Math.PI / 2, 0] },
            { color: 0x7fc8f8, rotation: [Math.PI / 2, 0, 0] },
            { color: 0x95d5b2, rotation: [0, 0, 0] },
        ];

        for (const config of ringConfigs) {
            const ring = new THREE.Mesh(
                new THREE.TorusGeometry(1.85, 0.12, 12, 48),
                new THREE.MeshBasicMaterial({ color: config.color, transparent: true, opacity: 0.52 })
            );
            ring.rotation.set(config.rotation[0], config.rotation[1], config.rotation[2]);
            group.add(ring);
        }

        group.visible = this.showCenterGizmo;
        this.orbitCenterGizmo = group;
        this.scene.add(group);
    }

    updateOrbitCenterGizmo() {
        if (!this.orbitCenterGizmo) {
            return;
        }
        const gizmoScale = Math.max(0.02, this.orbitDist * 0.00875);
        this.orbitCenterGizmo.visible = this.showCenterGizmo;
        this.orbitCenterGizmo.position.set(this.cx, this.cy, this.cz);
        this.orbitCenterGizmo.scale.setScalar(gizmoScale);
    }

    updateReflectionTransforms() {
        const reflectionOffsetZ = this.groundZ * 2 - 0.001;
        for (const bundle of this.meshObjectsByKey.values()) {
            if (!bundle.reflection) {
                continue;
            }
            bundle.reflection.position.set(0, 0, reflectionOffsetZ);
            bundle.reflection.scale.set(1, 1, -1);
            bundle.reflection.visible = this.reflectionsEnabled;
        }
    }

    setCenterGizmoEnabled(enabled) {
        this.showCenterGizmo = enabled;
        this.updateOrbitCenterGizmo();
    }

    setEdgesEnabled(enabled) {
        this.edgesEnabled = enabled;
        for (const bundle of this.meshObjectsByKey.values()) {
            if (bundle.edges) {
                bundle.edges.visible = enabled;
            }
        }
    }

    setShadowsEnabled(enabled) {
        this.shadowsEnabled = enabled;
        if (this.renderer) {
            this.renderer.shadowMap.enabled = enabled;
        }
        if (this.sun) {
            this.sun.castShadow = enabled;
        }
        if (this.shadowCatcher) {
            this.shadowCatcher.visible = enabled;
        }
    }

    setReflectionsEnabled(enabled) {
        this.reflectionsEnabled = enabled;
        this.updateReflectionTransforms();
    }

    resolveRenderProfile(profileId) {
        if (profileId && this.renderProfiles[profileId]) {
            return this.renderProfiles[profileId];
        }
        return this.renderProfiles['timber-default'];
    }

    resolveRenderProfileIdForMemberType(memberType) {
        if (memberType === 'accessory') {
            return this.memberRenderProfileByType.accessory;
        }
        return this.memberRenderProfileByType.timber;
    }

    createMaterialSetForMemberType(memberType) {
        const profileId = this.resolveRenderProfileIdForMemberType(memberType);
        const profile = this.resolveRenderProfile(profileId);
        return {
            profileId,
            solid: new THREE.MeshStandardMaterial({
                color: profile.solidColor,
                metalness: profile.metalness,
                roughness: profile.roughness,
                flatShading: true,
                polygonOffset: true,
                polygonOffsetFactor: 2,
                polygonOffsetUnits: 2,
                side: THREE.FrontSide,
            }),
            edge: new THREE.LineBasicMaterial({
                color: profile.edgeColor,
                transparent: true,
                opacity: profile.edgeOpacity,
                depthTest: false,
                depthWrite: false,
            }),
            reflection: new THREE.MeshStandardMaterial({
                color: profile.reflectionColor,
                metalness: profile.reflectionMetalness,
                roughness: profile.reflectionRoughness,
                transparent: true,
                opacity: profile.reflectionOpacity,
                flatShading: true,
                depthWrite: false,
                side: THREE.DoubleSide,
            }),
        };
    }

    applyRenderProfileToBundle(bundle, profileId) {
        if (!bundle || !bundle.mesh || !bundle.mesh.material || !bundle.edges || !bundle.edges.material || !bundle.reflection || !bundle.reflection.material) {
            return;
        }
        const profile = this.resolveRenderProfile(profileId);
        bundle.profileId = profileId;

        bundle.mesh.material.color.setHex(profile.solidColor);
        bundle.mesh.material.metalness = profile.metalness;
        bundle.mesh.material.roughness = profile.roughness;
        bundle.mesh.material.flatShading = true;
        bundle.mesh.material.polygonOffset = true;
        bundle.mesh.material.polygonOffsetFactor = 2;
        bundle.mesh.material.polygonOffsetUnits = 2;
        bundle.mesh.material.side = THREE.FrontSide;
        bundle.mesh.material.needsUpdate = true;

        bundle.edges.material.color.setHex(profile.edgeColor);
        bundle.edges.material.opacity = profile.edgeOpacity;
        bundle.edges.material.transparent = true;
        bundle.edges.material.depthTest = false;
        bundle.edges.material.depthWrite = false;
        bundle.edges.material.needsUpdate = true;

        bundle.reflection.material.color.setHex(profile.reflectionColor);
        bundle.reflection.material.metalness = profile.reflectionMetalness;
        bundle.reflection.material.roughness = profile.reflectionRoughness;
        bundle.reflection.material.opacity = profile.reflectionOpacity;
        bundle.reflection.material.transparent = true;
        bundle.reflection.material.flatShading = true;
        bundle.reflection.material.depthWrite = false;
        bundle.reflection.material.side = THREE.DoubleSide;
        bundle.reflection.material.needsUpdate = true;
    }

    applyRenderProfilesToScene() {
        for (const [memberKey, bundle] of this.meshObjectsByKey.entries()) {
            const metadata = this.memberMetadataByKey.get(memberKey) || { type: 'timber' };
            const profileId = this.resolveRenderProfileIdForMemberType(metadata.type);
            this.applyRenderProfileToBundle(bundle, profileId);
        }
        this.applySelectionOpacity();
    }

    setMemberRenderProfile(memberType, profileId) {
        if (!this.renderProfiles[profileId]) {
            return;
        }
        if (memberType !== 'timber' && memberType !== 'accessory') {
            return;
        }
        this.memberRenderProfileByType = {
            ...this.memberRenderProfileByType,
            [memberType]: profileId,
        };
        this.applyRenderProfilesToScene();
        this.requestUpdate();
    }

    createGizmoFaceMaterial(label, backgroundColor) {
        const canvas = document.createElement('canvas');
        canvas.width = 256;
        canvas.height = 256;
        const context = canvas.getContext('2d');

        context.fillStyle = backgroundColor;
        context.fillRect(0, 0, canvas.width, canvas.height);

        context.strokeStyle = 'rgba(93, 104, 130, 0.35)';
        context.lineWidth = 10;
        context.strokeRect(16, 16, canvas.width - 32, canvas.height - 32);

        context.fillStyle = '#39496e';
        context.textAlign = 'center';
        context.textBaseline = 'middle';
        context.font = '600 42px Segoe UI';
        context.fillText(label, canvas.width / 2, canvas.height / 2);

        const texture = new THREE.CanvasTexture(canvas);
        texture.needsUpdate = true;
        return new THREE.MeshStandardMaterial({ color: 0xffffff, map: texture });
    }

    createOrUpdateShadowCatcher(bounds) {
        const dx = bounds.maxX - bounds.minX;
        const dy = bounds.maxY - bounds.minY;
        const centerX = (bounds.minX + bounds.maxX) / 2;
        const centerY = (bounds.minY + bounds.maxY) / 2;
        const groundZ = bounds.minZ - 0.0005;
        this.groundZ = groundZ;
        this.shadowSize = Math.max(60, Math.max(dx, dy) * 8 || 60);

        if (!this.shadowCatcher) {
            this.shadowCatcher = new THREE.Mesh(
                new THREE.PlaneBufferGeometry(1, 1),
                new THREE.ShadowMaterial({ opacity: 0.22 })
            );
            this.shadowCatcher.receiveShadow = true;
            this.shadowCatcher.renderOrder = 1;
            this.scene.add(this.shadowCatcher);
        } else {
            this.shadowCatcher.geometry.dispose();
            this.shadowCatcher.geometry = new THREE.PlaneBufferGeometry(1, 1);
        }

        this.shadowCatcher.position.set(centerX, centerY, groundZ + 0.0001);
        this.shadowCatcher.scale.set(this.shadowSize, this.shadowSize, 1);
        this.shadowCatcher.visible = this.shadowsEnabled;
        this.updateReflectionTransforms();
        this.configureShadowCamera(bounds, this.shadowSize);
    }

    configureShadowCamera(bounds, size) {
        if (!this.sun || !this.sun.shadow || !this.sun.shadow.camera) {
            return;
        }
        const shadowCam = this.sun.shadow.camera;
        const half = size / 2;
        shadowCam.left = -half;
        shadowCam.right = half;
        shadowCam.top = half;
        shadowCam.bottom = -half;
        shadowCam.near = 0.5;
        shadowCam.far = Math.max(40, (bounds.maxZ - bounds.minZ) * 8 || 40);
        shadowCam.updateProjectionMatrix();
        const centerX = (bounds.minX + bounds.maxX) / 2;
        const centerY = (bounds.minY + bounds.maxY) / 2;
        const centerZ = (bounds.minZ + bounds.maxZ) / 2;
        this.sun.target.position.set(centerX, centerY, centerZ);
        if (!this.sun.target.parent) {
            this.scene.add(this.sun.target);
        }
    }

    setupCameraGizmoScene() {
        const canvas = this.renderRoot.querySelector('#gizmo-cube-c');
        this.gizmoRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
        this.gizmoRenderer.setClearColor(0x000000, 0);

        this.gizmoScene = new THREE.Scene();
        this.gizmoCamera = new THREE.PerspectiveCamera(35, 1, 0.1, 20);

        this.gizmoScene.add(new THREE.AmbientLight(0xffffff, 0.82));
        const light = new THREE.DirectionalLight(0xffffff, 0.65);
        light.position.set(2, 2, 3);
        this.gizmoScene.add(light);

        const materials = [
            this.createGizmoFaceMaterial('right', '#c9d6ea'),
            this.createGizmoFaceMaterial('left', '#bfcee4'),
            this.createGizmoFaceMaterial('back', '#d6deee'),
            this.createGizmoFaceMaterial('front', '#c4d2e8'),
            this.createGizmoFaceMaterial('top', '#bccbe2'),
            this.createGizmoFaceMaterial('bottom', '#b6c6df'),
        ];
        this.gizmoCube = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), materials);
        this.gizmoScene.add(this.gizmoCube);
        this.resizeGizmoRenderer();
    }

    getCameraSnapForDirection(direction) {
        const angles = this.directionToAngles(direction);
        if (direction.z > 0) {
            return { theta: angles.theta, phi: angles.phi, upVector: { x: 0, y: 1, z: 0 } };
        }
        if (direction.z < 0) {
            return { theta: angles.theta, phi: angles.phi, upVector: { x: 0, y: -1, z: 0 } };
        }
        return { theta: angles.theta, phi: angles.phi, upVector: { x: 0, y: 0, z: 1 } };
    }

    resizeGizmoRenderer() {
        if (!this.gizmoRenderer || !this.gizmoCamera) {
            return;
        }
        const canvas = this.renderRoot.querySelector('#gizmo-cube-c');
        const width = Math.max(1, canvas.clientWidth);
        const height = Math.max(1, canvas.clientHeight);
        this.gizmoRenderer.setPixelRatio(window.devicePixelRatio || 1);
        this.gizmoRenderer.setSize(width, height, false);
        this.gizmoCamera.aspect = width / height;
        this.gizmoCamera.updateProjectionMatrix();
    }

    renderCameraGizmo() {
        if (!this.gizmoRenderer || !this.gizmoCamera || !this.camera) {
            return;
        }
        const dx = this.camera.position.x - this.cx;
        const dy = this.camera.position.y - this.cy;
        const dz = this.camera.position.z - this.cz;
        const length = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
        this.gizmoCamera.position.set((dx / length) * 2.8, (dy / length) * 2.8, (dz / length) * 2.8);
        this.gizmoCamera.up.set(0, 0, 1);
        this.gizmoCamera.lookAt(0, 0, 0);
        this.gizmoRenderer.render(this.gizmoScene, this.gizmoCamera);
    }

    snapCameraFromGizmoFace(localX, localY) {
        if (!this.gizmoCube || !this.gizmoCamera) {
            return;
        }
        const canvas = this.renderRoot.querySelector('#gizmo-cube-c');
        const width = canvas.clientWidth || 1;
        const height = canvas.clientHeight || 1;

        this.gizmoPointer.x = (localX / width) * 2 - 1;
        this.gizmoPointer.y = -((localY / height) * 2 - 1);
        this.gizmoRaycaster.setFromCamera(this.gizmoPointer, this.gizmoCamera);
        const hits = this.gizmoRaycaster.intersectObject(this.gizmoCube, false);
        if (!hits.length || !hits[0].face) {
            return;
        }

        const normal = hits[0].face.normal;
        const ax = Math.abs(normal.x);
        const ay = Math.abs(normal.y);
        const az = Math.abs(normal.z);
        let direction;

        if (ax >= ay && ax >= az) {
            direction = { x: Math.sign(normal.x), y: 0, z: 0 };
        } else if (ay >= ax && ay >= az) {
            direction = { x: 0, y: Math.sign(normal.y), z: 0 };
        } else {
            direction = { x: 0, y: 0, z: Math.sign(normal.z) };
        }

        const snap = this.getCameraSnapForDirection(direction);
        this.animateCameraTo(snap.theta, snap.phi, this.orbitDist, 260, snap.upVector);
    }

    syncLightAnglesFromSun() {
        if (!this.sun) {
            return;
        }
        const dx = this.sun.position.x - this.focusedCx;
        const dy = this.sun.position.y - this.focusedCy;
        const dz = this.sun.position.z - this.focusedCz;
        const distance = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
        this.lightDistance = distance;
        this.lightAzimuth = Math.atan2(dy, dx);
        this.lightElevation = Math.max(0.2, Math.min(1.3, Math.asin(dz / distance)));
    }

    updateLightFromAngles() {
        if (!this.sun) {
            return;
        }
        const cosElevation = Math.cos(this.lightElevation);
        const dx = cosElevation * Math.cos(this.lightAzimuth) * this.lightDistance;
        const dy = cosElevation * Math.sin(this.lightAzimuth) * this.lightDistance;
        const dz = Math.sin(this.lightElevation) * this.lightDistance;

        this.sun.position.set(this.focusedCx + dx, this.focusedCy + dy, this.focusedCz + dz);
        this.sun.target.position.set(this.focusedCx, this.focusedCy, this.focusedCz);
        if (!this.sun.target.parent) {
            this.scene.add(this.sun.target);
        }
        this.configureShadowCamera(this.lastBounds, this.shadowSize || 60);
    }

    drawLightDial() {
        const canvas = this.renderRoot.querySelector('#light-dial-c');
        if (!canvas) {
            return;
        }
        const width = Math.max(1, canvas.clientWidth);
        const height = Math.max(1, canvas.clientHeight);
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);

        const context = canvas.getContext('2d');
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        context.clearRect(0, 0, width, height);

        const cx = width / 2;
        const cy = height / 2;
        const radius = Math.min(width, height) * 0.36;

        context.strokeStyle = 'rgba(88, 115, 166, 0.5)';
        context.lineWidth = 2;
        context.beginPath();
        context.arc(cx, cy, radius, 0, Math.PI * 2);
        context.stroke();

        const minElevation = 0.2;
        const maxElevation = 1.3;
        const elevationRatio = (this.lightElevation - minElevation) / (maxElevation - minElevation);
        const knobRadius = radius * (1 - elevationRatio * 0.85);
        const knobX = cx + Math.cos(this.lightAzimuth) * knobRadius;
        const knobY = cy + Math.sin(this.lightAzimuth) * knobRadius;

        context.strokeStyle = 'rgba(88, 115, 166, 0.45)';
        context.lineWidth = 1.5;
        context.beginPath();
        context.moveTo(cx, cy);
        context.lineTo(knobX, knobY);
        context.stroke();

        context.fillStyle = '#5873a6';
        context.beginPath();
        context.arc(knobX, knobY, 5, 0, Math.PI * 2);
        context.fill();
    }

    applyLightDialFromPointer(event) {
        const canvas = this.renderRoot.querySelector('#light-dial-c');
        if (!canvas) {
            return;
        }
        const rect = canvas.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const dx = event.clientX - cx;
        const dy = event.clientY - cy;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const maxDistance = Math.min(rect.width, rect.height) * 0.36;

        const minElevation = 0.2;
        const maxElevation = 1.3;
        const clampedDistance = Math.min(maxDistance, distance);

        this.lightAzimuth = Math.atan2(dy, dx);
        this.lightElevation = minElevation + (1 - clampedDistance / Math.max(1, maxDistance)) * (maxElevation - minElevation);
        this.updateLightFromAngles();
        this.drawLightDial();
    }

    disposeMeshBundle(bundle) {
        if (!bundle) {
            return;
        }
        this.scene.remove(bundle.mesh);
        this.scene.remove(bundle.edges);
        if (bundle.reflection) {
            this.scene.remove(bundle.reflection);
        }
        bundle.mesh.geometry.dispose();
        if (bundle.mesh.material && typeof bundle.mesh.material.dispose === 'function') {
            bundle.mesh.material.dispose();
        }
        bundle.edges.geometry.dispose();
        if (bundle.edges.material && typeof bundle.edges.material.dispose === 'function') {
            bundle.edges.material.dispose();
        }
        if (bundle.reflection && bundle.reflection.material && typeof bundle.reflection.material.dispose === 'function') {
            bundle.reflection.material.dispose();
        }
    }

    rebuildTimberTable(meshes) {
        const tbody = this.renderRoot.querySelector('#timber-rows');
        tbody.textContent = '';
        for (let index = 0; index < meshes.length; index += 1) {
            const mesh = meshes[index];
            const typeLabel = mesh.memberType === 'accessory' ? 'Accessory' : 'Timber';
            const memberName = mesh.memberName || mesh.name || '?';
            const row = document.createElement('tr');
            row.innerHTML = '<td>' + (index + 1) + '</td>' +
                '<td>' + typeLabel + '</td>' +
                '<td>' + memberName + '</td>' +
                '<td class="dim">' + (mesh.prism_length !== undefined ? this.fmt(mesh.prism_length) : '—') + '</td>' +
                '<td class="dim">' + (mesh.prism_width  !== undefined ? this.fmt(mesh.prism_width)  : '—') + '</td>' +
                '<td class="dim">' + (mesh.prism_height !== undefined ? this.fmt(mesh.prism_height) : '—') + '</td>' +
                '<td class="dim">' + (mesh.csg_nodes !== undefined ? mesh.csg_nodes : '—') + '</td>' +
                '<td class="dim">' + (mesh.csg_features !== undefined ? mesh.csg_features : '—') + '</td>';
            tbody.appendChild(row);
        }
    }

    updateInfo(frameData) {
        this.currentFrameData = frameData || {};
        const timberCount = frameData && frameData.timber_count ? frameData.timber_count : 0;
        const accessoriesCount = frameData && frameData.accessories_count ? frameData.accessories_count : 0;
        const selectedMembers = this.selectionManager.getSelectedTimbers();
        let selectedTimberCount = 0;
        let selectedAccessoryCount = 0;
        let selectedSingleName = '';
        let selectedKnownCount = 0;

        for (const selectedKey of selectedMembers) {
            const metadata = this.memberMetadataByKey.get(selectedKey);
            if (!metadata) {
                continue;
            }
            selectedKnownCount += 1;
            if (metadata.type === 'accessory') {
                selectedAccessoryCount += 1;
            } else {
                selectedTimberCount += 1;
            }
            if (selectedKnownCount === 1) {
                selectedSingleName = metadata.name || '';
            }
        }

        if (selectedKnownCount !== 1) {
            selectedSingleName = '';
        }

        let breadcrumb = '';
        if (selectedSingleName && this.selectionManager.csgSelection) {
            const csg = this.selectionManager.csgSelection;
            const parts = [selectedSingleName].concat(csg.path);
            if (csg.featureLabel) {
                parts.push('face (' + csg.featureLabel + ')');
            }
            breadcrumb = parts.join(' &gt; ');
        } else {
            breadcrumb = selectedSingleName;
        }

        this.renderRoot.querySelector('#info').innerHTML =
            'timbers (' + selectedTimberCount + '/' + timberCount + ') accesories (' + selectedAccessoryCount + '/' + accessoriesCount + ')' +
            '<br>' + breadcrumb;
    }

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
        const meshes = (geometryData && geometryData.meshes) ? geometryData.meshes : [];
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

            const existing = this.meshObjectsByKey.get(key);
            if (existing) {
                this.meshKeyMap.delete(existing.mesh);
                this.memberMetadataByKey.delete(key);
                this.disposeMeshBundle(existing);
                this.meshObjectsByKey.delete(key);
            }

            const meshT0 = performance.now();
            const positions = new Float32Array(mesh.vertices || []);
            const indexedGeometry = new THREE.BufferGeometry();
            indexedGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
            indexedGeometry.setIndex(mesh.indices || []);

            const geometry = indexedGeometry.toNonIndexed();
            geometry.computeVertexNormals();
            geometry.computeBoundingSphere();
            indexedGeometry.dispose();

            const materialSet = this.createMaterialSetForMemberType(memberType);

            const solidMesh = new THREE.Mesh(geometry, materialSet.solid);
            const edgeGeometry = new THREE.EdgesGeometry(geometry, 25);
            const edgeMesh = new THREE.LineSegments(edgeGeometry, materialSet.edge);
            const reflectionMesh = new THREE.Mesh(geometry, materialSet.reflection);
            solidMesh.renderOrder = 1;
            edgeMesh.renderOrder = 2;
            reflectionMesh.renderOrder = 0;
            solidMesh.castShadow = true;
            solidMesh.receiveShadow = true;
            edgeMesh.visible = this.edgesEnabled;
            reflectionMesh.castShadow = false;
            reflectionMesh.receiveShadow = false;
            reflectionMesh.visible = this.reflectionsEnabled;

            this.scene.add(solidMesh);
            this.scene.add(edgeMesh);
            this.scene.add(reflectionMesh);
            this.meshKeyMap.set(solidMesh, key);
            this.memberMetadataByKey.set(key, { name: memberName, type: memberType });
            this.meshObjectsByKey.set(key, {
                memberType,
                profileId: materialSet.profileId,
                mesh: solidMesh,
                edges: edgeMesh,
                reflection: reflectionMesh,
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

        for (const existingKey of Array.from(this.meshObjectsByKey.keys())) {
            if (!nextKeys.has(existingKey)) {
                const bundle = this.meshObjectsByKey.get(existingKey);
                this.meshKeyMap.delete(bundle.mesh);
                this.memberMetadataByKey.delete(existingKey);
                this.disposeMeshBundle(bundle);
                this.meshObjectsByKey.delete(existingKey);
            }
        }

        this.rebuildTimberTable(meshes);
        this.updateReflectionTransforms();
        this.applySelectionOpacity();
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

        return {
            phase,
            loadingText,
            refreshToken,
            error,
            showOutputLink,
            keepLoading: Boolean(next.keepLoading),
        };
    }

    defaultLoadingTextForPhase(phase) {
        if (phase === ViewerPhase.BOOTING) {
            return 'starting viewer';
        }
        if (phase === ViewerPhase.WAITING_FOR_RUNNER) {
            return 'raising frame';
        }
        if (phase === ViewerPhase.APPLYING_GEOMETRY) {
            return 'cutting joints 0/0';
        }
        if (phase === ViewerPhase.ERROR) {
            return 'viewer error';
        }
        return '';
    }

    isOverlayVisible() {
        return this.viewState.phase !== ViewerPhase.READY;
    }

    setViewState(nextPartial) {
        this.viewState = {
            ...this.viewState,
            ...nextPartial,
        };

        const overlay = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#loading-overlay')
            : null;
        if (overlay) {
            const textEl = overlay.querySelector('#loading-text');
            if (textEl) {
                textEl.textContent = this.viewState.loadingText;
            } else {
                overlay.textContent = this.viewState.loadingText;
            }
            overlay.classList.toggle('visible', this.isOverlayVisible());
            overlay.classList.toggle('error', this.viewState.phase === ViewerPhase.ERROR);
            const btn = overlay.querySelector('#output-btn');
            if (btn) {
                btn.style.display = this.viewState.showOutputLink ? 'block' : 'none';
            }
        }
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

    waitForNextPaint() {
        return new Promise((resolve) => {
            requestAnimationFrame(() => {
                requestAnimationFrame(() => resolve());
            });
        });
    }

    getSceneBounds() {
        let minX = Infinity;
        let minY = Infinity;
        let minZ = Infinity;
        let maxX = -Infinity;
        let maxY = -Infinity;
        let maxZ = -Infinity;
        let hasAny = false;

        this.meshObjectsByKey.forEach((bundle) => {
            const positions = bundle.mesh.geometry.getAttribute('position').array;
            for (let index = 0; index < positions.length; index += 3) {
                hasAny = true;
                const vx = positions[index];
                const vy = positions[index + 1];
                const vz = positions[index + 2];
                if (vx < minX) minX = vx;
                if (vx > maxX) maxX = vx;
                if (vy < minY) minY = vy;
                if (vy > maxY) maxY = vy;
                if (vz < minZ) minZ = vz;
                if (vz > maxZ) maxZ = vz;
            }
        });

        if (!hasAny) {
            return { minX: -1, minY: -1, minZ: -1, maxX: 1, maxY: 1, maxZ: 1 };
        }

        return { minX, minY, minZ, maxX, maxY, maxZ };
    }

    async applyPayload(payload, refreshToken) {
        const frameData = payload.frame || {};
        const geometryData = payload.geometry || { meshes: [] };
        const profiling = payload.profiling || null;
        const uiState = this.normalizeUiState(payload.uiState || null);
        const hadExistingScene = this.meshObjectsByKey.size > 0;

        if (uiState.keepLoading) {
            this.setViewPhase(uiState.phase, uiState.loadingText, { refreshToken, error: uiState.error });
            this.updateInfo(frameData);
            this.updateDebug(geometryData, profiling);
            this.renderRoot.querySelector('#raw-output').textContent = JSON.stringify({
                frame: frameData,
                geometry: geometryData,
            }, null, 2);
            return;
        }

        this.setViewPhase(ViewerPhase.APPLYING_GEOMETRY, uiState.loadingText || 'raising frame', {
            refreshToken,
            error: null,
        });
        await this.waitForNextPaint();
        if (this.isRefreshStale(refreshToken)) {
            return;
        }

        this.updateInfo(frameData);
        const applyStartMs = performance.now();
        const completed = await this.updateMeshScene(geometryData, refreshToken, (processed, total) => {
            this.setViewPhase(ViewerPhase.APPLYING_GEOMETRY, `cutting joints ${processed}/${total}`, {
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
        const fovRad = this.camera.fov * Math.PI / 180;
        if (!hadExistingScene) {
            this.cx = this.focusedCx;
            this.cy = this.focusedCy;
            this.cz = this.focusedCz;
            this.orbitDist = radius / Math.sin(fovRad / 2) * 1.3;
        }
        this.lightDistance = Math.max(12, radius * 4);
        this.camera.near = Math.max(0.1, radius * 0.03);
        this.camera.far = Math.max(200, radius * 20);
        this.camera.updateProjectionMatrix();
        this.updateCamera();
        this.updateLightFromAngles();
        this.drawLightDial();
        this.updateStructureScreenBounds();
        if (this.isRefreshStale(refreshToken)) {
            return;
        }
        this.setViewPhase(ViewerPhase.READY, '', { refreshToken, error: null });
    }

    updateCamera() {
        if (!this.camera) {
            return;
        }
        this.camera.position.set(
            this.cx + this.orbitDist * Math.sin(this.phi) * Math.cos(this.theta),
            this.cy + this.orbitDist * Math.sin(this.phi) * Math.sin(this.theta),
            this.cz + this.orbitDist * Math.cos(this.phi)
        );
        this.camera.up.copy(this.cameraUpVector);
        this.camera.lookAt(this.cx, this.cy, this.cz);
        this.updateOrbitCenterGizmo();
        this.updateStructureScreenBounds();
    }
}

customElements.define('kigumi-app', KigumiViewerApp);
