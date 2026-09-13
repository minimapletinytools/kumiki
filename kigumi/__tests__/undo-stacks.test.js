const { UndoStacks, stackKey } = require('../webview/undo-stacks.js');

const entry = (label) => ({ label, redo: { command: 'do', label }, undo: { command: 'undo', label } });

describe('a stack per drawing per frame', () => {
    // Not one stack for the viewer. Undoing in one drawing after working in
    // another takes back a change you cannot see.
    test('what is done in one drawing is not undoable in another', () => {
        const stacks = new UndoStacks();
        stacks.push('house.py', 'plan', entry('made'));

        expect(stacks.canUndo('house.py', 'plan')).toBe(true);
        expect(stacks.canUndo('house.py', 'elevation')).toBe(false);
    });

    test('nor in the same drawing of another frame', () => {
        // Drawing ids repeat between files; they are separate pieces of work.
        const stacks = new UndoStacks();
        stacks.push('house.py', 'plan', entry('made'));

        expect(stacks.canUndo('shed.py', 'plan')).toBe(false);
    });

    test('the 3D measurements are a drawing like any other', () => {
        const stacks = new UndoStacks();
        stacks.push('house.py', 'three-d-measurements', entry('made'));

        expect(stacks.canUndo('house.py', 'three-d-measurements')).toBe(true);
        expect(stacks.canUndo('house.py', 'plan')).toBe(false);
    });

    test('an untouched drawing has nothing to undo and does not throw', () => {
        const stacks = new UndoStacks();

        expect(stacks.canUndo('house.py', 'never-opened')).toBe(false);
        expect(stacks.undo('house.py', 'never-opened')).toBeNull();
    });
});

describe('undo and redo', () => {
    test('undo hands back the last thing done, most recent first', () => {
        const stacks = new UndoStacks();
        stacks.push('f', 'd', entry('first'));
        stacks.push('f', 'd', entry('second'));

        expect(stacks.undo('f', 'd').label).toBe('second');
        expect(stacks.undo('f', 'd').label).toBe('first');
        expect(stacks.undo('f', 'd')).toBeNull();
    });

    test('redo puts them back in the order they were taken off', () => {
        const stacks = new UndoStacks();
        stacks.push('f', 'd', entry('first'));
        stacks.push('f', 'd', entry('second'));
        stacks.undo('f', 'd');
        stacks.undo('f', 'd');

        expect(stacks.redo('f', 'd').label).toBe('first');
        expect(stacks.redo('f', 'd').label).toBe('second');
        expect(stacks.redo('f', 'd')).toBeNull();
    });

    test('doing something new makes the undone future unreachable', () => {
        const stacks = new UndoStacks();
        stacks.push('f', 'd', entry('first'));
        stacks.undo('f', 'd');

        stacks.push('f', 'd', entry('instead'));

        expect(stacks.canRedo('f', 'd')).toBe(false);
    });

    test('an entry carries both directions, and neither is looked inside', () => {
        const stacks = new UndoStacks();
        stacks.push('f', 'd', entry('dragged'));

        const undone = stacks.undo('f', 'd');

        expect(undone.undo).toEqual({ command: 'undo', label: 'dragged' });
        expect(undone.redo).toEqual({ command: 'do', label: 'dragged' });
    });
});

describe('while a measurement is being made', () => {
    // There is nothing on the stack for a half-made one -- it is not written
    // until confirmed -- so undo would reach past it to something else.
    test('undo and redo are refused', () => {
        const stacks = new UndoStacks();
        stacks.push('f', 'd', entry('made'));
        stacks.undo('f', 'd');
        stacks.suspend(true);

        expect(stacks.canUndo('f', 'd')).toBe(false);
        expect(stacks.canRedo('f', 'd')).toBe(false);
        expect(stacks.undo('f', 'd')).toBeNull();
        expect(stacks.redo('f', 'd')).toBeNull();
    });

    test('and available again once it is confirmed or cancelled', () => {
        const stacks = new UndoStacks();
        stacks.push('f', 'd', entry('made'));
        stacks.suspend(true);

        stacks.suspend(false);

        expect(stacks.canUndo('f', 'd')).toBe(true);
    });

    test('suspending does not throw anything away', () => {
        const stacks = new UndoStacks();
        stacks.push('f', 'd', entry('made'));
        stacks.suspend(true);

        expect(stacks.depth('f', 'd').done).toBe(1);
    });
});

describe('purging', () => {
    // What a stack holds names features and viewports the reloaded frame may
    // not have. An undo that cannot be trusted to apply is worse than one that
    // is not offered.
    test('a frame takes all its drawings with it', () => {
        const stacks = new UndoStacks();
        stacks.push('house.py', 'plan', entry('a'));
        stacks.push('house.py', 'elevation', entry('b'));
        stacks.push('shed.py', 'plan', entry('c'));

        stacks.purgeFrame('house.py');

        expect(stacks.canUndo('house.py', 'plan')).toBe(false);
        expect(stacks.canUndo('house.py', 'elevation')).toBe(false);
        expect(stacks.canUndo('shed.py', 'plan')).toBe(true);
    });

    test('a frame whose name starts the same is left alone', () => {
        const stacks = new UndoStacks();
        stacks.push('house.py', 'plan', entry('a'));
        stacks.push('house2.py', 'plan', entry('b'));

        stacks.purgeFrame('house.py');

        expect(stacks.canUndo('house2.py', 'plan')).toBe(true);
    });

    test('purging everything also lets undo work again', () => {
        const stacks = new UndoStacks();
        stacks.push('f', 'd', entry('a'));
        stacks.suspend(true);

        stacks.purgeAll();

        expect(stacks.suspended).toBe(false);
        expect(stacks.canUndo('f', 'd')).toBe(false);
    });
});

describe('depth', () => {
    test('says what each direction has in it', () => {
        const stacks = new UndoStacks();
        stacks.push('f', 'd', entry('a'));
        stacks.push('f', 'd', entry('b'));
        stacks.undo('f', 'd');

        expect(stacks.depth('f', 'd')).toEqual({ done: 1, undone: 1 });
    });
});

describe('stackKey', () => {
    test('a frame and a drawing make one key', () => {
        expect(stackKey('f', 'd')).toBe(stackKey('f', 'd'));
        expect(stackKey('f', 'd')).not.toBe(stackKey('d', 'f'));
    });

    test('the separator is one no id contains, so keys cannot collide', () => {
        // 'a' + 'bc' and 'ab' + 'c' are different drawings of different frames.
        expect(stackKey('a', 'bc')).not.toBe(stackKey('ab', 'c'));
    });
});
