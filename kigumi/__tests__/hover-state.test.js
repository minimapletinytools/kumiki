const { HoverState } = require('../webview/hover-state.js');

function answer(feature, path = ['cut'], memberKey = 'post#0') {
    return { memberKey, path, feature };
}

describe('hover pacing', () => {
    it('holds nothing to begin with', () => {
        expect(new HoverState().feature).toBeNull();
    });

    it('a move that has barely travelled is not worth asking about', () => {
        const hover = new HoverState();
        hover.moved(100, 100, 0);
        hover.due(1000);

        const result = hover.moved(101, 100, 1000);

        expect(result.ask).toBe(false);
        expect(result.reason).toBe('barely-moved');
    });

    it('nothing is asked until the pointer settles', () => {
        const hover = new HoverState({ settle: 40 });
        hover.moved(100, 100, 0);

        expect(hover.due(20)).toBeNull();
        expect(hover.due(40)).not.toBeNull();
    });

    it('a pointer that keeps moving keeps resetting the wait', () => {
        // Otherwise a sweep across the model would fire a question per step.
        const hover = new HoverState({ settle: 40 });
        hover.moved(100, 100, 0);
        hover.moved(200, 100, 30);
        hover.moved(300, 100, 60);

        expect(hover.due(80)).toBeNull();
        expect(hover.due(100)).not.toBeNull();
    });

    it('asks about where the pointer ended up, not where it began', () => {
        const hover = new HoverState({ settle: 40 });
        hover.moved(100, 100, 0);
        hover.moved(300, 200, 10);

        const due = hover.due(60);

        expect([due.x, due.y]).toEqual([300, 200]);
    });

    it('an answer to the current question is kept', () => {
        const hover = new HoverState({ settle: 0 });
        hover.moved(100, 100, 0);
        const due = hover.due(10);

        const result = hover.answered(due.request, answer('mortise_right'));

        expect(result.kept).toBe(true);
        expect(hover.feature.feature).toBe('mortise_right');
    });

    it('an answer overtaken by a newer question is dropped', () => {
        // The normal case, not an edge one: the pointer keeps moving while the
        // runner is working, and the old answer is about a place it has left.
        const hover = new HoverState({ settle: 0 });
        hover.moved(100, 100, 0);
        const first = hover.due(10);
        hover.moved(400, 400, 20);
        hover.due(30);

        const result = hover.answered(first.request, answer('stale_feature'));

        expect(result.kept).toBe(false);
        expect(result.reason).toBe('stale');
        expect(hover.feature).toBeNull();
    });

    it('clearing forgets what was under the pointer', () => {
        const hover = new HoverState({ settle: 0 });
        hover.moved(100, 100, 0);
        hover.answered(hover.due(10).request, answer('mortise_right'));

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
