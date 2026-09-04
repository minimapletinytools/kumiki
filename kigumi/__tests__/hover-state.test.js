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

    it('asks straight away, with nothing to wait for', () => {
        const hover = new HoverState();
        hover.moved(100, 100);

        expect(hover.due()).not.toBeNull();
    });

    it('asks nothing more while a question is still out', () => {
        // Answering is not parallel: the requests go to one runner over a pipe.
        // Firing per frame regardless would build a queue answered long after
        // the pointer has gone.
        const hover = new HoverState();
        hover.moved(100, 100);
        hover.due();

        hover.moved(200, 100);

        expect(hover.due()).toBeNull();
    });

    it('asks again as soon as the answer arrives', () => {
        const hover = new HoverState();
        hover.moved(100, 100);
        const first = hover.due();
        hover.answered(first.request, answer('a'));

        hover.moved(200, 100);

        expect(hover.due()).not.toBeNull();
    });

    it('gives up on a question that never comes back', () => {
        // Otherwise one failure leaves hover silent for the rest of the session.
        const hover = new HoverState({ abandonAfter: 3 });
        hover.moved(100, 100);
        hover.due();
        hover.moved(200, 100);

        expect(hover.due()).toBeNull();
        expect(hover.due()).toBeNull();
        expect(hover.due()).not.toBeNull();
    });

    it('asks about where the pointer ended up, not where it began', () => {
        // Several moves can land in one frame; only the last is worth asking.
        const hover = new HoverState();
        hover.moved(100, 100);
        hover.moved(300, 200);

        const due = hover.due();

        expect([due.x, due.y]).toEqual([300, 200]);
    });

    it('an answer to the current question is kept', () => {
        const hover = new HoverState();
        hover.moved(100, 100);
        const due = hover.due();

        const result = hover.answered(due.request, answer('mortise_right'));

        expect(result.kept).toBe(true);
        expect(hover.feature.featureLabel).toBe('mortise_right');
    });

    it('an answer overtaken by a newer question is dropped', () => {
        // Reachable once a question has been abandoned and asked again: the
        // late answer is about a place the pointer has long left.
        const hover = new HoverState({ abandonAfter: 1 });
        hover.moved(100, 100);
        const first = hover.due();
        hover.moved(400, 400);
        hover.due();

        const result = hover.answered(first.request, answer('stale_feature'));

        expect(result.kept).toBe(false);
        expect(result.reason).toBe('stale');
        expect(hover.feature).toBeNull();
    });

    it('settling can be asked for, and is off by default', () => {
        // Zero asks the frame the pointer moves. A larger number trades
        // responsiveness for fewer questions.
        expect(new HoverState().due()).toBeNull();

        const patient = new HoverState({ settleFrames: 2 });
        patient.moved(100, 100);

        expect(patient.due()).toBeNull();
        expect(patient.due()).toBeNull();
        expect(patient.due()).not.toBeNull();
    });

    it('a move restarts the settling', () => {
        const patient = new HoverState({ settleFrames: 2 });
        patient.moved(100, 100);
        patient.due();
        patient.moved(300, 100);

        expect(patient.due()).toBeNull();
        expect(patient.due()).toBeNull();
        expect(patient.due()).not.toBeNull();
    });

    it('clearing forgets what was under the pointer', () => {
        const hover = new HoverState();
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
