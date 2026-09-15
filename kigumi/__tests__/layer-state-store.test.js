const { LayerStateStore } = require('../webview/layer-state-store.js');

// Locked, hidden and fixed, per member. `hidden` is the one with teeth: it is
// the first thing _memberAppearance checks, ahead of the selection, so a member
// hidden here is invisible whatever else is going on.

describe('what a member starts as', () => {
    test('a member nobody has touched is plain', () => {
        expect(new LayerStateStore().getState('post#0'))
            .toEqual({ locked: false, hidden: false, fixed: false });
    });

    test('and asking does not create an entry', () => {
        // pruneKeys walks what is stored; reading must not make work for it.
        const store = new LayerStateStore();
        store.getState('post#0');

        expect(store.states.size).toBe(0);
    });
});

describe('setting one flag leaves the others alone', () => {
    test.each(['locked', 'hidden', 'fixed'])('%s', (prop) => {
        const store = new LayerStateStore();
        const setter = { locked: 'setLocked', hidden: 'setHidden', fixed: 'setFixed' }[prop];
        store.setLocked('post#0', true);
        store.setHidden('post#0', true);
        store.setFixed('post#0', true);

        store[setter]('post#0', false);

        const state = store.getState('post#0');
        expect(state[prop]).toBe(false);
        for (const other of ['locked', 'hidden', 'fixed'].filter((name) => name !== prop)) {
            expect(state[other]).toBe(true);
        }
    });

    test('and only that member', () => {
        const store = new LayerStateStore();

        store.setHidden('post#0', true);

        expect(store.isHidden('girt#0')).toBe(false);
    });
});

describe('telling listeners', () => {
    test('a change is announced, with what changed', () => {
        const store = new LayerStateStore();
        const heard = [];
        store.onStateChanged((event) => heard.push(event));

        store.setHidden('post#0', true);

        expect(heard).toEqual([{
            type: 'layer-state-changed',
            key: 'post#0',
            prop: 'hidden',
            value: true,
            state: { locked: false, hidden: true, fixed: false },
        }]);
    });

    test('setting a flag to what it already is says nothing', () => {
        // Anything redrawing on this event would redraw for no reason.
        const store = new LayerStateStore();
        store.setHidden('post#0', true);
        const heard = [];
        store.onStateChanged((event) => heard.push(event));

        store.setHidden('post#0', true);

        expect(heard).toEqual([]);
    });

    test('unsubscribing stops the telling', () => {
        const store = new LayerStateStore();
        const heard = [];
        const stop = store.onStateChanged((event) => heard.push(event));

        stop();
        store.setHidden('post#0', true);

        expect(heard).toEqual([]);
    });

    test('every listener hears it', () => {
        const store = new LayerStateStore();
        const heard = [];
        store.onStateChanged(() => heard.push('one'));
        store.onStateChanged(() => heard.push('two'));

        store.setLocked('post#0', true);

        expect(heard).toEqual(['one', 'two']);
    });
});

describe('toggling', () => {
    test.each([
        ['toggleHidden', 'isHidden'],
        ['toggleLocked', 'isLocked'],
        ['toggleFixed', 'isFixed'],
    ])('%s flips it', (toggle, ask) => {
        const store = new LayerStateStore();

        store[toggle]('post#0');
        expect(store[ask]('post#0')).toBe(true);
        store[toggle]('post#0');
        expect(store[ask]('post#0')).toBe(false);
    });
});

describe('asking about the whole frame', () => {
    test('nothing hidden or locked to begin with', () => {
        const store = new LayerStateStore();

        expect(store.hasAnyHidden()).toBe(false);
        expect(store.hasAnyLocked()).toBe(false);
    });

    test('one hidden member is enough', () => {
        const store = new LayerStateStore();
        store.setHidden('post#0', true);

        expect(store.hasAnyHidden()).toBe(true);
        expect(store.hasAnyLocked()).toBe(false);
    });

    test('showAll un-hides everything and leaves locks alone', () => {
        const store = new LayerStateStore();
        store.setHidden('post#0', true);
        store.setHidden('girt#0', true);
        store.setLocked('post#0', true);

        store.showAll();

        expect(store.hasAnyHidden()).toBe(false);
        expect(store.isLocked('post#0')).toBe(true);
    });

    test('unlockAll unlocks everything and leaves hiding alone', () => {
        const store = new LayerStateStore();
        store.setLocked('post#0', true);
        store.setHidden('post#0', true);

        store.unlockAll();

        expect(store.hasAnyLocked()).toBe(false);
        expect(store.isHidden('post#0')).toBe(true);
    });
});

describe('members that are no longer there', () => {
    test('pruning forgets them', () => {
        const store = new LayerStateStore();
        store.setHidden('post#0', true);
        store.setHidden('gone#0', true);

        store.pruneKeys(['post#0']);

        expect(store.isHidden('post#0')).toBe(true);
        expect(store.isHidden('gone#0')).toBe(false);
    });

    test('a member that comes back comes back plain', () => {
        // The alternative -- remembering a hidden member across a reload that
        // dropped it -- is a timber invisible for a reason nobody can see.
        const store = new LayerStateStore();
        store.setHidden('gone#0', true);

        store.pruneKeys([]);

        expect(store.getState('gone#0'))
            .toEqual({ locked: false, hidden: false, fixed: false });
    });

    test('pruning says nothing to listeners', () => {
        // It is not an edit: it is the frame no longer having that member.
        const store = new LayerStateStore();
        store.setHidden('gone#0', true);
        const heard = [];
        store.onStateChanged((event) => heard.push(event));

        store.pruneKeys([]);

        expect(heard).toEqual([]);
    });
});
