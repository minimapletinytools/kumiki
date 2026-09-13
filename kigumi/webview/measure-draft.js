(function (globalScope) {
    'use strict';
    // Making a measurement, from the first feature to a written one.
    //
    // Pure: no projection, no camera, no DOM. Whether a pair CAN be measured
    // from where you are standing depends on the view and is answered before
    // anything gets here -- see the verdict in measurements.js. What this owns
    // is the sequence, which is the same in the 3D view and in a drawing.
    //
    //   state     input      goes to   and
    //   -------   --------   -------   ------------------------------------
    //   IDLE      hold(A)    HOLDING   A is held. It is NOT the selection --
    //                                  picking B moves the focus off it, and
    //                                  it has to survive that.
    //   HOLDING   pick(B)    PENDING   the measurement exists in the viewer
    //   HOLDING   escape     IDLE      A released, the flow left
    //   PENDING   pick(C)    PENDING   B replaced by C. For a misclick: the
    //                                  fix is to click the right one.
    //   PENDING   escape     HOLDING   B released, A still held
    //   PENDING   confirm    IDLE      written, and handed back to be sent
    //
    // ESCAPE RELEASES ONE END AT A TIME, so leaving a half-made measurement
    // takes two presses. The alternative -- one press throwing away both -- is
    // the same keystroke doing a small thing and a large one depending on state
    // you cannot see.
    //
    // NOTHING IS WRITTEN UNTIL CONFIRM. A pending measurement lives here and
    // nowhere else, so a reload, an edit to the drawings file, or a change of
    // scene in the middle of making one has nothing to tidy up. Confirm hands
    // back what to write; this module never talks to the runner.
    //
    // THE PLANE ARRIVES WITH THE SECOND ANCHOR. Deriving it needs both
    // geometries and the camera, and the rule for it lives in python -- so the
    // pick that resolves the second feature brings the plane back with it,
    // rather than this working it out a second way.

    const IDLE = 'idle';
    const HOLDING = 'holding';
    const PENDING = 'pending';

    const STATES = { IDLE, HOLDING, PENDING };

    /** Whether an anchor is one a measurement could be written against. */
    function anchorIsMeasurable(anchor) {
        if (!anchor || !anchor.reference) {
            // A feature nobody declared cannot be referred to afterwards, so a
            // dimension to it could not be saved.
            return { ok: false, reason: 'no-reference' };
        }
        if (!anchor.geometry) {
            // A cylinder's barrel, a lofted side: good to select, nothing to
            // measure against.
            return { ok: false, reason: 'not-measurable' };
        }
        return { ok: true };
    }

    class MeasureDraft {
        constructor() {
            this.reset();
        }

        reset() {
            this.state = IDLE;
            /** The first end. Held, not selected. */
            this.held = null;
            /** The second end, once picked. */
            this.other = null;
            /** Which viewport the second pick landed in; the measurement is drawn there. */
            this.viewportId = null;
            /** Where it is taken, as the runner derived it from both ends. */
            this.plane = null;
        }

        get isActive() {
            return this.state !== IDLE;
        }

        /** The measurement as it stands, or null while only one end is held. */
        get pending() {
            if (this.state !== PENDING) {
                return null;
            }
            return {
                a: this.held.reference,
                b: this.other.reference,
                viewportId: this.viewportId,
                plane: this.plane,
            };
        }

        /**
         * Start from a feature already being looked at.
         *
         * The entry point is deliberately explicit -- a button, or the context
         * menu -- rather than a click meaning something different in a drawing.
         * That is what leaves a drawing with a plain selection.
         */
        hold(anchor) {
            const measurable = anchorIsMeasurable(anchor);
            if (!measurable.ok) {
                return { action: 'refused', reason: measurable.reason };
            }
            this.reset();
            this.held = anchor;
            this.state = HOLDING;
            return { action: 'holding' };
        }

        /**
         * The second end, or a correction of it.
         *
         * `anchor.plane` is where the pair is measured, worked out by the
         * runner from both ends and the camera. Absent is allowed and means the
         * viewport's own plane, which is what an orthographic view implies.
         */
        pick(anchor, viewportId) {
            if (this.state === IDLE) {
                return { action: 'refused', reason: 'nothing-held' };
            }
            const measurable = anchorIsMeasurable(anchor);
            if (!measurable.ok) {
                return { action: 'refused', reason: measurable.reason };
            }
            if (sameReference(anchor.reference, this.held.reference)) {
                // The end already held. A measurement from a feature to itself
                // measures nothing.
                return { action: 'refused', reason: 'same-feature' };
            }
            const replacing = this.state === PENDING;
            this.other = anchor;
            this.plane = anchor.plane || null;
            // The second pick decides where it is drawn, so re-picking moves it.
            this.viewportId = viewportId === undefined ? null : viewportId;
            this.state = PENDING;
            return {
                action: replacing ? 'replaced' : 'pending',
                pending: this.pending,
            };
        }

        /** Release the most recent end. */
        escape() {
            if (this.state === PENDING) {
                this.other = null;
                this.plane = null;
                this.viewportId = null;
                this.state = HOLDING;
                return { action: 'released-second' };
            }
            if (this.state === HOLDING) {
                this.reset();
                return { action: 'left' };
            }
            return { action: 'none' };
        }

        /**
         * Take the measurement. Hands back what to write and goes idle.
         *
         * The caller writes it and pushes one entry onto the undo stack. Until
         * this is called nothing outside the viewer knows the measurement was
         * ever being made.
         */
        confirm() {
            if (this.state !== PENDING) {
                return { action: 'refused', reason: 'nothing-pending' };
            }
            const measurement = this.pending;
            this.reset();
            return { action: 'confirmed', measurement };
        }

        /** Changing scene or mode: hold nothing, and say whether anything was held. */
        leave() {
            const wasActive = this.isActive;
            this.reset();
            return { action: wasActive ? 'left' : 'none' };
        }
    }

    /** Whether two references name the same feature, by their wire form. */
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
     * way round is the same edge -- the rule DerivedFeaturePath applies when it
     * sorts its parents on the python side.
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

    const KigumiMeasureDraft = {
        MeasureDraft, STATES, sameReference, referenceKey, anchorIsMeasurable,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiMeasureDraft;
    }
    globalScope.KigumiMeasureDraft = KigumiMeasureDraft;
})(typeof window !== 'undefined' ? window : globalThis);
