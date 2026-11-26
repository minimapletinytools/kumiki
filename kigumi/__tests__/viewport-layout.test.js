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
