// A file that shows several frames lists each as a section of its own, holding its
// drawings, timbers and joints. One frame keeps the plain sections.

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
const { KigumiLayersView } = require('../webview/layers-panel.js');

const TIMBERS = [
    { key: 'post', name: 'post' },
    { key: 'sill', name: 'sill' },
    { key: 'roof', name: 'roof' },
];
const JOINTS = [
    { id: '1', name: 'post to sill', timberKeys: ['post', 'sill'], cuttings: [], accessoryKeys: [] },
    { id: '2', name: 'roof trim', timberKeys: ['roof'], cuttings: [], accessoryKeys: [] },
];
const FRAMES = [
    { name: 'Pavilion', timberKeys: ['post', 'sill'], jointIds: ['1'] },
    { name: 'Cottage', timberKeys: ['roof'], jointIds: ['2'] },
];

function openPanel(frames) {
    const panel = new LayersPanel(new SelectionStore(), new LayerStateStore());
    panel.collapsed = false;
    panel.drawingsEnabled = true;
    panel.mount(fakeElement());
    panel.setHierarchy({ timbers: TIMBERS, joints: JOINTS, frames });
    return panel;
}

// The header's title, without its chevron. Outside the viewer t() answers with the key.
const titleOf = (section) => section.children[0].children[1].textContent.trim().replace('viewer.layers.section.', '');
const topSections = (panel) => panel._treeEl.children.map(titleOf);
const HOUSE = '\u{1F3E0} ';
const frameSection = (panel, name) => panel._treeEl.children.find((section) => titleOf(section) === HOUSE + name);
const headerOf = (panel, title) => panel._treeEl.children.find((section) => titleOf(section) === title).children[0];
const rowIds = (node, type) => fakeQuery(node, 'lp-row-' + type).map((row) => row.dataset.nodeId);

function fakeQuery(node, className) {
    const found = [];
    const walk = (at) => {
        for (const child of at.children) {
            if (String(child.className).split(/\s+/).includes(className)) found.push(child);
            walk(child);
        }
    };
    walk(node);
    return found;
}

describe('a file with several frames', () => {
    test('one frame keeps the plain sections', () => {
        expect(topSections(openPanel(null))).toEqual(['drawings', 'tags', 'timbers', 'joints', 'measurements']);
    });

    test('each frame is a section of its own', () => {
        expect(topSections(openPanel(FRAMES)))
            .toEqual(['drawings', 'tags', HOUSE + 'Pavilion', HOUSE + 'Cottage', 'measurements']);
    });

    test('a frame holds only its own timbers and joints', () => {
        const panel = openPanel(FRAMES);
        expect(rowIds(frameSection(panel, 'Pavilion'), 'timber')).toEqual(['timber:post', 'timber:sill']);
        expect(rowIds(frameSection(panel, 'Pavilion'), 'joint')).toEqual(['joint:1']);
        expect(rowIds(frameSection(panel, 'Cottage'), 'timber')).toEqual(['timber:roof']);
    });

    test('a drawing goes under the frame all its timbers are in', () => {
        const panel = openPanel(FRAMES);
        // Closed to start with, like the drawings section at the top.
        panel.expandedNodes.add('section:' + panel._frameSectionId(0) + ':drawings');
        panel.expandedNodes.add('section:drawings');
        panel.setDrawings([
            { id: 'posts', name: 'posts', members: ['post', 'sill'] },
            { id: 'both', name: 'both', members: ['post', 'roof'] },
            // A member no frame lists (an accessory, say) does not make it span frames.
            { id: 'post-and-peg', name: 'post and peg', members: ['post', 'peg'] },
        ], null, { inDrawing: false });

        expect(rowIds(frameSection(panel, 'Pavilion'), 'drawing')).toEqual(['drawing:posts', 'drawing:post-and-peg']);
        // One spanning frames is the file's, so it is listed at the top.
        expect(topSections(panel)[0]).toBe('drawings');
        expect(rowIds(panel._treeEl.children[0], 'drawing')).toEqual(['drawing:both']);
    });

    test('with every drawing in a frame the drawings section at the top is empty', () => {
        const panel = openPanel(FRAMES);
        panel.setDrawings([{ id: 'posts', name: 'posts', members: ['post'] }], null, { inDrawing: false });
        expect(headerOf(panel, 'drawings').className).toContain('lp-section-empty');
    });

    test('a frame closed by hand stays closed when the frame is rebuilt', () => {
        const panel = openPanel(FRAMES);
        panel.expandedNodes.delete('section:' + panel._frameSectionId(0));
        panel.setHierarchy({ timbers: TIMBERS, joints: JOINTS, frames: FRAMES });
        expect(rowIds(frameSection(panel, 'Pavilion'), 'timber')).toEqual([]);
    });
});

describe('an empty section', () => {
    test('is greyed, has no chevron and does not open', () => {
        const panel = openPanel(null);
        const tags = headerOf(panel, 'tags');
        expect(tags.className).toContain('lp-section-empty');
        expect(tags.children[0].textContent).toBe('');
        tags.dispatch('click');
        expect(panel._treeEl.children.find((section) => titleOf(section) === 'tags').children.length).toBe(1);
    });

    test('one with something in it opens as before', () => {
        const timbers = headerOf(openPanel(null), 'timbers');
        expect(timbers.className).not.toContain('lp-section-empty');
        expect(timbers.children[0].textContent).toBe('\u25be');
    });
});

describe('the runner’s frames', () => {
    const convert = (payload) => Object.create(KigumiLayersView.prototype)._convertRunnerPayload(payload);
    const RUNNER_TIMBERS = [
        { kumikiEphemeralId: 1, memberKey: 'T1', name: 'post' },
        { kumikiEphemeralId: 2, memberKey: 'T2', name: 'roof' },
    ];

    test('are joined to member keys and joint ids', () => {
        const { frames } = convert({
            timbers: RUNNER_TIMBERS,
            frames: [
                { name: 'Pavilion', timberKumikiEphemeralIds: [1], jointKumikiEphemeralIds: [9] },
                { name: 'Cottage', timberKumikiEphemeralIds: [2], jointKumikiEphemeralIds: [] },
            ],
        });
        expect(frames).toEqual([
            { name: 'Pavilion', timberKeys: ['T1'], jointIds: ['9'] },
            { name: 'Cottage', timberKeys: ['T2'], jointIds: [] },
        ]);
    });

    test('are nothing when there is only the one', () => {
        expect(convert({ timbers: RUNNER_TIMBERS, frames: null }).frames).toBeNull();
    });
});
