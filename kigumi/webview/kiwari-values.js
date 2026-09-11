(function (globalScope) {
    'use strict';
    // What the parameter panel holds while someone is editing, kept apart from
    // how it is drawn: a draft per parameter (the text in the box, which may
    // not be a measurement yet), what would be sent on a refresh, and what the
    // frame on screen was actually built from.
    //
    // No Lit in here on purpose — this is the part that has to survive the UI
    // being rewritten.
    const dimensionText = (typeof require === 'function' && typeof module !== 'undefined')
        ? require('./dimension-text')
        : globalScope.KigumiDimensionText;

    const MEASURED = { length: 'parseLength', angle: 'parseAngle' };
    const VECTOR_AXES = { point2: ['x', 'y'], point3: ['x', 'y', 'z'] };

    /** The unit a bare number in a box means, given what the viewer is set to. */
    function defaultUnitFor(kind, unitSystem) {
        if (kind === 'angle') {
            return 'deg';
        }
        return unitSystem === 'imperial' ? 'in' : 'mm';
    }

    /** A parameter's value as text, ready to put in an input. */
    function toDraft(parameter, entry) {
        if (!entry || entry.value === null || entry.value === undefined) {
            return parameter.kind === 'flag' ? false : '';
        }
        if (parameter.kind === 'flag') {
            return Boolean(entry.value);
        }
        if (VECTOR_AXES[parameter.kind]) {
            const axes = VECTOR_AXES[parameter.kind];
            const vector = entry.value || {};
            const drafts = {};
            for (const axis of axes) {
                drafts[axis] = vector[axis] === undefined || vector[axis] === null
                    ? ''
                    : dimensionText.formatLength(Number(vector[axis]));
            }
            return drafts;
        }
        if (typeof entry.text === 'string' && entry.text.length) {
            return entry.text;
        }
        return String(entry.value);
    }

    /**
     * null when *draft* is something this parameter could be, otherwise why not.
     * This is the whole of "is the box valid" — the panel only renders it.
     */
    function whyNotValid(parameter, draft, unitSystem) {
        if (parameter.kind === 'flag' || parameter.kind === 'text' || parameter.kind === 'choice') {
            return null;
        }
        if (VECTOR_AXES[parameter.kind]) {
            for (const axis of VECTOR_AXES[parameter.kind]) {
                const why = whyNotOneNumber(parameter, 'length', (draft || {})[axis], unitSystem);
                if (why) {
                    return `${axis}: ${why}`;
                }
            }
            return null;
        }
        return whyNotOneNumber(parameter, parameter.kind, draft, unitSystem);
    }

    function whyNotOneNumber(parameter, kind, draft, unitSystem) {
        const written = typeof draft === 'string' ? draft.trim() : draft;
        if (written === '' || written === null || written === undefined) {
            return parameter.optional ? null : 'needs a value';
        }
        let value;
        if (MEASURED[kind]) {
            try {
                value = dimensionText[MEASURED[kind]](written, defaultUnitFor(kind, unitSystem));
            } catch (error) {
                return error.message;
            }
        } else {
            value = Number(written);
            if (!Number.isFinite(value)) {
                return `"${written}" is not a number`;
            }
            if (kind === 'count' && Math.abs(value - Math.round(value)) > 1e-9) {
                return 'counts things, so it has to be a whole number';
            }
        }
        if (parameter.minimum !== undefined && parameter.minimum !== null && value < parameter.minimum) {
            return `must be at least ${describeBound(kind, parameter.minimum, unitSystem)}`;
        }
        if (parameter.maximum !== undefined && parameter.maximum !== null && value > parameter.maximum) {
            return `must be at most ${describeBound(kind, parameter.maximum, unitSystem)}`;
        }
        return null;
    }

    function describeBound(kind, bound, unitSystem) {
        if (kind === 'length') {
            return dimensionText.formatLength(bound, defaultUnitFor(kind, unitSystem));
        }
        if (kind === 'angle') {
            return dimensionText.formatAngle(bound);
        }
        return String(bound);
    }

    /** A draft as it goes on the wire: the number, and how it was typed. */
    function toWireValue(parameter, draft, unitSystem) {
        if (parameter.kind === 'flag') {
            return { value: Boolean(draft) };
        }
        if (parameter.kind === 'text' || parameter.kind === 'choice') {
            return { value: draft === '' ? null : String(draft) };
        }
        if (VECTOR_AXES[parameter.kind]) {
            const value = {};
            for (const axis of VECTOR_AXES[parameter.kind]) {
                value[axis] = dimensionText.parseLength(
                    String((draft || {})[axis]).trim(), defaultUnitFor('length', unitSystem),
                );
            }
            return { value };
        }
        const written = String(draft).trim();
        if (written === '') {
            return { value: null };
        }
        if (MEASURED[parameter.kind]) {
            return {
                value: dimensionText[MEASURED[parameter.kind]](written, defaultUnitFor(parameter.kind, unitSystem)),
                text: written,
            };
        }
        return { value: parameter.kind === 'count' ? Math.round(Number(written)) : Number(written) };
    }

    /** True when two wire values mean the same measurement. */
    function sameValue(parameter, one, other) {
        const a = one && one.value;
        const b = other && other.value;
        if (a === null || a === undefined || b === null || b === undefined) {
            return (a === null || a === undefined) && (b === null || b === undefined);
        }
        if (VECTOR_AXES[parameter.kind]) {
            return VECTOR_AXES[parameter.kind].every((axis) => close(Number(a[axis]), Number(b[axis])));
        }
        if (typeof a === 'number' && typeof b === 'number') {
            return close(a, b);
        }
        return String(a) === String(b);
    }

    function close(a, b) {
        return Math.abs(a - b) <= 1e-9;
    }

    /**
     * The panel's state, rebuilt whenever the runner sends a kiwari.
     * `schema` is what may be adjusted, `applied` is what the frame on screen
     * was built from, and `drafts` is what is currently in the boxes.
     */
    function fromPayload(payload) {
        const schema = (payload && Array.isArray(payload.schema) ? payload.schema : [])
            .filter((entry) => entry && typeof entry.key === 'string' && entry.key.length);
        const applied = (payload && payload.applied) || {};
        const drafts = {};
        for (const parameter of schema) {
            drafts[parameter.key] = toDraft(parameter, applied[parameter.key]);
        }
        return {
            schema,
            applied,
            drafts,
            changed: new Set((payload && payload.changed) || []),
            canSave: Boolean(payload && payload.canSave),
            stale: Boolean(payload && payload.stale),
        };
    }

    /** That state with one box edited. */
    function withDraft(state, key, draft) {
        return { ...state, drafts: { ...state.drafts, [key]: draft } };
    }

    /** That state with one axis of a point edited. */
    function withAxisDraft(state, key, axis, draft) {
        const current = state.drafts[key] || {};
        return withDraft(state, key, { ...current, [axis]: draft });
    }

    /** Every box's complaint, keyed by parameter. Empty when all of them read. */
    function problems(state, unitSystem) {
        const found = {};
        for (const parameter of state.schema) {
            const why = whyNotValid(parameter, state.drafts[parameter.key], unitSystem);
            if (why) {
                found[parameter.key] = why;
            }
        }
        return found;
    }

    /** Whether a box differs from what the frame on screen was built from. */
    function isEdited(state, parameter, unitSystem) {
        try {
            return !sameValue(
                parameter,
                toWireValue(parameter, state.drafts[parameter.key], unitSystem),
                state.applied[parameter.key],
            );
        } catch (error) {
            return true; // it does not even read as a value, so it is certainly not what was built
        }
    }

    /**
     * Whether a parameter is away from what the code says. Measured against the
     * code's default, never against a saved file — compared with the file, the
     * mark would vanish the moment it was saved, which is when it starts to
     * matter.
     */
    function isChangedFromDefault(state, parameter, unitSystem) {
        if (state.changed.has(parameter.key)) {
            return true;
        }
        try {
            return !sameValue(
                parameter,
                toWireValue(parameter, state.drafts[parameter.key], unitSystem),
                parameter.default,
            );
        } catch (error) {
            return true;
        }
    }

    /** What to send on a refresh, or null if any box does not read. */
    function toWire(state, unitSystem) {
        const values = {};
        for (const parameter of state.schema) {
            try {
                values[parameter.key] = toWireValue(parameter, state.drafts[parameter.key], unitSystem);
            } catch (error) {
                return null;
            }
        }
        return values;
    }

    /** Every box back to what the code says. */
    function resetToDefaults(state) {
        const drafts = {};
        for (const parameter of state.schema) {
            drafts[parameter.key] = toDraft(parameter, parameter.default);
        }
        return { ...state, drafts };
    }

    const KigumiKiwariValues = {
        fromPayload,
        withDraft,
        withAxisDraft,
        problems,
        isEdited,
        isChangedFromDefault,
        toWire,
        toWireValue,
        toDraft,
        whyNotValid,
        sameValue,
        resetToDefaults,
        defaultUnitFor,
        VECTOR_AXES,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiKiwariValues;
    }
    globalScope.KigumiKiwariValues = KigumiKiwariValues;
})(typeof window !== 'undefined' ? window : globalThis);
