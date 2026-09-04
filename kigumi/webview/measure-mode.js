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
    //   FROM      pick B    BETWEEN    the measurement A-B is made, in B's
    //                                  viewport
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
    //
    //
    // WHICH VIEWPORT IT BELONGS TO
    //
    // The second pick's. The first may be taken from any view -- whichever one
    // shows that feature best -- and the dimension is drawn where the pair was
    // completed. Re-picking the second end moves it, since that pick is the one
    // that decides.
    //
    // It has to be one of them rather than both, because a dimension is a
    // projection and only means anything in the plane it is projected onto. And
    // it is the second because that is the one you are looking at when you
    // finish, which is the view you meant to draw it in.

    /**
     * Below this a measurement measures nothing, in world units.
     *
     * The same threshold the sheet uses to decline drawing a dimension, so a
     * pair refused here and one drawn as broken agree about what is too small.
     */
    const DEGENERATE = 1e-6;

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
            this.fromGeometry = null;
            this.toGeometry = null;
            this.fromAt = null;
            /** Where the second pick landed. The measurement is drawn there. */
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
                this.fromGeometry = pick.geometry || null;
                this.fromAt = pick.at || null;
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
            this.toGeometry = pick.geometry || null;
            // The second pick decides where it is drawn, so re-picking moves it.
            this.viewportId = viewportId === undefined ? null : viewportId;
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
                this.toGeometry = null;
                this.viewportId = null;
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

    /**
     * Whether a second pick could complete a measurement with the first.
     *
     * Answered per VIEWPORT, because a dimension is a projection: two faces at
     * an angle are an angle in one view and cover each other in another. That
     * is also why it is the second pick that decides which viewport the
     * measurement belongs to -- the answer depends on where you are standing.
     *
     * `axes` is that viewport's, and `kinds` is measurements.availableKinds
     * passed in rather than reached for, so this stays free of the module that
     * knows about projection.
     */
    function couldMeasure(held, candidate, axes, forms, value) {
        if (!held || !candidate) {
            return { ok: false, reason: 'nothing-held' };
        }
        if (!held.geometry || !candidate.geometry) {
            // A cylinder's barrel, a lofted side: good to select, nothing to
            // measure against, and worth saying before the click rather than
            // after.
            return { ok: false, reason: 'not-measurable' };
        }
        const available = forms(held.geometry, candidate.geometry, axes);
        if (!available || available.length === 0) {
            return { ok: false, reason: 'not-measurable' };
        }
        // A pair can admit a measurement and admit a measurement of nothing.
        // Two edges in line with each other in this view are a good pair whose
        // distance is zero, and a dimension reading zero is not worth drawing:
        // it says nothing and covers what it is drawn over.
        if (value && held.at && candidate.at) {
            const size = value(available[0], held.at, candidate.at, held.geometry,
                               candidate.geometry, axes);
            if (size !== null && Math.abs(size) < DEGENERATE) {
                return { ok: false, reason: 'degenerate', kinds: available };
            }
        }
        return { ok: true, kinds: available };
    }

    const KigumiMeasureMode = {
        MeasureMode,
        couldMeasure,
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
