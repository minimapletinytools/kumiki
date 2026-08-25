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

    test('focusing leaves other selected timbers alone', () => {
        // You can have several timbers selected and still drill into one.
        const store = new SelectionStore();
        store.selectTimber('A');
        store.selectTimber('B', true);

        store.setCsgFocus(focus({ timberKey: 'B' }));

        expect(new Set(store.getSelectedTimbers())).toEqual(new Set(['A', 'B']));
        expect(store.csgFocus.timberKey).toBe('B');
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

    test('deselecting a different timber leaves the focus alone', () => {
        const store = new SelectionStore();
        store.selectTimber('B');
        store.setCsgFocus(focusA);

        store.deselectTimber('B');
        expect(store.csgFocus).not.toBeNull();
    });

    test('replacing the selection outright drops the focus', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focusA);
        store.selectTimber('B');

        expect(store.csgFocus).toBeNull();
        expect(store.getSelectedTimbers()).toEqual(['B']);
    });

    test('adding a timber to the selection keeps the focus', () => {
        const store = new SelectionStore();
        store.setCsgFocus(focusA);
        store.selectTimber('B', true);

        expect(store.csgFocus).not.toBeNull();
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
