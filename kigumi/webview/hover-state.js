(function (globalScope) {
    'use strict';
    // What the pointer is over, and how often it is worth asking.
    //
    // Hover is a pick that does not commit: the same question a click asks,
    // with none of the consequences. Kept apart from selection deliberately --
    // moving the mouse must never change what is selected, and the two are
    // drawn differently so "about to click" and "clicked" cannot be confused.
    //
    //
    // WHY THIS IS NOT JUST A CLICK PER MOUSE MOVE
    //
    // Answering a click costs about 78ms on a timber of any size, nearly all of
    // it walking every triangle to build a highlight mesh. Mouse moves arrive
    // every 16ms. Asking per move would queue faster than it could answer and
    // the highlight would trail the pointer by seconds.
    //
    // So hover asks a cheaper question -- resolve the feature, outline it from
    // the CSG, never touch the mesh -- which measures about 4ms. That is
    // affordable, but not free, so this also:
    //
    //   - ignores a move that has not travelled far enough to mean anything,
    //   - waits for one still frame, so a sweep asks nothing on the way past,
    //   - keeps only the newest answer, since an older one is about a place the
    //     pointer has already left.

    /** Below this the pointer has not really moved, in canvas pixels. */
    const MOVE_SLOP_PX = 3;

    /**
     * A pointer is settled once a frame has passed without it moving.
     *
     * Not a wait measured in milliseconds: any number long enough to be worth
     * having is long enough to feel. One still frame is the shortest thing
     * that means "stopped", and it costs nothing when the pointer is sweeping,
     * since every frame of a sweep has a move in it.
     */
    const SETTLE_FRAMES = 1;

    class HoverState {
        constructor(options) {
            const settings = options || {};
            this.slop = settings.slop === undefined ? MOVE_SLOP_PX : settings.slop;
            this.settleFrames = settings.settleFrames === undefined
                ? SETTLE_FRAMES : settings.settleFrames;
            this.reset();
        }

        reset() {
            /** What is under the pointer, as the runner answered. */
            this.feature = null;
            this.at = null;
            this._pending = null;
            this._asked = 0;
            this._stillFrames = 0;
        }

        /**
         * The pointer moved. Returns whether it is worth asking about.
         *
         * `now` is passed in rather than read, so a test can drive time.
         */
        moved(x, y) {
            const far = this.at === null
                || Math.abs(x - this.at.x) + Math.abs(y - this.at.y) > this.slop;
            this.at = { x, y };
            if (!far) {
                return { ask: false, reason: 'barely-moved' };
            }
            this._pending = { x, y };
            this._stillFrames = 0;
            return { ask: false, reason: 'settling' };
        }

        /**
         * Time passed. Returns the point to ask about once the pointer settles.
         *
         * Called from the render loop rather than a timer, so a hover cannot
         * outlive the viewer that owns it.
         */
        due() {
            if (this._pending === null) {
                return null;
            }
            // Counted before it is raised, so a frame that had a move in it is
            // not the still frame: the first call after moving always waits.
            if (this._stillFrames < this.settleFrames) {
                this._stillFrames += 1;
                return null;
            }
            const point = this._pending;
            this._pending = null;
            this._stillFrames = 0;
            this._asked += 1;
            return { x: point.x, y: point.y, request: this._asked };
        }

        /**
         * An answer came back. Ignored if a newer question has been asked since.
         *
         * Out-of-order answers are the normal case, not an edge one: the
         * pointer keeps moving while the runner is working.
         */
        answered(request, feature) {
            if (request !== this._asked) {
                return { kept: false, reason: 'stale' };
            }
            this.feature = feature || null;
            return { kept: true, feature: this.feature };
        }

        /** The pointer left, or the mode changed: hold nothing. */
        clear() {
            const had = this.feature !== null;
            this.reset();
            return { cleared: had };
        }

        /**
         * Whether two answers are about the same feature, so redrawing is pointless.
         *
         * The feature's name as well as the path: two faces of one prism share
         * a path and differ only by which face, so comparing paths alone would
         * leave the first one drawn while the pointer sits on the second.
         */
        static sameFeature(one, other) {
            if (!one || !other) {
                return one === other;
            }
            return one.memberKey === other.memberKey
                && (one.path || []).join('/') === (other.path || []).join('/')
                && (one.featureLabel || null) === (other.featureLabel || null);
        }
    }

    /**
     * What to ask about, given what a click here would act on.
     *
     * Takes the pick decision rather than the ray hits, because those are not
     * the same member: a click drills into a SELECTED timber wherever it sits
     * along the ray, not into whatever is nearest. Handed the hits instead,
     * hover asked about the frontmost one and lit something a click would not
     * have touched.
     *
     * The shape is {memberKey, hit}, and the inner hit carries the world point
     * -- two nested things both reasonably called "hit", which is exactly how
     * the wrong one gets used.
     */
    function hoverTarget(decision) {
        if (!decision || !decision.hit || !decision.hit.point) {
            return null;
        }
        const point = decision.hit.point;
        return {
            memberKey: decision.memberKey,
            point: [point.x, point.y, point.z],
        };
    }

    const KigumiHover = { HoverState, hoverTarget, MOVE_SLOP_PX, SETTLE_FRAMES };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiHover;
    }
    globalScope.KigumiHover = KigumiHover;
})(typeof window !== 'undefined' ? window : globalThis);
