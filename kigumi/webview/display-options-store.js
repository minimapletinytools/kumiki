(function (globalScope) {
    'use strict';
    // The display settings a viewer carries: how the frame is drawn, rather
    // than what is drawn or how the panel behaves. Export formats, debug and
    // the assembly timeline are deliberately not here -- they are not things a
    // drawing would ever want to override.
    //
    // Each option normalizes its own input, because the rules genuinely differ:
    // a percent snaps to a step, a bad theme id is ignored outright, and a bad
    // edge mode falls back to the default. Those rules used to live inside ten
    // setters on the viewer where nothing could reach them.
    //
    // reject() means "leave the value alone", which is not the same as
    // returning the default -- setTheme('nonsense') must not repaint the frame.
    const REJECT = Symbol('reject');

    function oneOf(allowed, fallback) {
        return (value) => (allowed.includes(value) ? value : fallback);
    }

    function oneOfOrReject(allowed) {
        return (value) => (allowed.includes(value) ? value : REJECT);
    }

    function percent(min, max, step, fallback) {
        return (value) => (Number.isFinite(value)
            ? Math.max(min, Math.min(max, Math.round(value / step) * step))
            : fallback);
    }

    function range(min, max, fallback) {
        return (value) => (Number.isFinite(value) ? Math.max(min, Math.min(max, value)) : fallback);
    }

    function bool(value) {
        return Boolean(value);
    }

    const EDGE_MODES = ['none', 'overlay', 'noOverlay'];
    const FOOTPRINT_COLORS = ['slate', 'moss', 'orange', 'transparent'];
    const UNIT_SYSTEMS = ['metric', 'imperial'];

    /**
     * The options, their defaults and how each takes a value.
     *
     * `themes` is passed in rather than baked in: the viewer owns the theme
     * registry, and this store only needs to know which ids are real.
     */
    function optionSpecs(themeIds) {
        return {
            activeTheme: { value: 'forest', normalize: oneOfOrReject(themeIds) },
            edgeMode: { value: 'noOverlay', normalize: oneOf(EDGE_MODES, 'noOverlay') },
            edgeLineVisibilityPercent: { value: 100, normalize: percent(0, 100, 5, 100) },
            edgeLineThicknessPx: { value: 1.5, normalize: range(0.5, 6, 1.5) },
            shadowsEnabled: { value: false, normalize: bool },
            reflectionsEnabled: { value: true, normalize: bool },
            footprintColor: { value: 'orange', normalize: oneOf(FOOTPRINT_COLORS, 'orange') },
            unselectedTransparencyPercent: { value: 70, normalize: percent(0, 95, 5, 70) },
            selectedTransparencyPercent: { value: 0, normalize: percent(0, 95, 5, 0) },
            units: { value: 'metric', normalize: oneOf(UNIT_SYSTEMS, 'metric') },
        };
    }

    class DisplayOptionsStore {
        constructor(options = {}) {
            const themeIds = options.themeIds || ['forest'];
            this.specs = optionSpecs(themeIds);
            this.values = {};
            for (const [key, spec] of Object.entries(this.specs)) {
                this.values[key] = spec.value;
            }
            // Per-scene overrides, for when a drawing wants to look unlike the
            // 3D view. Nothing writes this yet; resolve() is the seam so that
            // when something does, no reader has to change.
            this.overridesBySceneId = new Map();
            this.listeners = new Set();
        }

        keys() {
            return Object.keys(this.specs);
        }

        get(key) {
            return this.values[key];
        }

        /** What *scene* should use for *key*: its override, else the global. */
        resolve(sceneId, key) {
            const overrides = this.overridesBySceneId.get(sceneId);
            if (overrides && Object.prototype.hasOwnProperty.call(overrides, key)) {
                return overrides[key];
            }
            return this.values[key];
        }

        /**
         * Take a value for *key*. Returns whether anything changed, so callers
         * can keep their early return and skip the work of applying it.
         */
        set(key, value) {
            const spec = this.specs[key];
            if (!spec) {
                return false;
            }
            const next = spec.normalize(value);
            if (next === REJECT || this.values[key] === next) {
                return false;
            }
            this.values[key] = next;
            this.emit(key, next);
            return true;
        }

        /** The saved shape, and the only thing that goes to disk. */
        toPayload() {
            return { ...this.values };
        }

        /** Take what was saved, ignoring anything unknown or unusable. */
        applyPayload(payload) {
            if (!payload || typeof payload !== 'object') {
                return [];
            }
            const changed = [];
            for (const key of this.keys()) {
                if (Object.prototype.hasOwnProperty.call(payload, key) && this.set(key, payload[key])) {
                    changed.push(key);
                }
            }
            return changed;
        }

        onChanged(callback) {
            this.listeners.add(callback);
            return () => {
                this.listeners.delete(callback);
            };
        }

        emit(key, value) {
            for (const listener of this.listeners) {
                listener({ key, value });
            }
        }
    }

    const KigumiDisplayOptions = { DisplayOptionsStore, EDGE_MODES, FOOTPRINT_COLORS, UNIT_SYSTEMS };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiDisplayOptions;
    }
    globalScope.KigumiDisplayOptions = KigumiDisplayOptions;
})(typeof window !== 'undefined' ? window : globalThis);
