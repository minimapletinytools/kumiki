const { SelectionStore, choosePickAction } = require('../webview/selection-store');

describe('timber selection', () => {
    test('single selection replaces the previous one', () => {
        const store = new SelectionStore();
        store.selectTimber('A');
        store.selectTimber('B');

        expect(store.getSelectedTimbers()).toEqual(['B']);
        expect(store.isTimberSelected('A')).toBe(false);
    });

    test('additive selection keeps what was already selected', () => {
        const store = new SelectionStore();
        store.selectTimber('A');
        store.selectTimber('B', true);

        expect(new Set(store.getSelectedTimbers())).toEqual(new Set(['A', 'B']));
    });

    test('toggle adds and removes', () => {
        const store = new SelectionStore();
        store.toggleTimber('A');
        expect(store.isTimberSelected('A')).toBe(true);

        store.toggleTimber('A');
        expect(store.isTimberSelected('A')).toBe(false);
    });

    test('deselecting a timber that was not selected emits nothing', () => {
        const store = new SelectionStore();
        const listener = jest.fn();
        store.onSelectionChanged(listener);

        store.deselectTimber('A');
        expect(listener).not.toHaveBeenCalled();
    });
});

describe('csg focus', () => {
    const focus = (over) => Object.assign({
        timberKey: 'A',
        path: ['mortise_and_tenon'],
        featureLabel: null,
        cutIndex: 0,
        context: { section: 'timbers' },
    }, over);

    test('focusing pulls the timber into the selection', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focus());

        expect(store.isTimberSelected('A')).toBe(true);
        expect(store.csgFocus.path).toEqual(['mortise_and_tenon']);
    });

    test('focusing narrows the selection to the timber drilled into', () => {
        // The canvas highlights the drilled timber and ghosts the rest, so
        // leaving the others selected made the trees disagree with it.
        const store = new SelectionStore();
        store.selectTimber('A');
        store.selectTimber('B', true);

        store.setCsgFocus(focus({ timberKey: 'B' }));

        expect(store.getSelectedTimbers()).toEqual(['B']);
        expect(store.csgFocus.timberKey).toBe('B');
    });

    test('drilling into another timber moves the selection to it', () => {
        const store = new SelectionStore();
        store.selectTimber('A');

        store.setCsgFocus(focus({ timberKey: 'B' }));

        expect(store.getSelectedTimbers()).toEqual(['B']);
    });

    test('only one node is focused at a time', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focus());
        store.setCsgFocus(focus({ path: ['mortise_and_tenon', 'tenon'] }));

        expect(store.csgFocus.path).toEqual(['mortise_and_tenon', 'tenon']);
    });

    test('it remembers which section the focus lives in', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focus({ context: { section: 'joints', jointId: '9', cutIndex: 1 } }));

        expect(store.csgFocus.context).toEqual({ section: 'joints', jointId: '9', cutIndex: 1 });
    });

    test('defaults to the timber section when no context is given', () => {
        const store = new SelectionStore();
        store.setCsgFocus({ timberKey: 'A', path: [] });

        expect(store.csgFocus.context).toEqual({ section: 'timbers' });
        expect(store.csgFocus.cutIndex).toBeNull();
    });

    test('a feature label rides along with the focus', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focus({ featureLabel: 'front' }));

        expect(store.csgFocus.featureLabel).toBe('front');
    });

    test('focusing emits, and unsubscribing stops it', () => {
        const store = new SelectionStore();
        const listener = jest.fn();
        const unsubscribe = store.onSelectionChanged(listener);

        store.setCsgFocus(focus());
        expect(listener).toHaveBeenCalledWith(
            expect.objectContaining({ type: 'csg-focus' }),
        );

        unsubscribe();
        store.clearCsgFocus();
        expect(listener).toHaveBeenCalledTimes(1);
    });

    test('clearing when there is nothing focused emits nothing', () => {
        const store = new SelectionStore();
        const listener = jest.fn();
        store.onSelectionChanged(listener);

        store.clearCsgFocus();
        expect(listener).not.toHaveBeenCalled();
    });
});

describe('focus follows the timber it points at', () => {
    const focusA = { timberKey: 'A', path: ['x'], cutIndex: 0, context: { section: 'timbers' } };

    test('deselecting the focused timber drops the focus', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focusA);
        store.deselectTimber('A');

        expect(store.csgFocus).toBeNull();
    });

    // There is no "deselect a different timber while focused" case any more:
    // selecting that other timber is what drops the focus.

    test('replacing the selection outright drops the focus', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focusA);
        store.selectTimber('B');

        expect(store.csgFocus).toBeNull();
        expect(store.getSelectedTimbers()).toEqual(['B']);
    });

    test('shift-adding a timber drops the focus', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focusA);

        store.selectTimber('B', true);

        expect(store.csgFocus).toBeNull();
        expect(new Set(store.getSelectedTimbers())).toEqual(new Set(['A', 'B']));
    });

    test('a tag that widens the selection drops the focus', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focusA);

        store.selectTimbers(['B', 'C'], true);

        expect(store.csgFocus).toBeNull();
    });

    test('a joint that widens the selection drops the focus', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focusA);

        store.selectJoint('j1', ['B', 'C'], true);

        expect(store.csgFocus).toBeNull();
    });

    test('re-adding the focused timber alone keeps the focus', () => {
        // The rule is about the selection widening, not about additive calls.
        const store = new SelectionStore();
        store.setCsgFocus(focusA);

        store.selectTimber('A', true);

        expect(store.csgFocus).not.toBeNull();
        expect(store.getSelectedTimbers()).toEqual(['A']);
    });

    test('a measurement focus survives a wider selection', () => {
        // It is not about one timber, so the invariant does not apply to it.
        const store = new SelectionStore();
        store.selectTimber('A');
        store.setMeasurementFocus({ viewportId: 'v1', measureKey: 'm1' });

        store.selectTimber('B', true);

        expect(store.measurementFocus).not.toBeNull();
    });

    test('clearing the timber selection drops the focus', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focusA);
        store.clearTimberSelection();

        expect(store.csgFocus).toBeNull();
        expect(store.getSelectedTimbers()).toEqual([]);
    });
});

describe('joints', () => {
    test('selecting a joint selects the timbers it touches', () => {
        const store = new SelectionStore();
        store.selectJoint('9', ['A', 'B']);

        expect(new Set(store.getSelectedTimbers())).toEqual(new Set(['A', 'B']));
    });

    test('selecting a joint replaces the previous selection by default', () => {
        const store = new SelectionStore();
        store.selectTimber('Z');
        store.selectJoint('9', ['A']);

        expect(store.getSelectedTimbers()).toEqual(['A']);
    });

    test('additive joint selection keeps what was there', () => {
        const store = new SelectionStore();
        store.selectTimber('Z');
        store.selectJoint('9', ['A'], true);

        expect(new Set(store.getSelectedTimbers())).toEqual(new Set(['Z', 'A']));
    });

    test('it announces the joint so the viewer can highlight its members', () => {
        const store = new SelectionStore();
        const listener = jest.fn();
        store.onSelectionChanged(listener);

        store.selectJoint('9', ['A', 'B']);
        expect(listener).toHaveBeenCalledWith({
            type: 'joint-selected', jointId: '9', timberKeys: ['A', 'B'],
        });
    });
});

describe('hasSelection', () => {
    test('is false when nothing is selected', () => {
        expect(new SelectionStore().hasSelection()).toBe(false);
    });

    test('counts timbers and csg focus alike', () => {
        const store = new SelectionStore();
        store.selectTimber('A');
        expect(store.hasSelection()).toBe(true);

        store.clearTimberSelection();
        expect(store.hasSelection()).toBe(false);
    });

    test('clearAll empties everything at once', () => {
        const store = new SelectionStore();
        store.selectTimber('A');
        store.setCsgFocus({ timberKey: 'A', path: [] });

        store.clearAll();
        expect(store.hasSelection()).toBe(false);
    });

    test('clearAll on an empty store emits nothing', () => {
        const store = new SelectionStore();
        const listener = jest.fn();
        store.onSelectionChanged(listener);

        store.clearAll();
        expect(listener).not.toHaveBeenCalled();
    });
});

describe('selectTimbers', () => {
    test('a batch is one event, not one per timber', () => {
        // Clicking a tag that covers forty members should not make every
        // listener re-render forty times.
        const store = new SelectionStore();
        const events = [];
        store.onSelectionChanged((event) => events.push(event));

        store.selectTimbers(['A', 'B', 'C']);

        expect(store.getSelectedTimbers()).toEqual(['A', 'B', 'C']);
        expect(events).toEqual([{ type: 'timbers-selected', timberNames: ['A', 'B', 'C'] }]);
    });

    test('a plain batch replaces the selection', () => {
        const store = new SelectionStore();
        store.selectTimber('Z');
        store.selectTimbers(['A', 'B']);
        expect(store.getSelectedTimbers()).toEqual(['A', 'B']);
    });

    test('an additive batch keeps what was selected', () => {
        const store = new SelectionStore();
        store.selectTimber('Z');
        store.selectTimbers(['A', 'Z'], true);
        expect(store.getSelectedTimbers()).toEqual(['Z', 'A']);
    });

    test('a batch replacing the selection drops the CSG focus with it', () => {
        const store = new SelectionStore();
        store.setCsgFocus({ timberKey: 'Z', path: ['cut'] });
        store.selectTimbers(['A']);
        expect(store.csgFocus).toBeNull();
    });
});

describe('choosePickAction', () => {
    const hit = (memberKey) => ({ memberKey, hit: { memberKey } });

    test('clicking empty space clears', () => {
        expect(choosePickAction({ hits: [], selectedTimbers: ['A'] }))
            .toEqual({ action: 'clear' });
    });

    test('clicking an unselected timber selects it', () => {
        const decision = choosePickAction({ hits: [hit('B')], selectedTimbers: ['A'] });
        expect(decision.action).toBe('select');
        expect(decision.memberKey).toBe('B');
    });

    test('clicking a selected timber drills into its CSG', () => {
        const decision = choosePickAction({ hits: [hit('A')], selectedTimbers: ['A'] });
        expect(decision.action).toBe('csg');
        expect(decision.memberKey).toBe('A');
    });

    test('a selected timber wins the ray even when something occludes it', () => {
        // The whole point of the rule: an unselected neighbour in front must
        // not steal a click while you are inspecting the timber behind it.
        const decision = choosePickAction({
            hits: [hit('B'), hit('A')],
            selectedTimbers: ['A'],
        });
        expect(decision).toMatchObject({ action: 'csg', memberKey: 'A' });
    });

    test('the nearest selected timber wins when several are on the ray', () => {
        const decision = choosePickAction({
            hits: [hit('C'), hit('A'), hit('B')],
            selectedTimbers: ['A', 'B'],
        });
        expect(decision.memberKey).toBe('A');
    });

    test('drilling works with several timbers selected', () => {
        const decision = choosePickAction({
            hits: [hit('B')],
            selectedTimbers: ['A', 'B', 'C'],
        });
        expect(decision.action).toBe('csg');
    });

    test('a ray missing every selected timber selects the frontmost hit', () => {
        const decision = choosePickAction({
            hits: [hit('C'), hit('D')],
            selectedTimbers: ['A', 'B'],
        });
        expect(decision).toMatchObject({ action: 'select', memberKey: 'C' });
    });

    test('shift acts on the frontmost hit, not the selected one behind it', () => {
        const decision = choosePickAction({
            hits: [hit('B'), hit('A')],
            selectedTimbers: ['A'],
            shiftKey: true,
        });
        expect(decision).toMatchObject({ action: 'toggle', memberKey: 'B' });
    });

    test('accepts a Set of selected timbers as well as an array', () => {
        const decision = choosePickAction({
            hits: [hit('A')],
            selectedTimbers: new Set(['A']),
        });
        expect(decision.action).toBe('csg');
    });

    test('with nothing selected every click selects', () => {
        expect(choosePickAction({ hits: [hit('A')], selectedTimbers: [] }).action)
            .toBe('select');
    });
});

describe('focusing a measurement', () => {
    // A third thing to look at, which must not be confused with the timbers a
    // command would act on.
    function store() {
        return new SelectionStore();
    }

    test('it becomes the focus', () => {
        const selection = store();
        selection.setMeasurementFocus({ viewportId: 'front', measureKey: 'a|b' });

        expect(selection.measurementFocus.viewportId).toBe('front');
        expect(selection.isMeasurementFocused('front', 'a|b')).toBe(true);
    });

    test('it is not a CSG focus, and cannot be mistaken for one', () => {
        // The trees, the info pane and the highlighting all ask csgFocus and
        // mean "the node being looked at".
        const selection = store();
        selection.setMeasurementFocus({ viewportId: 'front', measureKey: 'a|b' });

        expect(selection.csgFocus).toBeNull();
    });

    test('looking at a measurement leaves the timber selection alone', () => {
        // Otherwise clicking a dimension to read it would quietly change what
        // the draw button would draw.
        const selection = store();
        selection.selectTimber('post#0');
        selection.selectTimber('beam#0', true);

        selection.setMeasurementFocus({ viewportId: 'front', measureKey: 'a|b' });

        expect(selection.getSelectedTimbers()).toEqual(['post#0', 'beam#0']);
    });

    test('only one thing is ever being looked at', () => {
        // Not a rule two fields have to remember: there is one field.
        const selection = store();
        selection.setCsgFocus({ timberKey: 'post#0', path: ['cut'] });
        expect(selection.csgFocus).not.toBeNull();

        selection.setMeasurementFocus({ viewportId: 'front', measureKey: 'a|b' });

        expect(selection.csgFocus).toBeNull();
        expect(selection.measurementFocus).not.toBeNull();
    });

    test('and looking at a node again stops looking at the measurement', () => {
        const selection = store();
        selection.setMeasurementFocus({ viewportId: 'front', measureKey: 'a|b' });

        selection.setCsgFocus({ timberKey: 'post#0', path: ['cut'] });

        expect(selection.measurementFocus).toBeNull();
        expect(selection.csgFocus).not.toBeNull();
    });

    test('clearing everything clears it too', () => {
        const selection = store();
        selection.setMeasurementFocus({ viewportId: 'front', measureKey: 'a|b' });

        selection.clearAll();

        expect(selection.measurementFocus).toBeNull();
        expect(selection.hasSelection()).toBe(false);
    });

    test('a measurement in another viewport is a different measurement', () => {
        const selection = store();
        selection.setMeasurementFocus({ viewportId: 'front', measureKey: 'a|b' });

        expect(selection.isMeasurementFocused('right', 'a|b')).toBe(false);
    });
});

const { SELECTION_MODES } = require('../webview/selection-store');

describe('a drawing has no timber selection', () => {
    // Picking a timber is something you do in the model. Refused in the store
    // rather than checked by each of the several callers that offer it, one of
    // which would eventually forget.
    const inDrawing = () => {
        const store = new SelectionStore();
        store.setMode(SELECTION_MODES.DRAWING);
        return store;
    };

    test('selecting a timber does nothing', () => {
        const store = inDrawing();

        store.selectTimber('A');

        expect(store.getSelectedTimbers()).toEqual([]);
    });

    test('nor does toggling, selecting several, or selecting a joint', () => {
        const store = inDrawing();

        store.toggleTimber('A');
        store.selectTimbers(['B', 'C']);
        store.selectJoint('j1', ['D']);

        expect(store.getSelectedTimbers()).toEqual([]);
    });

    test('but focusing a feature still narrows to its timber', () => {
        // The invariant is left alone: it is what the canvas draws by, and a
        // feature belongs to a timber in a drawing as much as in the model.
        const store = inDrawing();

        store.setCsgFocus({ timberKey: 'A', path: ['cut'] });

        expect(store.getSelectedTimbers()).toEqual(['A']);
        expect(store.csgFocus.timberKey).toBe('A');
    });

    test('changing mode drops what the other mode held', () => {
        const store = new SelectionStore();
        store.selectTimber('A');
        store.setCsgFocus({ timberKey: 'A', path: [] });

        store.setMode(SELECTION_MODES.DRAWING);

        expect(store.getSelectedTimbers()).toEqual([]);
        expect(store.csgFocus).toBeNull();
    });

    test('setting the mode it is already in changes nothing', () => {
        const store = new SelectionStore();
        store.selectTimber('A');

        expect(store.setMode(SELECTION_MODES.MODEL)).toBe(false);
        expect(store.getSelectedTimbers()).toEqual(['A']);
    });
});

describe('picking a feature in a drawing', () => {
    const hits = [
        { memberKey: 'front', hit: { point: {} } },
        { memberKey: 'behind', hit: { point: {} } },
    ];

    test('goes straight to the feature, with nothing selected', () => {
        // In the model this would select the timber and take a second click to
        // drill in. A drawing has no selection to drill in from.
        const decision = choosePickAction({
            hits, selectedTimbers: [], shiftKey: false, inDrawing: true,
        });

        expect(decision.action).toBe('csg');
        expect(decision.memberKey).toBe('front');
    });

    test('and shift does not toggle a selection that does not exist', () => {
        const decision = choosePickAction({
            hits, selectedTimbers: [], shiftKey: true, inDrawing: true,
        });

        expect(decision.action).toBe('csg');
    });

    test('while the model still wants a timber selected first', () => {
        const decision = choosePickAction({
            hits, selectedTimbers: [], shiftKey: false,
        });

        expect(decision.action).toBe('select');
    });

    test('a click on nothing still clears', () => {
        expect(choosePickAction({ hits: [], selectedTimbers: [], inDrawing: true }).action)
            .toBe('clear');
    });
});

describe('measurements picked out to delete together', () => {
    const one = { viewportId: 'front', measureKey: 'a|b' };
    const other = { viewportId: 'front', measureKey: 'c|d' };
    const elsewhere = { viewportId: 'top', measureKey: 'a|b' };

    test('looking at one picks out exactly it', () => {
        const store = new SelectionStore();

        store.setMeasurementFocus(one);

        expect(store.getMarkedMeasurements()).toEqual([one]);
    });

    test('looking at another replaces what was picked out', () => {
        // Several at once can only be deleted; everything else is about one.
        const store = new SelectionStore();
        store.setMeasurementFocus(one);

        store.setMeasurementFocus(other);

        expect(store.getMarkedMeasurements()).toEqual([other]);
    });

    test('adding one keeps the others and moves the focus', () => {
        const store = new SelectionStore();
        store.setMeasurementFocus(one);

        store.toggleMeasurementMark(other);

        expect(store.getMarkedMeasurements()).toEqual([one, other]);
        expect(store.measurementFocus.measureKey).toBe('c|d');
    });

    test('the same key in another viewport is another measurement', () => {
        const store = new SelectionStore();
        store.setMeasurementFocus(one);

        store.toggleMeasurementMark(elsewhere);

        expect(store.getMarkedMeasurements()).toHaveLength(2);
        expect(store.isMeasurementMarked('top', 'a|b')).toBe(true);
    });

    test('taking the focused one back out leaves nothing focused', () => {
        const store = new SelectionStore();
        store.setMeasurementFocus(one);

        store.toggleMeasurementMark(one);

        expect(store.getMarkedMeasurements()).toEqual([]);
        expect(store.measurementFocus).toBeNull();
    });

    test('looking at a feature instead puts the measurements down', () => {
        const store = new SelectionStore();
        store.setMeasurementFocus(one);
        store.toggleMeasurementMark(other);

        store.setCsgFocus({ timberKey: 'A', path: [] });

        expect(store.getMarkedMeasurements()).toEqual([]);
    });

    test('and so does clearing everything', () => {
        const store = new SelectionStore();
        store.setMeasurementFocus(one);

        store.clearAll();

        expect(store.getMarkedMeasurements()).toEqual([]);
    });
});

const { drawButtonKey } = require('../webview/selection-store');

describe('what the draw button says', () => {
    // Never disabled: drawing nothing means drawing the whole frame, which is a
    // reasonable thing to ask for. So it says which of the two it will do.
    test('nothing selected draws the frame', () => {
        expect(drawButtonKey(0)).toBe('viewer.selection.drawFrame');
    });

    test('one timber is singular, several are not', () => {
        expect(drawButtonKey(1)).toBe('viewer.selection.drawTimber');
        expect(drawButtonKey(4)).toBe('viewer.selection.drawTimbers');
    });

    test('a missing count reads as nothing selected', () => {
        expect(drawButtonKey(undefined)).toBe('viewer.selection.drawFrame');
    });
});
