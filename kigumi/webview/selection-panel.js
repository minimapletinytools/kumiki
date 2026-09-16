import { html } from 'lit';

const KigumiUnits = window.KigumiUnits;
const KigumiMeasurements = window.KigumiMeasurements;
const TagIndex = window.TagIndex;

/**
 * The selection pane: what is selected, as stock and as a path into the CSG.
 *
 * Follows the panel shape already in the viewer. It owns whether it is
 * expanded, since nothing outside it cares, and asks the app for anything about
 * the frame or the selection.
 */
export class SelectionPanel {
    constructor(app, { t, csgTreeView, featureTypeNouns }) {
        this.app = app;
        this.t = t;
        this.CsgTreeView = csgTreeView;
        this.featureTypeNouns = featureTypeNouns;
        // It never expands itself -- expanding is the user's choice, and the
        // CSG trees live in the layers panel rather than here.
        this.expanded = false;
    }

    render() {
        return html`<div id="info-panel" class="ip-panel"></div>`;
    }

    /** The draw / close button, which is the way into and out of a drawing. */
    _drawingButton() {
        const action = document.createElement('button');
        action.type = 'button';
        action.className = 'ip-action';
        const inDrawing = this.app.isInDrawing;
        // Drawing nothing means drawing the whole frame, which is a reasonable
        // thing to ask for -- so rather than disabling the button with nothing
        // selected, it says which of the two it is about to do.
        const drawKey = window.drawButtonKey(
            this.app.selectionManager.getSelectedTimbers().length);
        action.textContent = inDrawing
            ? this.t('viewer.selection.leaveDrawing')
            : this.t(drawKey);
        action.title = inDrawing
            ? this.t('viewer.selection.leaveDrawing.title')
            : this.t(`${drawKey}.title`);
        action.addEventListener('click', (event) => {
            event.stopPropagation();
            if (inDrawing) {
                this.app.leaveDrawing();
            } else {
                this.app.drawSelection();
            }
        });
        return action;
    }

    /**
     * Start a measurement from the feature being looked at.
     *
     * In the body rather than the header: it is about what is selected, which
     * is what the body is, and unlike the way out of a drawing there is no harm
     * in it being collapsed away when nothing is focused.
     */
    _measureButton() {
        const action = document.createElement('button');
        action.type = 'button';
        action.className = 'ip-action ip-measure';
        const making = this.app.measureDraft.isActive;
        // There is nothing to confirm: the second feature is confirmed by being
        // clicked, and what the click takes is already drawn under the pointer.
        // So while an end is held this is the way OUT, which is otherwise only
        // on the Escape key.
        action.textContent = making
            ? this.t('viewer.selection.measureCancel')
            : this.t('viewer.selection.measureFrom');
        action.title = making
            ? this.t('viewer.selection.measureCancel.title')
            : this.t('viewer.selection.measureFrom.title');
        action.addEventListener('click', (event) => {
            event.stopPropagation();
            if (making) {
                this.app.escapeMeasurement();
            } else {
                this.app.startMeasurementFromFocus();
            }
        });
        return action;
    }

    /**
     * How the focused measurement is measured.
     *
     * Always said; only OFFERED when there is something to offer. A pair of
     * points admits three kinds and a pair of crossing lines admits exactly
     * one, and a dropdown holding a single entry is a control that lies about
     * being one -- so one kind reads out as a value and several become a
     * choice. What the measurement comes to is already on the row in the
     * drawing panel, so this says how rather than how much.
     */
    _measureKindRow(found) {
        const available = found.available || [];
        // The written kind BY NAME, or the one the view falls back to when none
        // was written -- which is what is being drawn, so it is what to show.
        //
        // By name because that is what `available` holds. A kind arrives from
        // python structured -- {operation, space, direction} -- and comparing
        // that object against a list of names matched nothing, so every
        // measurement looked as though its kind were unavailable: the dropdown
        // appeared even with a single choice, and the entry it showed was
        // labelled from a key built out of "[object Object]".
        const space = found.status && found.status.space;
        const current = KigumiMeasurements.kindName(found.measure.kind, space)
            || (found.status && found.status.kind);
        // A kind this view cannot draw is still the kind this measurement is.
        // Showing an alternative as though it were selected would misreport it,
        // so it is listed, unselectable, and choosing anything else is the way
        // out of it.
        const broken = current && available.indexOf(current) === -1;
        if (!current && available.length === 0) {
            // Nothing is known about how this is measured, so there is nothing
            // to say about it.
            return null;
        }
        const line = document.createElement('div');
        line.className = 'ip-detail';
        const label = document.createElement('span');
        label.className = 'ip-detail-label';
        label.textContent = this.t('viewer.selection.measureKind');
        line.appendChild(label);

        // What the dropdown would hold: everything on offer, plus the written
        // kind when this view cannot draw it -- that one is listed unselectable
        // so the measurement is not misreported, and it counts, because with it
        // there IS something to change away from.
        const choices = available.length + (broken ? 1 : 0);
        if (choices < 2) {
            // Nothing to choose between. WHICH kind it is is still worth
            // saying, so it is said as a value -- a dropdown holding a single
            // entry is a control that lies about being one, and offering to
            // change what cannot change is worse than reading it out.
            const value = document.createElement('span');
            value.className = 'ip-detail-value';
            value.textContent = this.t(`viewer.measure.kind.${current || available[0]}`);
            line.appendChild(value);
            return line;
        }

        const select = document.createElement('select');
        select.className = 'ip-kind';
        if (broken) {
            const option = document.createElement('option');
            option.value = current;
            option.textContent = this.t('viewer.measure.kind.' + current);
            option.selected = true;
            option.disabled = true;
            select.appendChild(option);
        }
        for (const kind of available) {
            const option = document.createElement('option');
            option.value = kind;
            option.textContent = this.t('viewer.measure.kind.' + kind);
            option.selected = kind === current;
            select.appendChild(option);
        }
        select.addEventListener('change', () => {
            this.app.setMeasurementKind(found.viewportId, found.measureKey, select.value);
        });
        line.appendChild(select);
        return line;
    }

    updateInfo(frameData) {
        this.app.currentFrameData = frameData || {};
        const timberCount = frameData && frameData.timber_count ? frameData.timber_count : 0;
        const accessoriesCount = frameData && frameData.accessories_count ? frameData.accessories_count : 0;
        const selectedMembers = this.app.selectionManager.getSelectedTimbers();
        let selectedTimberCount = 0;
        let selectedAccessoryCount = 0;
        let selectedSingleName = '';
        let selectedKnownCount = 0;

        for (const selectedKey of selectedMembers) {
            const metadata = this.app.memberMetadataByKey.get(selectedKey);
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

        const selectedTags = this._selectedTags(selectedMembers);
        // Only with exactly one member selected: two sets of dimensions in one
        // line would read as one member's.
        const selectedSize = selectedKnownCount === 1
            ? this._describeMemberSize(this.app.memberMetadataByKey.get(selectedMembers[0]))
            : null;

        const focus = this.app.selectionManager.csgFocus;
        const detail = this.app.lastPickDetail;
        let breadcrumb = selectedSingleName;
        if (focus) {
            const focused = this.app.memberMetadataByKey.get(focus.timberKey);
            breadcrumb = this.CsgTreeView.breadcrumbSegments(
                (focused && focused.name) || focus.timberKey,
                focus.path,
                {
                    featureLabel: focus.featureLabel,
                    featureType: detail && detail.featureType,
                    nodeKind: detail && detail.nodeKind,
                    nodeDisplayName: detail && detail.nodeDisplayName,
                    nodeLabel: detail && detail.nodeLabel,
                },
                this.featureTypeNouns(),
            ).join(' \u203a ');
        }

        this._renderInfoPanel({
            timberCount,
            accessoriesCount,
            selectedTimberCount,
            selectedAccessoryCount,
            breadcrumb,
            tags: selectedTags,
            size: selectedSize,
        });
    }

    _describeMemberSize(metadata) {
        const mesh = metadata && metadata.mesh;
        if (!mesh || metadata.type === 'accessory') {
            return null;
        }
        const width = this.app.memberListPanel.formatCrossSection(mesh, 'width');
        const height = this.app.memberListPanel.formatCrossSection(mesh, 'height');
        // cut_length is absent on an older runner; the uncut length is the
        // honest fallback, and it is what the member list shows anyway.
        const lengthMeters = KigumiUnits.memberLengthMeters(mesh);
        const lengthValue = lengthMeters === null ? '—' : this.app.fmt(lengthMeters);
        if (width === '—' || height === '—' || lengthValue === '—') {
            return null;
        }
        return `${width} x ${height} - ${lengthValue}`;
    }

    _selectedTags(selectedMembers) {
        const byId = new Map();
        for (const key of selectedMembers) {
            const metadata = this.app.memberMetadataByKey.get(key);
            for (const tag of (metadata && metadata.tags) || []) {
                byId.set(tag.kind + ':' + tag.name, tag);
            }
        }
        const kindRank = (kind) => {
            const rank = TagIndex.KIND_ORDER.indexOf(kind);
            return rank === -1 ? TagIndex.KIND_ORDER.length : rank;
        };
        return Array.from(byId.values()).sort((a, b) => (
            kindRank(a.kind) - kindRank(b.kind) || a.name.localeCompare(b.name)
        ));
    }

    _renderInfoPanel(summary) {
        const panel = this.app.renderRoot.querySelector('#info-panel');
        if (!panel) {
            return;
        }

        panel.className = 'ip-panel';
        panel.innerHTML = '';

        const header = document.createElement('div');
        header.className = 'ip-header';
        const chev = document.createElement('span');
        chev.className = 'ip-chev';
        chev.textContent = this.expanded ? '\u25be' : '\u25b8';
        header.appendChild(chev);
        const headerTitle = document.createElement('span');
        headerTitle.className = 'ip-title';
        headerTitle.textContent = this.t('viewer.selection.header');
        header.appendChild(headerTitle);
        header.addEventListener('click', () => {
            this.expanded = !this.expanded;
            this.updateInfo(this.app.currentFrameData);
        });

        // Getting into and out of a drawing lives in the header rather than the
        // body: the body is collapsed by default, and a way out of a drawing
        // that can be collapsed is a trap. Absent entirely while drawing mode
        // is off, which is what keeps the viewer in the 3D scene.
        if (this.app.drawingBetaEnabled) {
            header.appendChild(this._drawingButton());
        }
        panel.appendChild(header);

        const body = document.createElement('div');
        body.className = 'ip-body';

        const counts = document.createElement('div');
        counts.className = 'ip-counts';
        counts.textContent = this.t('viewer.selection.counts', {
            selectedTimbers: summary.selectedTimberCount,
            timbers: summary.timberCount,
            selectedAccessories: summary.selectedAccessoryCount,
            accessories: summary.accessoriesCount,
        });
        body.appendChild(counts);

        if (summary.size) {
            // No member name here: the breadcrumb underneath already carries it,
            // and the room is better spent on the dimensions.
            const size = document.createElement('div');
            size.className = 'ip-size';
            size.textContent = summary.size;
            size.title = summary.size;
            body.appendChild(size);
        }

        // Not behind the expander: it appears when a measurement is focused,
        // which is immediately after making one, and a control you have to go
        // looking for is one nobody finds.
        const measurement = this.app.focusedMeasurement();
        if (measurement) {
            const kindRow = this._measureKindRow(measurement);
            if (kindRow) {
                body.appendChild(kindRow);
            }
        }

        // Measuring from what is focused. Present while a measurement is being
        // made too, since that is when it becomes the way to finish one.
        if (this.app.canStartMeasurement || this.app.measureDraft.isActive) {
            const line = document.createElement('div');
            line.className = 'ip-detail';
            line.appendChild(this._measureButton());
            body.appendChild(line);
        }

        if (summary.breadcrumb) {
            const crumb = document.createElement('div');
            crumb.className = 'ip-breadcrumb';
            crumb.textContent = summary.breadcrumb;
            crumb.title = summary.breadcrumb;
            body.appendChild(crumb);
        }

        // The pills the member rows no longer carry: they live here, where
        // there is room for them, and only for what is selected.
        if (this.expanded && summary.tags && summary.tags.length > 0) {
            const line = document.createElement('div');
            line.className = 'ip-detail ip-tags';
            const label = document.createElement('span');
            label.className = 'ip-detail-label';
            label.textContent = this.t('viewer.selection.tags');
            line.appendChild(label);
            const chips = document.createElement('span');
            chips.className = 'ip-chips';
            for (const tag of summary.tags) {
                const chip = document.createElement('span');
                chip.className = 'tag-chip';
                chip.dataset.tagKind = tag.kind;
                chip.textContent = tag.name;
                chips.appendChild(chip);
            }
            line.appendChild(chips);
            body.appendChild(line);
        }

        // Detail lines are the reward for expanding, so they stay behind it.
        const detail = this.app.lastPickDetail;
        if (this.expanded && detail && this.app.selectionManager.csgFocus) {
            const normalText = this.CsgTreeView.describeOutwardNormal(
                detail.outwardNormal,
                detail.facesToward,
                this.t('viewer.selection.approximatelyFacing'),
            );
            for (const [key, value] of [
                ['viewer.selection.featureType', detail.featureType],
                ['viewer.selection.joint', detail.jointName],
                ['viewer.selection.normal', normalText],
            ]) {
                if (!value) {
                    continue;
                }
                const line = document.createElement('div');
                line.className = 'ip-detail';
                const label = document.createElement('span');
                label.className = 'ip-detail-label';
                label.textContent = this.t(key);
                const val = document.createElement('span');
                val.className = 'ip-detail-value';
                val.textContent = String(value).toLowerCase();
                line.appendChild(label);
                line.appendChild(val);
                body.appendChild(line);
            }
        }

        panel.appendChild(body);
    }}
