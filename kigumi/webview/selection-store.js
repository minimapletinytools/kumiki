(function (globalScope) {
    class SelectionStore {
        constructor() {
            this.selectedTimbers = new Set();
            this.selectedFeatures = [];
            this.csgSelection = null;
            this.listeners = new Set();
        }

        selectTimber(name, addToSelection = false) {
            if (!addToSelection) {
                this.selectedTimbers.clear();
            }
            this.selectedTimbers.add(name);
            this.emit({ type: 'timber-selected', timberName: name });
        }

        deselectTimber(name) {
            this.selectedTimbers.delete(name);
            this.emit({ type: 'timber-deselected', timberName: name });
        }

        toggleTimber(name) {
            if (this.selectedTimbers.has(name)) {
                this.deselectTimber(name);
                return;
            }
            this.selectTimber(name, true);
        }

        clearTimberSelection() {
            if (this.selectedTimbers.size === 0) {
                return;
            }
            this.selectedTimbers.clear();
            this.emit({ type: 'clear-timbers' });
        }

        isTimberSelected(name) {
            return this.selectedTimbers.has(name);
        }

        getSelectedTimbers() {
            return Array.from(this.selectedTimbers);
        }

        selectFeature(timberName, featureId, addToSelection = false) {
            if (!addToSelection) {
                this.selectedFeatures = [];
            }
            this.addFeature(timberName, featureId);
        }

        addFeature(timberName, featureId) {
            const alreadySelected = this.selectedFeatures.some((feature) => (
                feature.timberName === timberName && feature.featureId === featureId
            ));
            if (alreadySelected) {
                return;
            }
            this.selectedFeatures.push({ timberName, featureId });
            this.emit({ type: 'feature-selected', timberName, featureId });
        }

        clearFeatureSelection() {
            if (this.selectedFeatures.length === 0) {
                return;
            }
            this.selectedFeatures = [];
            this.emit({ type: 'clear-features' });
        }

        selectCSG(timberKey, path, featureLabel) {
            this.csgSelection = { timberKey, path: path || [], featureLabel: featureLabel || null };
            this.emit({ type: 'csg-selected', csgSelection: this.csgSelection });
        }

        clearCSGSelection() {
            if (!this.csgSelection) {
                return;
            }
            this.csgSelection = null;
            this.emit({ type: 'clear-csg' });
        }

        hasSelection() {
            return this.selectedTimbers.size > 0 || this.selectedFeatures.length > 0 || this.csgSelection !== null;
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

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { SelectionStore };
    }
    globalScope.SelectionStore = SelectionStore;
})(typeof window !== 'undefined' ? window : globalThis);
