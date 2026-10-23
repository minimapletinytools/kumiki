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
    const { overlayHeader } = globalScope.KigumiOverlay
        || (typeof require === 'function' ? require('./overlay-header') : {});

    const ORIGIN_MARKS = {
        code: '○',
        overridden: '◐',
        file: '●',
        deleted: '○',
    };

    class DrawingPanel {
        constructor(selectionManager) {
            this.selectionManager = selectionManager;
            this.el = null;
            this.drawing = null;
            this.viewports = [];
            this.members = [];
            this.expanded = new Set(['section:viewports', 'section:members']);
            this.collapsedViewports = new Set();
            this.collapsed = false;
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
        setDrawing({ drawing, viewports, members, slice }) {
            const nextDrawingId = (drawing && (drawing.id || drawing.name)) || null;
            const currentDrawingId = (this.drawing && (this.drawing.id || this.drawing.name)) || null;
            if (nextDrawingId !== currentDrawingId) {
                this.collapsedViewports.clear();
            }
            this.drawing = drawing || null;
            this.viewports = viewports || [];
            this.members = members || [];
            /** What the members are a slice of, or null for all of them. */
            this.slice = slice || null;
            this._render();
        }

        _emit(type, detail) {
            if (this.el) {
                this.el.dispatchEvent(new CustomEvent(type, {
                    detail, bubbles: true, composed: true,
                }));
            }
        }

        _isViewportExpanded(viewportId) {
            if (this.collapsedViewports.has(viewportId)) {
                // If a measurement in this viewport is currently focused, reveal it.
                if (this.selectionManager) {
                    const viewport = this.viewports.find((v) => v.id === viewportId);
                    const hasFocused = (viewport && viewport.measurements || []).some((m) =>
                        this.selectionManager.isMeasurementFocused(viewportId, m.key));
                    if (hasFocused) {
                        this.collapsedViewports.delete(viewportId);
                        return true;
                    }
                }
                return false;
            }
            return true;
        }

        _toggle(nodeId) {
            if (nodeId.startsWith('viewport:')) {
                const viewportId = nodeId.slice('viewport:'.length);
                if (this.collapsedViewports.has(viewportId)) {
                    this.collapsedViewports.delete(viewportId);
                } else {
                    this.collapsedViewports.add(viewportId);
                }
            } else {
                if (this.expanded.has(nodeId)) {
                    this.expanded.delete(nodeId);
                } else {
                    this.expanded.add(nodeId);
                }
            }
            this._render();
        }

        toggleViewport(viewportId) {
            this._toggle('viewport:' + viewportId);
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
            if (this.collapsed) {
                return;
            }
            this.el.appendChild(this._section(
                'viewports', t('viewer.drawing.viewports'), () => this._viewportRows(),
            ));
            this.el.appendChild(this._section(
                'members', this._membersTitle(), () => this._memberRows(),
            ));
        }

        /**
         * "members (everything)", or "members (the piece it is of)".
         *
         * The list alone cannot say which: a drawing of every timber and a
         * drawing that happens to name every timber look the same in it.
         */
        _membersTitle() {
            return membersTitle(this.slice, t);
        }

        _header() {
            const header = overlayHeader(t('viewer.drawing.measurements', { name: this.drawing.name || this.drawing.id }), {
                collapsed: this.collapsed,
                onToggle: () => {
                    this.collapsed = !this.collapsed;
                    this._render();
                },
                doc: document,
            });
            header.classList.add('dp-header');

            const origin = document.createElement('span');
            origin.className = 'dp-origin';
            origin.textContent = ORIGIN_MARKS[this.drawing.origin] || ORIGIN_MARKS.file;
            header.insertBefore(origin, header.lastChild);

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
            save.addEventListener('click', (event) => {
                event.stopPropagation();
                this._emit('kigumi-save-drawings', {});
            });
            header.appendChild(save);

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
                const nodeId = 'viewport:' + viewport.id;
                const measurements = viewport.measurements || [];
                const hasChildren = measurements.length > 0;
                const open = this._isViewportExpanded(viewport.id);

                const head = document.createElement('div');
                head.className = 'dp-row dp-viewport' + (hasChildren ? '' : ' dp-viewport-empty');

                const chevron = document.createElement('span');
                chevron.className = 'dp-chev' + (hasChildren ? '' : ' dp-leaf');
                chevron.textContent = hasChildren ? (open ? '▾' : '▸') : '';
                head.appendChild(chevron);

                const label = document.createElement('span');
                label.className = 'dp-viewport-label';
                label.textContent = viewport.id;
                head.appendChild(label);

                if (hasChildren) {
                    head.role = 'button';
                    head.ariaExpanded = open ? 'true' : 'false';
                    head.addEventListener('click', () => this._toggle(nodeId));
                }
                rows.push(head);

                if (open) {
                    for (const entry of measurements) {
                        rows.push(this._measurementRow(viewport, entry));
                    }
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
            const broken = globalScope.KigumiMeasurements.isBroken(entry.status);
            const deleted = globalScope.KigumiMeasurements.isDeleted(entry);
            row.className = 'dp-row dp-measurement'
                + (entry.status.drawable || deleted ? '' : ' dp-unavailable')
                + (broken ? ' dp-broken' : '')
                + (deleted ? ' dp-deleted' : '')
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
            if (deleted) {
                value.textContent = t('viewer.drawing.deleted');
                value.classList.add('dp-reason');
            } else if (entry.status.drawable) {
                value.textContent = entry.formatted;
            } else {
                value.textContent = t('viewer.drawing.refused.' + entry.status.reason);
                value.classList.add('dp-reason');
            }
            row.appendChild(value);

            row.addEventListener('click', () => this._emit('kigumi-focus-measurement', {
                viewportId: viewport.id, measureKey: entry.key,
            }));
            row.addEventListener('contextmenu', (event) => {
                event.preventDefault();
                this._emit('kigumi-measurement-contextmenu', {
                    viewportId: viewport.id, measureKey: entry.key,
                    clientX: event.clientX, clientY: event.clientY,
                });
            });
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
                row.addEventListener('contextmenu', (event) => {
                    event.preventDefault();
                    this._emit('kigumi-member-contextmenu', {
                        memberKey: member.key, clientX: event.clientX, clientY: event.clientY,
                    });
                });
                return row;
            });
        }
    }

    /**
     * "members (everything)", or "members (the piece it is of)".
     *
     * The list alone cannot say which: a drawing of every timber and a drawing
     * that happens to name every timber look identical in it.
     */
    function membersTitle(slice, translate) {
        const of = slice || translate('viewer.drawing.members.everything');
        return `${translate('viewer.drawing.members')} (${of})`;
    }

    const KigumiDrawingPanel = { DrawingPanel, ORIGIN_MARKS, membersTitle };
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = KigumiDrawingPanel;
    }
    globalScope.KigumiDrawingPanel = KigumiDrawingPanel;
})(typeof window !== 'undefined' ? window : globalThis);
