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
    //   - waits for the pointer to settle before asking,
    //   - keeps only the newest answer, since an older one is about a place the
    //     pointer has already left.

    /** Below this the pointer has not really moved, in canvas pixels. */
    const MOVE_SLOP_PX = 3;

    /** How long the pointer settles before asking, in milliseconds. */
    const SETTLE_MS = 40;

    class HoverState {
        constructor(options) {
            const settings = options || {};
            this.slop = settings.slop === undefined ? MOVE_SLOP_PX : settings.slop;
            this.settle = settings.settle === undefined ? SETTLE_MS : settings.settle;
            this.reset();
        }

        reset() {
            /** What is under the pointer, as the runner answered. */
            this.feature = null;
            this.at = null;
            this._pending = null;
            this._asked = 0;
        }

        /**
         * The pointer moved. Returns whether it is worth asking about.
         *
         * `now` is passed in rather than read, so a test can drive time.
         */
        moved(x, y, now) {
            const far = this.at === null
                || Math.abs(x - this.at.x) + Math.abs(y - this.at.y) > this.slop;
            this.at = { x, y };
            if (!far) {
                return { ask: false, reason: 'barely-moved' };
            }
            this._pending = { x, y, since: now };
            return { ask: false, reason: 'settling' };
        }

        /**
         * Time passed. Returns the point to ask about once the pointer settles.
         *
         * Called from the render loop rather than a timer, so a hover cannot
         * outlive the viewer that owns it.
         */
        due(now) {
            if (this._pending === null || now - this._pending.since < this.settle) {
                return null;
            }
            const point = this._pending;
            this._pending = null;
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

        /** Whether two answers are about the same feature, so redrawing is pointless. */
        static sameFeature(one, other) {
            if (!one || !other) {
                return one === other;
            }
            return one.memberKey === other.memberKey
                && (one.path || []).join('/') === (other.path || []).join('/')
                && one.feature === other.feature;
        }
    }

    /**
     * What to ask about, given the ray hits under the pointer.
     *
     * A hit is {memberKey, hit}, where the inner hit carries the world point --
     * two nested things both reasonably called "hit", which is exactly how the
     * wrong one gets used. Pinned here by a test rather than by memory.
     */
    function hoverTarget(hits) {
        const found = (hits || [])[0];
        if (!found || !found.hit || !found.hit.point) {
            return null;
        }
        const point = found.hit.point;
        return {
            memberKey: found.memberKey,
            point: [point.x, point.y, point.z],
        };
    }

    const KigumiHover = { HoverState, hoverTarget, MOVE_SLOP_PX, SETTLE_MS };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiHover;
    }
    globalScope.KigumiHover = KigumiHover;
})(typeof window !== 'undefined' ? window : globalThis);
