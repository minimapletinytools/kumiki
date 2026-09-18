(function (globalScope) {
    'use strict';
    // Making a measurement, from the first feature to a written one.
    //
    // Pure: no projection, no camera, no DOM. Whether a pair CAN be measured
    // from where you are standing is answered by the runner and arrives as a
    // verdict; what this owns is the sequence, which is the same in the 3D view
    // and in a drawing.
    //
    //   state     input        goes to   and
    //   -------   ----------   -------   ----------------------------------
    //   IDLE      hold(A)      HOLDING   A is held. It is NOT the selection --
    //                                    looking at B moves the focus off it,
    //                                    and it has to survive that.
    //   HOLDING   confirm(B)   IDLE      written, and handed back to be sent
    //   HOLDING   escape       IDLE      A released, the flow left
    //
    // THERE IS NO PENDING MEASUREMENT. Hovering a candidate draws what you
    // would get; clicking writes it. A pending state existed so a measurement
    // could be looked at before being committed to -- but looking at it is what
    // hovering does, so it was a second way to see one thing, with its own
    // state to keep consistent, and that state is where the bugs lived. See
    // docs/measuring-states.md.
    //
    // NOTHING IS WRITTEN UNTIL THE CLICK. Confirm hands back what to write;
    // this module never talks to the runner.
    //
    // THE PLANE ARRIVES WITH THE SECOND END. Deriving it needs both geometries
    // and the camera, and the rule for it lives in python -- so the pick that
    // resolves the second feature brings the plane back with it, rather than
    // this working it out a second way.

    const IDLE = 'idle';
    const HOLDING = 'holding';

    const STATES = { IDLE, HOLDING };

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
        }

        get isActive() {
            return this.state !== IDLE;
        }

        /**
         * The first end, while there is one, for judging what is hovered next.
         *
         * The app asks the runner to judge a candidate against this, so it has
         * to be on offer for as long as the draft is active.
         */
        get heldEnd() {
            return this.isActive ? this.held : null;
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
         * Whether this candidate could be the second end right now.
         *
         * Asked by the PREVIEW and by the CLICK, so what is drawn under the
         * pointer is exactly what clicking will take. Two judgements here would
         * be the same bug the verdict exists to remove.
         */
        canTake(anchor) {
            if (this.state !== HOLDING) {
                return { ok: false, reason: 'nothing-held' };
            }
            const measurable = anchorIsMeasurable(anchor);
            if (!measurable.ok) {
                return measurable;
            }
            if (sameReference(anchor.reference, this.held.reference)) {
                // A measurement from a feature to itself measures nothing.
                return { ok: false, reason: 'same-feature' };
            }
            return { ok: true };
        }

        /**
         * Take the measurement. Hands back what to write and goes idle.
         *
         * `anchor.plane` is where the pair is measured, worked out by the
         * runner from both ends and the camera. Absent is allowed and means the
         * viewport's own plane, which is what an orthographic view implies.
         *
         * The caller writes it and pushes one entry onto the undo stack. Until
         * this is called nothing outside the viewer knows a measurement was
         * being made at all.
         */
        confirm(anchor, viewportId) {
            const allowed = this.canTake(anchor);
            if (!allowed.ok) {
                return { action: 'refused', reason: allowed.reason };
            }
            const measurement = {
                a: this.held.reference,
                b: anchor.reference,
                viewportId: viewportId === undefined ? null : viewportId,
                plane: anchor.plane || null,
            };
            this.reset();
            return { action: 'confirmed', measurement };
        }

        /** Release the held end. */
        escape() {
            if (this.state === HOLDING) {
                this.reset();
                return { action: 'left' };
            }
            return { action: 'none' };
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
     * A derived feature's two parents are sorted, because the same feature
     * written either way round is the same feature -- the rule
     * DerivedFeaturePath applies when it sorts its parents on the python side.
     * The kind goes in the key: an edge and a point can be built from one pair
     * of parents, and they are not the same reference.
     */
    function referenceKey(reference) {
        if (reference.kind === 'edge' || reference.kind === 'point') {
            const parents = [reference.a, reference.b]
                .map((part) => [((part || {}).csgPath || []).join('/'), (part || {}).feature || ''])
                .sort();
            return [reference.timber, reference.kind, parents];
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
