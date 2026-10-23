// Per-node layer state: locked, hidden, fixed.
// Keyed by memberKey (same keys used by SelectionStore and Three.js mesh map).
// lock/hide/fix are scaffolded as no-ops; visual enforcement is wired in later.
class LayerStateStore {
    constructor() {
        this.states = new Map(); // memberKey -> { locked, hidden, fixed }
        this.listeners = new Set();
    }

    getState(key) {
        return this.states.get(key) || { locked: false, hidden: false, fixed: false };
    }

    setLocked(key, value) {
        this._set(key, 'locked', Boolean(value));
    }

    setHidden(key, value) {
        this._set(key, 'hidden', Boolean(value));
    }

    setFixed(key, value) {
        this._set(key, 'fixed', Boolean(value));
    }

    toggleLocked(key) {
        this.setLocked(key, !this.getState(key).locked);
    }

    toggleHidden(key) {
        this.setHidden(key, !this.getState(key).hidden);
    }

    toggleFixed(key) {
        this.setFixed(key, !this.getState(key).fixed);
    }

    isHidden(key) { return this.getState(key).hidden; }
    isLocked(key) { return this.getState(key).locked; }
    isFixed(key)  { return this.getState(key).fixed; }

    showAll() {
        for (const key of this.states.keys()) this.setHidden(key, false);
    }

    unlockAll() {
        for (const key of this.states.keys()) this.setLocked(key, false);
    }

    hasAnyHidden() {
        for (const s of this.states.values()) if (s.hidden) return true;
        return false;
    }

    hasAnyLocked() {
        for (const s of this.states.values()) if (s.locked) return true;
        return false;
    }

    // Remove state for keys that are no longer in the scene.
    pruneKeys(validKeys) {
        const validSet = new Set(validKeys);
        for (const key of Array.from(this.states.keys())) {
            if (!validSet.has(key)) {
                this.states.delete(key);
            }
        }
    }

    onStateChanged(callback) {
        this.listeners.add(callback);
        return () => this.listeners.delete(callback);
    }

    _set(key, prop, value) {
        const current = this.getState(key);
        if (current[prop] === value) return;
        const next = Object.assign({}, current, { [prop]: value });
        this.states.set(key, next);
        this._emit({ type: 'layer-state-changed', key, prop, value, state: next });
    }

    _emit(event) {
        for (const listener of this.listeners) {
            listener(event);
        }
    }
}

export { LayerStateStore };
