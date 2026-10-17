function fakeElement() {
    const handlers = {};
    let _innerHTML = '';
    const element = {
        className: '',
        _textContent: '',
        get textContent() {
            if (this.children.length > 0) {
                return this.children.map((c) => c.textContent).join('');
            }
            return this._textContent;
        },
        set textContent(val) {
            this._textContent = val;
        },
        get innerHTML() {
            return _innerHTML;
        },
        set innerHTML(val) {
            _innerHTML = val;
            if (val === '') {
                this.children = [];
            }
        },
        title: '',
        role: '',
        ariaExpanded: '',
        children: [],
        classList: {
            names: new Set(),
            add(...names) {
                names.forEach((name) => this.names.add(name));
                element.className = Array.from(this.names).join(' ');
            },
            remove(...names) {
                names.forEach((name) => this.names.delete(name));
                element.className = Array.from(this.names).join(' ');
            },
            toggle(name, on) { return on ? this.add(name) : this.remove(name); },
            contains(name) { return this.names.has(name); },
        },
        appendChild(child) {
            element.children.push(child);
            return child;
        },
        insertBefore(child, reference) {
            const index = element.children.indexOf(reference);
            if (index !== -1) {
                element.children.splice(index, 0, child);
            } else {
                element.children.push(child);
            }
            return child;
        },
        removeChild(child) {
            const index = element.children.indexOf(child);
            if (index !== -1) {
                element.children.splice(index, 1);
            }
            return child;
        },
        addEventListener(type, handler) {
            (handlers[type] = handlers[type] || []).push(handler);
        },
        dispatch(type, event) {
            (handlers[type] || []).forEach((handler) => handler(event));
        },
        handles(type) {
            return Boolean(handlers[type] && handlers[type].length > 0);
        },
    };
    return element;
}

global.document = {
    createElement: () => fakeElement(),
};

const KigumiMeasurements = require('../webview/measurements.js');
global.KigumiMeasurements = KigumiMeasurements;
const { DrawingPanel } = require('../webview/drawing-panel.js');

function createSampleDrawing(viewports) {
    return {
        drawing: { id: 'sheet-1', name: 'Sheet 1', origin: 'file' },
        viewports: viewports || [
            {
                id: 'front',
                measurements: [
                    { key: 'm1', origin: 'code', between: 'a / b', describes: 'a to b', formatted: '100mm', status: { drawable: true } },
                    { key: 'm2', origin: 'file', between: 'c / d', describes: 'c to d', formatted: '50mm', status: { drawable: true } },
                ],
            },
            {
                id: 'side',
                measurements: [
                    { key: 'm3', origin: 'code', between: 'e / f', describes: 'e to f', formatted: '80mm', status: { drawable: true } },
                ],
            },
            {
                id: 'top',
                measurements: [],
            },
        ],
        members: [],
    };
}

describe('DrawingPanel collapsible viewports', () => {
    test('viewports and their measurements are expanded by default', () => {
        const panel = new DrawingPanel(null);
        panel.mount(fakeElement());
        panel.setDrawing(createSampleDrawing());

        const viewportSection = panel.el.children.find((child) =>
            child.className === 'dp-section' && child.children[0].textContent.includes('viewports')
        );
        expect(viewportSection).toBeDefined();

        // Check front viewport header (children[1])
        const frontHead = viewportSection.children[1];
        expect(frontHead.className).toContain('dp-viewport');
        expect(frontHead.children[0].className).toContain('dp-chev');
        expect(frontHead.children[0].textContent).toBe('▾');
        expect(frontHead.children[1].textContent).toBe('front');
        expect(frontHead.ariaExpanded).toBe('true');

        // Measurement rows under front viewport
        const frontM1 = viewportSection.children[2];
        const frontM2 = viewportSection.children[3];
        expect(frontM1.className).toContain('dp-measurement');
        expect(frontM2.className).toContain('dp-measurement');

        // Check side viewport header (children[4])
        const sideHead = viewportSection.children[4];
        expect(sideHead.children[0].textContent).toBe('▾');
        expect(sideHead.children[1].textContent).toBe('side');
        expect(sideHead.ariaExpanded).toBe('true');

        // Measurement row under side viewport
        const sideM1 = viewportSection.children[5];
        expect(sideM1.className).toContain('dp-measurement');

        // Check empty viewport (children[6])
        const topHead = viewportSection.children[6];
        expect(topHead.className).toContain('dp-viewport-empty');
        expect(topHead.children[0].className).toContain('dp-leaf');
        expect(topHead.children[0].textContent).toBe('');
        expect(topHead.handles('click')).toBe(false);
    });

    test('clicking a viewport header collapses its measurements', () => {
        const panel = new DrawingPanel(null);
        panel.mount(fakeElement());
        panel.setDrawing(createSampleDrawing());

        let viewportSection = panel.el.children.find((child) =>
            child.className === 'dp-section' && child.children[0].textContent.includes('viewports')
        );
        const frontHead = viewportSection.children[1];

        // Click front header to collapse
        frontHead.dispatch('click', {});

        viewportSection = panel.el.children.find((child) =>
            child.className === 'dp-section' && child.children[0].textContent.includes('viewports')
        );

        // Front viewport is now collapsed
        const collapsedFront = viewportSection.children[1];
        expect(collapsedFront.children[0].textContent).toBe('▸');
        expect(collapsedFront.ariaExpanded).toBe('false');

        // Next item is side viewport, because front's measurements are omitted
        const nextItem = viewportSection.children[2];
        expect(nextItem.className).toContain('dp-viewport');
        expect(nextItem.children[1].textContent).toBe('side');
        // Side measurements are still visible
        expect(viewportSection.children[3].className).toContain('dp-measurement');
    });

    test('clicking a collapsed viewport header re-expands it', () => {
        const panel = new DrawingPanel(null);
        panel.mount(fakeElement());
        panel.setDrawing(createSampleDrawing());

        // Collapse front
        let viewportSection = panel.el.children.find((child) =>
            child.className === 'dp-section' && child.children[0].textContent.includes('viewports')
        );
        viewportSection.children[1].dispatch('click', {});

        // Re-expand front
        viewportSection = panel.el.children.find((child) =>
            child.className === 'dp-section' && child.children[0].textContent.includes('viewports')
        );
        viewportSection.children[1].dispatch('click', {});

        viewportSection = panel.el.children.find((child) =>
            child.className === 'dp-section' && child.children[0].textContent.includes('viewports')
        );
        const expandedFront = viewportSection.children[1];
        expect(expandedFront.children[0].textContent).toBe('▾');
        expect(expandedFront.ariaExpanded).toBe('true');
        expect(viewportSection.children[2].className).toContain('dp-measurement');
        expect(viewportSection.children[3].className).toContain('dp-measurement');
    });

    test('switching drawings resets collapsed viewports', () => {
        const panel = new DrawingPanel(null);
        panel.mount(fakeElement());
        panel.setDrawing(createSampleDrawing());

        // Collapse front
        panel.toggleViewport('front');
        expect(panel._isViewportExpanded('front')).toBe(false);

        // Switch to a new drawing
        const newDrawing = createSampleDrawing();
        newDrawing.drawing = { id: 'sheet-2', name: 'Sheet 2' };
        panel.setDrawing(newDrawing);

        expect(panel._isViewportExpanded('front')).toBe(true);
    });

    test('auto-expands collapsed viewport when a measurement in it is focused', () => {
        const selectionManager = {
            focused: { viewportId: 'front', measureKey: 'm1' },
            isMeasurementFocused(viewportId, key) {
                return this.focused && this.focused.viewportId === viewportId && this.focused.measureKey === key;
            },
        };

        const panel = new DrawingPanel(selectionManager);
        panel.mount(fakeElement());
        selectionManager.focused = null;
        panel.setDrawing(createSampleDrawing());

        // Explicitly collapse front
        panel.toggleViewport('front');
        expect(panel.collapsedViewports.has('front')).toBe(true);
        expect(panel._isViewportExpanded('front')).toBe(false);

        // Focus measurement m1 in front viewport
        selectionManager.focused = { viewportId: 'front', measureKey: 'm1' };

        // Querying or re-rendering reveals the viewport
        expect(panel._isViewportExpanded('front')).toBe(true);
        expect(panel.collapsedViewports.has('front')).toBe(false);
    });
});
