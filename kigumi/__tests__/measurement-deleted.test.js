// A code measurement the drawings file deleted: listed greyed, never drawn, and
// put back from a right-click.

function fakeElement() {
    const handlers = {};
    const element = {
        className: '',
        textContent: '',
        title: '',
        children: [],
        classList: { add(name) { element.className += ' ' + name; } },
        appendChild(child) { element.children.push(child); return child; },
        addEventListener(type, handler) { (handlers[type] = handlers[type] || []).push(handler); },
        dispatch(type, event) { (handlers[type] || []).forEach((handler) => handler(event)); },
        handles(type) { return Boolean(handlers[type]); },
    };
    return element;
}

global.document = { createElement: () => fakeElement() };

const KigumiMeasurements = require('../webview/measurements.js');
global.KigumiMeasurements = KigumiMeasurements;
const { DrawingPanel } = require('../webview/drawing-panel.js');

const ROW = { key: 'k', between: 'a / b', describes: '', formatted: '12mm', status: { drawable: true } };

function rowFor(origin) {
    const panel = new DrawingPanel(null);
    const emitted = [];
    panel._emit = (type, detail) => emitted.push({ type, detail });
    return { row: panel._measurementRow({ id: 'front' }, { ...ROW, origin }), emitted };
}

describe('a deleted measurement', () => {
    test('is one whose origin says so', () => {
        expect(KigumiMeasurements.isDeleted({ origin: 'deleted' })).toBe(true);
        expect(KigumiMeasurements.isDeleted({ origin: 'code' })).toBe(false);
        expect(KigumiMeasurements.isDeleted(null)).toBe(false);
    });

    test('is listed greyed, saying it is deleted rather than its value', () => {
        const { row } = rowFor('deleted');
        expect(row.className).toContain('dp-deleted');
        expect(row.children[2].textContent).toBe('viewer.drawing.deleted');
    });

    test('asks for the put-back menu on a right-click', () => {
        const { row, emitted } = rowFor('deleted');
        row.dispatch('contextmenu', { preventDefault() {}, clientX: 3, clientY: 4 });
        expect(emitted).toEqual([{
            type: 'kigumi-measurement-contextmenu',
            detail: { viewportId: 'front', measureKey: 'k', clientX: 3, clientY: 4 },
        }]);
    });

    test('one that is not deleted has its value, and a menu only to copy it', () => {
        const { row } = rowFor('code');
        expect(row.className).not.toContain('dp-deleted');
        expect(row.children[2].textContent).toBe('12mm');
        expect(row.handles('contextmenu')).toBe(true);
    });
});
