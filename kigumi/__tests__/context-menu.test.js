const { ContextMenu, menuPosition } = require('../webview/context-menu.js');

const items = [
    { id: 'stl', label: 'Export STL' },
    { id: 'step', label: 'Export STEP' },
];

describe('what a right-click offers', () => {
    test('nothing is open to begin with', () => {
        const menu = new ContextMenu();

        expect(menu.isOpen).toBe(false);
        expect(menu.state).toBeNull();
    });

    test('opening says where it is and what it says', () => {
        const menu = new ContextMenu();

        menu.open({ x: 10, y: 20, title: 'Front Post', items });

        expect(menu.state).toEqual({ x: 10, y: 20, title: 'Front Post', kind: null, items });
    });

    test('an empty menu is not a menu', () => {
        // Saying so here means no caller has to remember to check first.
        const menu = new ContextMenu();

        expect(menu.open({ x: 0, y: 0, items: [] })).toBe(false);
        expect(menu.isOpen).toBe(false);
    });

    test('items without an id are not offered', () => {
        const menu = new ContextMenu();

        menu.open({ x: 0, y: 0, items: [{ label: 'nameless' }, items[0]] });

        expect(menu.state.items).toEqual([items[0]]);
    });

    test('opening again replaces what was open', () => {
        // Two menus at once is not a state worth being able to reach.
        const menu = new ContextMenu();
        menu.open({ x: 0, y: 0, title: 'first', items });

        menu.open({ x: 5, y: 5, title: 'second', items });

        expect(menu.state.title).toBe('second');
    });
});

describe('choosing', () => {
    test('calls back with what was picked', () => {
        const menu = new ContextMenu();
        const picked = [];
        menu.open({ x: 0, y: 0, items, onChoose: (id) => picked.push(id) });

        expect(menu.choose('step')).toBe(true);
        expect(picked).toEqual(['step']);
    });

    test('and closes, because a menu that stays open is one nobody dismissed', () => {
        const menu = new ContextMenu();
        menu.open({ x: 0, y: 0, items });

        menu.choose('stl');

        expect(menu.isOpen).toBe(false);
    });

    test('a disabled item does nothing, and does not even close', () => {
        // It is offered so that what is NOT available is visible rather than
        // missing. Choosing one has not used the menu.
        const menu = new ContextMenu();
        const picked = [];
        menu.open({
            x: 0, y: 0, onChoose: (id) => picked.push(id),
            items: [{ id: 'stl', label: 'Export STL', disabled: true }],
        });

        expect(menu.choose('stl')).toBe(false);
        expect(picked).toEqual([]);
        expect(menu.isOpen).toBe(true);
    });

    test('an id that is not there does nothing', () => {
        const menu = new ContextMenu();
        menu.open({ x: 0, y: 0, items });

        expect(menu.choose('nonsense')).toBe(false);
        expect(menu.isOpen).toBe(true);
    });

    test('choosing with nothing open does nothing', () => {
        expect(new ContextMenu().choose('stl')).toBe(false);
    });

    test('closing says whether anything was open', () => {
        const menu = new ContextMenu();

        expect(menu.close()).toBe(false);
        menu.open({ x: 0, y: 0, items });
        expect(menu.close()).toBe(true);
    });
});

describe('where it sits', () => {
    const room = { width: 800, height: 600 };
    const size = { width: 160, height: 80 };

    test('at the pointer when there is room', () => {
        expect(menuPosition({ x: 100, y: 100 }, size, room)).toEqual({ x: 100, y: 100 });
    });

    test('flipped back from the right edge rather than clipped at it', () => {
        const at = menuPosition({ x: 790, y: 100 }, size, room);

        expect(at.x + size.width).toBeLessThanOrEqual(room.width);
    });

    test('and from the bottom, where the last item would be lost', () => {
        const at = menuPosition({ x: 100, y: 595 }, size, room);

        expect(at.y + size.height).toBeLessThanOrEqual(room.height);
    });

    test('a menu too big for the room is still reachable', () => {
        // Hard against the near edge rather than off the far one: cramped beats
        // unreachable.
        const at = menuPosition({ x: 700, y: 500 }, { width: 900, height: 700 }, room);

        expect(at.x).toBeGreaterThanOrEqual(0);
        expect(at.y).toBeGreaterThanOrEqual(0);
    });
});


// Which menu this is, for a caller that renders one of them differently: the
// feature menu marks the row the 3D view is lighting, which exporting a member
// has no notion of.
describe('which menu is open', () => {
    test('a menu that did not say is no kind in particular', () => {
        const menu = new ContextMenu();

        menu.open({ x: 0, y: 0, items });

        expect(menu.state.kind).toBeNull();
    });

    test('and one that did says so', () => {
        const menu = new ContextMenu();

        menu.open({ x: 0, y: 0, items, kind: 'feature' });

        expect(menu.state.kind).toBe('feature');
    });
});

// Shift and ctrl mean the same thing on a menu row as on the thing it stands
// for, so whatever chose is handed on untouched.
describe('what chose', () => {
    test('is passed to onChoose', () => {
        const menu = new ContextMenu();
        const seen = [];
        menu.open({ x: 0, y: 0, items, onChoose: (id, item, event) => seen.push(event) });

        menu.choose('stl', { shiftKey: true });

        expect(seen).toEqual([{ shiftKey: true }]);
    });

    test('and is null when nothing was given', () => {
        const menu = new ContextMenu();
        const seen = [];
        menu.open({ x: 0, y: 0, items, onChoose: (id, item, event) => seen.push(event) });

        menu.choose('stl');

        expect(seen).toEqual([null]);
    });
});
