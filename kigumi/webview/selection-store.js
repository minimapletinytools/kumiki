(function (globalScope) {
    'use strict';
    // What is selected in the viewer, in two independent pieces:
    //
    //   selectedTimbers  a set, because timbers multi-select
    //   focus            at most one, because it is what you are looking at
    //
    // They coexist: several timbers can be selected while you drill into the
    // CSG of exactly one of them. Focusing a CSG node pulls its timber into
    // the selection but leaves the rest of the selection alone.
    //
    // csgFocus is:
    //   { timberKey, path, featureLabel, cutIndex, context }
    // where context records which of the two trees the focus lives in:
    //   { section: 'timbers' }
    //   { section: 'joints', jointId, cutIndex }
    // The section matters because the same CSG node is shown in both places,
    // and a pick should reveal itself where the user is already looking.

    class SelectionStore {
        constructor() {
            this.selectedTimbers = new Set();
            // The one thing being looked at, whatever kind of thing it is. One
            // field rather than one per kind, so that "never two at once" is
            // something that cannot happen rather than a rule every place has
            // to remember.
            this.focus = null;
            this.listeners = new Set();
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

        // --- timbers -------------------------------------------------------

        selectTimber(name, addToSelection = false) {
            if (!addToSelection) {
                this.selectedTimbers.clear();
                this.clearCsgFocus({ silent: true });
            }
            this.selectedTimbers.add(name);
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
            const keys = Array.from(names || []);
            if (!addToSelection) {
                this.selectedTimbers.clear();
                this.clearCsgFocus({ silent: true });
            }
            for (const key of keys) {
                this.selectedTimbers.add(key);
            }
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

        isTimberSelected(name) {
            return this.selectedTimbers.has(name);
        }

        getSelectedTimbers() {
            return Array.from(this.selectedTimbers);
        }

        // --- the one CSG focus ---------------------------------------------

        /**
         * Focus a node in one of the CSG trees. The timber joins the selection
         * if it is not already in it; any other selected timbers stay, since
         * you can have several selected and still drill into one.
         */
        setCsgFocus({ timberKey, path, featureLabel, cutIndex, context }) {
            this.selectedTimbers.add(timberKey);
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
            this.focus = { kind: 'measurement', viewportId, measureKey };
            this.emit({ type: 'measurement-focus', measurementFocus: this.focus });
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
            if (!addToSelection) {
                this.selectedTimbers.clear();
                this.clearCsgFocus({ silent: true });
            }
            for (const key of timberKeys || []) {
                this.selectedTimbers.add(key);
            }
            this.emit({ type: 'joint-selected', jointId, timberKeys: timberKeys || [] });
        }

        // --- everything ------------------------------------------------------

        clearAll() {
            if (!this.hasSelection()) {
                return;
            }
            this.selectedTimbers.clear();
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
     * What a click in the 3D view should do, given every member the ray passes
     * through (nearest first) and what is currently selected.
     *
     * While timbers are selected, a click drills into the CSG of the nearest
     * *selected* timber along the ray -- even one sitting behind an unselected
     * timber -- so a neighbour in front cannot steal the click while you are
     * inspecting. Only when the ray misses every selected timber does a click
     * select something new. Shift always means "change which timbers are
     * selected", so it acts on the frontmost hit.
     */
    function choosePickAction({ hits, selectedTimbers, shiftKey }) {
        const along = hits || [];
        if (along.length === 0) {
            return { action: 'clear' };
        }
        const selected = selectedTimbers instanceof Set
            ? selectedTimbers
            : new Set(selectedTimbers || []);
        const nearest = along[0];
        if (shiftKey) {
            return { action: 'toggle', memberKey: nearest.memberKey, hit: nearest.hit };
        }
        const onSelected = along.find((entry) => selected.has(entry.memberKey));
        if (onSelected) {
            return { action: 'csg', memberKey: onSelected.memberKey, hit: onSelected.hit };
        }
        return { action: 'select', memberKey: nearest.memberKey, hit: nearest.hit };
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { SelectionStore, choosePickAction };
    }
    globalScope.SelectionStore = SelectionStore;
    globalScope.choosePickAction = choosePickAction;
})(typeof window !== 'undefined' ? window : globalThis);
