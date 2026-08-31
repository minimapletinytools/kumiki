import { html } from 'lit';

const KigumiTags = window.KigumiTags;
const KigumiUnits = window.KigumiUnits;

/**
 * The member list: every timber and accessory in the frame, as a table.
 *
 * Follows the panel shape already in the viewer -- render, bindEvents,
 * syncControls -- and holds its own options, since nothing outside it cares
 * whether rough lengths or tags are on.
 *
 * Lengths and sizes are asked of the app rather than computed here: they follow
 * the units setting, which belongs to the viewer as a whole.
 */
export class MemberListPanel {
    constructor(app, { t }) {
        this.app = app;
        this.t = t;
        this.options = {
            showRoughLength: false,
            showNominalSizes: false,
            showCsgFeatureCount: false,
            showTags: false,
        };
        // The allowance a rough length adds to a finished one.
        this.roughLengthAllowanceMm = 30;
    }

    render() {
        const t = this.t;
        return html`
            <div class="panel-box">
                <div class="panel-title">${t('viewer.memberList.title')}</div>
                <div id="member-list-options" aria-label=${t('viewer.memberList.ariaLabel')}>
                    <label>
                        <input id="member-opt-rough-length" type="checkbox" ?checked=${this.options.showRoughLength}>
                        ${t('viewer.memberList.opt.roughLength', { allowance: this.roughLengthAllowanceMm })}
                    </label>
                    <label>
                        <input id="member-opt-sizes" type="checkbox" ?checked=${this.options.showNominalSizes}>
                        ${t('viewer.memberList.opt.sizes')}
                    </label>
                    <label>
                        <input id="member-opt-csg" type="checkbox" ?checked=${this.options.showCsgFeatureCount}>
                        ${t('viewer.memberList.opt.csg')}
                    </label>
                    <label>
                        <input id="member-opt-tags" type="checkbox" ?checked=${this.options.showTags}>
                        ${t('viewer.memberList.opt.tags')}
                    </label>
                </div>
                <details id="member-list-legend" open>
                    <summary>${t('viewer.memberList.legend.summary')}</summary>
                    <div class="member-list-legend-body">
                        <p><strong>${t('viewer.memberList.legend.length.term')}</strong>: ${t('viewer.memberList.legend.length.desc')}</p>
                        <p><strong>${t('viewer.memberList.legend.sizeToggle.term')}</strong>: ${t('viewer.memberList.legend.sizeToggle.desc')}</p>
                        <p><strong>${t('viewer.memberList.legend.csg.term')}</strong>: ${t('viewer.memberList.legend.csg.desc')}</p>
                        <p><strong>${t('viewer.memberList.legend.features.term')}</strong>: ${t('viewer.memberList.legend.features.desc')}</p>
                        <p><strong>${t('viewer.memberList.legend.tags.term')}</strong>: ${t('viewer.memberList.legend.tags.desc')}</p>
                    </div>
                </details>
                <div id="timber-panel">
                    <table>
                        <thead>
                            <tr>
                                <th>#</th><th>${t('viewer.memberList.table.type')}</th><th>${t('viewer.memberList.table.name')}</th>
                                <th data-col="tags">${t('viewer.memberList.table.tags')}</th>
                                <th data-col="length">${t('viewer.memberList.table.length')}</th><th data-col="width">${t('viewer.memberList.table.width')}</th><th data-col="height">${t('viewer.memberList.table.height')}</th>
                                <th data-col="csg">${t('viewer.memberList.legend.csg.term')}</th><th data-col="feature">${t('viewer.memberList.legend.features.term')}</th>
                            </tr>
                        </thead>
                        <tbody id="timber-rows"></tbody>
                    </table>
                </div>
            </div>
        `;
    }

    bindEvents(renderRoot) {
        const bindings = [
            ['#member-opt-rough-length', 'showRoughLength'],
            ['#member-opt-sizes', 'showNominalSizes'],
            ['#member-opt-csg', 'showCsgFeatureCount'],
            ['#member-opt-tags', 'showTags'],
        ];
        for (const [selector, option] of bindings) {
            const element = renderRoot.querySelector(selector);
            if (!element) {
                continue;
            }
            element.addEventListener('change', (event) => {
                this.options[option] = Boolean(event.target.checked);
                this.refresh();
            });
        }
    }

    syncControls(renderRoot) {
        const checkboxes = {
            '#member-opt-rough-length': this.options.showRoughLength,
            '#member-opt-sizes': this.options.showNominalSizes,
            '#member-opt-csg': this.options.showCsgFeatureCount,
            '#member-opt-tags': this.options.showTags,
        };
        for (const [selector, checked] of Object.entries(checkboxes)) {
            const element = renderRoot.querySelector(selector);
            if (element) {
                element.checked = checked;
            }
        }
    }

    /** Redraw from the geometry the viewer last received. */
    refresh() {
        const geometry = this.app._lastGeometryData;
        this.rebuild(geometry && geometry.meshes ? geometry.meshes : []);
    }

    rebuild(meshes) {
        const tbody = this.app.renderRoot && this.app.renderRoot.querySelector
            ? this.app.renderRoot.querySelector('#timber-rows')
            : null;
        if (!tbody) {
            return;
        }
        tbody.textContent = '';
        for (let index = 0; index < meshes.length; index += 1) {
            const mesh = meshes[index];
            const typeLabel = mesh.memberType === 'accessory' ? 'Accessory' : 'Timber';
            const memberName = mesh.memberName || mesh.name || '?';
            const tags = KigumiTags.coerceTags(mesh.tags);
            const tagsLabel = tags.length > 0 ? tags.map((tag) => tag.name).join(', ') : '—';
            const row = document.createElement('tr');
            row.innerHTML = '<td>' + (index + 1) + '</td>'
                + '<td>' + escapeHtml(typeLabel) + '</td>'
                + '<td>' + escapeHtml(memberName) + '</td>'
                + '<td data-col="tags" class="dim">' + escapeHtml(tagsLabel) + '</td>'
                + '<td data-col="length" class="dim">' + this.formatLength(mesh) + '</td>'
                + '<td data-col="width" class="dim">' + this.formatCrossSection(mesh, 'width') + '</td>'
                + '<td data-col="height" class="dim">' + this.formatCrossSection(mesh, 'height') + '</td>'
                + '<td data-col="csg" class="dim">' + (mesh.csg_nodes !== undefined ? mesh.csg_nodes : '—') + '</td>'
                + '<td data-col="feature" class="dim">' + (mesh.csg_features !== undefined ? mesh.csg_features : '—') + '</td>';
            tbody.appendChild(row);
        }
        this.applyOptionVisibility();
    }

    formatCrossSection(mesh, axis) {
        const nominalKey = axis === 'width' ? 'nominal_width' : 'nominal_height';
        const perfectKey = axis === 'width' ? 'perfect_width' : 'perfect_height';
        const legacyKey = axis === 'width' ? 'prism_width' : 'prism_height';

        const selected = this.options.showNominalSizes ? mesh[nominalKey] : mesh[perfectKey];
        const value = selected !== undefined ? selected : mesh[legacyKey];
        return value === undefined ? '—' : this.app.fmt(value);
    }

    formatLength(mesh) {
        // The finished piece rather than the stock it was cut from: a timber
        // with an end joint is never cut to length first, so its declared
        // length is not a dimension anyone meant (see docs/concepts.md).
        const exactLengthM = KigumiUnits.memberLengthMeters(mesh);
        if (exactLengthM === null) {
            return '—';
        }
        if (this.options.showRoughLength) {
            return this.app.fmt(exactLengthM + (this.roughLengthAllowanceMm / 1000));
        }
        return this.app.fmt(exactLengthM);
    }

    applyOptionVisibility() {
        const table = this.app.renderRoot && this.app.renderRoot.querySelector
            ? this.app.renderRoot.querySelector('#timber-panel table')
            : null;
        if (!table) {
            return;
        }

        table.classList.toggle('member-hide-tags', !this.options.showTags);
        table.classList.toggle('member-hide-csg', !this.options.showCsgFeatureCount);

        const lengthHeader = table.querySelector('th[data-col="length"]');
        if (lengthHeader) {
            lengthHeader.textContent = this.options.showRoughLength ? 'Length (Rough)' : 'Length (Exact)';
        }

        const widthHeader = table.querySelector('th[data-col="width"]');
        if (widthHeader) {
            widthHeader.textContent = this.options.showNominalSizes ? 'Width (Nominal)' : 'Width (Perfect)';
        }

        const heightHeader = table.querySelector('th[data-col="height"]');
        if (heightHeader) {
            heightHeader.textContent = this.options.showNominalSizes ? 'Height (Nominal)' : 'Height (Perfect)';
        }
    }
}

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = String(value);
    return div.innerHTML;
}
