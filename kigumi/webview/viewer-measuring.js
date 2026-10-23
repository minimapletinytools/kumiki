/**
 * Measurements: making one (picking its ends, kind and placement), changing and deleting them, and drawing them on the page.
 *
 * A mixin of the viewer (viewer-app.js): its methods run as the viewer's.
 */

import { KigumiMeasurements, MEASUREMENT_ANGLE_RADIUS_PX, MEASUREMENT_CODE_ORIGIN, MEASUREMENT_DRAG_SLOP_PX, MEASUREMENT_OFFSET_PX, MEASUREMENT_SETTLE_MS, THREE_D_MEASUREMENTS_ID, anchorName, describeAnchor, measurementKey, t, vscode } from './viewer-shared.js';

export const MeasuringMixin = (Base) => class extends Base {

    get canStartMeasurement() {
        return Boolean(this.drawingBetaEnabled
            && this.selectionManager.csgFocus
            && this._lastPickAnchor
            && this._lastPickAnchor.reference
            && this._lastPickAnchor.geometry);
    }

    /**
     * Begin a measurement from the feature being looked at.
     *
     * Deliberately an explicit action rather than a click meaning something
     * different in a drawing. That is what leaves a drawing with a plain
     * selection, and what makes the first end something you chose rather than
     * something the last click happened to leave behind.
     */
    startMeasurementFromFocus() {
        if (!this.canStartMeasurement) {
            return;
        }
        const result = this.measureDraft.hold(this._lastPickAnchor);
        if (result.action !== 'holding') {
            this.reportMeasureRefusal(result.reason);
            return;
        }
        // Nothing half-made is on the stack to undo, so undo would reach past
        // it to something you are no longer looking at.
        this.undoStacks.suspend(true);
        this.emitViewerLog('measure-hold', {
            feature: this._lastPickAnchor.reference.feature || null,
        });
        this._reaskHover();
        this._measureStateChanged();
    }

    /**
     * A measurement started, finished or was let go of. The info pane says which, and it is
     * built from scratch rather than bound, so it has to be told.
     */
    _measureStateChanged() {
        if (this.selectionPanel) {
            this.selectionPanel.updateInfo(this.currentFrameData);
        }
        this.requestUpdate();
    }

    /** A pick came back while a measurement is being made. Offers it to the draft. */
    _measurePicked(message) {
        // A pick the hover painted red never gets here: handleCSGSelectionResult stops it.
        const anchor = this._anchorFromPick(message);
        // Into the view it was made in, which is the selection's: picking in another drops it.
        const result = this.measureDraft.confirm(anchor, this.selectionManager.scope);
        this.emitViewerLog('measure-pick', {
            feature: message.featureLabel, action: result.action, reason: result.reason,
        });
        if (result.action === 'refused') {
            this.reportMeasureRefusal(result.reason);
            return;
        }
        this._writeMeasurement(
            result.measurement, (message.verdict && message.verdict.kinds) || null);
        this._measureStateChanged();
    }

    /** What a pick offers as one end of a measurement. */
    _anchorFromPick(message) {
        // One object, from the runner, read by the colour, the preview and the
        // click alike. Null when no measurement is being made; kinds empty when
        // this pair admits nothing from here. See .claude/plans/measuring-states.md.
        const verdict = message.verdict || null;
        return {
            // The same key the selection and the hover name this feature by,
            // so a held end merges with them into one feature state.
            featureKey: window.KigumiFeatureStates.featureKeyOf({
                memberKey: message.memberKey || (this.selectionManager.csgFocus || {}).timberKey,
                path: message.path,
                featureLabel: message.featureLabel,
            }),
            reference: message.reference || null,
            geometry: message.geometry || null,
            at: message.at || null,
            verdict,
            plane: (verdict && verdict.plane) || null,
            // Where the pair would attach. The runner works it out with the
            // rules that place a written measurement, so the preview sits where
            // the result will.
            anchors: (verdict && verdict.anchors) || null,
            highlight: {
                highlightMesh: message.highlightMesh,
                highlightEdgeSegments: message.highlightEdgeSegments,
            },
        };
    }

    /**
     * Write the measurement the click just took.
     *
     * There is no confirm step: the preview under the pointer was already what
     * this writes, so clicking it IS the confirmation. See
     * .claude/plans/measuring-states.md.
     *
     * The kind is the first the pair admits from here, which the runner worked
     * out while judging the pick. Written rather than left blank: no kind reads
     * as "whatever this view admits", which draws the right dimension today and
     * quietly becomes a different one when the viewport moves.
     */
    _writeMeasurement(measurement, kinds) {
        // Structured, not named, so a solid angle cannot be read back as the
        // projected one it shares a name with.
        const kind = KigumiMeasurements.kindWire(
            (kinds && kinds[0]) || null, this.measurementSpace);
        this.undoStacks.suspend(false);
        this._measurePreview = null;
        // The feature selection has served its purpose; the measurement it made
        // takes its place, so the kind can be changed in the moment you want to
        // change it.
        this._dropCsgFocus();
        this.selectionManager.clearTimberSelection();
        this._reaskHover();

        const drawingId = this.measurementDrawingId;
        // Focused once it arrives, so the kind can be changed without hunting
        // for the row it landed on.
        this._focusMeasurementOnArrival = {
            viewportId: measurement.viewportId,
            measureKey: measurementKey(measurement),
        };
        const payload = {
            type: 'addMeasurement',
            drawingId,
            viewportId: measurement.viewportId,
            a: measurement.a,
            b: measurement.b,
            plane: measurement.plane,
            kind,
        };
        this.emitViewerLog('measurement-created', {
            drawing: drawingId,
            viewport: measurement.viewportId || null,
            from: describeAnchor(measurement.a),
            to: describeAnchor(measurement.b),
            kind,
        });
        this.undoStacks.push(this.frameKey, drawingId, {
            label: 'measure',
            redo: payload,
            undo: {
                type: 'deleteMeasurement',
                drawingId,
                viewportId: measurement.viewportId,
                a: measurement.a,
                b: measurement.b,
            },
        });
        this._sendMeasurementCommand(payload);
        this.requestUpdate();
    }

    /**
     * Ask the hover its question again, the held end having changed.
     *
     * The place did not change, the question did -- the same reason Tab does
     * this. What sits under the pointer is drawn in the colour that says
     * whether a click will be taken, and that answer turns on what is held.
     * Taking or releasing an end is a button or a key, so the pointer does not
     * move, and the hover only asks when it moves: without this the verdict on
     * screen is the one from before the end was taken, and stays that way until
     * the pointer happens to move.
     */
    _reaskHover() {
        if (this._hover) {
            this._hover.askAgain();
        }
    }

    /** Release the most recent end, or leave the flow. */
    escapeMeasurement() {
        const released = this.measureDraft.escape();
        if (released.action === 'none') {
            return false;
        }
        if (released.action === 'left') {
                this.undoStacks.suspend(false);
        }
        this._measurePreview = null;
        this.renderMeasurements();
        this.emitViewerLog('measure-escape', { action: released.action });
        this._reaskHover();
        this._measureStateChanged();
        return true;
    }

    /** Changing scene or mode: hold nothing, show nothing held. */
    clearMeasureDraft() {
        this.measureDraft.leave();
        this._measurePreview = null;
        this.undoStacks.suspend(false);
        this._reaskHover();
        this._measureStateChanged();
    }

    _sendMeasurementCommand(payload) {
        if (typeof vscode !== 'undefined') {
            vscode.postMessage(payload);
        }
    }

    /**
     * The measurement being looked at, with what this view makes of it.
     *
     * Defaults to the focused one; the arguments ask about a particular one.
     */
    focusedMeasurement(viewportId, measureKey) {
        let wanted = { viewportId, measureKey };
        if (viewportId === undefined) {
            const focus = this.selectionManager.measurementFocus;
            if (!focus) {
                return null;
            }
            wanted = focus;
        }
        // A drawing's measurements hang off its viewports; the 3D view's live
        // in a reserved drawing of their own and are on no viewport the scene
        // knows about. Looking only at the scene's viewports found none of
        // them, which quietly took the kind dropdown, the drag and delete with
        // it -- all three ask this first.
        const viewport = this.viewports.find((one) => one.id === wanted.viewportId);
        const measure = (viewport ? (viewport.spec.measurements || []) : [])
            .concat(this._threeDMeasurements())
            .find((one) => measurementKey(one) === wanted.measureKey);
        if (!measure) {
            return null;
        }
        // A 3D measurement is on no viewport, and carries its own plane, so
        // there is nothing for the plane to be checked against.
        const axes = viewport ? this.viewportAxes(viewport) : { look: [0, 0, -1] };
        const status = KigumiMeasurements.measurementStatus(
            measure, axes, this.viewportProjection(viewport));
        return {
            viewportId: wanted.viewportId,
            measureKey: wanted.measureKey,
            measure,
            status,
            // Every kind this pair admits here, refusals included: a measurement
            // whose kind this view cannot draw, or one that comes to zero, is
            // the one most worth offering another kind for. The runner settles
            // them and sends them with every answer, refusals included, so
            // there is nothing to work out here and nothing to fall back to --
            // a measurement it could not place offers none, which is the truth
            // about it rather than a gap.
            available: status.available || [],
        };
    }

    /**
     * Change what a measurement measures between its two features.
     *
     * Sent as an update rather than an add: an add replaces whatever measured
     * that pair, which would make this indistinguishable from a create on the
     * undo stack.
     */
    setMeasurementKind(viewportId, measureKey, kind) {
        const found = this.focusedMeasurement(viewportId, measureKey);
        if (!found) {
            return;
        }
        const drawingId = this.measurementDrawingId;
        const space = this.measurementSpace;
        const asked = KigumiMeasurements.kindWire(kind, space);
        const was = KigumiMeasurements.kindWire(found.measure.kind || null, space);
        const where = {
            drawingId,
            viewportId,
            a: KigumiMeasurements.anchorReference(found.measure.a),
            b: KigumiMeasurements.anchorReference(found.measure.b),
            measureId: found.measure.measureId || null,
        };
        this._focusMeasurementOnArrival = { viewportId, measureKey };
        this.undoStacks.push(this.frameKey, drawingId, {
            label: 'measurement kind',
            redo: { type: 'updateMeasurement', ...where, changes: { kind: asked } },
            undo: { type: 'updateMeasurement', ...where, changes: { kind: was } },
        });
        this._sendMeasurementCommand(
            { type: 'updateMeasurement', ...where, changes: { kind: asked } });
        this.emitViewerLog('measure-kind', { viewport: viewportId, kind: asked });
    }

    /**
     * Delete each measurement in `foundList` (focusedMeasurement results).
     *
     * See MEASUREMENT_CODE_ORIGIN for what that does to each; one already
     * deleted is passed over. Each gets its own undo entry, so undoing a batch
     * puts them back one at a time.
     */
    _deleteMeasurements(foundList) {
        if (this.measureDraft.isActive) {
            return false;
        }
        const drawingId = this.measurementDrawingId;
        const removable = (foundList || [])
            .filter((found) => found && !KigumiMeasurements.isDeleted(found.measure));
        if (removable.length === 0) {
            return false;
        }
        for (const found of removable) {
            const measure = found.measure;
            const a = KigumiMeasurements.anchorReference(measure.a);
            const b = KigumiMeasurements.anchorReference(measure.b);
            const payload = {
                type: 'deleteMeasurement',
                drawingId,
                viewportId: found.viewportId,
                a,
                b,
                measureId: measure.measureId || null,
            };
            this.undoStacks.push(this.frameKey, drawingId, {
                label: 'delete measurement',
                redo: payload,
                // A code one was marked deleted, so undoing puts it back. Any other
                // was taken out of the file, so undoing writes it there again --
                // for an override, the change it carried.
                undo: measure.origin === MEASUREMENT_CODE_ORIGIN
                    ? { ...payload, type: 'restoreMeasurement' }
                    : {
                        type: 'addMeasurement',
                        drawingId,
                        viewportId: found.viewportId,
                        a,
                        b,
                        measureId: measure.measureId || null,
                        kind: measure.kind || null,
                        plane: measure.plane || null,
                        placement: measure.placement || null,
                    },
            });
            this._sendMeasurementCommand(payload);
        }
        return true;
    }

    /** Delete every measurement picked out. */
    deleteMarkedMeasurements() {
        const removed = this._deleteMeasurements(
            this.selectionManager.getMarkedMeasurements()
                .map((mark) => this.focusedMeasurement(mark.viewportId, mark.measureKey)));
        if (!removed) {
            return false;
        }
        this.selectionManager.clearMeasurementMarks();
        return true;
    }

    /** Delete one measurement, named by its viewport and key. */
    deleteMeasurement(viewportId, measureKey) {
        const removed = this._deleteMeasurements([
            this.focusedMeasurement(viewportId, measureKey),
        ]);
        if (!removed) {
            return false;
        }
        this.selectionManager.forgetMeasurement({ viewportId, measureKey });
        return true;
    }

    /** Put back a code measurement the drawings file deleted. */
    restoreMeasurement(viewportId, measureKey) {
        const found = this.focusedMeasurement(viewportId, measureKey);
        if (!found || !KigumiMeasurements.isDeleted(found.measure)) {
            return false;
        }
        const drawingId = this.measurementDrawingId;
        const payload = {
            type: 'restoreMeasurement',
            drawingId,
            viewportId: found.viewportId,
            a: KigumiMeasurements.anchorReference(found.measure.a),
            b: KigumiMeasurements.anchorReference(found.measure.b),
            measureId: found.measure.measureId || null,
        };
        this.undoStacks.push(this.frameKey, drawingId, {
            label: 'put back measurement',
            redo: payload,
            undo: { ...payload, type: 'deleteMeasurement' },
        });
        this._sendMeasurementCommand(payload);
        return true;
    }

    /**
     * Right-click on a measurement, in a list or on the sheet.
     *
     * The same menu either way: copy it for an assistant, or delete it. A
     * deleted one is not drawn, but its list row can still offer to put it
     * back.
     */
    showMeasurementContextMenu({ viewportId, measureKey, clientX, clientY }) {
        const found = this.focusedMeasurement(viewportId, measureKey);
        if (!found) {
            return false;
        }
        const deleted = KigumiMeasurements.isDeleted(found.measure);
        const item = this._measurementForCopy(viewportId, found);
        this.contextMenu.open({
            x: clientX,
            y: clientY,
            title: deleted ? t('viewer.contextMenu.deletedMeasurement') : item.between,
            items: [
                ...this._copyMenuItems(),
                deleted
                    ? { id: 'restore', label: t('viewer.contextMenu.putBack') }
                    : { id: 'delete', label: t('viewer.contextMenu.deleteMeasurement') },
            ],
            onChoose: (id) => {
                if (this._copyFromMenu(id, item)) {
                    return true;
                }
                if (id === 'restore') {
                    return this.restoreMeasurement(viewportId, measureKey);
                }
                if (id === 'delete') {
                    return this.deleteMeasurement(viewportId, measureKey);
                }
                return false;
            },
        });
        this.requestUpdate();
        return true;
    }

    /** A measurement, as selection-copy.js's itemLines takes it. */
    _measurementForCopy(viewportId, found) {
        const { measure, status } = found;
        const named = anchorName;
        const scene = this.sceneStore.activeScene();
        const value = status && status.drawable && status.value
            ? (status.value.unit === 'angle'
                ? `${Number(status.value.value).toFixed(3)} degrees`
                : `${Number(status.value.value)} m`)
            : null;
        return {
            kind: 'measurement',
            drawing: viewportId ? ((scene && (scene.name || scene.id)) || null) : '3D',
            viewport: viewportId || null,
            between: `${named(measure.a)} / ${named(measure.b)}`,
            anchors: [measure.a, measure.b].map((anchor) => ({
                describes: describeAnchor(anchor),
                reference: KigumiMeasurements.anchorReference(anchor),
            })),
            measureKind: measure.kind || null,
            value,
            origin: measure.origin || null,
            refused: status && !status.drawable ? status.reason || null : null,
        };
    }

    /**
     * Take back the last change to this drawing, or put it back.
     *
     * The entries hold a pair of calls rather than a snapshot, because the model
     * of record is python and the viewer keeps no copy to restore. So undoing is
     * sending the other one.
     */
    undoMeasurementChange() {
        const drawingId = this.measurementDrawingId;
        const entry = this.undoStacks.undo(this.frameKey, drawingId);
        if (!entry) {
            return false;
        }
        this.emitViewerLog('measure-undo', { label: entry.label });
        this._sendMeasurementCommand(entry.undo);
        return true;
    }

    redoMeasurementChange() {
        const drawingId = this.measurementDrawingId;
        const entry = this.undoStacks.redo(this.frameKey, drawingId);
        if (!entry) {
            return false;
        }
        this.emitViewerLog('measure-redo', { label: entry.label });
        this._sendMeasurementCommand(entry.redo);
        return true;
    }

    /**
     * Look at the measurement just made, once it comes back.
     *
     * It cannot be focused before then: until the runner answers it is not on a
     * viewport to be focused on.
     */
    _applyPendingMeasurementFocus() {
        const wanted = this._focusMeasurementOnArrival;
        if (!wanted) {
            return;
        }
        this._focusMeasurementOnArrival = null;
        if (!this.focusedMeasurement(wanted.viewportId, wanted.measureKey)) {
            return;
        }
        this.selectionManager.setMeasurementFocus(wanted);
        this._syncDrawingPanel();
        this.selectionPanel.updateInfo(this.currentFrameData);
    }

    /**
     * How far a dimension sits from what it measures, in page pixels.
     *
     * The reader's, when they have moved it; otherwise the viewport's default.
     * A measurement's one degree of freedom once its two ends are fixed.
     */
    _measurementOffset(measure) {
        const placement = measure && measure.placement;
        const offset = placement && placement.offset;
        return typeof offset === 'number' ? offset : null;
    }

    /** How far a dimension has been slid along its two lines, in world units; 0 for not at all. */
    _measurementAlong(measure) {
        const placement = measure && measure.placement;
        const along = placement && placement.along;
        return typeof along === 'number' ? along : 0;
    }

    /**
     * How many screen pixels one world unit is worth along this dimension.
     *
     * Read off the run rather than off the camera: the run is a length we know
     * in the world and have just drawn on the page, so their ratio is the scale
     * at exactly the place the dimension sits -- true under perspective as well,
     * where a scale taken from the camera would not be.
     */
    _pixelsPerWorldUnit(from, to, ends) {
        const world = Math.hypot(to[0] - from[0], to[1] - from[1], to[2] - from[2]);
        const drawn = Math.hypot(ends.to.x - ends.from.x, ends.to.y - ends.from.y);
        return world > 1e-9 ? drawn / world : null;
    }

    /**
     * Where to draw a dimension line, in screen pixels.
     *
     * The stored offset is in WORLD units, so that a dimension stays where it
     * was put as the view zooms -- what changes with zoom is how big the
     * drawing is, not where on it somebody placed a dimension. Only the drawn
     * SIZE of things is measured in pixels: line weights and text stay legible
     * whatever the scale.
     *
     * No stored offset means the viewport's own default, which is a pixel
     * distance -- there is nothing in the world it could be derived from, and
     * an untouched dimension sitting a readable distance away at any zoom is
     * the better default.
     */
    _offsetInPixels(measure, viewportId, measureKey, perWorld) {
        const dragging = this._draggingMeasurement;
        const inWorld = (dragging && dragging.viewportId === viewportId
            && dragging.measureKey === measureKey)
            ? dragging.offset
            : this._measurementOffset(measure);
        if (inWorld === null || !perWorld) {
            return MEASUREMENT_OFFSET_PX;
        }
        return inWorld * perWorld;
    }

    /**
     * The measurement the pointer is currently offering, or null.
     *
     * Drawn from the HOVER, not from any state of its own: while an end is
     * held, whatever is under the pointer is shown as the measurement it would
     * make, and clicking writes exactly that. There is nothing pending in
     * between, and so nothing to keep in step. See .claude/plans/measuring-states.md.
     *
     * Both ends carry their resolved geometry already -- the hover brought it
     * back -- and the anchors are the ones the runner placed for the pair, so
     * the preview sits where the result will.
     */
    _previewMeasurementForDisplay() {
        const preview = this._measurePreview;
        if (!preview) {
            return null;
        }
        const placed = preview.anchors;
        const end = (anchor, at) => ({
            ...anchor.reference, at: at || anchor.at, geometry: anchor.geometry,
        });
        return {
            a: end(preview.held, placed && placed.a),
            b: end(preview.other, placed && placed.b),
            plane: preview.plane || null,
            kind: preview.kind || null,
            angle: preview.angle || null,
            // What it comes to, from the same verdict the picture came from.
            settled: preview.settled || null,
            extents: preview.extents || null,
        };
    }

    /**
     * Offer, or stop offering, the measurement under the pointer.
     *
     * The verdict decides, and it is the same verdict that colours the
     * highlight and that the click will read -- so what is drawn is what
     * clicking takes, by construction rather than by agreement.
     */
    _updateMeasurePreview(message) {
        const held = this.measureDraft.heldEnd;
        const verdict = message && message.verdict;
        const anchor = message ? this._anchorFromPick(message) : null;
        const offered = Boolean(
            held && verdict && verdict.kinds && verdict.kinds.length > 0
            && anchor && this.measureDraft.canTake(anchor).ok);
        const was = this._measurePreview;
        this._measurePreview = offered ? {
            held,
            other: anchor,
            anchors: verdict.anchors || null,
            angle: verdict.angle || null,
            plane: verdict.plane || null,
            kind: verdict.kinds[0],
            settled: verdict.settled || null,
            extents: verdict.extents || null,
        } : null;
        if (was || this._measurePreview) {
            this.renderMeasurements();
        }
    }

    /**
     * Start moving a dimension, if the pointer turns out to be dragging.
     *
     * Armed rather than begun: a click and the start of a drag look identical
     * until the pointer moves, and a click has to keep meaning "select this".
     * So nothing happens until it has travelled far enough to be a gesture.
     */
    _beginMeasurementDrag(event, group, viewportId, measureKey, measure) {
        const run = group._dimensionRun;
        if (!run) {
            return;
        }
        const was = this._measurementOffset(measure);
        const wasPlacement = measure.placement || { offset: was };
        const startAlong = this._measurementAlong(measure);
        const start = { x: event.clientX, y: event.clientY };
        let moved = false;

        const pageOf = (moveEvent) => {
            const canvas = this.renderRoot.querySelector('#viewport');
            const rect = canvas.getBoundingClientRect();
            return { x: moveEvent.clientX - rect.left, y: moveEvent.clientY - rect.top };
        };

        const onMove = (moveEvent) => {
            if (!moved
                && Math.abs(moveEvent.clientX - start.x)
                   + Math.abs(moveEvent.clientY - start.y) < MEASUREMENT_DRAG_SLOP_PX) {
                return;
            }
            moved = true;
            if (run.slide) {
                // Between two lines: the anchors follow the pointer along them, and the dimension
                // sits right between them -- past the end of a line, a phantom carries it on.
                const along = KigumiMeasurements.alongForPointer(
                    startAlong, { x: moveEvent.clientX - start.x, y: moveEvent.clientY - start.y }, run.slide);
                if (along === null) {
                    return;
                }
                this._draggingMeasurement = { viewportId, measureKey, offset: 0, along };
                this.renderMeasurements();
                return;
            }
            const inPixels = KigumiMeasurements.offsetForPointer(
                run.from, run.to, pageOf(moveEvent));
            if (inPixels === null || !run.perWorld) {
                return;
            }
            // Stored in world units: where somebody put a dimension should not
            // depend on how far they happened to be zoomed in at the time.
            const offset = inPixels / run.perWorld;
            // Held here while the pointer is down, so the dimension follows
            // without a round trip for every pixel.
            this._draggingMeasurement = { viewportId, measureKey, offset };
            this.renderMeasurements();
        };

        const onUp = () => {
            const dragged = this._draggingMeasurement;
            if (!moved || !dragged) {
                this._draggingMeasurement = null;
                return;
            }
            // Held where it was dropped until the runner's answer redraws it there: let go at once,
            // it drew at the old place for the round trip -- a flicker on every drag.
            this._settleMeasurementDrag(dragged);
            const placement = typeof dragged.along === 'number'
                ? { offset: 0, along: dragged.along }
                : { offset: dragged.offset };
            this._writeMeasurementPlacement(viewportId, measureKey, placement, wasPlacement);
        };

        this._beginPointerGesture('measurement-drag', { onMove, onEnd: onUp });
    }

    /**
     * Keep a dropped dimension where it was dropped until the drawings come back with it there
     * (the 'scenes' answer clears it), or for a moment if they never do.
     */
    _settleMeasurementDrag(dragged) {
        const settling = { ...dragged, settling: true };
        this._draggingMeasurement = settling;
        setTimeout(() => {
            if (this._draggingMeasurement === settling) {
                this._draggingMeasurement = null;
                this.renderMeasurements();
            }
        }, MEASUREMENT_SETTLE_MS);
    }

    /** Measure an angle on the other side of the corner: its supplement. */
    flipMeasurementAngle(viewportId, measureKey) {
        const found = this.focusedMeasurement(viewportId, measureKey);
        if (!found) {
            return;
        }
        const was = found.measure.placement || { offset: 0 };
        this._writeMeasurementPlacement(
            viewportId, measureKey, { ...was, flip: !was.flip }, was, 'flip angle');
        this.emitViewerLog('measure-flip', { viewport: viewportId, flip: !was.flip });
    }

    /** Write where a dimension now sits, and what would put it back. */
    _writeMeasurementPlacement(viewportId, measureKey, placement, was, label = 'move measurement') {
        const found = this.focusedMeasurement(viewportId, measureKey);
        if (!found) {
            return;
        }
        const drawingId = this.measurementDrawingId;
        const where = {
            drawingId,
            viewportId,
            a: KigumiMeasurements.anchorReference(found.measure.a),
            b: KigumiMeasurements.anchorReference(found.measure.b),
            measureId: found.measure.measureId || null,
        };
        this._focusMeasurementOnArrival = { viewportId, measureKey };
        this.undoStacks.push(this.frameKey, drawingId, {
            label,
            redo: { type: 'updateMeasurement', ...where, changes: { placement } },
            undo: { type: 'updateMeasurement', ...where, changes: { placement: was } },
        });
        this._sendMeasurementCommand(
            { type: 'updateMeasurement', ...where, changes: { placement } });
    }

    /**
     * Look at a measurement, from wherever it was clicked.
     *
     * One path for the dimension itself, the drawing panel and the tree, so
     * what they highlight and what the info pane shows cannot drift. `add` puts
     * it beside the others rather than replacing them, which only deletion does
     * anything with.
     */
    _focusMeasurementFrom(detail) {
        if (!detail || !detail.measureKey) {
            return;
        }
        const where = { viewportId: detail.viewportId, measureKey: detail.measureKey };
        if (detail.add) {
            this.selectionManager.toggleMeasurementMark(where);
        } else {
            this.selectionManager.setMeasurementFocus(where);
        }
        this._syncDrawingPanel();
        this._layersDrawingsChanged();
        this.selectionPanel.updateInfo(this.currentFrameData);
        this.renderMeasurements();
    }

    /** The measurements held against the model rather than against a drawing. */
    _threeDMeasurements() {
        const drawing = this.sceneStore.drawings()
            .find((one) => one.id === THREE_D_MEASUREMENTS_ID);
        return (drawing ? drawing.viewports || [] : [])
            .flatMap((pane) => pane.measurements || []);
    }

    /** Show or hide every 3D measurement at once. */
    setMeasurementsHidden(hidden) {
        const next = Boolean(hidden);
        if (this.measurementsHidden === next) {
            return;
        }
        this.measurementsHidden = next;
        this.renderMeasurements();
        this.requestUpdate();
    }

    /**
     * Which drawing a measurement here belongs to.
     *
     * NOT the active scene: the 3D view's measurements live in a reserved
     * drawing of their own, so asking the scene gives 'default-3d', which holds
     * none of them. Every reader and writer goes through this -- three of them
     * did not, and in the 3D view undo silently did nothing, delete was refused
     * by the runner, and entries landed on a stack nobody read.
     */
    /**
     * Which space measurements here are taken in.
     *
     * A drawing projects onto its sheet; the 3D view projects nothing. It
     * settles the one kind name that cannot say it for itself -- a bare `angle`
     * composes for a solid angle and is what every measurement written before
     * spaces called a projected one.
     */
    get measurementSpace() {
        return this.isInDrawing ? 'projected' : '3d';
    }

    get measurementDrawingId() {
        return this.isInDrawing ? this.sceneStore.activeSceneId : THREE_D_MEASUREMENTS_ID;
    }

    /**
     * Say why a pick cannot be measured, rather than doing nothing.
     *
     * A click that silently achieves nothing is the worst of the options: it
     * looks like the viewer missed the click.
     */
    reportMeasureRefusal(reason) {
        const said = {
            'nothing-held': 'nothing is being measured from yet',
            'same-feature': 'that is the feature already held; pick a different one',
            'no-reference': 'that one cannot be measured to -- it is a face nobody named, '
                + 'so a dimension to it could not be saved',
            'not-measurable': 'that one has no plane or line of its own, so there is '
                + 'nothing to measure to',
            'nothing-pending': 'pick a second feature first',
            'nothing-under-pointer': 'there is nothing there to measure to',
            'no-kind': 'those two cannot be measured against each other from '
                + 'this view -- turn the camera, or pick a different feature',
            'degenerate': 'those two are in the same place, so there is nothing '
                + 'between them to measure -- an arris lying on a face is the '
                + 'usual way to land here',
        }[reason] || reason;
        // Through the viewer log, which the extension does listen for. It used
        // to post a `log` message as well, which nothing has ever handled -- so
        // every reason a pick was refused went out twice and arrived once.
        this.emitViewerLog('measure-refused', { reason, said });
    }

    /**
     * Draw every measurement of the active scene, on the sheet.
     *
     * In SVG over the canvas rather than in the scene, because a dimension is
     * an annotation on the page: it keeps its line weight and its text upright
     * whatever the camera does, which is the whole point of it being on paper.
     */
    renderMeasurements() {
        const overlay = this.renderRoot && this.renderRoot.querySelector
            ? this.renderRoot.querySelector('#measurement-overlay')
            : null;
        if (!overlay) {
            return;
        }
        const element = this.renderRoot.querySelector('#viewport');
        if (!element || !element.offsetHeight) {
            return;
        }
        overlay.setAttribute('viewBox', `0 0 ${element.offsetWidth} ${element.offsetHeight}`);
        overlay.innerHTML = '';

        // A drawing is laid out on a sheet, so its viewports sit on the page
        // rect. The 3D scene is not a sheet: its one viewport IS the canvas, so
        // the page rect is the canvas and the rest of the path is the same. It
        // used to return here, which is why a measurement made in the 3D view
        // had nowhere to appear.
        const pageRect = this.activePage
            ? this.pageScreenRect(element.offsetWidth, element.offsetHeight)
            : { x: 0, y: 0, width: element.offsetWidth, height: element.offsetHeight };

        for (const viewport of this.viewports) {
            for (const measure of (viewport.spec.measurements || [])) {
                if (!KigumiMeasurements.isDeleted(measure)) {
                    this._drawMeasurement(overlay, viewport, pageRect, measure);
                }
            }
        }
        if (!this.activePage) {
            this._drawThreeDMeasurements(overlay, pageRect);
        }

        // Last, and over the rest: what is being made now is what you are
        // looking at.
        const pending = this._previewMeasurementForDisplay();
        if (pending) {
            // In the view the measurement is being made in, which is the selection's.
            const viewport = this.viewports.find((one) => one.id === this.selectionManager.scope);
            if (viewport) {
                this._drawMeasurement(
                    overlay, viewport, pageRect, pending,
                    { className: 'dim-pending', pending: true });
            }
        }
    }

    /**
     * The 3D view's own measurements, which belong to no drawing on screen.
     *
     * They live in a reserved drawing rather than on the scene the viewer is
     * showing, so they are not on any viewport's spec and have to be fetched.
     * Drawn through the live camera: each carries its own plane, so the number
     * does not move when the camera does, only the picture of it.
     */
    _drawThreeDMeasurements(overlay, pageRect) {
        if (this.measurementsHidden) {
            return;
        }
        const viewport = this.viewports[0];
        const drawing = this.sceneStore.drawings()
            .find((one) => one.id === THREE_D_MEASUREMENTS_ID);
        if (!viewport || !drawing) {
            return;
        }
        for (const pane of drawing.viewports || []) {
            for (const measure of pane.measurements || []) {
                if (!KigumiMeasurements.isDeleted(measure)) {
                    this._drawMeasurement(overlay, viewport, pageRect, measure);
                }
            }
        }
    }

    /** Where a world point lands on the page, in the viewport's own pixels. */
    _projectToPage(point, viewport, pageRect) {
        const [x, y, width, height] = viewport.spec.rect;
        const projected = new THREE.Vector3(point[0], point[1], point[2]).project(viewport.camera);
        return {
            x: pageRect.x + (x + (projected.x * 0.5 + 0.5) * width) * pageRect.width,
            y: pageRect.y + (y + (0.5 - projected.y * 0.5) * height) * pageRect.height,
            inFront: projected.z < 1,
        };
    }

    /**
     * A viewport's camera axes, as the measurement code wants them.
     *
     * In one place because three callers ask -- drawing a dimension, listing
     * one, and now colouring a hover -- and a dimension that is drawn against
     * different axes than it was judged against would be drawn wrong.
     */
    /**
     * Whether this viewport projects onto a plane at all.
     *
     * A perspective camera does not, so a measurement's plane cannot be checked
     * against it -- the 3D view and a drawing's preview both behave that way.
     * Passed alongside the axes rather than read from them, because the axes
     * are a direction and this is a fact about the camera.
     */
    viewportProjection(viewport) {
        // A viewport with no DECLARED camera projects onto no particular plane,
        // whatever its projection toggle says: the 3D view's angle is wherever
        // the reader last left it. Checking a measurement's plane against the
        // fallback look turned every 3D measurement red the moment the view was
        // switched to orthographic. See .claude/plans/measurement-spec.md, which says
        // the invariant does not apply there.
        const declared = Boolean(viewport && viewport.spec && viewport.spec.camera);
        return {
            orthographic: declared && Boolean(viewport.isOrthographic),
            // A declared camera means a sheet to project onto, whatever its
            // projection toggle says. Only the 3D view has none, and only
            // there is a face a plane rather than whatever shape it presents.
            space: declared ? 'projected' : '3d',
        };
    }

    viewportAxes(viewport) {
        const camera = (viewport && viewport.spec && viewport.spec.camera) || null;
        if (!camera) {
            // The 3D view declares no camera, because its camera is the
            // reader's. A fixed basis here told the runner the view looked down
            // -Z with Y up -- neither where it points nor which way is up, this
            // world being Z-up -- so the plane a measurement was taken on, and
            // which feature under the pointer was preferred, were both worked
            // out against a view nobody was looking from.
            return this._liveAxes(viewport);
        }
        return {
            look: camera.look || [0, 0, -1],
            right: camera.right || [1, 0, 0],
            up: camera.up || [0, 1, 0],
        };
    }

    /** Where a camera actually points, for a viewport that declares none. */
    _liveAxes(viewport) {
        const live = viewport && viewport.camera;
        if (!live) {
            return { look: [0, 0, -1], right: [1, 0, 0], up: [0, 0, 1] };
        }
        // From the camera's own basis rather than from its `up` hint: `up` is
        // what lookAt aims for, not where the camera ended up.
        live.updateMatrixWorld();
        const basis = new THREE.Matrix4().extractRotation(live.matrixWorld);
        const axis = (x, y, z) => {
            const out = new THREE.Vector3(x, y, z).applyMatrix4(basis).normalize();
            return [out.x, out.y, out.z];
        };
        return { look: axis(0, 0, -1), right: axis(1, 0, 0), up: axis(0, 1, 0) };
    }

    /**
     * A group for one dimension, which is the thing a click lands on.
     *
     * Hit-testing the geometry by hand would mean a second copy of where every
     * line was put. The lines themselves already know, so they are asked --
     * which also means the hit area is exactly what is drawn, arrowheads and
     * text included.
     */
    _measurementGroup(overlay, viewport, measure, options) {
        const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        overlay.appendChild(group);
        if (options.pending) {
            // Not there yet, so not selectable: the way to change it is to pick
            // another feature or press escape.
            return group;
        }
        const key = measurementKey(measure);
        group.setAttribute('class', 'dim-group'
            + (this.selectionManager.isMeasurementFocused(viewport.id, key)
                ? ' dim-focused' : ''));
        group.addEventListener('pointerdown', (event) => {
            event.stopPropagation();
            this._focusMeasurementFrom({
                viewportId: viewport.id, measureKey: key, add: event.shiftKey });
            if (event.shiftKey) {
                // Marking several to delete, not moving one.
                return;
            }
            this._beginMeasurementDrag(event, group, viewport.id, key, measure);
        });
        // The overlay is not the canvas, so its right-click never reaches the
        // canvas's handler that keeps the browser menu away.
        group.addEventListener('contextmenu', (event) => {
            event.preventDefault();
            event.stopPropagation();
            this.showMeasurementContextMenu({
                viewportId: viewport.id,
                measureKey: key,
                clientX: event.clientX,
                clientY: event.clientY,
            });
        });
        return group;
    }

    _drawMeasurement(overlay, viewport, pageRect, measure, options = {}) {
        const axes = this.viewportAxes(viewport);
        // The same answer the list shows, so a dimension that is not drawn and
        // a row that says why can never disagree.
        const status = KigumiMeasurements.measurementStatus(
            measure, axes, this.viewportProjection(viewport));
        if (!status.drawable) {
            return;
        }
        const into = this._measurementGroup(overlay, viewport, measure, options);
        let from = measure.a.at;
        let to = measure.b.at;
        const value = status.value;
        const dragging = this._draggingMeasurement;
        if (measure.slide && dragging && typeof dragging.along === 'number'
            && dragging.viewportId === viewport.id && dragging.measureKey === measurementKey(measure)) {
            // Being slid: both anchors move along the lines together, until the runner places them.
            const shift = dragging.along - this._measurementAlong(measure);
            const moveBy = (point) => point.map((part, axis) => part + measure.slide[axis] * shift);
            from = moveBy(from);
            to = moveBy(to);
        }

        // What the value IS, not what the kind is called. The kinds became
        // composed names -- `projected_angle` -- and this still asked for the
        // old bare `angle`, so every angle fell through and was drawn as a
        // linear dimension: the right number, with the wrong picture and the
        // wrong units beside it.
        if (value.unit === 'angle') {
            this._drawAngle(into, viewport, pageRect, from, to,
                            status.formA, status.formB, value,
                            { ...options, rays: measure.angle || null });
            return;
        }

        // Projected, and nothing more. Where the two ends sit was decided once,
        // against the measurement's own plane, when it was placed; drawing it
        // only says where those points land in this view.
        //
        // This used to re-square the ends against the LIVE camera, which is a
        // no-op only while the camera is the measurement's plane. In the 3D
        // view it is not, so the ends were slid by an amount that changed as
        // the camera turned -- anchors wandering off their features while you
        // orbited, which is the opposite of what a placed anchor means.
        const ends = {
            from: this._projectToPage(from, viewport, pageRect),
            to: this._projectToPage(to, viewport, pageRect),
        };
        // How many screen pixels a world unit is worth HERE -- taken from the
        // run itself, which is a known world length and a known drawn length.
        // An offset is stored in world units so that it stays where it was put
        // as the view zooms; only what is drawn is measured in pixels.
        //
        // Worked out before it is used, which is the whole of what went wrong:
        // it was declared further down, beside the drag that also wants it, and
        // a const is not reachable before its declaration.
        const perWorld = this._pixelsPerWorldUnit(from, to, ends);
        const layout = KigumiMeasurements.dimensionLayout(
            ends.from,
            ends.to,
            // Where the reader put it, or the viewport's own default. This is
            // the one degree of freedom a dimension has once its two ends are
            // fixed, and it was being ignored: a saved offset drew where the
            // default said, and dragging would have had nothing to change.
            { offset: this._offsetInPixels(
                measure, viewport.id, measurementKey(measure), perWorld) },
        );
        if (!layout) {
            // Far enough apart in the world, but on top of each other once
            // drawn at this scale: nothing to put a dimension line along.
            return;
        }

        const extra = options.className ? ` ${options.className}` : '';
        // What a drag measures against. Kept from the drawing rather than
        // projected again, so what is dragged is exactly what is on screen.
        into._dimensionRun = {
            from: ends.from, to: ends.to, perWorld,
            slide: measure.slide ? this._slideOnPage(from, measure.slide, ends.from, viewport, pageRect) : null,
        };
        const draw = (from_, to_, className) => {
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', from_.x);
            line.setAttribute('y1', from_.y);
            line.setAttribute('x2', to_.x);
            line.setAttribute('y2', to_.y);
            line.setAttribute('class', className + extra);
            into.appendChild(line);
        };

        for (const witness of layout.witness) {
            draw(witness.from, witness.to, 'dim-witness');
        }
        this._drawPhantoms(into, viewport, pageRect, measure.extents, [from, to], extra);
        draw(layout.line.from, layout.line.to, 'dim-line');

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', layout.label.x);
        text.setAttribute('y', layout.label.y);
        text.setAttribute('class', `dim-label${extra}`);
        text.setAttribute('transform', `rotate(${layout.label.angle} ${layout.label.x} ${layout.label.y})`);
        text.textContent = this.fmt(value.value);
        into.appendChild(text);
    }

    /**
     * Which way a dimension slides on the page, and how many pixels a world unit along it is
     * worth: what a drag along the features is measured against.
     */
    _slideOnPage(anchor, slide, anchorOnPage, viewport, pageRect) {
        const ahead = this._projectToPage(anchor.map((part, axis) => part + slide[axis]), viewport, pageRect);
        const step = { x: ahead.x - anchorOnPage.x, y: ahead.y - anchorOnPage.y };
        const perWorld = Math.hypot(step.x, step.y);
        return perWorld > 1e-9 ? { x: step.x / perWorld, y: step.y / perWorld, perWorld } : null;
    }

    /**
     * Each feature drawn on, dashed, to its anchor where the anchor is past its end -- slid off it,
     * say -- so the dimension is seen to belong to it.
     */
    _drawPhantoms(into, viewport, pageRect, extents, points, extra = '') {
        if (!extents) {
            return;
        }
        [['a', points[0]], ['b', points[1]]].forEach(([key, point]) => {
            const segment = KigumiMeasurements.phantomSegment(extents[key], point);
            if (!segment) {
                return;
            }
            const from = this._projectToPage(segment.from, viewport, pageRect);
            const to = this._projectToPage(segment.to, viewport, pageRect);
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', from.x);
            line.setAttribute('y1', from.y);
            line.setAttribute('x2', to.x);
            line.setAttribute('y2', to.y);
            line.setAttribute('class', `dim-phantom${extra}`);
            into.appendChild(line);
        });
    }

    /**
     * An angle, drawn as an arc in the corner the two features make.
     *
     * At the corner rather than between them, because that is where an angle
     * is: the same two faces read as nothing at all anywhere else on the sheet.
     */
    _drawAngle(into, viewport, pageRect, from, to, formA, formB, value, options = {}) {
        const rays = options.rays || null;
        const drawn = rays
            ? this._angleArcInItsOwnPlane(viewport, pageRect, rays)
            : this._angleArcOnTheScreen(viewport, pageRect, from, to, formA, formB);
        if (!drawn) {
            return;
        }

        const arc = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        arc.setAttribute('d', drawn.path);
        arc.setAttribute('class', `dim-line${options.className ? ` ${options.className}` : ''}`);
        arc.setAttribute('fill', 'none');
        into.appendChild(arc);
        // Each feature carried on, dashed, to the corner it does not reach.
        for (const [start, end] of (rays && rays.phantoms) || []) {
            const a = this._projectToPage(start, viewport, pageRect);
            const b = this._projectToPage(end, viewport, pageRect);
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', a.x);
            line.setAttribute('y1', a.y);
            line.setAttribute('x2', b.x);
            line.setAttribute('y2', b.y);
            line.setAttribute('class', `dim-phantom${options.className ? ` ${options.className}` : ''}`);
            into.appendChild(line);
        }

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', drawn.label.x);
        text.setAttribute('y', drawn.label.y);
        text.setAttribute('class', `dim-label${options.className ? ` ${options.className}` : ''}`);
        text.textContent = `${value.value.toFixed(1)}\u00b0`;
        into.appendChild(text);
    }

    /**
     * The arc swept in the angle's own plane, then projected.
     *
     * A drafted angle lies on the work: the arc turns in the plane the two
     * features make a corner in, so it foreshortens with the timber and reads
     * as the angle beside it. Drawn flat on the screen instead it showed the
     * PROJECTED angle, which agrees with its own number only from the one
     * direction -- from anywhere else a right angle reads as twenty degrees and
     * the arc floats free of the work.
     */
    _angleArcInItsOwnPlane(viewport, pageRect, rays) {
        const at = this._projectToPage(rays.vertex, viewport, pageRect);
        // A radius in world units that comes out near the pixels a dimension
        // wants, so the arc is legible at any zoom without being drawn flat.
        const unit = this._projectToPage([
            rays.vertex[0] + rays.from[0],
            rays.vertex[1] + rays.from[1],
            rays.vertex[2] + rays.from[2],
        ], viewport, pageRect);
        const perWorld = Math.hypot(unit.x - at.x, unit.y - at.y);
        if (!(perWorld > 1e-9)) {
            // Looking straight down the ray: it has no length on screen, so
            // there is no scale to take and nothing worth drawing.
            return null;
        }
        const radius = MEASUREMENT_ANGLE_RADIUS_PX / perWorld;
        const points = KigumiMeasurements.angleArcPoints(rays, radius)
            .map((point) => this._projectToPage(point, viewport, pageRect));
        if (points.length < 2) {
            return null;
        }
        const path = points
            .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
            .join(' ');
        return {
            path,
            label: this._projectToPage(
                KigumiMeasurements.angleLabelPoint(rays, radius), viewport, pageRect),
        };
    }

    /**
     * The older arc, for a measurement carrying no corner.
     *
     * Two features' own anchors and their own directions, with the vertex where
     * those two screen lines cross. Kept for anything the runner could not
     * place -- it is better than drawing nothing, and it is what every angle
     * used to get.
     */
    _angleArcOnTheScreen(viewport, pageRect, from, to, formA, formB) {
        const screenDirection = (point, direction) => {
            const here = this._projectToPage(point, viewport, pageRect);
            const step = 0.01;
            const there = this._projectToPage([
                point[0] + direction[0] * step,
                point[1] + direction[1] * step,
                point[2] + direction[2] * step,
            ], viewport, pageRect);
            const run = { x: there.x - here.x, y: there.y - here.y };
            const size = Math.hypot(run.x, run.y);
            return size > 0 ? { x: run.x / size, y: run.y / size } : null;
        };
        // Only for forms that RUN somewhere. A solid plane has a normal and no
        // direction, and this arc is built from the way each feature runs as
        // drawn -- feeding it a normal is what drew the arc out of two normals
        // in the first place, and reading a direction that is not there threw
        // on every frame, which took the whole render down with it.
        if (!formA.direction || !formB.direction) {
            return null;
        }
        const fromDirection = screenDirection(from, formA.direction);
        const toDirection = screenDirection(to, formB.direction);
        if (!fromDirection || !toDirection) {
            return null;
        }
        const layout = KigumiMeasurements.angleLayout(
            this._projectToPage(from, viewport, pageRect), fromDirection,
            this._projectToPage(to, viewport, pageRect), toDirection,
            { radius: MEASUREMENT_ANGLE_RADIUS_PX },
        );
        if (!layout) {
            return null;
        }
        return {
            path: [
                'M', layout.start.x, layout.start.y,
                'A', layout.radius, layout.radius, 0, layout.largeArc, layout.sweepFlag,
                layout.end.x, layout.end.y,
            ].join(' '),
            label: layout.label,
        };
    }
};
