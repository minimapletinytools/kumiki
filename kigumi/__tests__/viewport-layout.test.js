const L = require('../webview/viewport-layout.js');

const PAGE = { width: 0.42, height: 0.297 };
// kumiki.drawings.layout.layout_to_wire of columns(rows(A, B, gap=0.01).taking(Share(2)), C.taking(Length(0.1)), gap=0.005).
const GRID = { roots: [{ split: { direction: 'columns', gap: 0.005, portions: [
    { share: 2, node: { split: { direction: 'rows', gap: 0.01, portions: [
        { share: 1, node: { leaf: 'A' } }, { share: 1, node: { leaf: 'B' } }] } } },
    { length: 0.1, node: { leaf: 'C' } }] }, rect: [0, 0, 1, 1], z: 0 }] };

const near = (got, want) => want.forEach((value, index) => expect(got[index]).toBeCloseTo(value, 6));
const rects = (layout) => L.resolveLayout(layout, PAGE);

test('rects come out as kumiki lays them out', () => {
    const got = rects(GRID);
    near(got.get('A'), [0, 0, 0.75, 0.483164983]);
    near(got.get('B'), [0, 0.516835017, 0.75, 0.483164983]);
    near(got.get('C'), [0.761904762, 0, 0.238095238, 1]);
});

test('a view taken out of a split of two leaves the other in its place', () => {
    const left = L.removeLeaf(GRID, 'A');
    expect(L.leafNames(left)).toEqual(['B', 'C']);
    expect(left.roots[0].split.portions[0].node).toEqual({ leaf: 'B' });
});

test('a floated view sits where it was put, in front, and the grid closes up', () => {
    const floated = L.floatLeaf(GRID, 'C', [0.5, 0.5, 0.3, 0.3]);
    expect(L.isFloating(floated, 'C')).toBe(true);
    expect(floated.roots[1].z).toBe(1);
    near(rects(floated).get('C'), [0.5, 0.5, 0.3, 0.3]);
    near(rects(floated).get('A'), [0, 0, 1, 0.483164983]);
});

test('a floating view keeps on the page', () => {
    const floated = L.floatLeaf(GRID, 'C', [0.9, 0.9, 0.3, 0.3]);
    near(rects(floated).get('C'), [0.7, 0.7, 0.3, 0.3]);
    near(rects(L.setFloatingRect(floated, 'C', [-0.2, 0.1, 0.001, 0.4])).get('C'), [0, 0.1, 0.03, 0.4]);
});

test('docked beside a view in a split that runs the same way, it shares that cell', () => {
    const docked = L.dockLeaf(GRID, 'C', 'A', 'bottom');
    expect(L.leafNames(docked)).toEqual(['A', 'C', 'B']);
    // A's share of the rows is halved between A and C.
    const got = rects(docked);
    expect(got.get('A')[3]).toBeCloseTo(got.get('C')[3], 9);
    expect(got.get('A')[3] + got.get('C')[3]).toBeCloseTo(got.get('B')[3], 9);
});

test('docked across a split, it makes a new split of the two', () => {
    const docked = L.dockLeaf(GRID, 'C', 'A', 'right');
    const row = docked.roots[0].split.portions[0].node;
    expect(row.split.direction).toBe('columns');
    expect(L.leafNames(docked)).toEqual(['A', 'C', 'B']);
});

test('a floating view docks and stops floating; one docked on a root view keeps its place on the page', () => {
    const floated = L.floatLeaf(GRID, 'C', [0.5, 0.5, 0.3, 0.3]);
    const onRoot = L.dockLeaf(floated, 'A', 'C', 'left');
    expect(onRoot.roots[1].rect).toEqual([0.5, 0.5, 0.3, 0.3]);
    near(rects(onRoot).get('A'), [0.5, 0.5, 0.15, 0.3]);
    expect(L.isFloating(L.dockLeaf(floated, 'C', 'B', 'top'), 'C')).toBe(false);
});

test('splitting makes a copy beside it that says what it copies', () => {
    const { layout, made } = L.splitLeaf(GRID, 'C', 'rows');
    expect(made).toBe('C 2');
    expect(L.leafNames(layout)).toEqual(['A', 'B', 'C', 'C 2']);
    const again = L.splitLeaf(layout, 'C 2', 'columns');
    expect(again.made).toBe('C 3');
    expect(JSON.stringify(again.layout)).toContain('"leaf":"C 3","copyOf":"C"');
});

test('a divider moves the space between two shares, and sets a length', () => {
    const [between] = L.dividers(GRID, PAGE).filter((one) => one.direction === 'rows');
    const moved = L.moveDivider(GRID, between.path, between.index, 0.25, PAGE);
    expect(rects(moved).get('A')[3]).toBeCloseTo(0.25, 6);
    const [edge] = L.dividers(GRID, PAGE).filter((one) => one.direction === 'columns');
    const wider = L.moveDivider(GRID, edge.path, edge.index, 0.5, PAGE);
    expect(rects(wider).get('A')[2]).toBeCloseTo(0.5, 6);
    expect(wider.roots[0].split.portions[1].length).toBeCloseTo(0.42 * (1 - 0.005 / 0.42 - 0.5), 6);
});

test('restacking puts a floating view in front or behind', () => {
    const floated = L.floatLeaf(GRID, 'C', [0.5, 0.5, 0.3, 0.3]);
    expect(L.restack(floated, 'C', false).roots[1].z).toBe(-1);
    expect(L.restack(floated, 'A', true).roots[0].z).toBe(2);
});

test('edits leave the tree they were given alone', () => {
    const before = JSON.stringify(GRID);
    L.floatLeaf(GRID, 'A', [0, 0, 0.5, 0.5]);
    L.dockLeaf(GRID, 'C', 'A', 'left');
    L.splitLeaf(GRID, 'B', 'columns');
    expect(JSON.stringify(GRID)).toBe(before);
});

test('a camera goes on a view, moves with it, and comes off', () => {
    const aimed = L.setLeafCamera(GRID, 'B', { look: [0, 1, 0], up: [0, 0, 1] });
    expect(L.leafCamera(aimed, 'B')).toEqual({ look: [0, 1, 0], up: [0, 0, 1] });
    expect(L.leafCamera(GRID, 'B')).toBeNull();
    const docked = L.dockLeaf(aimed, 'B', 'C', 'right');
    expect(L.leafCamera(docked, 'B')).toEqual({ look: [0, 1, 0], up: [0, 0, 1] });
    expect(L.leafCamera(L.setLeafCamera(aimed, 'B', null), 'B')).toBeNull();
});

test('the views a change moves are the ones whose rects changed', () => {
    const moved = L.moveDivider(GRID, [0, 0], 0, 0.3, PAGE);
    expect(L.movedLeaves(GRID, moved, PAGE).sort()).toEqual(['A', 'B']);
    expect(L.movedLeaves(GRID, GRID, PAGE)).toEqual([]);
});

test('a drop on an edge goes one of up to three ways, nearest the edge first', () => {
    const levels = (target, side) => L.dropChoices(GRID, target, side, PAGE).map((one) => one.level);
    // A's bottom is only A's, and A is in a list running down: one more in it, or a split of A.
    expect(levels('A', 'bottom')).toEqual(['sibling', 'split']);
    // A's right is its column's too, and C is beside that column.
    expect(levels('A', 'right')).toEqual(['outer', 'split']);
    // B's bottom is the page's too: a new row across the whole page as well.
    expect(levels('B', 'bottom')).toEqual(['outer', 'sibling', 'split']);

    const [outer, sibling, split] = L.dropChoices(GRID, 'B', 'bottom', PAGE).map((one) => one.rect);
    expect(outer[2]).toBeCloseTo(1, 6);  // across the page
    expect(sibling[3]).toBeLessThan(split[3] * 1.5);  // a third of the column, against half of B
    expect(sibling[3]).toBeGreaterThan(split[3] * 1.2);
});

test('docked one more in a list, it is as big as the view it went beside', () => {
    const floated = L.floatLeaf(GRID, 'C', [0.5, 0.5, 0.3, 0.3]);
    const sibling = rects(L.dockLeaf(floated, 'C', 'A', 'bottom', 'sibling', PAGE));
    expect(sibling.get('C')[3]).toBeCloseTo(sibling.get('A')[3], 6);
    expect(sibling.get('C')[3]).toBeCloseTo(sibling.get('B')[3], 6);
    const split = rects(L.dockLeaf(floated, 'C', 'A', 'bottom', 'split', PAGE));
    expect(split.get('C')[3]).toBeCloseTo(split.get('A')[3], 6);
    expect(split.get('B')[3]).toBeGreaterThan(split.get('A')[3] * 1.5);
    const outer = rects(L.dockLeaf(floated, 'C', 'A', 'right', 'outer', PAGE));
    expect(outer.get('C')[3]).toBeCloseTo(1, 6);
});
