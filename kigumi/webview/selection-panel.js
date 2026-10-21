import { html } from 'lit';

const KigumiUnits = window.KigumiUnits;
const KigumiMeasurements = window.KigumiMeasurements;
const TagIndex = window.TagIndex;
const KigumiSelectionCopy = window.KigumiSelectionCopy;
const { overlayHeader } = window.KigumiOverlay;

/**
 * The selection pane: what is selected, as stock and as a path into the CSG.
 *
 * Follows the panel shape already in the viewer. It owns whether it is
 * collapsed, since nothing outside it cares, and asks the app for anything about
 * the frame or the selection.
 */
export class SelectionPanel {
    constructor(app, { t, csgTreeView, featureTypeNouns }) {
        this.app = app;
        this.t = t;
        this.CsgTreeView = csgTreeView;
        this.featureTypeNouns = featureTypeNouns;
        // Open until the user collapses it to its header.
        this.collapsed = false;
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
        action.textContent = this.t('viewer.selection.measureFrom');
        action.title = this.t('viewer.selection.measureFrom.title');
        action.addEventListener('click', (event) => {
            event.stopPropagation();
            this.app.startMeasurementFromFocus();
        });
        return action;
    }

    /**
     * While an end is held: how to pick the second feature, one line each, and the
     * way out below it -- a button, or Escape. There is nothing to confirm: the
     * second feature is confirmed by being clicked.
     */
    _measuringHint() {
        const box = document.createElement('div');
        box.className = 'ip-measure-hint';
        for (const key of ['pick', 'byTimber']) {
            const line = document.createElement('div');
            line.textContent = this.t(`viewer.selection.measuring.${key}`);
            box.appendChild(line);
        }
        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.className = 'ip-action ip-measure';
        cancel.textContent = this.t('viewer.selection.measuring.cancel');
        cancel.title = this.t('viewer.selection.measuring.cancel.title');
        cancel.addEventListener('click', (event) => {
            event.stopPropagation();
            this.app.escapeMeasurement();
        });
        box.appendChild(cancel);
        return box;
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

    /** For an angle: measure the other side of the corner. */
    _angleFlipRow(found) {
        if (!found.measure.angle) {
            return null;
        }
        const line = document.createElement('div');
        line.className = 'ip-detail';
        const action = document.createElement('button');
        action.type = 'button';
        action.className = 'ip-action';
        action.textContent = this.t('viewer.selection.flipAngle');
        action.title = this.t('viewer.selection.flipAngle.title');
        action.addEventListener('click', (event) => {
            event.stopPropagation();
            this.app.flipMeasurementAngle(found.viewportId, found.measureKey);
        });
        line.appendChild(action);
        return line;
    }

    updateInfo(frameData) {
        this.app.currentFrameData = frameData || {};
        const selectedMembers = this.app.selectionManager.getSelectedTimbers();
        let selectedSingleName = '';
        let selectedKnownCount = 0;

        for (const selectedKey of selectedMembers) {
            const metadata = this.app.memberMetadataByKey.get(selectedKey);
            if (!metadata) {
                continue;
            }
            selectedKnownCount += 1;
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
                    derivation: detail && detail.derivation,
                },
                this.featureTypeNouns(),
            ).join(' \u203a ');
        }

        // A derived edge or point, named by the features it is formed from.
        const derivedFrom = focus && detail
            ? this.CsgTreeView.derivedFromPaths(
                (this.app.memberMetadataByKey.get(focus.timberKey) || {}).name || focus.timberKey,
                detail.derivation)
            : null;

        // What is selected, in one line: the path to a focus, the member's name,
        // or how many there are.
        let selected = null;
        if (focus) {
            selected = breadcrumb;
        } else if (selectedKnownCount === 1) {
            selected = selectedSingleName;
        } else if (selectedKnownCount > 1) {
            selected = `(${selectedKnownCount})`;
        }

        this._renderInfoPanel({
            selected,
            derivedFrom,
            canCopy: KigumiSelectionCopy.canCopy(selectedKnownCount, Boolean(focus && focus.featureLabel)),
            tags: selectedTags,
            size: selectedSize,
        });
    }

    /** What "copy for AI" describes, and what an agent asking about this view is told:
     *  the focused feature, or the selected members. */
    selectionForCopy() {
        const frame = this.app.currentFrameData || {};
        const placements = new Map((frame.timbers || []).map((timber) => [timber.name, timber]));
        const focus = this.app.selectionManager.csgFocus;
        let feature = null;
        if (focus && focus.featureLabel) {
            const metadata = this.app.memberMetadataByKey.get(focus.timberKey) || {};
            const detail = this.app.lastPickDetail || {};
            const picked = this.app.pickedFeature || {};
            feature = {
                timberName: metadata.name || focus.timberKey,
                memberKey: focus.timberKey,
                path: (focus.path || []).join(' \u203a '),
                featureLabel: focus.featureLabel,
                featureType: detail.featureType || null,
                jointName: detail.jointName || null,
                geometry: picked.geometry || null,
                reference: picked.reference || null,
            };
        }
        const members = this.app.selectionManager.getSelectedTimbers()
            .slice(0, KigumiSelectionCopy.MAX_MEMBERS)
            .map((key) => this.memberForCopy(key, placements));
        return { frameName: frame.name || null, members, feature };
    }

    /** One member, as selection-copy.js's memberLines takes it. */
    memberForCopy(key, placements = null) {
        const frame = this.app.currentFrameData || {};
        const placed = placements || new Map((frame.timbers || []).map((timber) => [timber.name, timber]));
        const metadata = this.app.memberMetadataByKey.get(key) || {};
        const mesh = metadata.mesh || {};
        const size = (value) => (Number.isFinite(Number(value)) ? Number(value) : null);
        return {
            key,
            name: metadata.name || key,
            type: metadata.type || 'timber',
            width: size(mesh.perfect_width),
            height: size(mesh.perfect_height),
            length: KigumiUnits.memberLengthMeters(mesh),
            placement: metadata.type === 'accessory' ? null : placed.get(metadata.name) || null,
            tags: metadata.tags || [],
        };
    }

    _copyButton() {
        const action = document.createElement('button');
        action.type = 'button';
        action.className = 'ip-action ip-copy';
        action.textContent = this.t('viewer.selection.copyForAI');
        action.title = this.t('viewer.selection.copyForAI.title');
        action.addEventListener('click', (event) => {
            event.stopPropagation();
            this.app.copySelectionForAI(this.selectionForCopy());
            action.textContent = this.t('viewer.selection.copied');
            setTimeout(() => {
                action.textContent = this.t('viewer.selection.copyForAI');
            }, 1500);
        });
        return action;
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

        const header = overlayHeader(this.t('viewer.selection.header'), {
            collapsed: this.collapsed,
            onToggle: () => {
                this.collapsed = !this.collapsed;
                this.updateInfo(this.app.currentFrameData);
            },
        });

        // Getting into and out of a drawing lives in the header rather than the
        // body: a way out of a drawing that can be collapsed is a trap. Absent
        // entirely while drawing mode is off, which is what keeps the viewer in
        // the 3D scene.
        if (this.app.drawingBetaEnabled) {
            header.appendChild(this._drawingButton());
        }
        panel.appendChild(header);

        const body = document.createElement('div');
        body.className = 'ip-body';

        // Collapsed, the panel keeps only how a focused measurement is measured: it
        // appears right after making one, and a control you have to go looking for is
        // one nobody finds.
        if (this.collapsed) {
            const measurement = this.app.focusedMeasurement();
            const rows = measurement
                ? [this._measureKindRow(measurement), this._angleFlipRow(measurement)].filter(Boolean)
                : [];
            if (rows.length > 0) {
                rows.forEach((row) => body.appendChild(row));
                panel.appendChild(body);
            }
            return;
        }

        const selected = document.createElement('div');
        selected.className = 'ip-breadcrumb';
        selected.textContent = summary.selected
            ? this.t('viewer.selection.selected', { what: summary.selected })
            : this.t('viewer.selection.none');
        selected.title = selected.textContent;
        body.appendChild(selected);

        // Which view it is in, when there are several: the others show nothing selected.
        if (summary.selected && this.app.isInDrawing && this.app.viewports.length > 1) {
            const view = document.createElement('div');
            view.className = 'ip-detail ip-in-view';
            view.textContent = this.t('viewer.selection.inView', { view: this.app.selectionManager.scope });
            body.appendChild(view);
        }

        if (summary.derivedFrom) {
            const from = document.createElement('div');
            from.className = 'ip-derived-from';
            const label = document.createElement('div');
            label.className = 'ip-detail-label';
            label.textContent = this.t('viewer.selection.derivedFrom');
            from.appendChild(label);
            summary.derivedFrom.forEach((path, index) => {
                if (index > 0) {
                    const cross = document.createElement('div');
                    cross.className = 'ip-derived-cross';
                    cross.textContent = '\u2716\ufe0f';
                    from.appendChild(cross);
                }
                const line = document.createElement('div');
                line.className = 'ip-derived-path';
                line.textContent = path;
                from.appendChild(line);
            });
            body.appendChild(from);
        }

        if (summary.canCopy) {
            const line = document.createElement('div');
            line.className = 'ip-detail ip-copy-line';
            line.appendChild(this._copyButton());
            body.appendChild(line);
        }

        if (summary.size) {
            // No member name here: the line above already carries it, and the
            // room is better spent on the dimensions.
            const size = document.createElement('div');
            size.className = 'ip-size';
            size.textContent = summary.size;
            size.title = summary.size;
            body.appendChild(size);
        }

        // Measuring from what is focused. Present while a measurement is being
        // made too, since that is when it becomes the way to finish one.
        if (this.app.canStartMeasurement || this.app.measureDraft.isActive) {
            const line = document.createElement('div');
            line.className = 'ip-detail ip-measure-line';
            line.appendChild(this.app.measureDraft.isActive ? this._measuringHint() : this._measureButton());
            body.appendChild(line);
        }

        const measurement = this.app.focusedMeasurement();
        if (measurement) {
            const kindRow = this._measureKindRow(measurement);
            if (kindRow) {
                body.appendChild(kindRow);
            }
            const flipRow = this._angleFlipRow(measurement);
            if (flipRow) {
                body.appendChild(flipRow);
            }
        }

        // The pills the member rows no longer carry: they live here, where
        // there is room for them, and only for what is selected.
        if (summary.tags && summary.tags.length > 0) {
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

        const detail = this.app.lastPickDetail;
        if (detail && this.app.selectionManager.csgFocus) {
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
