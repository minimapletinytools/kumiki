// layers-panel builds its rows with plain DOM calls and this project has no
// jsdom, so this is the smallest document _makeTagRow needs: enough to record
// classes, data attributes, text and click handlers.
function fakeElement() {
    const handlers = {};
    const element = {
        className: '',
        textContent: '',
        title: '',
        dataset: {},
        children: [],
        classList: {
            names: new Set(),
            add(...names) { names.forEach((name) => this.names.add(name)); },
            remove(...names) { names.forEach((name) => this.names.delete(name)); },
            toggle(name, on) { return on ? this.add(name) : this.remove(name); },
            contains(name) { return this.names.has(name); },
        },
        appendChild(child) { element.children.push(child); return child; },
        addEventListener(type, handler) { (handlers[type] = handlers[type] || []).push(handler); },
        dispatch(type, event) { (handlers[type] || []).forEach((handler) => handler(event)); },
    };
    return element;
}

global.document = { createElement: () => fakeElement() };

require('../webview/tags.js');
require('../webview/tag-index.js');
const { SelectionStore } = require('../webview/selection-store.js');
const { LayersPanel } = require('../webview/layers-panel.js');

const BENT1 = { id: 'slice:bent1', kind: 'slice', name: 'bent1', memberKeys: ['A', 'B'] };

function panelWithSelection() {
    const selection = new SelectionStore();
    return { selection, panel: new LayersPanel(selection, {}) };
}

function childrenByClass(row, className) {
    return row.children.filter((child) => child.className.includes(className));
}

describe('tag rows', () => {
    test('the chip shows the tag name, not the tag object', () => {
        const { panel } = panelWithSelection();
        const chip = childrenByClass(panel._makeTagRow(BENT1), 'tag-chip')[0];
        expect(chip.textContent).toBe('bent1');
        expect(chip.dataset.tagKind).toBe('slice');
    });

    test('the row counts the members wearing the tag', () => {
        const { panel } = panelWithSelection();
        const count = childrenByClass(panel._makeTagRow(BENT1), 'lp-tag-count')[0];
        expect(count.textContent).toBe('2');
    });

    test('clicking a tag selects everything wearing it', () => {
        const { panel, selection } = panelWithSelection();
        selection.selectTimber('Z');

        panel._makeTagRow(BENT1).dispatch('click', { shiftKey: false });

        expect(selection.getSelectedTimbers()).toEqual(['A', 'B']);
    });

    test('shift-clicking a tag adds it to the selection', () => {
        const { panel, selection } = panelWithSelection();
        selection.selectTimber('Z');

        panel._makeTagRow(BENT1).dispatch('click', { shiftKey: true });

        expect(selection.getSelectedTimbers()).toEqual(['Z', 'A', 'B']);
    });
});
