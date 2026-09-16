// The layers tree is wiped and rebuilt on every change, and a browser resets a
// container's scrollTop when its contents go. The 3D measurements sit in the
// LAST section, so you are scrolled to the bottom when you click one -- and
// clicking one rebuilds the tree, which threw you back to the top and out of
// sight of the row you had just clicked.
//
// No jsdom in this project, so this is the smallest document the tree needs.
// What matters is that the fake resets scrollTop on a wipe the way a real
// element does; without that the test cannot see the bug.
function fakeElement() {
    const handlers = {};
    const element = {
        id: '',
        className: '',
        textContent: '',
        title: '',
        scrollTop: 0,
        revealed: 0,
        scrollIntoView() { element.revealed += 1; },
        // A cap, so a restore past the end clamps the way a real one does.
        scrollHeight: 10000,
        dataset: {},
        style: {},
        children: [],
        classList: {
            names: new Set(),
            add(...names) { names.forEach((name) => this.names.add(name)); },
            remove(...names) { names.forEach((name) => this.names.delete(name)); },
            toggle(name, on) { return on ? this.add(name) : this.remove(name); },
            contains(name) { return this.names.has(name); },
        },
        set innerHTML(value) {
            if (value !== '') throw new Error('the panel only ever clears');
            element.children.length = 0;
            // The behaviour under test: emptying a scroll container puts it
            // back at the top.
            element.scrollTop = 0;
        },
        get innerHTML() { return ''; },
        appendChild(child) { element.children.push(child); return child; },
        insertBefore(child) { element.children.unshift(child); return child; },
        removeChild(child) {
            const at = element.children.indexOf(child);
            if (at !== -1) element.children.splice(at, 1);
            return child;
        },
        get firstChild() { return element.children[0] || null; },
        addEventListener(type, handler) { (handlers[type] = handlers[type] || []).push(handler); },
        removeEventListener() {},
        dispatch(type, event) { (handlers[type] || []).forEach((handler) => handler(event)); },
        querySelector(selector) { return element.querySelectorAll(selector)[0] || null; },
        // Enough of a selector engine for what _syncHighlight asks: classes,
        // and one [data-x="y"] or [data-x$="y"] predicate.
        querySelectorAll(selector) {
            const attrs = [];
            const classPart = selector.replace(
                /\[data-([\w-]+)(\$?)="([^"]*)"\]/g,
                (whole, name, endsWith, value) => {
                    const key = name.replace(/-(\w)/g, (_, c) => c.toUpperCase());
                    attrs.push({ key, value, endsWith: endsWith === '$' });
                    return '';
                });
            const wanted = classPart.split('.').filter(Boolean);
            const matches = (node) => wanted.every(
                (name) => String(node.className).split(/\s+/).includes(name))
                && attrs.every(({ key, value, endsWith }) => {
                    const held = node.dataset[key];
                    if (held === undefined) return false;
                    return endsWith ? String(held).endsWith(value) : held === value;
                });
            const found = [];
            const walk = (node) => {
                for (const child of node.children) {
                    if (matches(child)) found.push(child);
                    walk(child);
                }
            };
            walk(element);
            return found;
        },
    };
    return element;
}

global.document = { createElement: () => fakeElement() };
global.CSS = { escape: (value) => value };

require('../webview/csg-tree-view.js');
require('../webview/tags.js');
require('../webview/tag-index.js');
const { SelectionStore } = require('../webview/selection-store.js');
const { LayerStateStore } = require('../webview/layer-state-store.js');
const { LayersPanel } = require('../webview/layers-panel.js');

const MEASUREMENTS = [{
    id: 'three-d-measurements',
    viewports: [{
        id: 'v0',
        measurements: [
            { a: { feature: 'post.front' }, b: { feature: 'post.back' } },
            { a: { feature: 'sill.top' }, b: { feature: 'sill.end' } },
        ],
    }],
}];

const TIMBERS = [
    { key: 'post', name: 'post' },
    { key: 'sill', name: 'sill' },
];

function openPanel() {
    const panel = new LayersPanel(new SelectionStore(), new LayerStateStore());
    panel.collapsed = false;
    panel.drawingsEnabled = true;
    panel.mount(fakeElement());
    panel.setHierarchy({ timbers: TIMBERS, joints: [] });
    return panel;
}

function treeOf(panel) {
    return panel._treeEl;
}

// Rows outlive a selection change but not a rebuild, so reveals are counted as
// a DELTA across the action rather than as a total.
function revealsDuring(panel, key, act) {
    const before = timberRow(panel, key).revealed;
    act();
    return timberRow(panel, key).revealed - before;
}

function timberRow(panel, key) {
    return treeOf(panel).querySelectorAll('lp-row')
        .find((row) => row.dataset.nodeId === 'timber:' + key);
}

describe('where the layers tree is scrolled to', () => {
    test('the measurements section is last, which is why this matters', () => {
        // If it ever stops being last this test still passes on its own terms,
        // but the bug it guards would be far less likely to be hit -- so the
        // ordering is asserted rather than assumed.
        const panel = openPanel();
        panel.expandedNodes.add('section:measurements');
        panel.setDrawings(MEASUREMENTS, null, { inDrawing: false });

        const sections = treeOf(panel).children.map((section) => section.children[0])
            .map((header) => header.children.map((part) => part.textContent).join(''));

        expect(sections[sections.length - 1]).toContain('measurements');
    });

    test('rebuilding the tree leaves you where you were', () => {
        const panel = openPanel();
        treeOf(panel).scrollTop = 420;

        panel._renderTree();

        expect(treeOf(panel).scrollTop).toBe(420);
    });

    test('a new set of drawings leaves you where you were', () => {
        // The path the reported bug took: clicking a measurement row makes the
        // viewer re-send the drawings, which rebuilds the panel outright.
        const panel = openPanel();
        treeOf(panel).scrollTop = 420;

        panel.setDrawings(MEASUREMENTS, null, { inDrawing: false });

        expect(treeOf(panel).scrollTop).toBe(420);
    });

    test('scrolling back to the top is remembered as well as any other place', () => {
        const panel = openPanel();
        treeOf(panel).scrollTop = 420;
        panel._renderTree();
        treeOf(panel).scrollTop = 0;

        panel._renderTree();

        expect(treeOf(panel).scrollTop).toBe(0);
    });

    test('a tree arriving for a timber leaves you where you were', () => {
        const panel = openPanel();
        treeOf(panel).scrollTop = 200;

        panel.setCsgTree('post', { tree: { id: 'root', children: [] } });

        expect(treeOf(panel).scrollTop).toBe(200);
    });
});


// The other way the tree moves under you. Marking rows selected is derived and
// may be redone as often as it likes; SCROLLING to one is an effect, and the
// rebuild was re-running it -- so every rebuild yanked you back to whatever was
// selected, wherever you had scrolled to since.
describe('revealing the selected row', () => {
    test('a newly selected timber is scrolled to', () => {
        const panel = openPanel();

        const reveals = revealsDuring(panel, 'post',
            () => panel.selectionManager.selectTimber('post'));

        expect(reveals).toBe(1);
    });

    test('a rebuild does not scroll to it again', () => {
        // The reported symptom. Clicking a measurement rebuilds the tree, and
        // the rebuild re-ran the reveal -- so the tree jumped to whatever
        // timber was selected, which sits above the measurements and so always
        // upward, and out of sight of the row just clicked.
        // Counted absolutely, not as a delta: a rebuild REPLACES the rows, so
        // the new one starts at zero and only this rebuild could have raised
        // it. A delta across a rebuild subtracts the old row's count from the
        // new row's and cancels the very thing being looked for.
        const panel = openPanel();
        panel.selectionManager.selectTimber('post');

        panel._renderTree();

        expect(timberRow(panel, 'post').revealed).toBe(0);
    });

    test('but selecting a different one is', () => {
        const panel = openPanel();
        panel.selectionManager.selectTimber('post');
        panel._renderTree();

        const reveals = revealsDuring(panel, 'sill',
            () => panel.selectionManager.selectTimber('sill'));

        expect(reveals).toBe(1);
    });

    test('and so is coming back to the first', () => {
        // What is remembered is what is revealed NOW, not everything ever shown.
        const panel = openPanel();
        panel.selectionManager.selectTimber('post');
        panel.selectionManager.selectTimber('sill');

        const reveals = revealsDuring(panel, 'post',
            () => panel.selectionManager.selectTimber('post'));

        expect(reveals).toBe(1);
    });

    test('losing the selection lets the next one be revealed again', () => {
        const panel = openPanel();
        panel.selectionManager.selectTimber('post');
        panel.selectionManager.clearTimberSelection();

        const reveals = revealsDuring(panel, 'post',
            () => panel.selectionManager.selectTimber('post'));

        expect(reveals).toBe(1);
    });
});

// revealCsg is the other caller: a 3D pick asking the list to follow. That one
// is a request rather than a repeat, and has to be honoured either way.
describe('a reveal asked for by name', () => {
    const PAYLOAD = { tree: { op: 'primitive', label: 'body', children: [] } };

    function panelShowingATree() {
        const panel = openPanel();
        panel.csgTreesByKey.set('post', PAYLOAD);
        return panel;
    }

    test('scrolls to the node', () => {
        const panel = panelShowingATree();

        panel.revealCsg({ section: 'timbers', timberKey: 'post', path: [] });

        const row = treeOf(panel).querySelectorAll('lp-row-csg')[0];
        expect(row.revealed).toBe(1);
    });

    test('scrolls again when asked for the same node twice', () => {
        // Unlike a rebuild: somebody said "show me this", and the answer to
        // saying it twice is to show it twice.
        const panel = panelShowingATree();
        panel.revealCsg({ section: 'timbers', timberKey: 'post', path: [] });

        panel.revealCsg({ section: 'timbers', timberKey: 'post', path: [] });

        const row = treeOf(panel).querySelectorAll('lp-row-csg')[0];
        expect(row.revealed).toBe(1);
    });
});
