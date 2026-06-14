import { LitElement, html } from 'lit';

const ViewerPhase = Object.freeze({
    BOOTING: 'booting',
    WAITING_FOR_RUNNER: 'waiting_for_runner',
    APPLYING_GEOMETRY: 'applying_geometry',
    READY: 'ready',
    ERROR: 'error',
});

const VALID_GEOMETRY_MODES = new Set(['actual', 'perfectAabb']);

function normalizeV3RenderParameterValue(value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        return {
            x: value.x == null ? '' : String(value.x),
            y: value.y == null ? '' : String(value.y),
            z: value.z == null ? '' : String(value.z),
        };
    }
    if (Array.isArray(value) && value.length === 3) {
        return {
            x: value[0] == null ? '' : String(value[0]),
            y: value[1] == null ? '' : String(value[1]),
            z: value[2] == null ? '' : String(value[2]),
        };
    }
    return { x: '0', y: '0', z: '0' };
}

function createRenderParameterEditorFallback(parameter) {
    if (parameter.kind === 'boolean') {
        return false;
    }
    if (parameter.kind === 'enum') {
        return Array.isArray(parameter.options) && parameter.options.length > 0 ? parameter.options[0] : '';
    }
    if (parameter.kind === 'v3') {
        return { x: '0', y: '0', z: '0' };
    }
    return '';
}

function normalizeRenderParameterEditorValue(parameter, value) {
    if (value == null) {
        return createRenderParameterEditorFallback(parameter);
    }
    if (parameter.kind === 'v3') {
        return normalizeV3RenderParameterValue(value);
    }
    if (parameter.kind === 'boolean') {
        return Boolean(value);
    }
    return value;
}

function normalizeComparableRenderParameterValue(parameter, value) {
    if (value == null) {
        return null;
    }
    if (parameter.kind === 'v3') {
        const vector = normalizeV3RenderParameterValue(value);
        return { x: vector.x, y: vector.y, z: vector.z };
    }
    if (parameter.kind === 'boolean') {
        return Boolean(value);
    }
    return String(value);
}

function cloneRenderParameterValue(parameter, value) {
    if (value == null) {
        return value;
    }
    if (parameter.kind === 'v3') {
        const vector = normalizeV3RenderParameterValue(value);
        return { x: vector.x, y: vector.y, z: vector.z };
    }
    return value;
}

function normalizeViewerOptions(viewerOptions) {
    const opts = (viewerOptions && typeof viewerOptions === 'object') ? viewerOptions : {};
    const geometryMode = VALID_GEOMETRY_MODES.has(opts.geometryMode) ? opts.geometryMode : 'actual';
    return { geometryMode };
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
    viewerSettings: null,
};
const vscode = typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : null;
const VIEWER_APP_VERSION = '2026.03.17.4';
const SelectionStore = window.SelectionStore;
const CameraController = window.CameraController;

const CSG_HIGHLIGHT_COLORS = Object.freeze({
    tagged: 0x4fc3f7,
    feature: 0x80d8ff,
});

const SELECTION_VISUAL_STATES = Object.freeze({
    NOTHING_SELECTED: 'nothing_selected',
    TIMBER_SELECTED_NO_SUB: 'timber_selected_no_sub',
    TIMBER_SELECTED_WITH_SUB: 'timber_selected_with_sub',
    TAGGED_CSG_SELECTED_NO_SUB: 'tagged_csg_selected_no_sub',
    TAGGED_CSG_SELECTED_WITH_SUB: 'tagged_csg_selected_with_sub',
    FEATURE_SELECTED: 'feature_selected',
});

const RENDER_PROFILES = Object.freeze({
    'timber-default': Object.freeze({
        label: 'Timber Default',
        solidColor: 0xb8c4d5,
        edgeColor: 0x49546d,
        reflectionColor: 0xe7edf8,
        roughness: 0.68,
        metalness: 0.02,
        reflectionRoughness: 0.28,
        reflectionMetalness: 0.04,
        edgeOpacity: 0.52,
        reflectionOpacity: 0.14,
    }),
    'timber-warm': Object.freeze({
        label: 'Timber Warm',
        solidColor: 0xcbb898,
        edgeColor: 0x564737,
        reflectionColor: 0xe7d8c2,
        roughness: 0.73,
        metalness: 0.01,
        reflectionRoughness: 0.31,
        reflectionMetalness: 0.02,
        edgeOpacity: 0.56,
        reflectionOpacity: 0.12,
    }),
    'accessory-cute': Object.freeze({
        label: 'Accessory Cute Tint',
        solidColor: 0xffb3c7,
        edgeColor: 0x7d4055,
        reflectionColor: 0xffd9e6,
        roughness: 0.54,
        metalness: 0.03,
        reflectionRoughness: 0.24,
        reflectionMetalness: 0.05,
        edgeOpacity: 0.56,
        reflectionOpacity: 0.17,
    }),
    'accessory-brass': Object.freeze({
        label: 'Accessory Brass',
        solidColor: 0xc8a64d,
        edgeColor: 0x4a3b17,
        reflectionColor: 0xe8cd80,
        roughness: 0.42,
        metalness: 0.2,
        reflectionRoughness: 0.2,
        reflectionMetalness: 0.24,
        edgeOpacity: 0.54,
        reflectionOpacity: 0.18,
    }),
    'timber-dark': Object.freeze({
        label: 'Timber Dark',
        solidColor: 0x586278,
        edgeColor: 0x171d2a,
        reflectionColor: 0x6a7a92,
        roughness: 0.75,
        metalness: 0.03,
        reflectionRoughness: 0.32,
        reflectionMetalness: 0.04,
        edgeOpacity: 0.72,
        reflectionOpacity: 0.10,
    }),
});

const DEFAULT_THEME_UI = Object.freeze({
    mode: 'light',
    bgTop: '#fff8dc',
    bgBottom: '#ffeef4',
    panelBg: 'rgba(255, 255, 255, 0.78)',
    panelBorder: '#d7dbe8',
    text: '#3a4152',
    title: '#5873a6',
    dim: '#6e7691',
    accent: '#8ca4cf',
    mesh: '#afbccf',
    edge: '#5d6882',
    strong: '#39496e',
    hint: 'rgba(72, 77, 94, 0.58)',
    overlayBg: 'rgba(255, 255, 255, 0.46)',
    overlayErrorBg: 'rgba(255, 236, 236, 0.78)',
    error: '#8a2b2b',
    errorHover: '#a63535',
    errorActive: '#6d1f1f',
    errorFg: '#fefefe',
    debugAccent: '#9eb5dc',
    controlBg: 'rgba(255, 255, 255, 0.55)',
    controlBgStrong: 'rgba(255, 255, 255, 0.9)',
    controlBgHover: 'rgba(140, 164, 207, 0.25)',
    controlBgSolid: 'rgba(255, 255, 255, 0.92)',
    controlBgSolidHover: '#ffffff',
    controlBorder: 'rgba(140, 164, 207, 0.22)',
    controlBorderStrong: 'rgba(140, 164, 207, 0.45)',
    panelHeaderBg: 'rgba(255, 255, 255, 0.6)',
    tableHeadBg: 'rgba(255, 255, 255, 0.95)',
    rowHoverBg: 'rgba(145, 161, 192, 0.12)',
    rowBorder: '#e8ebf3',
    rowIndex: '#707a97',
    inputBg: 'rgba(255, 255, 255, 0.7)',
    inputBorder: 'rgba(140, 164, 207, 0.22)',
    accentSoft: 'rgba(140, 164, 207, 0.08)',
    accentMid: 'rgba(140, 164, 207, 0.18)',
    accentStrong: 'rgba(140, 164, 207, 0.28)',
    accentBorder: 'rgba(140, 164, 207, 0.22)',
    accentBorderStrong: 'rgba(140, 164, 207, 0.7)',
    layersBg: 'rgba(255, 255, 255, 0.55)',
    layersCollapsedBg: 'rgba(255, 255, 255, 0.4)',
    layersHeaderBg: 'rgba(255, 255, 255, 0.35)',
    layersHoverBg: 'rgba(140, 164, 207, 0.18)',
    layersSelectedBg: 'rgba(140, 164, 207, 0.32)',
    chipBg: 'rgba(255, 255, 255, 0.8)',
});

function createTheme(theme) {
    return Object.freeze({
        ...theme,
        ui: Object.freeze({
            ...DEFAULT_THEME_UI,
            ...(theme.ui || {}),
        }),
    });
}

const THEMES = Object.freeze({
    'cream': createTheme({
        label: 'Cream',
        gradientTop: '#fff8dc',
        gradientBottom: '#ffeef4',
        timberProfileId: 'timber-warm',
        accessoryProfileId: 'accessory-cute',
    }),
    'sky': createTheme({
        label: 'Sky',
        gradientTop: '#cde4ff',
        gradientBottom: '#e6f2ff',
        timberProfileId: 'timber-default',
        accessoryProfileId: 'accessory-cute',
    }),
    'forest': createTheme({
        label: 'Forest Mist',
        gradientTop: '#d4ead0',
        gradientBottom: '#e8f5ea',
        timberProfileId: 'timber-warm',
        accessoryProfileId: 'accessory-brass',
    }),
    'warm-white': createTheme({
        label: 'Warm White',
        gradientTop: '#fdfaf5',
        gradientBottom: '#f8f4ee',
        timberProfileId: 'timber-warm',
        accessoryProfileId: 'accessory-cute',
    }),
    'linen': createTheme({
        label: 'Linen',
        gradientTop: '#f5efe0',
        gradientBottom: '#ece6d5',
        pattern: 'linen',
        timberProfileId: 'timber-warm',
        accessoryProfileId: 'accessory-brass',
    }),
    'slate': createTheme({
        label: 'Slate Night',
        gradientTop: '#1a2030',
        gradientBottom: '#2a3244',
        timberProfileId: 'timber-dark',
        accessoryProfileId: 'accessory-brass',
        ui: {
            mode: 'dark',
            panelBg: 'rgba(24, 30, 44, 0.72)',
            panelBorder: '#3f4d66',
            text: '#d7deea',
            title: '#c1d1f4',
            dim: '#9aa8c4',
            accent: '#82a3de',
            mesh: '#7f93b3',
            edge: '#d2def5',
            strong: '#eaf1ff',
            hint: 'rgba(204, 218, 242, 0.74)',
            overlayBg: 'rgba(17, 22, 33, 0.56)',
            overlayErrorBg: 'rgba(67, 28, 38, 0.74)',
            error: '#ff8ea3',
            errorHover: '#ff9db0',
            errorActive: '#ef708b',
            errorFg: '#1c0f13',
            debugAccent: '#89a9e8',
            controlBg: 'rgba(37, 46, 68, 0.78)',
            controlBgStrong: 'rgba(40, 50, 75, 0.9)',
            controlBgHover: 'rgba(111, 143, 201, 0.34)',
            controlBgSolid: 'rgba(38, 47, 70, 0.94)',
            controlBgSolidHover: 'rgba(58, 71, 101, 0.97)',
            controlBorder: 'rgba(130, 163, 222, 0.35)',
            controlBorderStrong: 'rgba(130, 163, 222, 0.55)',
            panelHeaderBg: 'rgba(30, 38, 57, 0.78)',
            tableHeadBg: 'rgba(31, 40, 60, 0.92)',
            rowHoverBg: 'rgba(130, 163, 222, 0.16)',
            rowBorder: '#34425c',
            rowIndex: '#aebcdc',
            inputBg: 'rgba(37, 46, 68, 0.86)',
            inputBorder: 'rgba(130, 163, 222, 0.35)',
            accentSoft: 'rgba(130, 163, 222, 0.16)',
            accentMid: 'rgba(130, 163, 222, 0.27)',
            accentStrong: 'rgba(130, 163, 222, 0.38)',
            accentBorder: 'rgba(130, 163, 222, 0.35)',
            accentBorderStrong: 'rgba(130, 163, 222, 0.65)',
            layersBg: 'rgba(24, 30, 44, 0.74)',
            layersCollapsedBg: 'rgba(24, 30, 44, 0.84)',
            layersHeaderBg: 'rgba(30, 38, 57, 0.78)',
            layersHoverBg: 'rgba(130, 163, 222, 0.2)',
            layersSelectedBg: 'rgba(130, 163, 222, 0.3)',
            chipBg: 'rgba(40, 50, 75, 0.9)',
        },
    }),
});

if (!SelectionStore) {
    throw new Error('SelectionStore is not loaded. Ensure selection-store.js is included before viewer-app.js.');
}
if (!CameraController) {
    throw new Error('CameraController is not loaded. Ensure camera-controller.js is included before viewer-app.js.');
}

class ViewerSettingsPanel {
    constructor(app) {
        this.app = app;
    }

    render() {
        return html`
            <section id="render-controls" aria-label="Viewer options">
                <label>
                    <input id="center-gizmo-toggle" type="checkbox" ?checked=${this.app.showCenterGizmo}>
                    center gizmo
                </label>
                <label>
                    <input id="edges-toggle" type="checkbox" ?checked=${this.app.edgesEnabled}>
                    edges
                </label>
                <label>
                    edge line visibility (${this.app.edgeLineVisibilityPercent}%)
                    <input
                        id="edge-visibility-slider"
                        type="range"
                        min="0"
                        max="100"
                        step="5"
                        .value=${String(this.app.edgeLineVisibilityPercent)}>
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
                    geometry
                    <select id="geometry-mode-select" .value=${this.app.viewerOptions && this.app.viewerOptions.geometryMode || 'actual'}>
                        <option value="actual">actual</option>
                        <option value="perfectAabb">perfect AABB</option>
                    </select>
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
                    theme
                    <select id="theme-select" .value=${this.app.activeTheme}>
                        ${Object.entries(THEMES).map(([themeId, theme]) => html`<option value=${themeId}>${theme.label}</option>`)}
                    </select>
                </label>
                <label>
                    <input id="export-individual-toggle" type="checkbox" ?checked=${this.app.exportIndividualsEnabled}>
                    also export timbers as individual files
                </label>
                <label>
                    <input id="export-accessories-toggle" type="checkbox" ?checked=${this.app.exportAccessoriesEnabled}>
                    export accessories
                </label>
                <button
                    id="save-settings-btn"
                    type="button"
                    title="Save current viewer options to .kigumi/kigumi-settings.json"
                    @click=${() => {
                        if (vscode) {
                            vscode.postMessage({
                                type: 'requestSaveViewerSettings',
                                settings: this.app.collectViewerSettingsPayload(),
                            });
                        }
                    }}>save settings</button>
                <button
                    id="export-stl-btn"
                    type="button"
                    title="Export frame members to STL files"
                    @click=${() => {
                        if (vscode) {
                            vscode.postMessage({
                                type: 'requestExportStl',
                                includeIndividuals: this.app.exportIndividualsEnabled,
                                includeAccessories: this.app.exportAccessoriesEnabled,
                            });
                        }
                    }}>export STL</button>
                ${this.app.cadqueryOcpInstalled === false
                    ? html`<button
                        id="install-cadquery-ocp-btn"
                        type="button"
                        title="Install cadquery-ocp for STEP export"
                        ?disabled=${this.app.installingCadqueryOcp === true}
                        @click=${() => {
                            if (vscode) {
                                vscode.postMessage({ type: 'requestInstallCadqueryOcp' });
                            }
                        }}>${this.app.installingCadqueryOcp === true
                            ? 'installing cadquery...'
                            : 'install cadquery, needed for STEP export'}</button>`
                    : html`<button
                        id="export-step-btn"
                        type="button"
                        title="Export frame members to STEP files"
                        ?disabled=${this.app.cadqueryOcpInstalled === null}
                        @click=${() => {
                            if (vscode) {
                                vscode.postMessage({
                                    type: 'requestExportStep',
                                    includeIndividuals: this.app.exportIndividualsEnabled,
                                    includeAccessories: this.app.exportAccessoriesEnabled,
                                });
                            }
                        }}>export STEP</button>`}
            </section>
        `;
    }

    bindEvents(renderRoot) {
        const centerGizmoToggle = renderRoot.querySelector('#center-gizmo-toggle');
        const edgesToggle = renderRoot.querySelector('#edges-toggle');
        const edgeVisibilitySlider = renderRoot.querySelector('#edge-visibility-slider');
        const shadowsToggle = renderRoot.querySelector('#shadows-toggle');
        const reflectionsToggle = renderRoot.querySelector('#reflections-toggle');
        const unselectedTransparencySlider = renderRoot.querySelector('#unselected-transparency-slider');
        const debugToggle = renderRoot.querySelector('#debug-toggle');
        const exportIndividualToggle = renderRoot.querySelector('#export-individual-toggle');
        const exportAccessoriesToggle = renderRoot.querySelector('#export-accessories-toggle');
        const themeSelect = renderRoot.querySelector('#theme-select');

        centerGizmoToggle.addEventListener('change', (event) => {
            this.app.setCenterGizmoEnabled(event.target.checked);
        });

        edgesToggle.addEventListener('change', (event) => {
            this.app.setEdgesEnabled(event.target.checked);
        });

        edgeVisibilitySlider.addEventListener('input', (event) => {
            const rawPercent = Number(event.target.value);
            const normalizedPercent = Number.isFinite(rawPercent)
                ? Math.max(0, Math.min(100, Math.round(rawPercent / 5) * 5))
                : 100;
            this.app.setEdgeLineVisibilityPercent(normalizedPercent);
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

        exportIndividualToggle.addEventListener('change', (event) => {
            this.app.setExportIndividualsEnabled(event.target.checked);
        });

        exportAccessoriesToggle.addEventListener('change', (event) => {
            this.app.setExportAccessoriesEnabled(event.target.checked);
        });

        unselectedTransparencySlider.addEventListener('input', (event) => {
            const rawVisibility = Number(event.target.value);
            const normalizedVisibility = Number.isFinite(rawVisibility)
                ? Math.max(5, Math.min(100, Math.round(rawVisibility / 5) * 5))
                : 60;
            this.app.setUnselectedTransparencyPercent(100 - normalizedVisibility);
        });

        themeSelect.addEventListener('change', (event) => {
            this.app.setTheme(event.target.value);
        });

        const geometryModeSelect = renderRoot.querySelector('#geometry-mode-select');
        if (geometryModeSelect) {
            geometryModeSelect.addEventListener('change', (event) => {
                this.app.setGeometryMode(event.target.value);
            });
        }
    }

    syncControls(renderRoot) {
        const edgeVisibilitySlider = renderRoot.querySelector('#edge-visibility-slider');
        const unselectedTransparencySlider = renderRoot.querySelector('#unselected-transparency-slider');
        const exportIndividualToggle = renderRoot.querySelector('#export-individual-toggle');
        const exportAccessoriesToggle = renderRoot.querySelector('#export-accessories-toggle');
        const themeSelect = renderRoot.querySelector('#theme-select');
        if (edgeVisibilitySlider) {
            edgeVisibilitySlider.value = String(this.app.edgeLineVisibilityPercent);
        }
        if (unselectedTransparencySlider) {
            unselectedTransparencySlider.value = String(100 - this.app.unselectedTransparencyPercent);
        }
        if (exportIndividualToggle) {
            exportIndividualToggle.checked = this.app.exportIndividualsEnabled;
        }
        if (exportAccessoriesToggle) {
            exportAccessoriesToggle.checked = this.app.exportAccessoriesEnabled;
        }
        if (themeSelect) {
            themeSelect.value = this.app.activeTheme;
        }
        const geometryModeSelect = renderRoot.querySelector('#geometry-mode-select');
        if (geometryModeSelect && this.app.viewerOptions) {
            geometryModeSelect.value = this.app.viewerOptions.geometryMode || 'actual';
        }
    }
}

class ViewerParameterPanel {
    constructor(app) {
        this.app = app;
    }

    formatV3Display(value) {
        const vector = normalizeV3RenderParameterValue(value);
        return `[${vector.x},${vector.y},${vector.z}]`;
    }

    getParameterTypeLabel(param) {
        if (param.kind === 'v3') return '(x,y,z)';
        if (param.kind === 'enum') return '(enum)';
        if (param.kind === 'boolean') return '(bool)';
        if (param.kind === 'number') return '(number)';
        return '(string)';
    }

    renderVector3Input(param, inputId, value, disabled) {
        const vector = normalizeV3RenderParameterValue(value);
        return html`
            <div class="parameter-vector3" style=${disabled ? 'opacity:0.52;' : 'opacity:1;'}>
                ${['x', 'y', 'z'].map((axis) => html`
                    <input
                        id=${`${inputId}-${axis}`}
                        class="parameter-vector3-component"
                        type="text"
                        placeholder=${axis}
                        .value=${vector[axis]}
                        ?disabled=${disabled}
                        @input=${(event) => this.app.setPendingRenderParameterComponentValue(param, axis, event.target.value)}>
                `)}
            </div>
        `;
    }

    renderParameterControl(param, inputId, value, options = {}) {
        const { disabled = false, inline = false } = options;

        if (param.kind === 'boolean') {
            return html`
                <label class="parameter-control-boolean">
                    <input
                        id=${inputId}
                        type="checkbox"
                        ?checked=${Boolean(value)}
                        ?disabled=${disabled}
                        @change=${(event) => this.app.setPendingRenderParameterValue(param.name, Boolean(event.target.checked))}>
                    <span>enabled</span>
                </label>
            `;
        }

        if (param.kind === 'enum') {
            const optionsList = Array.isArray(param.options) ? param.options : [];
            return html`
                <select
                    id=${inputId}
                    class="parameter-control-select"
                    .value=${String(value ?? '')}
                    ?disabled=${disabled}
                    @change=${(event) => this.app.setPendingRenderParameterValue(param.name, String(event.target.value))}>
                    ${optionsList.map((option) => html`<option value=${option}>${option}</option>`)}
                </select>
            `;
        }

        if (param.kind === 'v3') {
            return this.renderVector3Input(param, inputId, value, disabled);
        }

        return html`
            <input
                id=${inputId}
                class="parameter-control-text"
                type="text"
                .value=${String(value ?? '')}
                ?disabled=${disabled}
                @input=${(event) => this.app.setPendingRenderParameterValue(param.name, event.target.value)}>
        `;
    }

    renderParameterInput(param, index) {
        const inputId = `render-param-${index}-${param.name}`;
        const value = this.app.getPendingRenderParameterValue(param);
        const typeLabel = this.getParameterTypeLabel(param);
        
        if (!param.optional) {
            const displayValue = param.kind === 'v3' ? this.formatV3Display(value) : String(value ?? '');
            return html`
                <div class="parameter-row">
                    <div class="parameter-row-header">
                        <span class="parameter-name">${param.name}</span>
                        <span class="parameter-type">${typeLabel}</span>
                        <span class="parameter-value">${displayValue}</span>
                    </div>
                    <div class="parameter-row-control">
                        ${this.renderParameterControl(param, inputId, value)}
                    </div>
                </div>
            `;
        }

        const enabled = this.app.isOptionalRenderParameterEnabled(param);
        const editorValue = this.app.getRenderParameterEditorValue(param);
        const displayValue = enabled ? (param.kind === 'v3' ? this.formatV3Display(editorValue) : String(editorValue ?? '')) : 'none';
        
        return html`
            <div class="parameter-row parameter-row-optional" style=${enabled ? 'opacity:1;' : 'opacity:0.62;'}>
                <div class="parameter-row-header">
                    <label class="parameter-checkbox" for=${`${inputId}-enabled`}>
                        <input
                            id=${`${inputId}-enabled`}
                            type="checkbox"
                            ?checked=${enabled}
                            @change=${(event) => this.app.setOptionalRenderParameterEnabled(param, Boolean(event.target.checked))}>
                        <span class="parameter-name">${param.name}</span>
                    </label>
                    <span class="parameter-type">${typeLabel}</span>
                    <span class="parameter-value">${displayValue}</span>
                </div>
                <div class="parameter-row-control">
                    ${this.renderParameterControl(param, inputId, editorValue, { disabled: !enabled })}
                </div>
            </div>
        `;
    }

    render() {
        const params = this.app.renderParameterSchema;
        const hasPendingChanges = this.app.hasPendingRenderParameterChanges();
        return html`
            <section id="parameter-controls" aria-label="Frame parameters">
                <div class="parameter-header">
                    <div class="parameter-controls-title">frame parameters</div>
                    <div class="parameter-refresh-controls">
                        ${hasPendingChanges
                            ? html`<span class="parameter-changes-indicator">changes detected</span>`
                            : ''}
                        <button
                            id="refresh-btn"
                            type="button"
                            title="Refresh using current parameter values"
                            @click=${() => this.app.requestRefreshWithPendingParameters()}>refresh</button>
                    </div>
                </div>
                ${params.length === 0
                    ? html`<div class="parameter-empty">No parameters exposed by this frame or pattern.</div>`
                    : html`
                        <div class="parameter-list">
                            ${params.map((param, index) => html`
                                <div class="parameter-container">
                                    ${this.renderParameterInput(param, index)}
                                    ${param.description
                                        ? html`<div class="parameter-description">${param.description}</div>`
                                        : ''}
                                </div>
                            `)}
                        </div>
                    `}
            </section>
        `;
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
        this.cameraController = new CameraController({ THREE });

        // Forward orbit-camera state from this.cameraController onto this for
        // backwards compatibility with the rest of the viewer-app code that still
        // reads/writes things like this.cx, this.orbitDist, etc.
        const FORWARDED_CAMERA_FIELDS = [
            'cx', 'cy', 'cz',
            'orbitDist',
            'cameraOffsetDir', 'cameraUpVector',
            'cameraAnimation',
            'dragOrbitUpAxis', 'dragOrbitRightAxis',
        ];
        for (const field of FORWARDED_CAMERA_FIELDS) {
            Object.defineProperty(this, field, {
                get() { return this.cameraController[field]; },
                set(value) { this.cameraController[field] = value; },
                configurable: true,
                enumerable: true,
            });
        }

        this.mouseAction = null;
        this.lastX = 0;
        this.lastY = 0;

        this.showCenterGizmo = true;
        this.edgesEnabled = true;
        this.shadowsEnabled = false;
        this.reflectionsEnabled = true;
        this.debugEnabled = false;
        this.logFilterText = '';
        this.memberListRoughLengthAllowanceMm = 30;
        this.memberListOptions = {
            showRoughLength: false,
            showNominalSizes: true,
            showCsgFeatureCount: true,
            showTags: true,
        };

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
        this.layerStatesByKey = new Map(); // member key -> { locked, hidden, fixed }
        this.renderProfiles = RENDER_PROFILES;
        this.memberRenderProfileByType = {
            timber: 'timber-default',
            accessory: 'accessory-cute',
        };
        this.edgeLineVisibilityPercent = 100;
        this.unselectedTransparencyPercent = 70;
        this.activeTheme = 'forest';
        this.activeBackground = this.activeTheme;

        this.animationHandle = null;
        this.viewState = createInitialViewState();
        this.currentFrameData = {};
        this.renderParameterSchema = [];
        this.appliedRenderParameters = {};
        this.pendingRenderParameters = {};
        this.renderParameterDraftValues = {};
        this.viewerOptions = normalizeViewerOptions(INITIAL_PAYLOAD.viewerOptions);
        this.cadqueryOcpInstalled = null;
        this.installingCadqueryOcp = false;
        this.exportIndividualsEnabled = false;
        this.exportAccessoriesEnabled = true;
        this.settingsPanel = new ViewerSettingsPanel(this);
        this.parameterPanel = new ViewerParameterPanel(this);
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
        this.onLayerStateChanged = this.onLayerStateChanged.bind(this);
        this.onLayerStateSync = this.onLayerStateSync.bind(this);
    }

    createRenderRoot() {
        return this;
    }

    render() {
        const cameraMode = this.cameraController.getCameraMode();
        return html`
            <button id="to-v3d" title="Jump back to 3D view">to v3d view</button>
            <div id="viewport">
                <canvas id="c"></canvas>
                <div id="loading-overlay" class=${this.isOverlayVisible() ? 'visible' : ''}>
                    <div id="loading-text">${this.viewState.loadingText}</div>
                    <button id="output-btn" type="button" title="Open Kigumi output channel" style="display: ${this.viewState.showOutputLink ? 'block' : 'none'}">view output</button>
                </div>
                <div id="info"></div>
                <kigumi-layers-view id="layers-view"></kigumi-layers-view>
                <div id="gizmo-panel" aria-label="Camera and light gizmos">
                    <div class="gizmo-block">
                        <div class="gizmo-title">camera</div>
                        <canvas id="gizmo-cube-c"></canvas>
                    </div>
                    <button id="focus-btn" type="button" title="Focus selection">focus</button>
                    <button
                        id="camera-mode-btn"
                        type="button"
                        title="Toggle camera mode: standard keeps camera up aligned to world Z"
                    >📷 ${cameraMode === 'standard' ? 'standard' : 'free'}</button>
                    <div class="gizmo-block">
                        <div class="gizmo-title">light</div>
                        <canvas id="light-dial-c"></canvas>
                    </div>
                </div>
                <div id="debug"></div>
                <div id="hint">right drag orbit • middle drag pan • scroll zoom • F focus</div>
            </div>
            <div id="top-controls">
                ${this.settingsPanel.render()}
                ${this.parameterPanel.render()}
            </div>
            <div id="panels">
                <div class="panel-box">
                    <div class="panel-title">Member List</div>
                    <div id="member-list-options" aria-label="Member list options">
                        <label>
                            <input id="member-opt-rough-length" type="checkbox" ?checked=${this.memberListOptions.showRoughLength}>
                            show rough length (exact + ${this.memberListRoughLengthAllowanceMm})
                        </label>
                        <label>
                            <input id="member-opt-sizes" type="checkbox" ?checked=${this.memberListOptions.showNominalSizes}>
                            show perfect timber within/nominal sizes
                        </label>
                        <label>
                            <input id="member-opt-csg" type="checkbox" ?checked=${this.memberListOptions.showCsgFeatureCount}>
                            show CSG/feature count
                        </label>
                        <label>
                            <input id="member-opt-tags" type="checkbox" ?checked=${this.memberListOptions.showTags}>
                            show tags
                        </label>
                    </div>
                    <details id="member-list-legend" open>
                        <summary>Legend</summary>
                        <div class="member-list-legend-body">
                            <p><strong>length</strong>: exact length of timber after making all joint cuts (add a bit to this for rough cut length) / rough cut length (depending on option)</p>
                            <p><strong>size toggle</strong>: when enabled, width/height columns show nominal sizes (from get_nominal_size). when disabled, they show perfect sizes (from get_perfect_size).</p>
                            <p><strong>#CSGs</strong>: total constructive solid geometry nodes used for the member.</p>
                            <p><strong>#Features</strong>: number of named CSG features on that member.</p>
                            <p><strong>tags</strong>: all ticket tags attached to the member.</p>
                        </div>
                    </details>
                    <div id="timber-panel">
                        <table>
                            <thead>
                                <tr>
                                    <th>#</th><th>Type</th><th>Name</th>
                                    <th data-col="tags">Tags</th>
                                    <th data-col="length">Length (Exact)</th><th data-col="width">Width</th><th data-col="height">Height</th>
                                    <th data-col="csg">#CSGs</th><th data-col="feature">#Features</th>
                                </tr>
                            </thead>
                            <tbody id="timber-rows"></tbody>
                        </table>
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
                <div class="panel-box">
                    <div class="panel-title">Raw Python Output</div>
                    <pre id="raw-output"></pre>
                </div>
            </div>
        `;
    }

    firstUpdated() {
        this.setupUiEvents();
        this.setupThreeScene();
        window.addEventListener('message', this.onWindowMessage);
        this.applyPersistedViewerSettings(INITIAL_PAYLOAD.viewerSettings || null);
        this.setViewerOptions(INITIAL_PAYLOAD.viewerOptions);
        this.setViewPhase(ViewerPhase.WAITING_FOR_RUNNER, 'raising frame', { refreshToken: 0 });
        void this.beginPayloadApplication(INITIAL_PAYLOAD);
        
        // Setup selection listener
        this.selectionManager.onSelectionChanged((event) => {
            if (event.type === 'clear-timbers' || event.type === 'timber-selected') {
                // Only clear CSG when the timber change is a "fresh" user
                // action (not caused by layers-view setting CSG first, which
                // also selects the timber for opacity purposes).
                if (!this.selectionManager.csgSelection) {
                    this.removeCSGHighlight();
                }
            }
            this.applySelectionOpacity();
            this.updateInfo(this.currentFrameData);
        });

        // Attach Layers panel to selection store + extension messaging.
        const layersView = this.renderRoot.querySelector('#layers-view');
        if (layersView && typeof layersView.attach === 'function') {
            layersView.attach(this.selectionManager, vscode);
        }
        this._layersView = layersView;
        if (this._layersView) {
            this._layersView.addEventListener('layer-state-changed', this.onLayerStateChanged);
            this._layersView.addEventListener('layer-state-sync', this.onLayerStateSync);
        }
        if (vscode) {
            vscode.postMessage({ type: 'requestLayersTree' });
        }

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
        if (this._layersView) {
            this._layersView.removeEventListener('layer-state-changed', this.onLayerStateChanged);
            this._layersView.removeEventListener('layer-state-sync', this.onLayerStateSync);
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

    onLayerStateChanged(event) {
        const detail = event && event.detail ? event.detail : {};
        const key = detail.key;
        if (typeof key !== 'string' || key.length === 0) {
            return;
        }
        const state = detail.state && typeof detail.state === 'object' ? detail.state : null;
        if (state) {
            this.layerStatesByKey.set(key, state);
        }
        if (detail.prop === 'locked' && detail.value === true) {
            if (this.selectionManager.isTimberSelected(key)) {
                this.selectionManager.clearCSGSelection();
                this.removeCSGHighlight();
                this.selectionManager.deselectTimber(key);
            }
        }
        this.applySelectionOpacity();
    }

    onLayerStateSync(event) {
        const detail = event && event.detail ? event.detail : {};
        const states = detail.states && typeof detail.states === 'object' ? detail.states : {};
        this.layerStatesByKey.clear();
        for (const [key, state] of Object.entries(states)) {
            if (typeof key === 'string' && key.length > 0 && state && typeof state === 'object') {
                this.layerStatesByKey.set(key, state);
            }
        }
        this.applySelectionOpacity();
    }

    isMemberHidden(memberKey) {
        const state = this.layerStatesByKey.get(memberKey);
        return Boolean(state && state.hidden);
    }

    isMemberLocked(memberKey) {
        const state = this.layerStatesByKey.get(memberKey);
        return Boolean(state && state.locked);
    }

    setupUiEvents() {
        const toV3d = this.renderRoot.querySelector('#to-v3d');
        const canvas = this.renderRoot.querySelector('#c');
        const viewport = this.renderRoot.querySelector('#viewport');
        const gizmoCanvas = this.renderRoot.querySelector('#gizmo-cube-c');
        const focusButton = this.renderRoot.querySelector('#focus-btn');
        const cameraModeButton = this.renderRoot.querySelector('#camera-mode-btn');
        const lightDialCanvas = this.renderRoot.querySelector('#light-dial-c');

        toV3d.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });

        canvas.addEventListener('mousedown', (event) => {
            if (event.button === 2) {
                this.mouseAction = 'orbit';
                this.cameraController.captureOrbitDragFrame();
            } else if (event.button === 1) {
                this.mouseAction = 'pan';
            } else {
                return;
            }
            event.preventDefault();
            this.lastX = event.clientX;
            this.lastY = event.clientY;
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

        const memberOptRoughLength = this.renderRoot.querySelector('#member-opt-rough-length');
        const memberOptSizes = this.renderRoot.querySelector('#member-opt-sizes');
        const memberOptCsg = this.renderRoot.querySelector('#member-opt-csg');
        const memberOptTags = this.renderRoot.querySelector('#member-opt-tags');

        if (memberOptRoughLength) {
            memberOptRoughLength.addEventListener('change', (event) => {
                this.memberListOptions.showRoughLength = Boolean(event.target.checked);
                this._refreshMemberList();
            });
        }
        if (memberOptSizes) {
            memberOptSizes.addEventListener('change', (event) => {
                this.memberListOptions.showNominalSizes = Boolean(event.target.checked);
                this._refreshMemberList();
            });
        }
        if (memberOptCsg) {
            memberOptCsg.addEventListener('change', (event) => {
                this.memberListOptions.showCsgFeatureCount = Boolean(event.target.checked);
                this._applyMemberListOptionVisibility();
            });
        }
        if (memberOptTags) {
            memberOptTags.addEventListener('change', (event) => {
                this.memberListOptions.showTags = Boolean(event.target.checked);
                this._applyMemberListOptionVisibility();
            });
        }

        this._applyMemberListOptionVisibility();

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
            preserveDrawingBuffer: true,
        });
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.setSize(viewport.offsetWidth, viewport.offsetHeight, false);
        this.renderer.outputEncoding = THREE.sRGBEncoding;
        this.renderer.shadowMap.enabled = false;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

        this.scene = new THREE.Scene();
        this.setTheme(this.activeTheme);

        this.camera = new THREE.PerspectiveCamera(45, viewport.offsetWidth / viewport.offsetHeight, 0.01, 10000);
        this.camera.up.set(0, 0, 1);

        this.scene.add(new THREE.AmbientLight(0xffffff, 0.61));
        this.sun = new THREE.DirectionalLight(0xffffff, 0.62);
        this.sun.position.set(2, 1, 18);
        this.sun.castShadow = true;
        this.sun.shadow.bias = -0.00008;
        this.sun.shadow.mapSize.set(2048, 2048);
        this.scene.add(this.sun);
        const fill = new THREE.DirectionalLight(0xd8e3f5, 0.34);
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
            : 70;
        if (this.unselectedTransparencyPercent === normalizedPercent) {
            return;
        }
        this.unselectedTransparencyPercent = normalizedPercent;
        this.requestUpdate();
        this.applySelectionOpacity();
    }

    setEdgeLineVisibilityPercent(nextPercent) {
        const normalizedPercent = Number.isFinite(nextPercent)
            ? Math.max(0, Math.min(100, Math.round(nextPercent / 5) * 5))
            : 100;
        if (this.edgeLineVisibilityPercent === normalizedPercent) {
            return;
        }
        this.edgeLineVisibilityPercent = normalizedPercent;
        this.requestUpdate();
        this.applySelectionOpacity();
    }

    setExportIndividualsEnabled(enabled) {
        const normalized = Boolean(enabled);
        if (this.exportIndividualsEnabled === normalized) {
            return;
        }
        this.exportIndividualsEnabled = normalized;
        this.requestUpdate();
    }

    setExportAccessoriesEnabled(enabled) {
        const normalized = Boolean(enabled);
        if (this.exportAccessoriesEnabled === normalized) {
            return;
        }
        this.exportAccessoriesEnabled = normalized;
        this.requestUpdate();
    }

    collectViewerSettingsPayload() {
        return {
            version: 1,
            viewerOptions: { ...this.viewerOptions },
            ui: {
                showCenterGizmo: Boolean(this.showCenterGizmo),
                edgesEnabled: Boolean(this.edgesEnabled),
                edgeLineVisibilityPercent: Number(this.edgeLineVisibilityPercent),
                shadowsEnabled: Boolean(this.shadowsEnabled),
                reflectionsEnabled: Boolean(this.reflectionsEnabled),
                debugEnabled: Boolean(this.debugEnabled),
                unselectedTransparencyPercent: Number(this.unselectedTransparencyPercent),
                activeTheme: String(this.activeTheme || 'forest'),
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
        if (typeof ui.edgesEnabled === 'boolean') {
            this.setEdgesEnabled(ui.edgesEnabled);
        }
        if (Number.isFinite(ui.edgeLineVisibilityPercent)) {
            this.setEdgeLineVisibilityPercent(Number(ui.edgeLineVisibilityPercent));
        }
        if (typeof ui.shadowsEnabled === 'boolean') {
            this.setShadowsEnabled(ui.shadowsEnabled);
        }
        if (typeof ui.reflectionsEnabled === 'boolean') {
            this.setReflectionsEnabled(ui.reflectionsEnabled);
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
        if (Number.isFinite(ui.unselectedTransparencyPercent)) {
            this.setUnselectedTransparencyPercent(Number(ui.unselectedTransparencyPercent));
        }
        if (typeof ui.activeTheme === 'string') {
            this.setTheme(ui.activeTheme);
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

    setRenderParametersFromFrame(frameData) {
        const contract = frameData && frameData.renderParameters && typeof frameData.renderParameters === 'object'
            ? frameData.renderParameters
            : null;
        if (!contract) {
            return;
        }

        const schema = Array.isArray(contract.schema) ? contract.schema : [];
        this.renderParameterSchema = schema
            .filter((entry) => entry && typeof entry === 'object' && typeof entry.name === 'string' && entry.name.length > 0)
            .map((entry) => ({
                name: entry.name,
                kind: typeof entry.kind === 'string' ? entry.kind : 'string',
                description: typeof entry.description === 'string' ? entry.description : '',
                default: Object.prototype.hasOwnProperty.call(entry, 'default') ? entry.default : '',
                options: Array.isArray(entry.options) ? entry.options.map((option) => String(option)) : [],
                optional: Boolean(entry.optional),
            }));

        const applied = contract.applied && typeof contract.applied === 'object' ? contract.applied : {};
        this.appliedRenderParameters = { ...applied };
        this.pendingRenderParameters = { ...applied };
        this.renderParameterDraftValues = Object.fromEntries(
            this.renderParameterSchema.map((parameter) => {
                const value = Object.prototype.hasOwnProperty.call(applied, parameter.name)
                    ? applied[parameter.name]
                    : parameter.default;
                return [parameter.name, normalizeRenderParameterEditorValue(parameter, value)];
            }),
        );
        this.requestUpdate();
    }

    getPendingRenderParameterValue(parameter) {
        if (Object.prototype.hasOwnProperty.call(this.pendingRenderParameters, parameter.name)) {
            return this.pendingRenderParameters[parameter.name];
        }
        return parameter.default;
    }

    getRenderParameterEditorValue(parameter) {
        if (Object.prototype.hasOwnProperty.call(this.renderParameterDraftValues, parameter.name)) {
            return this.renderParameterDraftValues[parameter.name];
        }
        return normalizeRenderParameterEditorValue(parameter, this.getPendingRenderParameterValue(parameter));
    }

    isOptionalRenderParameterEnabled(parameter) {
        if (!parameter.optional) {
            return true;
        }
        const value = this.getPendingRenderParameterValue(parameter);
        return value != null;
    }

    findRenderParameter(name) {
        return this.renderParameterSchema.find((parameter) => parameter.name === name) || null;
    }

    setOptionalRenderParameterEnabled(parameter, enabled) {
        const nextDrafts = { ...this.renderParameterDraftValues };
        const currentValue = this.getPendingRenderParameterValue(parameter);
        if (currentValue != null) {
            nextDrafts[parameter.name] = normalizeRenderParameterEditorValue(parameter, currentValue);
        }
        this.renderParameterDraftValues = nextDrafts;

        this.pendingRenderParameters = {
            ...this.pendingRenderParameters,
            [parameter.name]: enabled
                ? cloneRenderParameterValue(parameter, this.getRenderParameterEditorValue(parameter))
                : null,
        };
        this.requestUpdate();
    }

    setPendingRenderParameterValue(name, value) {
        const parameter = this.findRenderParameter(name);
        if (!parameter) {
            return;
        }
        const normalizedValue = normalizeRenderParameterEditorValue(parameter, value);
        this.renderParameterDraftValues = {
            ...this.renderParameterDraftValues,
            [name]: normalizedValue,
        };
        this.pendingRenderParameters = {
            ...this.pendingRenderParameters,
            [name]: cloneRenderParameterValue(parameter, normalizedValue),
        };
        this.requestUpdate();
    }

    setPendingRenderParameterComponentValue(parameter, component, value) {
        const current = normalizeV3RenderParameterValue(this.getRenderParameterEditorValue(parameter));
        const nextValue = {
            ...current,
            [component]: value,
        };
        this.setPendingRenderParameterValue(parameter.name, nextValue);
    }

    hasPendingRenderParameterChanges() {
        const schema = Array.isArray(this.renderParameterSchema) ? this.renderParameterSchema : [];
        for (const parameter of schema) {
            const pendingValue = this.getPendingRenderParameterValue(parameter);
            const appliedValue = Object.prototype.hasOwnProperty.call(this.appliedRenderParameters, parameter.name)
                ? this.appliedRenderParameters[parameter.name]
                : parameter.default;
            if (JSON.stringify(normalizeComparableRenderParameterValue(parameter, pendingValue))
                !== JSON.stringify(normalizeComparableRenderParameterValue(parameter, appliedValue))) {
                return true;
            }
        }
        return false;
    }

    requestRefreshWithPendingParameters() {
        if (!vscode) {
            return;
        }
        vscode.postMessage({
            type: 'requestRefresh',
            renderParameters: { ...this.pendingRenderParameters },
        });
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

        if (message.type === 'capturePanelSnapshotRequest') {
            this.handleCapturePanelSnapshotRequest(message);
            return;
        }

        if (message.type === 'collectPendingRenderParametersRequest') {
            this.handleCollectPendingRenderParametersRequest(message);
            return;
        }

        if (message.type === 'getCameraStateRequest') {
            this.handleGetCameraStateRequest(message);
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

        if (message.type === 'csgSelectionResult') {
            this.handleCSGSelectionResult(message);
            return;
        }

        if (message.type === 'layersTree') {
            if (this._layersView && typeof this._layersView.setLayersPayload === 'function') {
                this._layersView.setLayersPayload(message.payload || {});
            }
            return;
        }

        if (message.type === 'csgTree') {
            if (this._layersView && typeof this._layersView.mergeCSGTreePayload === 'function') {
                this._layersView.mergeCSGTreePayload(message.payload || {});
            }
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

        await new Promise((resolve) => requestAnimationFrame(() => resolve()));

        try {
            if (this.renderer && this.scene && this.camera) {
                this.renderer.render(this.scene, this.camera);
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

    handleCollectPendingRenderParametersRequest(message) {
        const requestId = message && message.requestId;
        if (!vscode || !requestId) {
            return;
        }

        try {
            vscode.postMessage({
                type: 'collectPendingRenderParametersResult',
                requestId,
                ok: true,
                payload: {
                    renderParameters: { ...this.pendingRenderParameters },
                },
            });
        } catch (error) {
            vscode.postMessage({
                type: 'collectPendingRenderParametersResult',
                requestId,
                ok: false,
                error: error && error.message ? error.message : 'Failed to read pending render parameters',
            });
        }
    }

    handleGetCameraStateRequest(message) {
        const requestId = message && message.requestId;
        if (!vscode || !requestId) {
            return;
        }
        try {
            vscode.postMessage({
                type: 'getCameraStateResult',
                requestId,
                ok: true,
                payload: this.buildCameraStatePayload(),
            });
        } catch (error) {
            vscode.postMessage({
                type: 'getCameraStateResult',
                requestId,
                ok: false,
                error: error && error.message ? error.message : 'Failed to read camera state',
            });
        }
    }

    handleSetCameraStateRequest(message) {
        const requestId = message && message.requestId;
        if (!vscode || !requestId) {
            return;
        }
        try {
            const cameraState = message && message.cameraState && typeof message.cameraState === 'object'
                ? message.cameraState
                : {};
            this.cameraController.applyStatePayload(cameraState);
            this.requestUpdate();
            this.updateCamera();

            vscode.postMessage({
                type: 'setCameraStateResult',
                requestId,
                ok: true,
                payload: this.buildCameraStatePayload(),
            });
        } catch (error) {
            vscode.postMessage({
                type: 'setCameraStateResult',
                requestId,
                ok: false,
                error: error && error.message ? error.message : 'Failed to set camera state',
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
            this.cameraController.applyOrbitDelta(
                event.clientX - this.lastX,
                event.clientY - this.lastY,
            );
        } else if (this.mouseAction === 'pan') {
            this.panCameraInViewPlane(this.lastX, this.lastY, event.clientX, event.clientY);
        }
        this.lastX = event.clientX;
        this.lastY = event.clientY;
        this.cameraController.cancelAnimation();
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

        const targetMeshes = [];
        for (const [memberKey, bundle] of this.meshObjectsByKey.entries()) {
            if (this.isMemberHidden(memberKey) || this.isMemberLocked(memberKey)) {
                continue;
            }
            targetMeshes.push(bundle.mesh);
        }
        const intersects = this.navigationRaycaster.intersectObjects(targetMeshes, false);

        if (intersects.length === 0) {
            this.selectionManager.clearLayerSelection();
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
        console.log('[csg-nav] click: allHits=' + JSON.stringify(allHitKeys) +
            ', selectedTimbers=' + JSON.stringify(this.selectionManager.getSelectedTimbers()) +
            ', csgSelection=' + JSON.stringify(this.selectionManager.csgSelection));

        this.selectionManager.clearLayerSelection();

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

        const baseUnselectedOpacity = 1 - (this.unselectedTransparencyPercent / 100);
        const visualContext = this._getSelectionVisualContext();
        const policy = this._getSelectionVisualPolicy(visualContext.state, baseUnselectedOpacity);

        // Build highlight geometry
        this.removeCSGHighlight();
        if (featureLabel && parentHlMesh && Array.isArray(parentHlMesh.vertices) && parentHlMesh.vertices.length > 0) {
            // Feature selected: parent CSG gets dim highlight, feature face gets bright highlight
            this._buildHighlightMesh(
                parentHlMesh.vertices,
                parentHlMesh.indices,
                CSG_HIGHLIGHT_COLORS.tagged,
                policy.parentHighlightOpacity,
                '_csgParentHighlightMesh',
            );
            if (hlMesh && Array.isArray(hlMesh.vertices) && hlMesh.vertices.length > 0) {
                this._buildHighlightMesh(
                    hlMesh.vertices,
                    hlMesh.indices,
                    CSG_HIGHLIGHT_COLORS.feature,
                    policy.featureHighlightOpacity,
                    '_csgHighlightMesh',
                );
            }
        } else if (hlMesh && Array.isArray(hlMesh.vertices) && hlMesh.vertices.length > 0 && Array.isArray(hlMesh.indices)) {
            // Tagged CSG selected (no feature): standard highlight
            this._buildHighlightMesh(
                hlMesh.vertices,
                hlMesh.indices,
                CSG_HIGHLIGHT_COLORS.tagged,
                policy.csgHighlightOpacity,
                '_csgHighlightMesh',
            );
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

    _getSelectionVisualContext() {
        const selectedTimbers = this.selectionManager.getSelectedTimbers();
        const selectedTimberSet = new Set(selectedTimbers);
        const hasTimberSelection = selectedTimberSet.size > 0;
        if (!hasTimberSelection) {
            return {
                state: SELECTION_VISUAL_STATES.NOTHING_SELECTED,
                selectedTimberSet,
                hasSubselection: false,
                subselectionTimberKey: null,
            };
        }

        const csg = this.selectionManager.csgSelection;
        const path = csg && Array.isArray(csg.path) ? csg.path : [];
        const featureLabel = csg && csg.featureLabel ? csg.featureLabel : null;
        const csgTimberKey = csg && csg.timberKey ? csg.timberKey : null;
        const hasSubselection = !!csg && (path.length > 0 || !!featureLabel);
        const subselectionTimberKey = hasSubselection
            ? (csgTimberKey || (selectedTimbers.length === 1 ? selectedTimbers[0] : null))
            : null;

        if (!hasSubselection) {
            return {
                state: SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB,
                selectedTimberSet,
                hasSubselection: false,
                subselectionTimberKey: null,
            };
        }

        if (featureLabel) {
            return {
                state: SELECTION_VISUAL_STATES.FEATURE_SELECTED,
                selectedTimberSet,
                hasSubselection: true,
                subselectionTimberKey,
            };
        }

        if (path.length >= 2) {
            return {
                state: SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_WITH_SUB,
                selectedTimberSet,
                hasSubselection: true,
                subselectionTimberKey,
            };
        }

        if (path.length === 1) {
            return {
                state: SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB,
                selectedTimberSet,
                hasSubselection: true,
                subselectionTimberKey,
            };
        }

        return {
            state: SELECTION_VISUAL_STATES.TIMBER_SELECTED_WITH_SUB,
            selectedTimberSet,
            hasSubselection: true,
            subselectionTimberKey,
        };
    }

    _getSelectionVisualPolicy(state, baseUnselectedOpacity) {
        if (state === SELECTION_VISUAL_STATES.NOTHING_SELECTED) {
            return {
                selectedTimberOpacity: 1.0,
                dimmedOpacity: 1.0,
                csgHighlightOpacity: 0.7,
                parentHighlightOpacity: 0.35,
                featureHighlightOpacity: 0.85,
            };
        }

        if (state === SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB) {
            return {
                selectedTimberOpacity: 1.0,
                dimmedOpacity: baseUnselectedOpacity,
                csgHighlightOpacity: 0.7,
                parentHighlightOpacity: 0.35,
                featureHighlightOpacity: 0.85,
            };
        }

        if (state === SELECTION_VISUAL_STATES.FEATURE_SELECTED) {
            return {
                selectedTimberOpacity: 0.62,
                dimmedOpacity: Math.min(baseUnselectedOpacity, 0.18),
                csgHighlightOpacity: 0.9,
                parentHighlightOpacity: 0.35,
                featureHighlightOpacity: 0.9,
            };
        }

        if (state === SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_WITH_SUB) {
            return {
                selectedTimberOpacity: 0.66,
                dimmedOpacity: Math.min(baseUnselectedOpacity, 0.2),
                csgHighlightOpacity: 0.8,
                parentHighlightOpacity: 0.3,
                featureHighlightOpacity: 0.85,
            };
        }

        if (state === SELECTION_VISUAL_STATES.TAGGED_CSG_SELECTED_NO_SUB) {
            return {
                selectedTimberOpacity: 0.72,
                dimmedOpacity: Math.min(baseUnselectedOpacity, 0.25),
                csgHighlightOpacity: 0.72,
                parentHighlightOpacity: 0.35,
                featureHighlightOpacity: 0.85,
            };
        }

        return {
            selectedTimberOpacity: 0.72,
            dimmedOpacity: Math.min(baseUnselectedOpacity, 0.25),
            csgHighlightOpacity: 0.72,
            parentHighlightOpacity: 0.35,
            featureHighlightOpacity: 0.85,
        };
    }

    applySelectionOpacity() {
        const baseUnselectedOpacity = 1 - (this.unselectedTransparencyPercent / 100);
        const visualContext = this._getSelectionVisualContext();
        const policy = this._getSelectionVisualPolicy(visualContext.state, baseUnselectedOpacity);

        for (const [name, bundle] of this.meshObjectsByKey) {
            const isHidden = this.isMemberHidden(name);
            let opacity = 1.0;

            if (visualContext.state === SELECTION_VISUAL_STATES.TIMBER_SELECTED_NO_SUB) {
                opacity = visualContext.selectedTimberSet.has(name) ? 1.0 : policy.dimmedOpacity;
            } else if (visualContext.hasSubselection) {
                const isSubselectionTarget = visualContext.subselectionTimberKey === name;
                opacity = isSubselectionTarget ? policy.selectedTimberOpacity : policy.dimmedOpacity;
            }

            const isTransparent = opacity < 1.0;
            bundle.mesh.visible = !isHidden;
            bundle.mesh.material.transparent = isTransparent;
            bundle.mesh.material.opacity = opacity;
            // Transparent unselected timbers should not cast shadows
            bundle.mesh.castShadow = !isHidden && !isTransparent;
            // Apply matching transparency to edges
            if (bundle.edges && bundle.edges.material) {
                const profile = this.resolveRenderProfile(bundle.profileId);
                const baseEdgeOpacity = profile
                    ? profile.edgeOpacity * (this.edgeLineVisibilityPercent / 100)
                    : (this.edgeLineVisibilityPercent / 100);
                bundle.edges.material.opacity = baseEdgeOpacity * opacity;
                bundle.edges.visible = !isHidden && this.edgesEnabled;
            }
            // Apply matching transparency to reflections
            if (bundle.reflection && bundle.reflection.material) {
                const profile = this.resolveRenderProfile(bundle.profileId);
                const baseReflectionOpacity = profile ? profile.reflectionOpacity : 0.14;
                bundle.reflection.material.opacity = baseReflectionOpacity * opacity;
                bundle.reflection.visible = !isHidden && this.reflectionsEnabled;
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
        this.cameraController.applyOrbitDelta(dx, dy);
        this.gizmoLastX = event.clientX;
        this.gizmoLastY = event.clientY;
        this.cameraController.cancelAnimation();
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
        return this.cameraController.clampPhi(value);
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

    animateCameraTo(targetOffsetDir, targetOrbitDist, durationMs = 260, targetUpVector = null, targetCenter = null) {
        this.cameraController.animateTo({
            offsetDir: targetOffsetDir,
            distance: targetOrbitDist,
            durationMs,
            upVector: targetUpVector,
            center: targetCenter,
        });
    }

    stepCameraAnimation() {
        if (!this.cameraController.hasAnimation()) {
            return;
        }
        this.cameraController.stepAnimation();
        this.updateCamera();
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

    setTheme(id) {
        const theme = THEMES[id];
        if (!theme) {
            return;
        }
        this.activeTheme = id;
        this.activeBackground = id;
        this.memberRenderProfileByType = {
            timber: theme.timberProfileId,
            accessory: theme.accessoryProfileId,
        };
        this.applyThemeUiTokens(theme);
        if (this.scene) {
            const tex = this._buildBackgroundTexture(theme);
            if (this.scene.background && this.scene.background.isTexture) {
                this.scene.background.dispose();
            }
            this.scene.background = tex;
        }
        this.style.background = this._buildCssBg(theme);
        this.applyRenderProfilesToScene();
        this.requestUpdate();
    }

    setBackground(id) {
        this.setTheme(id);
    }

    setGeometryMode(mode) {
        const next = VALID_GEOMETRY_MODES.has(mode) ? mode : 'actual';
        const prev = (this.viewerOptions && this.viewerOptions.geometryMode) || 'actual';
        if (next === prev) {
            return;
        }
        this.viewerOptions = { ...this.viewerOptions, geometryMode: next };

        // Identify timbers whose displayed mesh will actually swap when the mode
        // changes. Only non-perfect timbers carry both meshes; perfect timbers
        // (and accessories) render the same geometry in either mode.
        const lastMeshes = (this._lastGeometryData && this._lastGeometryData.meshes) || [];
        const swappedKeys = new Set();
        for (const mesh of lastMeshes) {
            if (mesh && mesh.memberType === 'timber'
                && mesh.hasActualGeometryDifferentFromPerfect
                && Array.isArray(mesh.perfectAabbVertices)) {
                const key = mesh.memberKey || mesh.timberKey;
                if (key) {
                    swappedKeys.add(key);
                }
            }
        }

        // Feature/CSG selections reference triangles on the actual-geometry mesh;
        // the perfect-AABB mesh is a different surface, so sub-selections become
        // invalid when geometry swaps. Timber-level selection (memberKey) is
        // preserved because identity is keyed by memberKey, not by mesh contents.
        if (swappedKeys.size > 0 && this.selectionManager) {
            const remainingFeatures = (this.selectionManager.selectedFeatures || []).filter(
                (f) => !swappedKeys.has(f.timberName)
            );
            if (remainingFeatures.length !== (this.selectionManager.selectedFeatures || []).length) {
                this.selectionManager.selectedFeatures = remainingFeatures;
                this.selectionManager.emit && this.selectionManager.emit({ type: 'clear-features' });
            }
            const csgSel = this.selectionManager.csgSelection;
            if (csgSel && swappedKeys.has(csgSel.timberKey)) {
                this.selectionManager.clearCSGSelection();
            }
        }

        if (this._lastGeometryData) {
            this.refreshSequence = (this.refreshSequence || 0) + 1;
            const token = this.refreshSequence;
            this.updateMeshScene(this._lastGeometryData, token, null).catch((err) => {
                // eslint-disable-next-line no-console
                console.error('setGeometryMode: updateMeshScene failed', err);
            });
        }

        if (this.settingsPanel && this.renderRoot && this.renderRoot.querySelector) {
            this.settingsPanel.syncControls(this.renderRoot);
        }

        // Persist the mode through the extension so subsequent refreshes start
        // in the same geometry mode. The runner does not need to act on this
        // (both meshes are always sent for non-perfect timbers), but the
        // extension echoes viewerOptions back on payload init.
        if (vscode) {
            vscode.postMessage({ type: 'setRefreshOptions', options: this.viewerOptions });
        }
    }

    setCameraMode(mode) {
        const currentMode = this.cameraController.getCameraMode();
        const nextMode = mode === 'free' ? 'free' : 'standard';
        const shouldAnimateToStandard = currentMode === 'free' && nextMode === 'standard';

        this.cameraController.cancelAnimation();
        this.cameraController.setCameraMode(nextMode, { snapUp: !shouldAnimateToStandard });

        if (shouldAnimateToStandard) {
            const center = this.cameraController.getCenter();
            const offset = this.cameraController.cameraOffsetDir;
            this.cameraController.animateTo({
                offsetDir: { x: offset.x, y: offset.y, z: offset.z },
                upVector: { x: 0, y: 0, z: 1 },
                distance: this.cameraController.orbitDist,
                center: { x: center.x, y: center.y, z: center.z },
                durationMs: 220,
            });
        }

        this.cameraController.clearOrbitDragFrame();
        this.requestUpdate();
        this.updateCamera();
    }

    applyThemeUiTokens(theme) {
        const ui = theme && theme.ui ? theme.ui : DEFAULT_THEME_UI;
        const tokenMap = {
            '--hv-bg-top': ui.bgTop,
            '--hv-bg-bottom': ui.bgBottom,
            '--hv-panel-bg': ui.panelBg,
            '--hv-panel-border': ui.panelBorder,
            '--hv-text': ui.text,
            '--hv-title': ui.title,
            '--hv-dim': ui.dim,
            '--hv-accent': ui.accent,
            '--hv-mesh': ui.mesh,
            '--hv-edge': ui.edge,
            '--hv-strong': ui.strong,
            '--hv-hint': ui.hint,
            '--hv-overlay-bg': ui.overlayBg,
            '--hv-overlay-error-bg': ui.overlayErrorBg,
            '--hv-error': ui.error,
            '--hv-error-hover': ui.errorHover,
            '--hv-error-active': ui.errorActive,
            '--hv-error-fg': ui.errorFg,
            '--hv-debug-accent': ui.debugAccent,
            '--hv-control-bg': ui.controlBg,
            '--hv-control-bg-strong': ui.controlBgStrong,
            '--hv-control-bg-hover': ui.controlBgHover,
            '--hv-control-bg-solid': ui.controlBgSolid,
            '--hv-control-bg-solid-hover': ui.controlBgSolidHover,
            '--hv-control-border': ui.controlBorder,
            '--hv-control-border-strong': ui.controlBorderStrong,
            '--hv-panel-header-bg': ui.panelHeaderBg,
            '--hv-table-head-bg': ui.tableHeadBg,
            '--hv-row-hover-bg': ui.rowHoverBg,
            '--hv-row-border': ui.rowBorder,
            '--hv-row-index': ui.rowIndex,
            '--hv-input-bg': ui.inputBg,
            '--hv-input-border': ui.inputBorder,
            '--hv-accent-soft': ui.accentSoft,
            '--hv-accent-mid': ui.accentMid,
            '--hv-accent-strong': ui.accentStrong,
            '--hv-accent-border': ui.accentBorder,
            '--hv-accent-border-strong': ui.accentBorderStrong,
            '--hv-layers-bg': ui.layersBg,
            '--hv-layers-collapsed-bg': ui.layersCollapsedBg,
            '--hv-layers-header-bg': ui.layersHeaderBg,
            '--hv-layers-hover-bg': ui.layersHoverBg,
            '--hv-layers-selected-bg': ui.layersSelectedBg,
            '--hv-chip-bg': ui.chipBg,
        };
        for (const [cssVar, value] of Object.entries(tokenMap)) {
            this.style.setProperty(cssVar, value);
        }
        this.dataset.theme = ui.mode || 'light';
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
            { x: 0, y: -1, z: 0 },
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
        return this.cameraController.getAdaptiveZoomFactor(isZoomingOut);
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
            { x: this.cameraOffsetDir.x, y: this.cameraOffsetDir.y, z: this.cameraOffsetDir.z },
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
        for (const [memberKey, bundle] of this.meshObjectsByKey.entries()) {
            if (!bundle.reflection) {
                continue;
            }
            bundle.reflection.position.set(0, 0, reflectionOffsetZ);
            bundle.reflection.scale.set(1, 1, -1);
            bundle.reflection.visible = this.reflectionsEnabled && !this.isMemberHidden(memberKey);
        }
    }

    setCenterGizmoEnabled(enabled) {
        this.showCenterGizmo = enabled;
        this.updateOrbitCenterGizmo();
    }

    setEdgesEnabled(enabled) {
        this.edgesEnabled = enabled;
        for (const [memberKey, bundle] of this.meshObjectsByKey.entries()) {
            if (bundle.edges) {
                bundle.edges.visible = enabled && !this.isMemberHidden(memberKey);
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
                opacity: profile.edgeOpacity * (this.edgeLineVisibilityPercent / 100),
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
        bundle.edges.material.opacity = profile.edgeOpacity * (this.edgeLineVisibilityPercent / 100);
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
        return this.cameraController.getCameraSnapForDirection(direction);
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
        this.animateCameraTo(snap.offsetDir, this.orbitDist, 260, snap.upVector);
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
            const tags = Array.isArray(mesh.tags)
                ? mesh.tags.filter((tag) => typeof tag === 'string' && tag.trim().length > 0)
                : [];
            const tagsLabel = tags.length > 0 ? tags.join(', ') : '—';
            const row = document.createElement('tr');
            const lengthValue = this._formatMemberLength(mesh);
            const widthValue = this._formatMemberCrossSection(mesh, 'width');
            const heightValue = this._formatMemberCrossSection(mesh, 'height');
            row.innerHTML = '<td>' + (index + 1) + '</td>' +
                '<td>' + this._escapeHtml(typeLabel) + '</td>' +
                '<td>' + this._escapeHtml(memberName) + '</td>' +
                '<td data-col="tags" class="dim">' + this._escapeHtml(tagsLabel) + '</td>' +
                '<td data-col="length" class="dim">' + lengthValue + '</td>' +
                '<td data-col="width" class="dim">' + widthValue + '</td>' +
                '<td data-col="height" class="dim">' + heightValue + '</td>' +
                '<td data-col="csg" class="dim">' + (mesh.csg_nodes !== undefined ? mesh.csg_nodes : '—') + '</td>' +
                '<td data-col="feature" class="dim">' + (mesh.csg_features !== undefined ? mesh.csg_features : '—') + '</td>';
            tbody.appendChild(row);
        }
        this._applyMemberListOptionVisibility();
    }

    _formatMemberCrossSection(mesh, axis) {
        const nominalKey = axis === 'width' ? 'nominal_width' : 'nominal_height';
        const perfectKey = axis === 'width' ? 'perfect_width' : 'perfect_height';
        const legacyKey = axis === 'width' ? 'prism_width' : 'prism_height';

        const selectedValue = this.memberListOptions.showNominalSizes
            ? mesh[nominalKey]
            : mesh[perfectKey];
        const fallbackValue = mesh[legacyKey];
        const value = selectedValue !== undefined ? selectedValue : fallbackValue;

        if (value === undefined) {
            return '—';
        }
        return this.fmt(value);
    }

    _formatMemberLength(mesh) {
        if (mesh.prism_length === undefined) {
            return '—';
        }

        const exactLengthM = Number(mesh.prism_length);
        if (!Number.isFinite(exactLengthM)) {
            return '—';
        }

        if (this.memberListOptions.showRoughLength) {
            const roughLengthM = exactLengthM + (this.memberListRoughLengthAllowanceMm / 1000);
            return this.fmt(roughLengthM);
        }

        return this.fmt(exactLengthM);
    }

    _refreshMemberList() {
        const meshes = (this._lastGeometryData && this._lastGeometryData.meshes) ? this._lastGeometryData.meshes : [];
        this.rebuildTimberTable(meshes);
    }

    _applyMemberListOptionVisibility() {
        const table = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#timber-panel table')
            : null;
        if (!table) {
            return;
        }

        table.classList.toggle('member-hide-tags', !this.memberListOptions.showTags);
        table.classList.toggle('member-hide-csg', !this.memberListOptions.showCsgFeatureCount);

        const lengthHeader = table.querySelector('th[data-col="length"]');
        if (lengthHeader) {
            lengthHeader.textContent = this.memberListOptions.showRoughLength ? 'Length (Rough)' : 'Length (Exact)';
        }

        const widthHeader = table.querySelector('th[data-col="width"]');
        if (widthHeader) {
            widthHeader.textContent = this.memberListOptions.showNominalSizes ? 'Width (Nominal)' : 'Width (Perfect)';
        }

        const heightHeader = table.querySelector('th[data-col="height"]');
        if (heightHeader) {
            heightHeader.textContent = this.memberListOptions.showNominalSizes ? 'Height (Nominal)' : 'Height (Perfect)';
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

            const existing = this.meshObjectsByKey.get(key);
            if (existing) {
                this.meshKeyMap.delete(existing.mesh);
                this.memberMetadataByKey.delete(key);
                this.disposeMeshBundle(existing);
                this.meshObjectsByKey.delete(key);
            }

            const meshT0 = performance.now();
            // Choose vertex/index arrays based on geometryMode. Non-perfect timbers
            // include perfectAabbVertices/perfectAabbIndices; perfect timbers and
            // accessories always use the actual vertices/indices regardless of mode.
            const useAabb = (
                geometryMode === 'perfectAabb'
                && memberType === 'timber'
                && mesh.hasActualGeometryDifferentFromPerfect
                && Array.isArray(mesh.perfectAabbVertices)
                && Array.isArray(mesh.perfectAabbIndices)
            );
            const vertexSource = useAabb ? mesh.perfectAabbVertices : (mesh.vertices || []);
            const indexSource = useAabb ? mesh.perfectAabbIndices : (mesh.indices || []);
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
            const edgeGeometry = new THREE.EdgesGeometry(geometry, 25);
            const edgeMesh = new THREE.LineSegments(edgeGeometry, materialSet.edge);
            const reflectionMesh = new THREE.Mesh(geometry, materialSet.reflection);
            solidMesh.renderOrder = 1;
            edgeMesh.renderOrder = 10;
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

        this.setRenderParametersFromFrame(frameData);

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
        this.cameraController.applyToCamera(this.camera);
        this.updateOrbitCenterGizmo();
        this.updateStructureScreenBounds();
    }
}

customElements.define('kigumi-app', KigumiViewerApp);
