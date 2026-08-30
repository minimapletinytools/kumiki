(function (globalScope) {
    'use strict';
    // What is selected in the viewer, in two independent pieces:
    //
    //   selectedTimbers  a set, because timbers multi-select
    //   csgFocus         at most one, because the CSG trees single-select
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
            this.csgFocus = null;
            this.listeners = new Set();
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
            this.csgFocus = {
                timberKey,
                path: path || [],
                featureLabel: featureLabel || null,
                cutIndex: cutIndex === undefined ? null : cutIndex,
                context: context || { section: 'timbers' },
            };
            this.emit({ type: 'csg-focus', csgFocus: this.csgFocus });
        }

        clearCsgFocus(options = {}) {
            if (!this.csgFocus) {
                return;
            }
            this.csgFocus = null;
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
            this.csgFocus.nodeId = nodeId || null;
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
            this.csgFocus = null;
            this.emit({ type: 'clear-all' });
        }

        hasSelection() {
            return this.selectedTimbers.size > 0 || this.csgFocus !== null;
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
