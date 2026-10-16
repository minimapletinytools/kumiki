(function (globalScope) {
    'use strict';
    // What is selected in the viewer, in two independent pieces:
    //
    //   selectedTimbers  a set, because timbers multi-select
    //   focus            at most one, because it is what you are looking at
    //
    // A CSG focus means exactly one timber is selected. Drilling in narrows the
    // selection to that timber, and widening the selection again drops the
    // focus. The canvas has always drawn it that way -- it highlights the
    // timber being drilled into and ghosts everything else -- so any other
    // rule left the trees and the canvas disagreeing about what was selected.
    // It is also the simpler rule to hold: the drilled timber IS the
    // selection, rather than "selected, but not highlighted".
    //
    // csgFocus is:
    //   { timberKey, path, featureLabel, cutIndex, context }
    // where context records which of the two trees the focus lives in:
    //   { section: 'timbers' }
    //   { section: 'joints', jointId, cutIndex }
    // The section matters because the same CSG node is shown in both places,
    // and a pick should reveal itself where the user is already looking.

    // Picking a timber is something you do in the model. A drawing has no
    // concept of a selected timber -- see .claude/plans/measurement-spec.md -- so the
    // mode is held here and the timber-selecting methods refuse in it, rather
    // than every caller checking first and one of them forgetting.
    const MODEL = 'model';
    const DRAWING = 'drawing';

    /** One measurement, across every viewport there is. */
    function measurementMark(viewportId, measureKey) {
        return `${viewportId}\u0000${measureKey}`;
    }

    class SelectionStore {
        constructor() {
            this.mode = MODEL;
            // Measurements picked out to be deleted together. Separate from the
            // focus, and for the same reason the focus is single: several at
            // once can only be deleted, while everything else -- the kind, the
            // drag, what the panel says -- is about exactly one.
            this.markedMeasures = new Set();
            this.selectedTimbers = new Set();
            // The one thing being looked at, whatever kind of thing it is. One
            // field rather than one per kind, so that "never two at once" is
            // something that cannot happen rather than a rule every place has
            // to remember.
            this.focus = null;
            // The viewport the selection belongs to, and the last one anything was selected in.
            // A feature or measurement selected in one view is not one in another, so selecting
            // in a different view starts again there -- see enterScope.
            this.scope = null;
            this.listeners = new Set();
        }

        // --- which view the selection is in --------------------------------

        /**
         * Selecting in `viewportId`. If that is another view, what was selected in the old one
         * (the focus, marked measurements) is dropped first. Timbers are kept: they are a
         * property of the model, the same in every view.
         */
        enterScope(viewportId) {
            if (!viewportId || viewportId === this.scope) {
                return false;
            }
            this.scope = viewportId;
            this.focus = null;
            this.markedMeasures.clear();
            this.emit({ type: 'scope', scope: viewportId });
            return true;
        }

        /** Keep the scope on one of these viewports: the first, when it is on none of them. */
        keepScopeWithin(viewportIds) {
            const ids = viewportIds || [];
            if (!ids.includes(this.scope)) {
                this.enterScope(ids[0] || null);
            }
        }

        /**
         * The focus, when it is a CSG node -- null when it is anything else.
         *
         * The trees, the info pane and the highlighting all ask this, and each
         * of them means "the node being looked at": a focused measurement is
         * not one, and must not be mistaken for one.
         */
        get csgFocus() {
            return this.focus && this.focus.kind === 'csg' ? this.focus : null;
        }

        /** The focus, when it is a measurement. */
        get measurementFocus() {
            return this.focus && this.focus.kind === 'measurement' ? this.focus : null;
        }

        // --- which mode the viewer is in -----------------------------------

        /**
         * Model or drawing. Switching drops everything the other mode held.
         *
         * A feature selected in the model means nothing in a drawing, a
         * half-made measurement means nothing outside one, and either left
         * behind is something the new mode cannot act on. Purging is cheaper to
         * hold than a rule about what survives.
         */
        setMode(mode) {
            const next = mode === DRAWING ? DRAWING : MODEL;
            if (this.mode === next) {
                return false;
            }
            this.mode = next;
            this.selectedTimbers.clear();
            this.markedMeasures.clear();
            this.focus = null;
            this.scope = null;
            this.emit({ type: 'mode', mode: next });
            return true;
        }

        get inDrawing() {
            return this.mode === DRAWING;
        }

        // --- timbers -------------------------------------------------------

        selectTimber(name, addToSelection = false) {
            if (this.inDrawing) {
                // Not an error: the tree and the canvas both offer this, and in
                // a drawing the answer is simply that there is nothing to do.
                return;
            }
            if (!addToSelection) {
                this.selectedTimbers.clear();
                this.clearCsgFocus({ silent: true });
            }
            this.selectedTimbers.add(name);
            this._dropCsgFocusIfSelectionWidened();
            this.emit({ type: 'timber-selected', timberName: name });
        }

        deselectTimber(name) {
            if (!this.selectedTimbers.delete(name)) {
                return;
            }
            // A focus on a timber that is no longer selected has nothing to
            // point at, so it goes with it.
            if (this.csgFocus && this.csgFocus.timberKey === name) {
                this.clearCsgFocus({ silent: true });
            }
            this.emit({ type: 'timber-deselected', timberName: name });
        }

        toggleTimber(name) {
            if (this.inDrawing) {
                return;
            }
            if (this.selectedTimbers.has(name)) {
                this.deselectTimber(name);
                return;
            }
            this.selectTimber(name, true);
        }

        /**
         * Select several timbers at once, as clicking a tag does. One event for
         * the whole batch: a tag covering forty members should not make the
         * panel and the canvas re-render forty times.
         */
        selectTimbers(names, addToSelection = false) {
            if (this.inDrawing) {
                return;
            }
            const keys = Array.from(names || []);
            if (!addToSelection) {
                this.selectedTimbers.clear();
                this.clearCsgFocus({ silent: true });
            }
            for (const key of keys) {
                this.selectedTimbers.add(key);
            }
            this._dropCsgFocusIfSelectionWidened();
            this.emit({ type: 'timbers-selected', timberNames: keys });
        }

        clearTimberSelection() {
            if (this.selectedTimbers.size === 0 && !this.csgFocus) {
                return;
            }
            this.selectedTimbers.clear();
            this.clearCsgFocus({ silent: true });
            this.emit({ type: 'clear-timbers' });
        }

        /**
         * Keep "a CSG focus means one selected timber" true.
         *
         * Enforced here, after the fact, rather than remembered by each of the
         * three paths that can widen the selection -- shift-clicking a timber,
         * clicking a tag, clicking a joint. A measurement focus is not about
         * one timber, so it is left alone.
         *
         * Silent: the caller emits its own event, and every listener re-reads
         * the store, so a second event would say nothing new.
         */
        _dropCsgFocusIfSelectionWidened() {
            if (this.csgFocus && this.selectedTimbers.size > 1) {
                this.clearCsgFocus({ silent: true });
            }
        }

        isTimberSelected(name) {
            return this.selectedTimbers.has(name);
        }

        getSelectedTimbers() {
            return Array.from(this.selectedTimbers);
        }

        // --- the one CSG focus ---------------------------------------------

        /**
         * Focus a node in one of the CSG trees.
         *
         * The selection narrows to this timber: you are looking at one timber's
         * insides, and the canvas already draws it that way.
         */
        setCsgFocus({ timberKey, path, featureLabel, cutIndex, context }) {
            this.selectedTimbers.clear();
            this.selectedTimbers.add(timberKey);
            // Looking at a feature means no longer looking at a measurement,
            // and the ones picked out went with the looking.
            this.markedMeasures.clear();
            this.focus = {
                kind: 'csg',
                timberKey,
                path: path || [],
                featureLabel: featureLabel || null,
                cutIndex: cutIndex === undefined ? null : cutIndex,
                context: context || { section: 'timbers' },
            };
            this.emit({ type: 'csg-focus', csgFocus: this.csgFocus });
        }

        /**
         * Stop looking at whatever is focused -- a feature OR a measurement.
         *
         * One field holds both, so this clears either. The name is about the
         * common case rather than the whole of what it does.
         */
        clearCsgFocus(options = {}) {
            if (!this.focus) {
                return;
            }
            if (this.measurementFocus) {
                this.markedMeasures.clear();
            }
            this.focus = null;
            if (!options.silent) {
                this.emit({ type: 'clear-csg-focus' });
            }
        }

        /** True if `nodeId` is the focused row of a rendered tree. */
        isCsgNodeFocused(nodeId) {
            return Boolean(this.csgFocus) && this.csgFocus.nodeId === nodeId;
        }

        /** Record which rendered row the focus corresponds to, for styling. */
        setFocusedNodeId(nodeId) {
            if (!this.csgFocus) {
                return;
            }
            this.focus.nodeId = nodeId || null;
        }

        /**
         * Look at a measurement.
         *
         * Deliberately leaves the timber selection alone. A CSG node is part of
         * a timber, so focusing one selects that timber; a measurement is about
         * timbers without being part of any, and often about two -- and reading
         * a dimension must not change what a command would act on.
         */
        setMeasurementFocus({ viewportId, measureKey }) {
            this.enterScope(viewportId);
            this.focus = { kind: 'measurement', viewportId, measureKey };
            // Looking at one replaces whatever several were picked out before.
            this.markedMeasures = new Set([measurementMark(viewportId, measureKey)]);
            this.emit({ type: 'measurement-focus', measurementFocus: this.focus });
        }

        /**
         * Add a measurement to the ones picked out, or take it back out.
         *
         * The focus follows the last one added, so that a panel reading the
         * focus always has something to show; taking the focused one back out
         * leaves the focus on whatever remains, and nothing when none do.
         */
        toggleMeasurementMark({ viewportId, measureKey }) {
            this.enterScope(viewportId);
            const mark = measurementMark(viewportId, measureKey);
            if (this.markedMeasures.delete(mark)) {
                if (this.measurementFocus
                    && measurementMark(this.focus.viewportId, this.focus.measureKey) === mark) {
                    this.focus = null;
                }
                this.emit({ type: 'measurement-marks' });
                return;
            }
            this.markedMeasures.add(mark);
            this.focus = { kind: 'measurement', viewportId, measureKey };
            this.emit({ type: 'measurement-marks' });
        }

        isMeasurementMarked(viewportId, measureKey) {
            return this.markedMeasures.has(measurementMark(viewportId, measureKey));
        }

        /** Every measurement picked out, as { viewportId, measureKey }. */
        getMarkedMeasurements() {
            return Array.from(this.markedMeasures).map((mark) => {
                const [viewportId, measureKey] = mark.split('\u0000');
                return { viewportId, measureKey };
            });
        }

        clearMeasurementMarks() {
            if (this.markedMeasures.size === 0) {
                return;
            }
            this.markedMeasures.clear();
            if (this.measurementFocus) {
                this.focus = null;
            }
            this.emit({ type: 'measurement-marks' });
        }

        /** True if this is the measurement row being looked at. */
        isMeasurementFocused(viewportId, measureKey) {
            const focused = this.measurementFocus;
            return Boolean(focused)
                && focused.viewportId === viewportId
                && focused.measureKey === measureKey;
        }

        // --- joints ---------------------------------------------------------

        /** Selecting a joint selects the timbers it touches. */
        selectJoint(jointId, timberKeys, addToSelection = false) {
            if (this.inDrawing) {
                return;
            }
            if (!addToSelection) {
                this.selectedTimbers.clear();
                this.clearCsgFocus({ silent: true });
            }
            for (const key of timberKeys || []) {
                this.selectedTimbers.add(key);
            }
            this._dropCsgFocusIfSelectionWidened();
            this.emit({ type: 'joint-selected', jointId, timberKeys: timberKeys || [] });
        }

        // --- everything ------------------------------------------------------

        clearAll() {
            if (!this.hasSelection()) {
                return;
            }
            this.selectedTimbers.clear();
            this.markedMeasures.clear();
            this.focus = null;
            this.emit({ type: 'clear-all' });
        }

        hasSelection() {
            return this.selectedTimbers.size > 0 || this.focus !== null;
        }

        onSelectionChanged(callback) {
            this.listeners.add(callback);
            return () => {
                this.listeners.delete(callback);
            };
        }

        emit(event) {
            for (const listener of this.listeners) {
                listener(event);
            }
        }
    }

    /**
     * Timber mode is not offered in drawings for now. Kept working behind this so it can be
     * turned on: with it, a drawing picks the way the 3D view does.
     */
    const TIMBER_MODE_IN_DRAWINGS = false;

    /**
     * Which of the two selection modes a pick is in.
     *
     * - 'feature': a click goes straight to the feature on the nearest timber, whatever
     *   is selected.
     * - 'timber': a click selects a timber; a click on one already selected picks the
     *   feature on it, wherever it is along the ray.
     *
     * In a drawing: feature mode (timber mode only with `timberModeInDrawings`, and then as
     * in 3D). In 3D: timber mode, until something is held to measure from -- then feature
     * mode, with shift held for timber mode.
     */
    function pickMode({ inDrawing, measuring, shiftKey, timberModeInDrawings = TIMBER_MODE_IN_DRAWINGS }) {
        if (inDrawing && !timberModeInDrawings) {
            return 'feature';
        }
        return measuring && !shiftKey ? 'feature' : 'timber';
    }

    /**
     * What a click should do, given every member the ray passes through (nearest
     * first) and what is currently selected. Hover asks the same question, so it
     * lights what a click would take.
     *
     * Feature mode goes straight to the nearest feature. In timber mode, a click
     * drills into the nearest *selected* timber along the ray -- even one sitting
     * behind an unselected timber, so a neighbour in front cannot steal the click
     * -- and only when the ray misses every selected timber does it select one.
     * Outside measuring, shift changes which timbers are selected, so it acts on
     * the frontmost hit. While measuring, shift is how timber mode is reached: a
     * click selects the timber in place of the selection, and a click on it then
     * picks its feature.
     */
    function choosePickAction({
        hits, selectedTimbers, shiftKey, inDrawing, measuring, timberModeInDrawings,
    }) {
        const along = hits || [];
        if (along.length === 0) {
            return { action: 'clear' };
        }
        const selected = selectedTimbers instanceof Set
            ? selectedTimbers
            : new Set(selectedTimbers || []);
        const nearest = along[0];
        if (pickMode({ inDrawing, measuring, shiftKey, timberModeInDrawings }) === 'feature') {
            return { action: 'csg', memberKey: nearest.memberKey, hit: nearest.hit };
        }
        if (shiftKey && !measuring) {
            return { action: 'toggle', memberKey: nearest.memberKey, hit: nearest.hit };
        }
        const onSelected = along.find((entry) => selected.has(entry.memberKey));
        if (onSelected) {
            return { action: 'csg', memberKey: onSelected.memberKey, hit: onSelected.hit };
        }
        return { action: 'select', memberKey: nearest.memberKey, hit: nearest.hit };
    }

    /**
     * Which label the draw button wears, given how many timbers are selected.
     *
     * Drawing nothing means drawing the whole frame, which is a reasonable
     * thing to ask for -- so the button is never disabled, and says which of
     * the two it is about to do instead.
     */
    function drawButtonKey(selectedCount) {
        if (!selectedCount) {
            return 'viewer.selection.drawFrame';
        }
        return selectedCount === 1
            ? 'viewer.selection.drawTimber'
            : 'viewer.selection.drawTimbers';
    }

    const SELECTION_MODES = Object.freeze({ MODEL, DRAWING });

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { SelectionStore, choosePickAction, pickMode, TIMBER_MODE_IN_DRAWINGS, SELECTION_MODES, drawButtonKey };
    }
    globalScope.SelectionStore = SelectionStore;
    globalScope.choosePickAction = choosePickAction;
    globalScope.pickMode = pickMode;
    globalScope.drawButtonKey = drawButtonKey;
    globalScope.SELECTION_MODES = SELECTION_MODES;
})(typeof window !== 'undefined' ? window : globalThis);
