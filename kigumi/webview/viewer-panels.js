/**
 * The viewer's options and its frame parameters (kiwari), as panels that draw from an `app` (the
 * viewer) and change things only through its methods. They live in the view's sidebar.
 *
 * The page passes its translator and the shared value modules (window globals) to usePanelRuntime
 * first.
 */

import { html } from 'lit';

let t;
let KigumiUnits;
let KigumiKiwariValues;

export function usePanelRuntime(runtime) {
    ({ t, KigumiUnits, KigumiKiwariValues } = runtime);
}

/** A precision as the step it reads to: '2' -> 0.01, '1/16' as it is. */
function precisionLabel(precision) {
    return precision.includes('/') ? precision : (10 ** -Number(precision)).toFixed(Number(precision));
}

// Export formats in menu order, and the viewer property backing each.
export const EXPORT_FORMATS = ['stl', '3mf', 'obj', 'step'];
export const EXPORT_FORMAT_PROP = {
    stl: 'exportFormatStlEnabled',
    '3mf': 'exportFormat3mfEnabled',
    obj: 'exportFormatObjEnabled',
    step: 'exportFormatStepEnabled',
};

export class ViewerSettingsPanel {
    constructor(app) {
        this.app = app;
    }

    render() {
        const footprintColorLabel = (colorId) => (colorId === 'transparent'
            ? t('viewer.options.footprint.color.transparent')
            : t(`viewer.options.footprint.color.${colorId}`));
        return html`
            <section id="render-controls" aria-label=${t('viewer.options.ariaLabel')}>
                <!-- Save belongs to the panel, not to any one section: it writes
                     every option down, and sitting at the end of the common list
                     it read as belonging to the 3D settings it sat above. -->
                <div class="viewer-settings-header">
                    <div class="viewer-settings-title">${t('viewer.options.ariaLabel')}</div>
                    <button
                        id="save-settings-btn"
                        type="button"
                        title=${t('viewer.options.saveSettings.title')}
                        @click=${() => this.app.saveViewerSettings()}>${t('viewer.options.saveSettings')}</button>
                </div>
                <div class="viewer-settings-divider" role="separator" aria-label=${t('viewer.options.section.common')}></div>
                <div class="viewer-settings-subtitle">${t('viewer.options.section.common')}</div>
                <label>
                    ${t('viewer.options.units.label')}
                    <select id="units-select" .value=${this.app.units || 'metric'}>
                        <option value="imperial">${t('viewer.options.units.imperial')}</option>
                        <option value="metric">${t('viewer.options.units.metric')}</option>
                        <option value="shaku">${t('viewer.options.units.shaku')}</option>
                    </select>
                    <!-- What it can be read to depends on the unit, so the
                         choices are redrawn with it. -->
                    <select id="unit-precision-select" title=${t('viewer.options.units.precision')}>
                        ${KigumiUnits.PRECISIONS[this.app.unitSystem()].map((precision) => html`
                            <option value=${precision} .selected=${precision === this.app.unitPrecision()}>
                                ${precisionLabel(precision)}
                            </option>`)}
                    </select>
                </label>
                <label>
                    <input id="feature-parent-toggle" type="checkbox" .checked=${Boolean(this.app.showFeatureParent)}>
                    ${t('viewer.options.featureParent')}
                </label>
                <label>
                    ${t('viewer.options.referenceFeatures.label')}
                    <select id="reference-features-select" .value=${this.app.referenceFeatures || 'drawings'}>
                        <option value="drawings">${t('viewer.options.referenceFeatures.drawings')}</option>
                        <option value="always">${t('viewer.options.referenceFeatures.always')}</option>
                        <option value="never">${t('viewer.options.referenceFeatures.never')}</option>
                    </select>
                </label>
                <label>
                    ${t('viewer.options.edges.label')}
                    <select id="edge-mode-select" .value=${this.app.edgeMode || 'noOverlay'}>
                        <option value="none">${t('viewer.options.edges.none')}</option>
                        <option value="overlay">${t('viewer.options.edges.overlay')}</option>
                        <option value="noOverlay">${t('viewer.options.edges.noOverlay')}</option>
                    </select>
                </label>
                <label>
                    ${t('viewer.options.edgeVisibility.label', { percent: this.app.edgeLineVisibilityPercent })}
                    <input
                        id="edge-visibility-slider"
                        type="range"
                        min="0"
                        max="100"
                        step="5"
                        .value=${String(this.app.edgeLineVisibilityPercent)}>
                </label>
                <label>
                    ${t('viewer.options.edgeThickness.label', { px: this.app.edgeLineThicknessPx })}
                    <input
                        id="edge-thickness-slider"
                        type="range"
                        min="0.5"
                        max="6"
                        step="0.5"
                        .value=${String(this.app.edgeLineThicknessPx)}>
                </label>
                <label>
                    ${t('viewer.options.geometry.label')}
                    <select id="geometry-mode-select" .value=${this.app.viewerOptions && this.app.viewerOptions.geometryMode || 'actual'}>
                        <option value="actual">${t('viewer.options.geometry.actual')}</option>
                        <option value="perfectTimberWithin">${t('viewer.options.geometry.perfectTimberWithin')}</option>
                        <option value="perfectBoxNoJoints">${t('viewer.options.geometry.perfectBoxNoJoints')}</option>
                        <option value="roughBoxNoJoints">${t('viewer.options.geometry.roughBoxNoJoints')}</option>
                    </select>
                </label>
                <label>
                    ${t('viewer.options.unselectedVisibility.label', { percent: 100 - this.app.unselectedTransparencyPercent })}
                    <input
                        id="unselected-transparency-slider"
                        type="range"
                        min="5"
                        max="100"
                        step="5"
                        .value=${String(100 - this.app.unselectedTransparencyPercent)}>
                </label>
                <label>
                    ${t('viewer.options.selectedVisibility.label', { percent: 100 - this.app.selectedTransparencyPercent })}
                    <input
                        id="selected-transparency-slider"
                        type="range"
                        min="5"
                        max="100"
                        step="5"
                        .value=${String(100 - this.app.selectedTransparencyPercent)}>
                </label>
                <label>
                    <input id="left-click-rotate-toggle" type="checkbox" .checked=${this.app.leftClickDragRotatesCamera}>
                    ${t('viewer.options.leftClickRotate')}
                </label>
                <label>
                    ${t('viewer.options.theme.label')}
                    <select id="theme-select" .value=${this.app.activeTheme}>
                        ${this.app.themeChoices.map(({ id, labelKey }) => html`<option value=${id}>${t(labelKey)}</option>`)}
                    </select>
                </label>
                <label>
                    <input id="debug-toggle" type="checkbox" .checked=${this.app.debugEnabled}>
                    ${t('viewer.options.debugInfo')}
                </label>
                <div class="viewer-settings-divider" role="separator" aria-label=${t('viewer.options.section.threeD')}></div>
                <div class="viewer-settings-subtitle">${t('viewer.options.section.threeD')}</div>
                <label>
                    <input id="center-gizmo-toggle" type="checkbox" .checked=${this.app.showCenterGizmo}>
                    ${t('viewer.options.centerGizmo')}
                </label>
                <label>
                    <input id="shadows-toggle" type="checkbox" .checked=${this.app.shadowsEnabled}>
                    ${t('viewer.options.shadows')}
                </label>
                <label>
                    <input id="reflections-toggle" type="checkbox" .checked=${this.app.reflectionsEnabled}>
                    ${t('viewer.options.reflection')}
                </label>
                <span class="swatch-group" role="group" aria-label=${t('viewer.options.footprint.ariaLabel')}>
                    ${t('viewer.options.footprint.label')}
                    ${this.app.footprintColorIds.map((colorId) => html`
                        <button
                            id="footprint-color-${colorId}"
                            type="button"
                            class="color-swatch color-swatch-${colorId}"
                            title=${footprintColorLabel(colorId)}
                            aria-label=${footprintColorLabel(colorId)}
                            aria-pressed=${String(this.app.footprintColor === colorId)}></button>
                    `)}
                </span>
                ${this.app.panelFlags.assemblyPreview ? html`
                <label>
                    <input id="assembly-timeline-toggle" type="checkbox" .checked=${this.app.showAssemblyTimeline}>
                    ${t('viewer.options.assemblyTimeline')}
                </label>
                <label>
                    ${t('viewer.options.disassemblySpacing.label', { multiplier: this.app.disassemblyMultiplier })}
                    <input
                        id="disassembly-multiplier-slider"
                        type="range"
                        min="1"
                        max="4"
                        step="0.1"
                        .value=${String(this.app.disassemblyMultiplier)}>
                </label>` : ''}
                ${this.app.panelFlags.drawingBeta ? html`
                <div class="viewer-settings-divider" role="separator" aria-label=${t('viewer.options.section.drawing')}></div>
                <div class="viewer-settings-subtitle">${t('viewer.options.section.drawing')}</div>
                <label>
                    <input id="drawing-ghosts-toggle" type="checkbox" .checked=${this.app.showDrawingGhosts}>
                    ${t('viewer.options.drawingGhosts')}
                </label>
                <label>
                    <input id="drawing-perfect-faces-toggle" type="checkbox" .checked=${this.app.showDrawingPerfectFaces}>
                    ${t('viewer.options.drawingPerfectFaces')}
                </label>
                <label>
                    <input id="drawing-centerplanes-toggle" type="checkbox" .checked=${this.app.showDrawingCenterplanes}>
                    ${t('viewer.options.drawingCenterplanes')}
                </label>
                <label>
                    <input id="drawing-reference-features-toggle" type="checkbox" .checked=${this.app.showDrawingReferenceFeatures}>
                    ${t('viewer.options.drawingReferenceFeatures')}
                </label>
                <button
                    id="debug-drawing-btn"
                    type="button"
                    title=${t('viewer.options.debugDrawing.title')}
                    @click=${() => this.app.openDebugDrawing()}>${t('viewer.options.debugDrawing')}</button>` : ''}
                <div class="viewer-settings-divider" role="separator" aria-label=${t('viewer.options.export.ariaLabel')}></div>
                <div class="viewer-settings-subtitle">${t('viewer.options.export.subtitle')}</div>
                <label>
                    <input id="export-format-stl-toggle" type="checkbox" .checked=${this.app.exportFormatStlEnabled}>
                    ${t('viewer.options.export.stl')}
                </label>
                <label>
                    <input id="export-format-3mf-toggle" type="checkbox" .checked=${this.app.exportFormat3mfEnabled}>
                    ${t('viewer.options.export.3mf')}
                </label>
                <label>
                    <input id="export-format-obj-toggle" type="checkbox" .checked=${this.app.exportFormatObjEnabled}>
                    ${t('viewer.options.export.obj')}
                </label>
                <label>
                    <input id="export-format-step-toggle" type="checkbox" .checked=${this.app.exportFormatStepEnabled}>
                    ${t('viewer.options.export.step')}
                </label>
                <label>
                    <input id="export-combined-toggle" type="checkbox" .checked=${this.app.exportCombinedEnabled}>
                    ${t('viewer.options.export.combinedFile')}
                </label>
                <label>
                    <input id="export-individual-toggle" type="checkbox" .checked=${this.app.exportIndividualsEnabled}>
                    ${t('viewer.options.export.individualFiles')}
                </label>
                <label>
                    <input id="export-accessories-toggle" type="checkbox" .checked=${this.app.exportAccessoriesEnabled}>
                    ${t('viewer.options.export.includeAccessories')}
                </label>
                <button
                    id="export-files-btn"
                    type="button"
                    title=${t('viewer.options.export.exportButton.title')}
                    @click=${() => this.app.exportFiles()}>${t('viewer.options.export.exportButton')}</button>
                ${this.app.cadqueryOcpInstalled === false
                    ? html`<button
                        id="install-cadquery-ocp-btn"
                        type="button"
                        title=${t('viewer.options.export.installCadquery.title')}
                        ?disabled=${this.app.installingCadqueryOcp === true}
                        @click=${() => this.app.installCadqueryOcp()}>${this.app.installingCadqueryOcp === true
                            ? t('viewer.options.export.installingCadquery')
                            : t('viewer.options.export.installCadquery')}</button>`
                    : ''}
                <!-- Saved as settings, so they hold for every view; the open views reload to show them. -->
                <div class="viewer-settings-divider" role="separator" aria-label=${t('viewer.options.section.beta')}></div>
                <div class="viewer-settings-subtitle">${t('viewer.options.section.beta')}</div>
                ${this.app.panelFlags.assemblyPreviewAvailable ? html`
                <label>
                    <input id="beta-assembly-toggle" type="checkbox" .checked=${this.app.panelFlags.assemblyPreview}
                        @change=${(event) => this.app.setBetaFeature('assemblyPreview', event.target.checked)}>
                    ${t('viewer.options.beta.assemblyPreview')}
                </label>` : ''}
                <label>
                    <input id="beta-drawing-toggle" type="checkbox" .checked=${this.app.panelFlags.drawingBeta}
                        @change=${(event) => this.app.setBetaFeature('drawingBeta', event.target.checked)}>
                    ${t('viewer.options.beta.drawings')}
                </label>
                ${this.app.panelFlags.mcpAvailable ? html`
                <label>
                    <input id="beta-mcp-toggle" type="checkbox" .checked=${Boolean(this.app.mcpState && this.app.mcpState.enabled)}
                        @change=${(event) => this.app.setBetaFeature('mcp', event.target.checked)}>
                    ${t('viewer.options.beta.mcp')}
                </label>
                ${this.renderMcp(this.app.mcpState)}` : ''}
            </section>
        `;
    }

    /** Kigumi's MCP server: whether it is serving, the setup to copy for each agent, and who has called. */
    renderMcp(state) {
        if (!state || !state.enabled) {
            return '';
        }
        const ago = (time) => {
            const minutes = Math.floor((Date.now() - time) / 60000);
            return minutes < 1 ? t('viewer.options.mcp.justNow') : t('viewer.options.mcp.minutesAgo', { minutes });
        };
        return html`
            <div class="viewer-settings-divider" role="separator" aria-label=${t('viewer.options.section.mcp')}></div>
            <div class="viewer-settings-subtitle">${t('viewer.options.section.mcp')}</div>
            <div class="mcp-status" id="mcp-status">${state.running
                ? t('viewer.options.mcp.serving', { url: state.url })
                : (state.error || t('viewer.options.mcp.starting'))}</div>
            <div class="mcp-copy">
                <span>${t('viewer.options.mcp.copyFor')}</span>
                ${(state.setups || []).map((setup) => html`
                    <button type="button" class="mcp-copy-btn" data-client=${setup.id} ?disabled=${!state.running}
                        title=${t('viewer.options.mcp.copy.title', { client: setup.label })}
                        @click=${() => this.app.copyMcpSetup(setup.id)}>${setup.label}</button>`)}
            </div>
            <div class="mcp-clients" id="mcp-clients">
                <div class="mcp-clients-title">${t('viewer.options.mcp.clients')}</div>
                ${(state.clients || []).length === 0
                    ? html`<div class="mcp-client dim">${t('viewer.options.mcp.noClients')}</div>`
                    : state.clients.map((client) => html`
                        <div class="mcp-client">
                            <span class="mcp-client-name">${client.name}${client.version ? ` ${client.version}` : ''}</span>
                            <span class="dim">${ago(client.lastSeen)} · ${t('viewer.options.mcp.calls', { count: client.calls })}${client.lastTool
                                ? ` · ${client.lastTool}` : ''}</span>
                        </div>`)}
            </div>`;
    }

    // Declarative description of every settings control: which element id it
    // binds to, which DOM event drives it, how to apply a change to the app
    // (`apply`), and — where the control reflects app state — how to sync the
    // element from the app (`sync`). bindEvents and syncControls both iterate
    // this instead of enumerating the same ~16 ids twice.
    get controlDescriptors() {
        const app = this.app;
        return [
            { id: 'center-gizmo-toggle', on: 'change', apply: (el) => app.setCenterGizmoEnabled(el.checked) },
            {
                id: 'units-select', on: 'change',
                apply: (el) => app.setUnits(el.value),
                sync: (el) => { el.value = app.units || KigumiUnits.DEFAULT_UNIT_SYSTEM; },
            },
            {
                id: 'unit-precision-select', on: 'change',
                apply: (el) => app.setUnitPrecision(el.value),
                sync: (el) => { el.value = app.unitPrecision(); },
            },
            {
                id: 'edge-mode-select', on: 'change',
                apply: (el) => app.setEdgeMode(el.value),
                sync: (el) => { el.value = app.edgeMode || 'noOverlay'; },
            },
            { id: 'shadows-toggle', on: 'change', apply: (el) => app.setShadowsEnabled(el.checked) },
            { id: 'reflections-toggle', on: 'change', apply: (el) => app.setReflectionsEnabled(el.checked) },
            ...this.app.footprintColorIds.map((colorId) => ({
                id: `footprint-color-${colorId}`,
                on: 'click',
                apply: () => app.setFootprintColor(colorId),
                sync: (el) => { el.setAttribute('aria-pressed', String(app.footprintColor === colorId)); },
            })),
            {
                id: 'debug-toggle', on: 'change',
                apply: (el) => app.setDebugEnabled(el.checked),
                sync: (el) => { el.checked = Boolean(app.debugEnabled); },
            },
            {
                id: 'feature-parent-toggle', on: 'change',
                apply: (el) => app.setShowFeatureParent(el.checked),
                sync: (el) => { el.checked = Boolean(app.showFeatureParent); },
            },
            {
                id: 'reference-features-select', on: 'change',
                apply: (el) => app.setReferenceFeatures(el.value),
                sync: (el) => { el.value = app.referenceFeatures || 'drawings'; },
            },
            {
                id: 'drawing-ghosts-toggle', on: 'change',
                apply: (el) => app.setDrawingGhostsVisible(el.checked),
                sync: (el) => { el.checked = app.showDrawingGhosts; },
            },
            ...[
                ['drawing-perfect-faces-toggle', 'showDrawingPerfectFaces'],
                ['drawing-centerplanes-toggle', 'showDrawingCenterplanes'],
                ['drawing-reference-features-toggle', 'showDrawingReferenceFeatures'],
            ].map(([id, option]) => ({
                id, on: 'change',
                apply: (el) => app.setDrawingOption(option, el.checked),
                sync: (el) => { el.checked = Boolean(app[option]); },
            })),
            {
                id: 'left-click-rotate-toggle', on: 'change',
                apply: (el) => app.setLeftClickDragRotatesCameraEnabled(el.checked),
                sync: (el) => { el.checked = app.leftClickDragRotatesCamera; },
            },
            {
                id: 'assembly-timeline-toggle', on: 'change',
                apply: (el) => app.setShowAssemblyTimeline(el.checked),
                sync: (el) => { el.checked = app.showAssemblyTimeline; },
            },
            {
                id: 'export-combined-toggle', on: 'change',
                apply: (el) => app.setExportCombinedEnabled(el.checked),
                sync: (el) => { el.checked = app.exportCombinedEnabled; },
            },
            {
                id: 'export-individual-toggle', on: 'change',
                apply: (el) => app.setExportIndividualsEnabled(el.checked),
                sync: (el) => { el.checked = app.exportIndividualsEnabled; },
            },
            {
                id: 'export-accessories-toggle', on: 'change',
                apply: (el) => app.setExportAccessoriesEnabled(el.checked),
                sync: (el) => { el.checked = app.exportAccessoriesEnabled; },
            },
            ...EXPORT_FORMATS.map((format) => ({
                id: `export-format-${format}-toggle`, on: 'change',
                apply: (el) => app.setExportFormatEnabled(format, el.checked),
                sync: (el) => { el.checked = app[EXPORT_FORMAT_PROP[format]]; },
            })),
            {
                id: 'edge-visibility-slider', on: 'input',
                apply: (el) => {
                    const raw = Number(el.value);
                    const percent = Number.isFinite(raw) ? Math.max(0, Math.min(100, Math.round(raw / 5) * 5)) : 100;
                    app.setEdgeLineVisibilityPercent(percent);
                },
                sync: (el) => { el.value = String(app.edgeLineVisibilityPercent); },
            },
            {
                id: 'edge-thickness-slider', on: 'input',
                apply: (el) => app.setEdgeLineThicknessPx(Number(el.value)),
                sync: (el) => { el.value = String(app.edgeLineThicknessPx); },
            },
            {
                id: 'unselected-transparency-slider', on: 'input',
                apply: (el) => {
                    const raw = Number(el.value);
                    const visibility = Number.isFinite(raw) ? Math.max(5, Math.min(100, Math.round(raw / 5) * 5)) : 60;
                    app.setUnselectedTransparencyPercent(100 - visibility);
                },
                sync: (el) => { el.value = String(100 - app.unselectedTransparencyPercent); },
            },
            {
                id: 'selected-transparency-slider', on: 'input',
                apply: (el) => {
                    const raw = Number(el.value);
                    const visibility = Number.isFinite(raw) ? Math.max(5, Math.min(100, Math.round(raw / 5) * 5)) : 100;
                    app.setSelectedTransparencyPercent(100 - visibility);
                },
                sync: (el) => { el.value = String(100 - app.selectedTransparencyPercent); },
            },
            {
                id: 'disassembly-multiplier-slider', on: 'input',
                apply: (el) => app.setDisassemblyMultiplier(Number(el.value)),
                sync: (el) => { el.value = String(app.disassemblyMultiplier); },
            },
            {
                id: 'theme-select', on: 'change',
                apply: (el) => app.setTheme(el.value),
                sync: (el) => { el.value = app.activeTheme; },
            },
            {
                id: 'geometry-mode-select', on: 'change',
                apply: (el) => app.setGeometryMode(el.value),
                sync: (el) => {
                    if (app.viewerOptions) {
                        el.value = app.viewerOptions.geometryMode || 'actual';
                    }
                },
            },
        ];
    }

    /** A control's event, for a page that listens on the panel as a whole (the inspector). */
    handleEvent(event) {
        const control = this.controlDescriptors.find((one) => one.id === event.target.id && one.on === event.type);
        if (control) {
            control.apply(event.target);
        }
    }

    bindEvents(renderRoot) {
        for (const control of this.controlDescriptors) {
            const el = renderRoot.querySelector(`#${control.id}`);
            if (!el) {
                continue;
            }
            el.addEventListener(control.on, () => control.apply(el));
        }
    }

    syncControls(renderRoot) {
        for (const control of this.controlDescriptors) {
            if (!control.sync) {
                continue;
            }
            const el = renderRoot.querySelector(`#${control.id}`);
            if (el) {
                control.sync(el);
            }
        }
    }
}

export class ViewerKiwariPanel {
    constructor(app) {
        this.app = app;
    }

    unitSystem() {
        return this.app.units || KigumiUnits.DEFAULT_UNIT_SYSTEM;
    }

    // A dimensioned box says what a bare number in it would mean, so nobody
    // has to guess whether "18" is inches or millimetres.
    placeholderFor(parameter) {
        if (parameter.kind === 'length' || parameter.kind === 'angle') {
            return KigumiKiwariValues.defaultUnitFor(parameter.kind, this.unitSystem());
        }
        return '';
    }

    renderTextControl(parameter, inputId, draft, problem, options = {}) {
        const { onInput, placeholder, disabled = false } = options;
        return html`
            <input
                id=${inputId}
                class=${problem ? 'kiwari-box kiwari-box-bad' : 'kiwari-box'}
                type="text"
                inputmode=${parameter.kind === 'count' ? 'numeric' : 'text'}
                .value=${String(draft ?? '')}
                placeholder=${placeholder ?? this.placeholderFor(parameter)}
                ?disabled=${disabled}
                aria-invalid=${problem ? 'true' : 'false'}
                @input=${(event) => onInput(event.target.value)}>
        `;
    }

    renderCount(parameter, inputId, draft, problem, disabled) {
        // Steppers, because a count is nearly always nudged rather than typed.
        const step = (by) => {
            const next = Math.round(Number(draft) || 0) + by;
            this.app.setKiwariDraft(parameter.section, parameter.key, String(next));
        };
        return html`
            <div class="kiwari-count">
                <button type="button" class="kiwari-step" ?disabled=${disabled}
                    title=${t('viewer.kiwari.decrement')}
                    @click=${() => step(-1)}>−</button>
                ${this.renderTextControl(parameter, inputId, draft, problem, {
                    onInput: (value) => this.app.setKiwariDraft(parameter.section, parameter.key, value),
                    disabled,
                })}
                <button type="button" class="kiwari-step" ?disabled=${disabled}
                    title=${t('viewer.kiwari.increment')}
                    @click=${() => step(1)}>+</button>
            </div>
        `;
    }

    renderChoice(parameter, inputId, draft, disabled) {
        // A datalist gives type-to-search for free, and still accepts a click.
        const choices = Array.isArray(parameter.choices) ? parameter.choices : [];
        return html`
            <select
                id=${inputId}
                class="kiwari-box kiwari-select"
                .value=${String(draft ?? '')}
                ?disabled=${disabled}
                @change=${(event) => this.app.setKiwariDraft(parameter.section, parameter.key, event.target.value)}>
                ${choices.map((option) => html`
                    <option value=${option.value} ?selected=${String(draft) === String(option.value)}>
                        ${option.label || option.value}
                    </option>`)}
            </select>
        `;
    }

    renderPoint(parameter, inputId, draft, problem, disabled) {
        const axes = KigumiKiwariValues.VECTOR_AXES[parameter.kind];
        return html`
            <div class="kiwari-point">
                ${axes.map((axis) => html`
                    <label class="kiwari-axis">
                        <span class="kiwari-axis-name">${axis}</span>
                        <input
                            id=${`${inputId}-${axis}`}
                            class=${problem && problem.startsWith(`${axis}:`) ? 'kiwari-box kiwari-box-bad' : 'kiwari-box'}
                            type="text"
                            .value=${String((draft || {})[axis] ?? '')}
                            placeholder=${this.placeholderFor({ kind: 'length' })}
                            ?disabled=${disabled}
                            @input=${(event) => this.app.setKiwariAxisDraft(parameter.section, parameter.key, axis, event.target.value)}>
                    </label>`)}
            </div>
        `;
    }

    renderControl(parameter, inputId, draft, problem, disabled) {
        if (parameter.kind === 'flag') {
            return html`
                <label class="kiwari-flag">
                    <input
                        id=${inputId}
                        type="checkbox"
                        .checked=${Boolean(draft)}
                        ?disabled=${disabled}
                        @change=${(event) => this.app.setKiwariDraft(parameter.section, parameter.key, event.target.checked)}>
                    <span>${t('common.enabled')}</span>
                </label>
            `;
        }
        if (parameter.kind === 'choice') {
            return this.renderChoice(parameter, inputId, draft, disabled);
        }
        if (parameter.kind === 'count') {
            return this.renderCount(parameter, inputId, draft, problem, disabled);
        }
        if (KigumiKiwariValues.VECTOR_AXES[parameter.kind]) {
            return this.renderPoint(parameter, inputId, draft, problem, disabled);
        }
        return this.renderTextControl(parameter, inputId, draft, problem, {
            onInput: (value) => this.app.setKiwariDraft(parameter.section, parameter.key, value),
            disabled,
        });
    }

    renderParameter(state, index, parameter, problems) {
        // The first section keeps the plain id, so a file with one kiwari reads as it always did.
        const inputId = index === 0 ? `kiwari-${parameter.key}` : `kiwari-${index}-${parameter.key}`;
        const draft = state.drafts[parameter.key];
        const problem = problems[parameter.key];
        const changed = KigumiKiwariValues.isChangedFromDefault(state, parameter, this.unitSystem());
        // An optional parameter can be nothing at all, which is a real answer
        // and not a missing one, so it gets a switch rather than an empty box.
        const on = KigumiKiwariValues.isEnabled(state, parameter);
        const rowClass = ['kiwari-row', changed ? 'kiwari-row-changed' : '', on ? '' : 'kiwari-row-off']
            .filter(Boolean).join(' ');
        return html`
            <div class=${rowClass}>
                <div class="kiwari-row-header">
                    ${parameter.optional
                        ? html`<input
                            class="kiwari-switch"
                            type="checkbox"
                            id=${`${inputId}-on`}
                            .checked=${on}
                            title=${on ? t('viewer.kiwari.optional.on') : t('viewer.kiwari.optional.off')}
                            @change=${(event) => this.app.setKiwariEnabled(parameter.section, parameter.key, event.target.checked)}>`
                        : ''}
                    <label class="kiwari-key" for=${parameter.optional ? `${inputId}-on` : inputId}>${parameter.key}</label>
                    <span class="kiwari-kind">${t(`viewer.kiwari.kind.${parameter.kind}`)}</span>
                    ${changed
                        ? html`<span class="kiwari-changed-dot" title=${t('viewer.kiwari.changedFromDefault')}>●</span>`
                        : ''}
                </div>
                <div class="kiwari-row-control">
                    ${on
                        ? this.renderControl(parameter, inputId, draft, problem, false)
                        : html`<span class="kiwari-nothing">${t('viewer.kiwari.optional.none')}</span>`}
                </div>
                ${problem
                    ? html`<div class="kiwari-problem" role="alert">${problem}</div>`
                    : parameter.about
                        ? html`<div class="kiwari-about">${parameter.about}</div>`
                        : ''}
            </div>
        `;
    }

    render() {
        const sections = this.app.kiwariSections;
        if (!sections.length) {
            return '';
        }
        const problems = sections.map((state) => KigumiKiwariValues.problems(state, this.unitSystem()));
        const problemCount = problems.reduce((count, found) => count + Object.keys(found).length, 0);
        const edited = sections.some((state) => state.schema.some(
            (parameter) => KigumiKiwariValues.isEdited(state, parameter, this.unitSystem()),
        ));
        const stale = sections.some((state) => state.stale);
        const canSave = sections.some((state) => state.canSave);
        return html`
            <section id="kiwari-controls" aria-label=${t('viewer.kiwari.ariaLabel')}>
                <div class="kiwari-header">
                    <div class="kiwari-title">${t('viewer.kiwari.title')}</div>
                    <div class="kiwari-actions">
                        ${stale
                            ? html`<span class="kiwari-stale" title=${t('viewer.kiwari.stale.title')}>${t('viewer.kiwari.stale')}</span>`
                            : ''}
                        <button
                            type="button"
                            class="kiwari-action"
                            title=${t('viewer.kiwari.reset.title')}
                            @click=${() => this.app.resetKiwariToDefaults()}>${t('viewer.kiwari.reset')}</button>
                        ${canSave
                            ? html`<button
                                type="button"
                                class="kiwari-action"
                                ?disabled=${problemCount > 0}
                                title=${t('viewer.kiwari.save.title')}
                                @click=${() => this.app.saveKiwariToFile()}>${t('viewer.kiwari.save')}</button>`
                            : ''}
                        <button
                            id="kiwari-build-btn"
                            type="button"
                            class="kiwari-action kiwari-build"
                            ?disabled=${problemCount > 0 || !edited}
                            title=${problemCount > 0 ? t('viewer.kiwari.cannotBuild') : t('viewer.kiwari.build.title')}
                            @click=${() => this.app.requestRefresh()}>${t('viewer.kiwari.build')}</button>
                    </div>
                </div>
                <div class="kiwari-list">
                    ${sections.map((state, index) => html`
                        ${sections.length > 1
                            ? html`<div class="kiwari-section-title">${state.frames.join(', ')}</div>`
                            : ''}
                        ${state.schema.map((parameter) => this.renderParameter(state, index, parameter, problems[index]))}
                    `)}
                </div>
            </section>
        `;
    }
}
