/**
 * The assembly preview timeline: its data, scrubbing and disassembly offsets, and its bar.
 *
 * A mixin of the viewer (viewer-app.js): its methods run as the viewer's.
 */

import { html } from 'lit';
import { ASSEMBLY_PREVIEW_ENABLED, AssemblyTimeline, t, vscode } from './viewer-shared.js';

export const AssemblyMixin = (Base) => class extends Base {
    setAssemblyData(assemblyData) {
        this.assemblyData = assemblyData;
        if (!assemblyData) {
            this.assemblyScrubValue = 0;
        } else {
            // Preserve the scrub position across geometry refreshes; just keep
            // it within the (possibly changed) step range.
            const max = AssemblyTimeline.getScrubMax(assemblyData.steps, assemblyData.failure);
            this.assemblyScrubValue = Math.min(Math.max(this.assemblyScrubValue, 0), max);
        }
        this.applyAssemblyOffsets();
        this.requestUpdate();
    }

    setAssemblyScrubValue(nextValue) {
        const max = this.assemblyData
            ? AssemblyTimeline.getScrubMax(this.assemblyData.steps, this.assemblyData.failure)
            : 0;
        const normalized = Number.isFinite(nextValue) ? Math.min(Math.max(nextValue, 0), max) : 0;
        if (this.assemblyScrubValue === normalized) {
            return;
        }
        this.assemblyScrubValue = normalized;
        this.applyAssemblyOffsets();
        this.requestUpdate();
    }

    setDisassemblyMultiplier(nextMultiplier) {
        const normalized = Number.isFinite(nextMultiplier)
            ? Math.max(1, Math.min(4, Math.round(nextMultiplier * 10) / 10))
            : 1.5;
        if (this.disassemblyMultiplier === normalized) {
            return;
        }
        this.disassemblyMultiplier = normalized;
        this.applyAssemblyOffsets();
        this.requestUpdate();
    }

    setShowAssemblyTimeline(enabled) {
        const normalized = Boolean(enabled);
        if (this.showAssemblyTimeline === normalized) {
            return;
        }
        this.showAssemblyTimeline = normalized;
        this.applyAssemblyOffsets();
        this.requestUpdate();
    }

    // Recompute per-member displacement from the current scrub position and
    // apply it to every mesh bundle. The continuous rAF loop repaints.
    applyAssemblyOffsets() {
        const active = this.assemblyData && this.showAssemblyTimeline;
        this._assemblyOffsetsByKey = active
            ? AssemblyTimeline.computeAssemblyOffsets(
                this.assemblyData.steps, this.assemblyScrubValue, this.disassemblyMultiplier)
            : new Map();
        this._assemblyRotationsByKey = active
            ? AssemblyTimeline.computeAssemblyRotations(this.assemblyData.steps, this.assemblyScrubValue)
            : new Map();
        for (const [memberKey, bundle] of this.sceneManager.entries()) {
            const offset = this._assemblyOffsetsByKey.get(memberKey) || [0, 0, 0];
            const rotation = this._assemblyRotationsByKey.get(memberKey);
            const shift = rotation ? rotation.shift : [0, 0, 0];
            const q = rotation ? rotation.quaternion : [0, 0, 0, 1];
            for (const object of [bundle.mesh, bundle.edges]) {
                if (object) {
                    object.position.set(offset[0] + shift[0], offset[1] + shift[1], offset[2] + shift[2]);
                    object.quaternion.set(q[0], q[1], q[2], q[3]);
                }
            }
        }
        this.updateReflectionTransforms();
    }

    logAssemblyFailure() {
        const failure = this.assemblyData && this.assemblyData.failure;
        if (!failure) {
            return;
        }
        const lines = [failure.message, ...failure.diagnostics];
        console.warn(['[assembly]', ...lines].join('\n'));
        if (vscode) {
            vscode.postMessage({ type: 'assemblyFailureLog', lines });
        }
    }

    renderAssemblyTimeline() {
        if (!ASSEMBLY_PREVIEW_ENABLED || !this.showAssemblyTimeline || this.isInDrawing) {
            return '';
        }
        if (this.assemblySolving) {
            return html`
                <div id="assembly-timeline"
                    aria-label=${t('viewer.assembly.ariaLabel')}
                    @pointerdown=${(event) => event.stopPropagation()}
                    @mousedown=${(event) => event.stopPropagation()}>
                    <span class="assembly-timeline-loading">${t('viewer.assembly.solving')}</span>
                </div>
            `;
        }
        if (!this.assemblyData) {
            return '';
        }
        const { steps, warnings, failure } = this.assemblyData;
        const scrubMax = AssemblyTimeline.getScrubMax(steps, failure);
        const marks = AssemblyTimeline.getTimelineMarks(steps);
        const failureTooltip = failure
            ? [failure.message, ...failure.diagnostics.slice(0, 3)].join('\n')
            : '';
        return html`
            <div id="assembly-timeline"
                aria-label=${t('viewer.assembly.ariaLabel')}
                @pointerdown=${(event) => event.stopPropagation()}
                @mousedown=${(event) => event.stopPropagation()}>
                <span class="assembly-timeline-end-label">${t('viewer.assembly.assembled')}</span>
                <div class="assembly-timeline-track">
                    <input
                        id="assembly-scrub-slider"
                        type="range"
                        min="0"
                        max=${String(scrubMax)}
                        step="0.01"
                        .value=${String(this.assemblyScrubValue)}
                        ?disabled=${scrubMax === 0}
                        @input=${(event) => this.setAssemblyScrubValue(Number(event.target.value))}>
                    <div class="assembly-timeline-marks">
                        ${marks.map((mark) => html`<span
                            class=${mark.kind === 'substep'
                                ? 'assembly-timeline-mark assembly-timeline-mark-substep'
                                : 'assembly-timeline-mark'}
                            data-left=${scrubMax > 0 ? String((mark.value / scrubMax) * 100) : '0'}
                            >${mark.kind === 'substep' ? '·' : mark.label}</span>`)}
                    </div>
                </div>
                ${failure
                    ? html`<button
                        class="assembly-timeline-end-label assembly-timeline-failure"
                        type="button"
                        title=${failureTooltip}
                        @click=${() => this.logAssemblyFailure()}>✕</button>`
                    : html`<span class="assembly-timeline-end-label">${t('viewer.assembly.disassembled')}</span>`}
                ${warnings.length > 0
                    ? html`<span class="assembly-timeline-warnings" title=${warnings.join('\n')}>⚠ ${warnings.length}</span>`
                    : ''}
            </div>
        `;
    }
};
