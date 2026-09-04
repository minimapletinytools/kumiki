const { HoverState, hoverTarget } = require('../webview/hover-state.js');

function answer(featureLabel, path = ['cut'], memberKey = 'post#0') {
    return { memberKey, path, featureLabel };
}

describe('hover pacing', () => {
    it('holds nothing to begin with', () => {
        expect(new HoverState().feature).toBeNull();
    });

    it('a move that has barely travelled is not worth asking about', () => {
        const hover = new HoverState();
        hover.moved(100, 100);
        hover.due();

        const result = hover.moved(101, 100, 1000);

        expect(result.ask).toBe(false);
        expect(result.reason).toBe('barely-moved');
    });

    it('nothing is asked until a frame has passed without moving', () => {
        const hover = new HoverState();
        hover.moved(100, 100);

        expect(hover.due()).toBeNull();
        expect(hover.due()).not.toBeNull();
    });

    it('a pointer that keeps moving asks nothing on the way past', () => {
        // Every frame of a sweep has a move in it, so the still frame never
        // arrives until the sweep stops.
        const hover = new HoverState();
        hover.moved(100, 100);
        hover.due();
        hover.moved(200, 100);
        hover.due();
        hover.moved(300, 100);

        expect(hover.due()).toBeNull();
        expect(hover.due()).not.toBeNull();
    });

    it('asks about where the pointer ended up, not where it began', () => {
        const hover = new HoverState();
        hover.moved(100, 100);
        hover.moved(300, 200);
        hover.due();

        const due = hover.due();

        expect([due.x, due.y]).toEqual([300, 200]);
    });

    it('an answer to the current question is kept', () => {
        const hover = new HoverState({ settleFrames: 0 });
        hover.moved(100, 100);
        const due = hover.due();

        const result = hover.answered(due.request, answer('mortise_right'));

        expect(result.kept).toBe(true);
        expect(hover.feature.featureLabel).toBe('mortise_right');
    });

    it('an answer overtaken by a newer question is dropped', () => {
        // The normal case, not an edge one: the pointer keeps moving while the
        // runner is working, and the old answer is about a place it has left.
        const hover = new HoverState({ settleFrames: 0 });
        hover.moved(100, 100);
        const first = hover.due();
        hover.moved(400, 400);
        hover.due();

        const result = hover.answered(first.request, answer('stale_feature'));

        expect(result.kept).toBe(false);
        expect(result.reason).toBe('stale');
        expect(hover.feature).toBeNull();
    });

    it('clearing forgets what was under the pointer', () => {
        const hover = new HoverState({ settleFrames: 0 });
        hover.moved(100, 100);
        hover.answered(hover.due().request, answer('mortise_right'));

        expect(hover.clear().cleared).toBe(true);
        expect(hover.feature).toBeNull();
    });

    it('clearing nothing says so', () => {
        expect(new HoverState().clear().cleared).toBe(false);
    });
});

describe('telling two answers apart', () => {
    it('the same feature on the same node is the same answer', () => {
        expect(HoverState.sameFeature(answer('a'), answer('a'))).toBe(true);
    });

    it('the same name on a different node is not', () => {
        expect(HoverState.sameFeature(answer('a', ['one']), answer('a', ['two']))).toBe(false);
    });

    it('two faces of one prism are told apart', () => {
        // Same path, different face. Comparing paths alone would leave the
        // first drawn while the pointer sits on the second.
        expect(HoverState.sameFeature(answer('left'), answer('right'))).toBe(false);
    });

    it('the same name on a different timber is not', () => {
        expect(HoverState.sameFeature(
            answer('a', ['cut'], 'post#0'),
            answer('a', ['cut'], 'post#1'),
        )).toBe(false);
    });

    it('nothing matches nothing', () => {
        expect(HoverState.sameFeature(null, null)).toBe(true);
        expect(HoverState.sameFeature(answer('a'), null)).toBe(false);
    });
});


describe('what to ask about', () => {
    // A ray hit is {memberKey, hit}, and the inner hit carries the point. Two
    // nested things both reasonably called "hit" -- reaching for the wrong one
    // threw inside the render loop and froze the view, so it is pinned here.
    const hit = (memberKey, x, y, z) => ({ memberKey, hit: { point: { x, y, z } } });

    it('takes the member the click decided on, and its world point', () => {
        expect(hoverTarget(hit('post#0', 1, 2, 3))).toEqual({
            memberKey: 'post#0',
            point: [1, 2, 3],
        });
    });

    it('nothing decided is nothing to ask', () => {
        expect(hoverTarget(null)).toBeNull();
        expect(hoverTarget({ action: 'clear' })).toBeNull();
    });

    it('a decision without a point is not asked about either', () => {
        // Rather than reading undefined off it, which is what threw.
        expect(hoverTarget({ memberKey: 'post#0' })).toBeNull();
        expect(hoverTarget({ memberKey: 'post#0', hit: {} })).toBeNull();
    });
});
