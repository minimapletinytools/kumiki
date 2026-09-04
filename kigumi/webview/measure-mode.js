(function (globalScope) {
    'use strict';
    // Making a measurement by picking, as a state machine and nothing else.
    //
    // No DOM, no scene, no runner: it takes picks and Escapes and says what the
    // measurement is now. That is what makes the awkward part -- which pick
    // replaces which -- something you can read in one place and test without a
    // viewer.
    //
    //
    // THE STATES
    //
    //   OFF        not in a drawing, or nothing picked yet.
    //   FROM       one feature held. This is what "measurement mode" means:
    //              picking a feature in a drawing enters it.
    //   BETWEEN    two features held, and a measurement exists between them.
    //
    //
    // THE MOVES
    //
    //   state     input     goes to    and
    //   -------   -------   --------   ---------------------------------------
    //   OFF       pick A    FROM       A is held
    //   FROM      pick B    BETWEEN    the measurement A-B is made
    //   FROM      escape    OFF        A released, mode left
    //   BETWEEN   pick C    BETWEEN    B replaced by C; the SAME measurement
    //                                  now reads A-C. For a misclick, so it
    //                                  does not leave a wrong one behind.
    //   BETWEEN   escape    FROM       B released, measurement removed, A kept
    //   any       leave     OFF        everything released
    //
    // Escape pops one step, which is why leaving takes two from BETWEEN. There
    // is only ever one measurement in flight: a second pick makes it and every
    // pick after edits it, so measuring the same pair twice cannot happen by
    // accident and no id has to be minted to tell two of them apart.
    //
    // Selecting a feature in a drawing is always the start of a measurement --
    // there is no plain "look at this one" selection while in a drawing. Both
    // feature and measurement selections are cleared when the mode changes, so
    // nothing is left highlighted that the current mode cannot act on.

    const OFF = 'off';
    const FROM = 'from';
    const BETWEEN = 'between';

    /**
     * Whether a pick can be measured to, and why not when it cannot.
     *
     * The reference is what a measurement would hold; without one the pick is
     * still drilling through compounds and names no feature yet.
     */
    function pickIsMeasurable(pick) {
        if (!pick || !pick.reference) {
            return { ok: false, reason: 'no-feature' };
        }
        return { ok: true };
    }

    class MeasureMode {
        constructor() {
            this.reset();
        }

        reset() {
            this.state = OFF;
            this.from = null;
            this.to = null;
            /** The viewport the first pick landed in; the measurement lives there. */
            this.viewportId = null;
        }

        get isActive() {
            return this.state !== OFF;
        }

        /** The measurement as it stands, or null while only one end is held. */
        get measurement() {
            if (this.state !== BETWEEN) {
                return null;
            }
            return { a: this.from, b: this.to, viewportId: this.viewportId };
        }

        /**
         * A feature was picked.
         *
         * Returns what happened, so the caller can report a refusal rather than
         * silently doing nothing: {action, reason?, measurement?}.
         */
        pick(pick, viewportId) {
            const measurable = pickIsMeasurable(pick);
            if (!measurable.ok) {
                return { action: 'refused', reason: measurable.reason };
            }
            const reference = pick.reference;

            if (this.state === OFF) {
                this.from = reference;
                this.viewportId = viewportId === undefined ? null : viewportId;
                this.state = FROM;
                return { action: 'from' };
            }

            // The second end, and every one after it, is the same end being
            // chosen again. A measurement to a feature already at the other end
            // measures nothing, so it is refused rather than made.
            if (sameReference(reference, this.from)) {
                return { action: 'refused', reason: 'same-feature' };
            }

            const replacing = this.state === BETWEEN;
            this.to = reference;
            this.state = BETWEEN;
            return {
                action: replacing ? 'replaced' : 'to',
                measurement: this.measurement,
            };
        }

        /** Escape: release the most recent end. */
        escape() {
            if (this.state === BETWEEN) {
                this.to = null;
                this.state = FROM;
                return { action: 'released-to' };
            }
            if (this.state === FROM) {
                this.reset();
                return { action: 'left' };
            }
            return { action: 'none' };
        }

        /** Leaving the drawing, or switching modes: hold nothing. */
        leave() {
            const wasActive = this.isActive;
            this.reset();
            return { action: wasActive ? 'left' : 'none' };
        }
    }

    /** Whether two references name the same thing, by their wire form. */
    function sameReference(one, other) {
        if (!one || !other) {
            return false;
        }
        return JSON.stringify(referenceKey(one)) === JSON.stringify(referenceKey(other));
    }

    /**
     * A comparable form of a reference.
     *
     * An edge's two parents are sorted, because the same edge written either
     * way round is the same edge -- the same rule DerivedFeaturePath applies
     * when it sorts its parents on the python side.
     */
    function referenceKey(reference) {
        if (reference.kind === 'edge') {
            const parents = [reference.a, reference.b]
                .map((part) => [((part || {}).csgPath || []).join('/'), (part || {}).feature || ''])
                .sort();
            return [reference.timber, 'edge', parents];
        }
        return [
            reference.timber,
            'single',
            (reference.csgPath || []).join('/'),
            reference.feature || '',
            reference.type || '',
        ];
    }

    const KigumiMeasureMode = {
        MeasureMode,
        sameReference,
        referenceKey,
        pickIsMeasurable,
        STATES: { OFF, FROM, BETWEEN },
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiMeasureMode;
    }
    globalScope.KigumiMeasureMode = KigumiMeasureMode;
})(typeof window !== 'undefined' ? window : globalThis);
