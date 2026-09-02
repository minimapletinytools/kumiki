(function (globalScope) {
    'use strict';
    // The tree for the drawing you are in: what it is, its viewports and the
    // measurements under them, and the members it is about.
    //
    // Content only. It takes what to show and emits what was asked for, and
    // knows nothing about where it is mounted -- whether that is a panel of its
    // own for drawing mode, the layers rail, or both at once is a decision made
    // outside it and changeable in a line.

    // Resolved once, the way every other panel here does it. viewer.html loads
    // i18n.js ahead of this file, which makes that ordering a stated dependency
    // rather than a lucky one.
    const _i18nStrings = (globalScope.__KIGUMI_INITIAL_PAYLOAD__
        && globalScope.__KIGUMI_INITIAL_PAYLOAD__.i18n
        && globalScope.__KIGUMI_INITIAL_PAYLOAD__.i18n.strings) || {};
    const t = globalScope.KigumiI18n
        ? globalScope.KigumiI18n.createTranslator(_i18nStrings)
        : (key) => key;

    // Where a drawing came from, as one mark. The same scheme the drawings
    // section uses, and for the same reason: the fill reads as how much of it
    // comes from the file.
    const ORIGIN_MARKS = {
        code: '○',
        overridden: '◐',
        file: '●',
    };

    class DrawingPanel {
        constructor(selectionManager) {
            this.selectionManager = selectionManager;
            this.el = null;
            this.drawing = null;
            this.viewports = [];
            this.members = [];
            this.expanded = new Set(['section:viewports', 'section:members']);
        }

        mount(container) {
            this.el = document.createElement('div');
            this.el.id = 'drawing-panel';
            container.appendChild(this.el);
            this._render();
        }

        unmount() {
            if (this.el && this.el.parentNode) {
                this.el.parentNode.removeChild(this.el);
            }
            this.el = null;
        }

        /**
         * What to show: the drawing, its viewports with their measurements
         * already judged, and the members it is about.
         *
         * `viewports` carries each measurement's status rather than working it
         * out here, because whether one can be drawn depends on how things lie
         * to that viewport's camera, which only the viewer knows.
         */
        setDrawing({ drawing, viewports, members }) {
            this.drawing = drawing || null;
            this.viewports = viewports || [];
            this.members = members || [];
            this._render();
        }

        _emit(type, detail) {
            if (this.el) {
                this.el.dispatchEvent(new CustomEvent(type, {
                    detail, bubbles: true, composed: true,
                }));
            }
        }

        _toggle(nodeId) {
            if (this.expanded.has(nodeId)) {
                this.expanded.delete(nodeId);
            } else {
                this.expanded.add(nodeId);
            }
            this._render();
        }

        _render() {
            if (!this.el) {
                return;
            }
            this.el.innerHTML = '';
            if (!this.drawing) {
                return;
            }
            this.el.appendChild(this._header());
            this.el.appendChild(this._section(
                'viewports', t('viewer.drawing.viewports'), () => this._viewportRows(),
            ));
            this.el.appendChild(this._section(
                'members', t('viewer.drawing.members'), () => this._memberRows(),
            ));
        }

        _header() {
            const header = document.createElement('div');
            header.className = 'dp-header';

            const origin = document.createElement('span');
            origin.className = 'dp-origin';
            origin.textContent = ORIGIN_MARKS[this.drawing.origin] || ORIGIN_MARKS.file;
            header.appendChild(origin);

            const name = document.createElement('span');
            name.className = 'dp-name';
            name.textContent = this.drawing.name || this.drawing.id;
            header.appendChild(name);

            if (this.drawing.dirty) {
                const unsaved = document.createElement('span');
                unsaved.className = 'dp-unsaved';
                unsaved.textContent = '•';
                unsaved.title = t('viewer.layers.drawing.unsaved');
                header.appendChild(unsaved);
            }

            const save = document.createElement('button');
            save.type = 'button';
            save.className = 'dp-action';
            save.textContent = t('viewer.layers.drawing.save');
            save.title = t('viewer.layers.drawing.save.title');
            save.addEventListener('click', () => this._emit('kigumi-save-drawings', {}));
            header.appendChild(save);

            const close = document.createElement('button');
            close.type = 'button';
            close.className = 'dp-action';
            close.textContent = t('viewer.selection.leaveDrawing');
            close.title = t('viewer.selection.leaveDrawing.title');
            close.addEventListener('click', () => this._emit('kigumi-close-drawing', {}));
            header.appendChild(close);

            return header;
        }

        _section(id, title, buildRows) {
            const nodeId = 'section:' + id;
            const open = this.expanded.has(nodeId);

            const section = document.createElement('div');
            section.className = 'dp-section';

            const head = document.createElement('div');
            head.className = 'dp-section-header';
            const chevron = document.createElement('span');
            chevron.className = 'dp-chev';
            chevron.textContent = open ? '▾' : '▸';
            head.appendChild(chevron);
            const label = document.createElement('span');
            label.textContent = ' ' + title;
            head.appendChild(label);
            head.addEventListener('click', () => this._toggle(nodeId));
            section.appendChild(head);

            if (open) {
                for (const row of buildRows()) {
                    section.appendChild(row);
                }
            }
            return section;
        }

        _viewportRows() {
            const rows = [];
            for (const viewport of this.viewports) {
                const head = document.createElement('div');
                head.className = 'dp-row dp-viewport';
                head.textContent = viewport.id;
                rows.push(head);
                for (const entry of viewport.measurements || []) {
                    rows.push(this._measurementRow(viewport, entry));
                }
            }
            return rows;
        }

        /**
         * One measurement: what it is between, and what it comes to.
         *
         * Or, when it cannot be drawn, which of the four it is. A measurement
         * that simply does not appear leaves no way to tell a broken reference
         * from one that is merely wrong for the view being looked at.
         */
        _measurementRow(viewport, entry) {
            const row = document.createElement('div');
            const focused = this.selectionManager
                && this.selectionManager.isMeasurementFocused(viewport.id, entry.key);
            row.className = 'dp-row dp-measurement'
                + (entry.status.drawable ? '' : ' dp-unavailable')
                + (focused ? ' dp-focused' : '');

            const origin = document.createElement('span');
            origin.className = 'dp-origin';
            origin.textContent = ORIGIN_MARKS[entry.origin] || ORIGIN_MARKS.file;
            row.appendChild(origin);

            const between = document.createElement('span');
            between.className = 'dp-between';
            between.textContent = entry.between;
            between.title = entry.describes;
            row.appendChild(between);

            const value = document.createElement('span');
            value.className = 'dp-value';
            if (entry.status.drawable) {
                value.textContent = entry.formatted;
            } else {
                value.textContent = t('viewer.drawing.refused.' + entry.status.reason);
                value.classList.add('dp-reason');
            }
            row.appendChild(value);

            row.addEventListener('click', () => this._emit('kigumi-focus-measurement', {
                viewportId: viewport.id, measureKey: entry.key,
            }));
            return row;
        }

        _memberRows() {
            return this.members.map((member) => {
                const row = document.createElement('div');
                row.className = 'dp-row dp-member'
                    + (this.selectionManager && this.selectionManager.isTimberSelected(member.key)
                        ? ' dp-selected' : '');
                row.textContent = member.name;
                row.addEventListener('click', (event) => this._emit('kigumi-select-drawing-member', {
                    memberKey: member.key, addToSelection: Boolean(event.shiftKey),
                }));
                return row;
            });
        }
    }

    const KigumiDrawingPanel = { DrawingPanel, ORIGIN_MARKS };
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiDrawingPanel;
    }
    globalScope.KigumiDrawingPanel = KigumiDrawingPanel;
})(typeof window !== 'undefined' ? window : globalThis);
