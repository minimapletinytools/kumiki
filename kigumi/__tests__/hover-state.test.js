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

    it('small moves add up, so a slow pointer is still asked about', () => {
        // The slop is travel since the last question, not the size of one
        // mouse event. When it was per-event, a pointer easing along at 2px a
        // frame never cleared it and nothing was ever asked, however far it
        // went -- which is what made the highlight look stuck on the face
        // while you tried to reach the arris beside it.
        const hover = new HoverState();
        hover.moved(100, 100);
        hover.answered(hover.due().request, answer('face'));

        let asked = 0;
        for (let step = 1; step <= 10; step += 1) {
            hover.moved(100 + step * 2, 100);
            const due = hover.due();
            if (due) {
                asked += 1;
                hover.answered(due.request, answer('arris'));
            }
        }

        expect(asked).toBeGreaterThan(0);
        expect(hover.feature.featureLabel).toBe('arris');
    });

    it('a pointer wobbling in place is still not worth asking about', () => {
        // The other half of the same rule: accumulating travel must not turn
        // jitter into a question, or the slop would buy nothing.
        const hover = new HoverState();
        hover.moved(100, 100);
        hover.answered(hover.due().request, answer('face'));

        let asked = 0;
        for (let tick = 0; tick < 20; tick += 1) {
            hover.moved(100 + (tick % 2 ? 2 : 0), 100);
            if (hover.due()) {
                asked += 1;
            }
        }

        expect(asked).toBe(0);
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

describe('asking about the same place again', () => {
    // Stepping to the next feature under the pointer asks the same point a
    // different question, and `moved` refuses a point that has not travelled.
    const answer = (name) => ({ featureLabel: name, path: [], memberKey: 'm' });

    test('the same place can be asked about again', () => {
        const hover = new HoverState();
        hover.moved(100, 100);
        const first = hover.due();
        hover.answered(first.request, answer('a'));

        expect(hover.askAgain()).toBe(true);
        const again = hover.due();

        expect([again.x, again.y]).toEqual([100, 100]);
        expect(again.request).not.toBe(first.request);
    });

    test('there is nothing to ask again about before the pointer has moved', () => {
        expect(new HoverState().askAgain()).toBe(false);
    });

    test('and nothing after the pointer has left', () => {
        const hover = new HoverState();
        hover.moved(100, 100);
        hover.clear();

        expect(hover.askAgain()).toBe(false);
    });
});

describe('whether redrawing the hover would change anything', () => {
    // What is drawn is geometry plus a colour, and the colour says whether the
    // click will be taken. The colour turns on what is HELD, which changes
    // without the pointer moving -- taking a first end is a button press. So a
    // hover cached by feature alone stayed green after a first end was taken
    // under a resting pointer, promising a click that was then refused.
    // The runner's one verdict. Absent means no measurement is being made;
    // present with no kinds means this pair admits nothing from here.
    const refused = (label) => ({ ...answer(label), verdict: { kinds: [], reason: 'no-kind' } });
    const allowed = (label) => ({
        ...answer(label), verdict: { kinds: [{ operation: 'distance', space: 'projected' }] },
    });
    const idle = (label) => ({ ...answer(label), verdict: null });

    test('an ordinary hover is not a refusal', () => {
        // Null kinds mean no measurement is being made, not that this one
        // cannot be finished.
        expect(HoverState.isRefused(idle('front'))).toBe(false);
        expect(HoverState.isRefused(answer('front'))).toBe(false);
    });

    test('no kind this view admits is', () => {
        expect(HoverState.isRefused(refused('front'))).toBe(true);
    });

    test('a kind it does admit is not', () => {
        expect(HoverState.isRefused(allowed('front'))).toBe(false);
    });

    test('the same feature with the same verdict need not be redrawn', () => {
        expect(HoverState.sameHighlight(allowed('front'), allowed('front'))).toBe(true);
        expect(HoverState.sameHighlight(refused('front'), refused('front'))).toBe(true);
    });

    test('the SAME feature whose verdict changed must be', () => {
        // The pointer has not moved; the first end was taken. This is the one
        // that was wrong: the highlight stayed green over a pair that could
        // not be measured.
        expect(HoverState.sameHighlight(idle('front'), refused('front'))).toBe(false);
    });

    test('and one that stopped being refused, equally', () => {
        expect(HoverState.sameHighlight(refused('front'), allowed('front'))).toBe(false);
    });

    test('a different feature is still a different drawing', () => {
        expect(HoverState.sameHighlight(allowed('front'), allowed('back'))).toBe(false);
    });

    test('nothing drawn yet, and an answer, differ', () => {
        expect(HoverState.sameHighlight(null, allowed('front'))).toBe(false);
        expect(HoverState.sameHighlight(null, null)).toBe(true);
    });
});

describe('which feature under the pointer is meant', () => {
    // Tab steps through them and the right-click menu names one outright. This
    // lived on the app, beside the call into here, and the two thresholds that
    // govern it sat on either side of that call.

    test('nobody has said, to begin with', () => {
        const hover = new HoverState();

        expect(hover.candidate).toBeUndefined();
        expect(hover.asking).toBeNull();
    });

    test('asking is null rather than undefined, because ZERO IS A CHOICE', () => {
        // Stepping round to the first feature is somebody choosing it, and the
        // runner has to tell that from "choose for me".
        const hover = new HoverState();
        hover.choose(0);

        expect(hover.asking).toBe(0);
    });

    test('Tab steps through them and wraps', () => {
        const hover = new HoverState();

        expect(hover.cycle(3)).toBe(0);
        expect(hover.cycle(3)).toBe(1);
        expect(hover.cycle(3)).toBe(2);
        expect(hover.cycle(3)).toBe(0);
    });

    test('and a count of nothing still steps somewhere', () => {
        expect(new HoverState().cycle(0)).toBe(0);
    });

    test('the menu names one', () => {
        const hover = new HoverState();

        expect(hover.choose('2')).toBe(2);
        expect(hover.asking).toBe(2);
    });
});

describe('the two thresholds a moving pointer meets', () => {
    // Different on purpose, and they used to sit on either side of the call
    // into this module.

    test('any movement at all forgets which feature was chosen', () => {
        // Cycling is about ONE place. Somewhere else is a different question.
        const hover = new HoverState({ slop: 20 });
        hover.pointerAt(100, 100);
        hover.choose(2);

        hover.pointerAt(101, 100);

        expect(hover.candidate).toBeUndefined();
    });

    test('but a pointer that has not moved keeps it', () => {
        const hover = new HoverState({ slop: 20 });
        hover.pointerAt(100, 100);
        hover.choose(2);

        hover.pointerAt(100, 100);

        expect(hover.candidate).toBe(2);
    });

    test('while asking again waits for the slop', () => {
        // Measured from the last point that COUNTED, so a slow drag adds up
        // rather than being refused one small move at a time.
        const hover = new HoverState({ slop: 20 });
        hover.pointerAt(100, 100);
        // Answered, because one question is outstanding at a time and an
        // unanswered one refuses the next whatever the pointer does.
        hover.answered(hover.due().request, { featureLabel: 'front' });

        hover.pointerAt(105, 100);
        expect(hover.due()).toBeNull();

        hover.pointerAt(130, 100);
        expect(hover.due()).not.toBeNull();
    });

    test('the question carries the point, so nobody keeps a copy', () => {
        const hover = new HoverState();
        hover.pointerAt(42, 77);

        expect(hover.due()).toMatchObject({ x: 42, y: 77 });
    });
});

describe('what is on screen', () => {
    const answer = (label, kinds) => ({
        memberKey: 'post#0', path: ['cut'], featureLabel: label,
        verdict: kinds === undefined ? null : { kinds },
    });

    test('nothing, to begin with', () => {
        expect(new HoverState().drawn).toBeNull();
    });

    test('the first answer is worth drawing', () => {
        expect(new HoverState().wouldRedraw(answer('front'))).toBe(true);
    });

    test('the same answer again is not', () => {
        const hover = new HoverState();
        hover.markDrawn(answer('front'));

        expect(hover.wouldRedraw(answer('front'))).toBe(false);
    });

    test('a different feature is', () => {
        const hover = new HoverState();
        hover.markDrawn(answer('front'));

        expect(hover.wouldRedraw(answer('back'))).toBe(true);
    });

    test('and so is the SAME feature whose verdict changed', () => {
        // The colour says whether the click will be taken, and that turns on
        // what is held -- which changes while the pointer rests still.
        const hover = new HoverState();
        hover.markDrawn(answer('front'));

        expect(hover.wouldRedraw(answer('front', []))).toBe(true);
    });

    test('forgetting it means the next answer is drawn again', () => {
        const hover = new HoverState();
        hover.markDrawn(answer('front'));

        hover.markDrawn(null);

        expect(hover.wouldRedraw(answer('front'))).toBe(true);
    });

    test('clearing the hover forgets it too', () => {
        // Leaving the canvas: nothing should stay lit, and nothing should think
        // it still is.
        const hover = new HoverState();
        hover.pointerAt(10, 10);
        hover.markDrawn(answer('front'));
        hover.choose(1);

        hover.clear();

        expect(hover.drawn).toBeNull();
        expect(hover.candidate).toBeUndefined();
    });
});

// The right-click menu names the features under the pointer. Reaching one of
// its rows means moving the pointer off the canvas -- which cleared the hover
// and forgot the cycled choice, so the menu was choosing on behalf of something
// that had already gone. Pinned, the place stays and only the question moves.
describe('holding the question still while a menu asks it', () => {
    function hovering() {
        const hover = new HoverState({ slop: 0 });
        hover.pointerAt(100, 100);
        hover.due();
        hover.answered(1, { memberKey: 'post', candidateCount: 3 });
        return hover;
    }

    test('there is nothing to hold on to before the pointer has been anywhere', () => {
        expect(new HoverState().pin()).toBe(false);
    });

    test('pinning holds the point it is already asking about', () => {
        const hover = hovering();

        expect(hover.pin()).toBe(true);
        expect(hover.pinned).toBe(true);
        expect(hover.at).toEqual({ x: 100, y: 100 });
    });

    test('the pointer moving away does not move it', () => {
        const hover = hovering();
        hover.pin();

        const answer = hover.pointerAt(400, 20);

        expect(answer).toEqual({ ask: false, reason: 'pinned' });
        expect(hover.at).toEqual({ x: 100, y: 100 });
    });

    test('and does not forget the choice being made', () => {
        // The whole point. Cycling is forgotten on ANY movement, and using a
        // menu is movement.
        const hover = hovering();
        hover.cycle(3);
        hover.pin();

        hover.pointerAt(400, 20);

        expect(hover.asking).toBe(0);
    });

    test('a pinned hover still asks about its own point', () => {
        const hover = hovering();
        hover.pin();
        hover.due();

        hover.choose(2);
        expect(hover.askAgain()).toBe(true);

        expect(hover.due()).toMatchObject({ x: 100, y: 100 });
    });

    test('unpinning gives the pointer the question back', () => {
        const hover = hovering();
        hover.pin();
        hover.pointerAt(400, 20);

        hover.unpin();
        hover.pointerAt(400, 20);

        expect(hover.pinned).toBe(false);
        expect(hover.at).toEqual({ x: 400, y: 20 });
    });

    test('clearing outright ends the pin as well', () => {
        // A mode change means what it says, and leaves nothing behind.
        const hover = hovering();
        hover.pin();

        hover.clear();

        expect(hover.pinned).toBe(false);
    });
});
