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
    //   - asks nothing while a question is still out, so a sweep cannot queue
    //     up hundreds of them and answer them all after the pointer has gone,
    //   - keeps only the newest answer, since an older one is about a place the
    //     pointer has already left.
    //
    // There is no delay before asking. A wait long enough to be worth having is
    // long enough to feel, and the question is cheap enough not to need one --
    // what paces it is the answer coming back, which is the honest limit.

    /** Below this the pointer has not really moved, in canvas pixels. */
    const MOVE_SLOP_PX = 3;

    /**
     * Frames of stillness before asking. Zero asks the frame the pointer moves.
     *
     * Zero is the default because the question is cheap and the answer paces
     * itself -- see due(). Raise it to trade responsiveness for fewer
     * questions, on a slow model or a slow machine.
     */
    const SETTLE_FRAMES = 0;

    /**
     * How many frames to wait on an unanswered question before asking again.
     *
     * Not a delay -- nothing waits on this in the normal case. It is the escape
     * from a question that never comes back, so a hover that failed once does
     * not stay silent for the rest of the session.
     */
    const ABANDON_AFTER_FRAMES = 60;

    class HoverState {
        constructor(options) {
            const settings = options || {};
            this.slop = settings.slop === undefined ? MOVE_SLOP_PX : settings.slop;
            this.settleFrames = settings.settleFrames === undefined
                ? SETTLE_FRAMES : settings.settleFrames;
            this.abandonAfter = settings.abandonAfter === undefined
                ? ABANDON_AFTER_FRAMES : settings.abandonAfter;
            this.reset();
        }

        reset() {
            /** What is under the pointer, as the runner answered. */
            this.feature = null;
            this.at = null;
            /**
             * The answer currently ON SCREEN, which is not the same as the last
             * one received: a redraw is skipped when it would change nothing.
             */
            this.drawn = null;
            /**
             * Which of the features under the pointer is meant, once somebody
             * has said -- by Tab, or from the right-click menu. Undefined means
             * "choose for me", and ZERO IS A CHOICE, so the two cannot be the
             * same value.
             */
            this.candidate = undefined;
            this._pending = null;
            this._asked = 0;
            this._outstanding = false;
            this._waited = 0;
            this._stillFrames = 0;
        }

        /**
         * The pointer moved. Returns whether it is worth asking about.
         *
         * `now` is passed in rather than read, so a test can drive time.
         *
         * `at` is the last point that COUNTED, not the last point seen, so the
         * slop measures travel since the last question rather than the size of
         * one mouse event. Advancing it on a rejected move instead made the
         * test per-event, and a pointer moving slowly never cleared it: sixty
         * pixels travelled three at a time asked nothing at all. Easing across
         * a face onto the arris beside it is exactly that movement, which is
         * why the highlight looked stuck on whatever it was already on --
         * while arriving from off the timber lit the same arris at once, that
         * path going through clear() and so starting with no `at` to be near.
         */
        moved(x, y) {
            const far = this.at === null
                || Math.abs(x - this.at.x) + Math.abs(y - this.at.y) > this.slop;
            if (!far) {
                return { ask: false, reason: 'barely-moved' };
            }
            this.at = { x, y };
            this._pending = { x, y };
            this._stillFrames = 0;
            return { ask: false, reason: 'pending' };
        }

        /**
         * The pointer is at a point. Answers whether it is worth asking about.
         *
         * TWO thresholds, deliberately different:
         *
         *  - the CANDIDATE is forgotten on any movement at all, because cycling
         *    is about one place and somewhere else is a different question;
         *  - the QUESTION is only asked once the pointer has travelled past the
         *    slop, measured from the last point that counted.
         *
         * Both used to live on the app, on either side of the call into here,
         * which is the seam both hover bugs grew on.
         */
        pointerAt(x, y) {
            if (this.at === null || x !== this.at.x || y !== this.at.y) {
                this.candidate = undefined;
            }
            return this.moved(x, y);
        }

        /** Step to the next of `count` features under the pointer. */
        cycle(count) {
            const many = Math.max(1, count || 1);
            this.candidate = ((this.candidate === undefined ? -1 : this.candidate) + 1) % many;
            return this.candidate;
        }

        /** Name one outright, as the right-click menu does. */
        choose(index) {
            this.candidate = Number(index);
            return this.candidate;
        }

        /**
         * Which feature to ask for, as the runner wants it.
         *
         * Null, never undefined: zero is a choice -- stepping round to the first
         * feature, or picking the first row of the menu -- and the runner has to
         * tell that from "choose for me".
         */
        get asking() {
            return this.candidate === undefined ? null : this.candidate;
        }

        /**
         * Whether drawing this answer would put something different on screen.
         *
         * The feature AND the verdict: what is drawn is geometry plus a colour,
         * and the colour turns on what is held, which changes without the
         * pointer moving.
         */
        wouldRedraw(answer) {
            return !HoverState.sameHighlight(this.drawn, answer);
        }

        /** Remember what is now on screen. */
        markDrawn(answer) {
            this.drawn = answer || null;
            return this.drawn;
        }

        /**
         * Ask about the same place again, without the pointer having moved.
         *
         * For when the QUESTION changed rather than the place: stepping to the
         * next feature under the pointer asks the same point a different thing,
         * and `moved` would refuse it for not having travelled far enough.
         */
        askAgain() {
            if (this.at === null) {
                return false;
            }
            this._pending = { x: this.at.x, y: this.at.y };
            this._stillFrames = 0;
            return true;
        }

        /**
         * A frame passed. Returns the point to ask about, or nothing.
         *
         * Called from the render loop rather than a timer, so a hover cannot
         * outlive the viewer that owns it.
         *
         * One question at a time. Asking is not free and answering is not
         * parallel -- the requests go to a single runner over a pipe and are
         * answered one after another -- so firing per frame regardless would
         * build a queue that gets answered long after the pointer has gone.
         * Waiting for the answer instead paces this at exactly the rate the
         * runner can keep up with, whatever that turns out to be.
         *
         * That is why settleFrames defaults to zero: the pacing comes from the
         * answer rather than from a delay decided in advance.
         */
        due() {
            if (this._outstanding) {
                this._waited += 1;
                if (this._waited < this.abandonAfter) {
                    return null;
                }
                // Nothing came back. Give up rather than going quiet for good;
                // if the answer ever arrives it is stale by number anyway.
                this._outstanding = false;
            }
            if (this._pending === null) {
                return null;
            }
            // Counted before it is raised, so a frame with a move in it is not
            // a still one. At the default of zero this never waits.
            if (this._stillFrames < this.settleFrames) {
                this._stillFrames += 1;
                return null;
            }
            const point = this._pending;
            this._pending = null;
            this._stillFrames = 0;
            this._outstanding = true;
            this._waited = 0;
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
            if (request === this._asked) {
                this._outstanding = false;
            }
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
         * Whether the runner judged this pair unmeasurable from where we stand.
         *
         * A verdict with no kinds, not an absent verdict: no verdict at all
         * means no measurement is being made, which is an ordinary hover and
         * not a refusal. Both are read; collapsing them is how a red hover
         * became a click that was accepted and drew nothing.
         */
        static isRefused(answer) {
            const verdict = answer && answer.verdict;
            return Boolean(verdict
                && Array.isArray(verdict.kinds)
                && verdict.kinds.length === 0);
        }

        /**
         * Whether drawing this answer would put the same thing on screen.
         *
         * The feature AND the verdict. What is drawn is geometry plus a colour,
         * and the colour turns on what is held -- which changes without the
         * pointer moving, because taking a first end is a button press. Comparing
         * the feature alone left a highlight green after a first end was taken
         * under a resting pointer, and green is the colour that promises the
         * click will be taken.
         */
        static sameHighlight(one, other) {
            return HoverState.sameFeature(one, other)
                && HoverState.isRefused(one) === HoverState.isRefused(other);
        }

        /**
         * Whether two answers are about the same feature.
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

    const KigumiHover = {
        HoverState, hoverTarget, MOVE_SLOP_PX, SETTLE_FRAMES, ABANDON_AFTER_FRAMES,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiHover;
    }
    globalScope.KigumiHover = KigumiHover;
})(typeof window !== 'undefined' ? window : globalThis);
