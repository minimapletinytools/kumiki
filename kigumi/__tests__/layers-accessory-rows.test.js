// Same minimal fake document as layers-tag-rows: layers-panel builds rows with
// plain DOM calls and this project has no jsdom.
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
const { LayerStateStore } = require('../webview/layer-state-store.js');
const { LayersPanel } = require('../webview/layers-panel.js');

const PEG = 'accessory:Peg#0';

function panelWithOneJoint() {
    const panel = new LayersPanel(new SelectionStore(), {});
    panel.layerStateStore = new LayerStateStore();
    panel.hierarchy = {
        timbers: [{ key: 'beam#0', name: 'beam' }],
        joints: [{
            id: '0',
            name: 'mortise and tenon',
            timberKeys: [],
            accessoryKeys: [PEG],
        }],
    };
    panel.expandedNodes = new Set(['joint:0']);
    return panel;
}

function buttons(row) {
    const icons = row.children.filter((child) => child.className.includes('lp-icons'));
    return icons.flatMap((group) => group.children);
}

function accessoryRow(panel) {
    return panel._buildJointRows().find((row) => row.dataset.memberKey === PEG);
}

describe('accessory rows in the tree', () => {
    test('an accessory carries its member key, so it is a member like any other', () => {
        const row = accessoryRow(panelWithOneJoint());
        expect(row).toBeDefined();
        expect(row.dataset.memberKey).toBe(PEG);
    });

    test('it gets the lock and hide buttons', () => {
        // Regression: the buttons hang off memberKey, and an accessory row had
        // none -- so a peg could be selected and never hidden.
        const actions = buttons(accessoryRow(panelWithOneJoint()))
            .map((button) => button.dataset.action);
        expect(actions).toEqual(expect.arrayContaining(['lock', 'hide']));
    });

    test('hiding one records it under the accessory member key', () => {
        const panel = panelWithOneJoint();
        const hide = buttons(accessoryRow(panel))
            .find((button) => button.dataset.action === 'hide');

        expect(panel.layerStateStore.isHidden(PEG)).toBe(false);
        hide.dispatch('click', { stopPropagation() {} });
        expect(panel.layerStateStore.isHidden(PEG)).toBe(true);
    });

    test('locking one stops the row selecting it', () => {
        const panel = panelWithOneJoint();
        const row = accessoryRow(panel);
        const lock = buttons(row).find((button) => button.dataset.action === 'lock');

        lock.dispatch('click', { stopPropagation() {} });
        row.dispatch('click', { shiftKey: false });
        expect(panel.selectionManager.getSelectedTimbers()).not.toContain(PEG);
    });
});

describe('extra accessory rows in the tree', () => {
    const EXTRA = 'accessory:extra#0';

    function extraRow(panel) {
        panel.extraAccessories = [{ key: EXTRA, name: 'A leg template' }];
        return panel._buildExtraAccessoryRows()[0];
    }

    test('one is a member row named as the tool named it', () => {
        const row = extraRow(panelWithOneJoint());
        expect(row.dataset.memberKey).toBe(EXTRA);
        expect(row.children.some((child) => child.textContent === 'A leg template')).toBe(true);
        expect(buttons(row).map((button) => button.dataset.action)).toEqual(expect.arrayContaining(['lock', 'hide']));
    });

    test('a click selects it, and a right click asks for the member menu, which offers to delete it', () => {
        const panel = panelWithOneJoint();
        const row = extraRow(panel);
        row.dispatch('click', { shiftKey: false });
        expect(panel.selectionManager.getSelectedTimbers()).toContain(EXTRA);

        let asked = null;
        row.dispatchEvent = (event) => { asked = event.detail; };
        global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
        row.dispatch('contextmenu', { preventDefault() {}, stopPropagation() {}, clientX: 1, clientY: 2 });
        expect(asked).toEqual({ memberKey: EXTRA, clientX: 1, clientY: 2 });
    });
});
