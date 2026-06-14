(function (globalScope) {
    // LayersPanel renders a collapsible overlay tree on the left edge of the viewport.
    // It syncs bidirectionally with SelectionStore: canvas clicks highlight the
    // corresponding row, and clicking a row updates the canvas selection.
    class LayersPanel {
        constructor(selectionManager, layerStateStore) {
            this.selectionManager = selectionManager;
            this.layerStateStore = layerStateStore;
            this.hierarchy = null;
            this.collapsed = true;
            // Default: top-level sections open, individual nodes closed
            this.expandedNodes = new Set(['section:timbers', 'section:joints']);
            this.filterText = '';
            this.showTagPills = true;
            this.el = null;
            this.viewport = null;
            this._unsubSelection = null;
            this._unsubLayerState = null;
            this._onPanelWheel = this._onPanelWheel.bind(this);
        }

        mount(viewport) {
            this.viewport = viewport;
            this.el = document.createElement('div');
            this.el.id = 'layers-panel';
            this.el.addEventListener('wheel', this._onPanelWheel, { passive: false });
            viewport.insertBefore(this.el, viewport.firstChild);
            this._render();

            this._unsubSelection = this.selectionManager.onSelectionChanged(() => {
                this._syncHighlight();
            });
            this._unsubLayerState = this.layerStateStore.onStateChanged(() => {
                this._updateStateIcons();
            });
        }

        setHierarchy(hierarchy) {
            this.hierarchy = hierarchy || { timbers: [], joints: [] };
            const allKeys = [
                ...this.hierarchy.timbers.map(t => t.key),
                ...(this.hierarchy.joints || []).flatMap(j => [...(j.timberKeys || []), ...(j.accessoryKeys || [])]),
            ];
            this.layerStateStore.pruneKeys(allKeys);
            this._render();
        }

        setShowTagPills(show) {
            this.showTagPills = !!show;
            this._renderTree();
        }

        destroy() {
            if (this._unsubSelection) this._unsubSelection();
            if (this._unsubLayerState) this._unsubLayerState();
            if (this.el) {
                this.el.removeEventListener('wheel', this._onPanelWheel);
            }
            if (this.el && this.el.parentNode) this.el.parentNode.removeChild(this.el);
            this.el = null;
        }

        _onPanelWheel(event) {
            if (!this.el || this.collapsed) {
                return;
            }
            const tree = this.el.querySelector('.lp-tree');
            if (!tree) {
                return;
            }

            // Keep wheel interaction local to layers so viewport wheel-zoom doesn't fire.
            tree.scrollTop += event.deltaY;
            event.preventDefault();
            event.stopPropagation();
        }

        // ------------------------------------------------------------------
        // Filter helpers
        // ------------------------------------------------------------------

        _matchesFilter(name, tags) {
            const q = this.filterText.trim().toLowerCase();
            if (!q) return true;
            if (name && name.toLowerCase().includes(q)) return true;
            if (tags && tags.some(t => t.toLowerCase().includes(q))) return true;
            return false;
        }

        // ------------------------------------------------------------------
        // Rendering
        // ------------------------------------------------------------------

        _render() {
            if (!this.el) return;
            this.el.innerHTML = '';
            this.el.className = 'lp-panel ' + (this.collapsed ? 'lp-collapsed' : 'lp-expanded');
            if (this.viewport) {
                this.viewport.classList.toggle('lp-open', !this.collapsed);
            }

            const toggleBtn = document.createElement('button');
            toggleBtn.className = 'lp-toggle-btn' + (this.collapsed ? ' lp-toggle-collapsed' : '');
            toggleBtn.title = this.collapsed ? 'Expand layers' : 'Collapse layers';
            if (this.collapsed) {
                toggleBtn.innerHTML = '<span class="lp-toggle-chev">▸</span><span class="lp-toggle-label">timber list</span>';
            } else {
                toggleBtn.textContent = '◁';
            }
            toggleBtn.addEventListener('click', () => {
                this.collapsed = !this.collapsed;
                this._render();
            });
            this.el.appendChild(toggleBtn);

            if (this.collapsed) return;

            const header = document.createElement('div');
            header.className = 'lp-header';
            header.textContent = 'Layers';
            this.el.appendChild(header);

            // Search input
            const filterBar = document.createElement('div');
            filterBar.className = 'lp-filter-bar';
            const filterInput = document.createElement('input');
            filterInput.className = 'lp-filter-input';
            filterInput.type = 'text';
            filterInput.placeholder = 'Search…';
            filterInput.value = this.filterText;
            filterInput.addEventListener('input', (e) => {
                this.filterText = e.target.value;
                this._renderTree();
            });
            filterBar.appendChild(filterInput);
            this.el.appendChild(filterBar);

            this._treeEl = document.createElement('div');
            this._treeEl.className = 'lp-tree';
            this.el.appendChild(this._treeEl);

            this._footerEl = document.createElement('div');
            this._footerEl.className = 'lp-footer';
            this.el.appendChild(this._footerEl);

            this._renderTree();
            this._renderFooter();
        }

        _renderTree() {
            if (!this._treeEl) return;
            this._treeEl.innerHTML = '';
            this._renderSection(this._treeEl, 'timbers', 'Timbers', () => this._buildTimberRows());
            this._renderSection(this._treeEl, 'joints', 'Joints', () => this._buildJointRows());
            this._syncHighlight();
        }

        _renderSection(parent, sectionId, title, buildRows) {
            const nodeId = 'section:' + sectionId;
            const expanded = this.expandedNodes.has(nodeId);

            const section = document.createElement('div');
            section.className = 'lp-section';

            const sectionHeader = document.createElement('div');
            sectionHeader.className = 'lp-section-header' + (expanded ? ' lp-open' : '');
            const chevSpan = document.createElement('span');
            chevSpan.className = 'lp-chev';
            chevSpan.textContent = expanded ? '▾' : '▸';
            sectionHeader.appendChild(chevSpan);
            const titleSpan = document.createElement('span');
            titleSpan.textContent = ' ' + title;
            sectionHeader.appendChild(titleSpan);
            sectionHeader.addEventListener('click', () => {
                this._toggle(nodeId);
            });
            section.appendChild(sectionHeader);

            if (expanded) {
                const body = document.createElement('div');
                body.className = 'lp-section-body';
                for (const row of buildRows()) {
                    body.appendChild(row);
                }
                section.appendChild(body);
            }

            parent.appendChild(section);
        }

        _makeRow(opts) {
            const { nodeId, rowType, depth, label, tags, hasChildren, selectNode, memberKey } = opts;
            const expanded = hasChildren && this.expandedNodes.has(nodeId);

            const row = document.createElement('div');
            row.className = 'lp-row lp-row-' + rowType + ' lp-depth-' + depth;
            row.dataset.nodeId = nodeId;
            if (memberKey) row.dataset.memberKey = memberKey;

            // Chevron / expand control
            const chev = document.createElement('span');
            chev.className = 'lp-chev' + (hasChildren ? ' lp-has-children' : ' lp-leaf');
            chev.textContent = hasChildren ? (expanded ? '▾' : '▸') : '';
            if (hasChildren) {
                chev.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this._toggle(nodeId);
                });
            }
            row.appendChild(chev);

            const labelEl = document.createElement('span');
            labelEl.className = 'lp-label';
            labelEl.textContent = label;
            row.appendChild(labelEl);

            // Tag pills (shown only when showTagPills is enabled)
            if (this.showTagPills && tags && tags.length > 0) {
                const chipsEl = document.createElement('span');
                chipsEl.className = 'lp-chips';
                for (const tag of tags) {
                    const chip = document.createElement('span');
                    chip.className = 'lp-chip';
                    chip.textContent = tag;
                    chipsEl.appendChild(chip);
                }
                row.appendChild(chipsEl);
            }

            // Lock / hide icon buttons (only for member-level rows)
            if (memberKey) {
                const icons = document.createElement('span');
                icons.className = 'lp-icons';

                const lockBtn = document.createElement('button');
                lockBtn.className = 'lp-icon-btn lp-btn-lock';
                lockBtn.dataset.action = 'lock';
                lockBtn.title = 'Lock';
                lockBtn.textContent = '🔒';
                lockBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.layerStateStore.toggleLocked(memberKey);
                });
                icons.appendChild(lockBtn);

                const hideBtn = document.createElement('button');
                hideBtn.className = 'lp-icon-btn lp-btn-hide';
                hideBtn.dataset.action = 'hide';
                hideBtn.title = 'Hide';
                hideBtn.textContent = '👁';
                hideBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.layerStateStore.toggleHidden(memberKey);
                });
                icons.appendChild(hideBtn);

                row.appendChild(icons);
            }

            if (selectNode) {
                row.classList.add('lp-selectable');
                row.addEventListener('click', (event) => {
                    if (memberKey && this.layerStateStore.isLocked(memberKey)) {
                        return;
                    }
                    this.selectionManager.selectLayerNode(selectNode, !!event.shiftKey);
                });
            }

            return row;
        }

        _buildTimberRows() {
            const rows = [];
            if (!this.hierarchy) return rows;

            for (const timber of this.hierarchy.timbers) {
                if (!this._matchesFilter(timber.name, timber.tags)) continue;
                rows.push(this._makeRow({
                    nodeId: 'timber:' + timber.key,
                    rowType: 'timber',
                    depth: 0,
                    label: timber.name,
                    tags: timber.tags || [],
                    hasChildren: false,
                    memberKey: timber.key,
                    selectNode: { type: 'timber', key: timber.key },
                }));
            }
            return rows;
        }

        _buildJointRows() {
            const rows = [];
            if (!this.hierarchy) return rows;

            const nameByKey = {};
            for (const t of this.hierarchy.timbers) nameByKey[t.key] = t.name;

            for (const joint of (this.hierarchy.joints || [])) {
                if (!this._matchesFilter(joint.name, joint.tags)) continue;

                const jointNodeId = 'joint:' + joint.id;
                const members = [...(joint.timberKeys || []), ...(joint.accessoryKeys || [])];
                const hasChildren = members.length > 0;

                rows.push(this._makeRow({
                    nodeId: jointNodeId,
                    rowType: 'joint',
                    depth: 0,
                    label: joint.name,
                    tags: joint.tags || [],
                    hasChildren,
                    selectNode: { type: 'joint', jointId: joint.id, timberKeys: joint.timberKeys || [] },
                }));

                if (!hasChildren || !this.expandedNodes.has(jointNodeId)) continue;

                for (const timberKey of (joint.timberKeys || [])) {
                    rows.push(this._makeRow({
                        nodeId: 'jm:' + joint.id + ':' + timberKey,
                        rowType: 'jointMember',
                        depth: 1,
                        label: nameByKey[timberKey] || timberKey,
                        tags: [],
                        hasChildren: false,
                        selectNode: { type: 'timber', key: timberKey },
                    }));
                }

                for (const accKey of (joint.accessoryKeys || [])) {
                    rows.push(this._makeRow({
                        nodeId: 'jm:' + joint.id + ':' + accKey,
                        rowType: 'jointMember',
                        depth: 1,
                        label: accKey.replace(/^accessory:[^:]+:/, '').replace(/^accessory:/, ''),
                        tags: [],
                        hasChildren: false,
                        selectNode: { type: 'accessory', key: accKey },
                    }));
                }
            }
            return rows;
        }

        // ------------------------------------------------------------------
        // Selection sync
        // ------------------------------------------------------------------

        _syncHighlight() {
            if (!this.el) return;

            for (const row of this.el.querySelectorAll('.lp-row.lp-selected')) {
                row.classList.remove('lp-selected');
            }

            const selectedTimbers = this.selectionManager.selectedTimbers;

            // Canvas-driven: highlight timber/accessory rows that match selected keys
            for (const key of selectedTimbers) {
                const safeKey = CSS.escape(key);
                for (const row of this.el.querySelectorAll('.lp-row[data-member-key="' + safeKey + '"]')) {
                    row.classList.add('lp-selected');
                }
                for (const row of this.el.querySelectorAll('.lp-row[data-node-id="timber:' + safeKey + '"]')) {
                    row.classList.add('lp-selected');
                }
                // Joint members referencing this key
                for (const row of this.el.querySelectorAll('.lp-row-jointMember[data-node-id$=":' + safeKey + '"]')) {
                    row.classList.add('lp-selected');
                }
            }

            // Layer-node driven: scroll to and highlight the specific node
            const layerNode = this.selectionManager.selectedLayerNode;
            if (layerNode) {
                let nodeId = null;
                if (layerNode.type === 'timber') nodeId = 'timber:' + layerNode.key;
                else if (layerNode.type === 'cutting') nodeId = 'cutting:' + layerNode.timberKey + ':' + layerNode.cuttingIdx;
                else if (layerNode.type === 'csgNode' && layerNode.path && layerNode.path[0]) {
                    const cuttingIdx = layerNode.cuttingIdx != null ? layerNode.cuttingIdx : 0;
                    nodeId = 'csgnode:' + layerNode.timberKey + ':' + cuttingIdx + ':' + layerNode.path[0];
                }
                else if (layerNode.type === 'joint') nodeId = 'joint:' + layerNode.jointId;
                else if (layerNode.type === 'accessory') nodeId = 'timber:' + layerNode.key;

                if (nodeId) {
                    const row = this.el.querySelector('.lp-row[data-node-id="' + CSS.escape(nodeId) + '"]');
                    if (row) {
                        row.classList.add('lp-selected');
                        row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                    }
                }
            } else if (selectedTimbers.size === 1) {
                // Scroll to selected timber row (canvas click)
                const key = Array.from(selectedTimbers)[0];
                const row = this.el.querySelector('.lp-row[data-node-id="timber:' + CSS.escape(key) + '"]');
                if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        }

        _renderFooter() {
            if (!this._footerEl) return;
            this._footerEl.innerHTML = '';
            const anyHidden = this.layerStateStore.hasAnyHidden();
            const anyLocked = this.layerStateStore.hasAnyLocked();
            if (!anyHidden && !anyLocked) return;

            if (anyHidden) {
                const btn = document.createElement('button');
                btn.className = 'lp-footer-btn';
                btn.textContent = 'show all';
                btn.addEventListener('click', () => this.layerStateStore.showAll());
                this._footerEl.appendChild(btn);
            }
            if (anyLocked) {
                const btn = document.createElement('button');
                btn.className = 'lp-footer-btn';
                btn.textContent = 'unlock all';
                btn.addEventListener('click', () => this.layerStateStore.unlockAll());
                this._footerEl.appendChild(btn);
            }
        }

        _updateStateIcons() {
            if (!this.el) return;
            for (const row of this.el.querySelectorAll('.lp-row[data-member-key]')) {
                const key = row.dataset.memberKey;
                const state = this.layerStateStore.getState(key);
                const lockBtn = row.querySelector('[data-action="lock"]');
                const hideBtn = row.querySelector('[data-action="hide"]');
                if (lockBtn) {
                    lockBtn.classList.toggle('lp-active', state.locked);
                    lockBtn.title = state.locked ? 'Unlock' : 'Lock';
                }
                if (hideBtn) {
                    hideBtn.classList.toggle('lp-active', state.hidden);
                    hideBtn.title = state.hidden ? 'Show' : 'Hide';
                }
            }
            this._renderFooter();
        }

        // ------------------------------------------------------------------
        // Helpers
        // ------------------------------------------------------------------

        _toggle(nodeId) {
            if (this.expandedNodes.has(nodeId)) {
                this.expandedNodes.delete(nodeId);
            } else {
                this.expandedNodes.add(nodeId);
            }
            this._renderTree();
        }
    }

    const LayersViewBase = typeof HTMLElement !== 'undefined' ? HTMLElement : class {};

    class KigumiLayersView extends LayersViewBase {
        constructor() {
            super();
            this._selectionManager = null;
            this._layerStateStore = null;
            this._panel = null;
            this._showTagPills = true;
            this._hierarchy = { timbers: [], joints: [] };
            this._unsubLayerState = null;
        }

        connectedCallback() {
            this._ensureMounted();
        }

        disconnectedCallback() {
            this._disposePanel();
        }

        attach(selectionManager, _vscode) {
            this._selectionManager = selectionManager;
            this._ensureMounted();
        }

        setShowTagPills(show) {
            this._showTagPills = Boolean(show);
            if (this._panel && typeof this._panel.setShowTagPills === 'function') {
                this._panel.setShowTagPills(this._showTagPills);
            }
        }

        setLayersPayload(payload) {
            this._hierarchy = this._convertRunnerPayload(payload || {});
            this._ensureMounted();
            if (this._panel) {
                this._panel.setHierarchy(this._hierarchy);
                this._panel.setShowTagPills(this._showTagPills);
            }
            this._emitLayerStateSync();
        }

        mergeCSGTreePayload(_payload) {
            // CSG subtree expansion is not rendered in this panel yet.
        }

        _ensureMounted() {
            if (this._panel || !this._selectionManager) {
                return;
            }

            const LayerStateStoreCtor = globalScope.LayerStateStore;
            if (!LayerStateStoreCtor) {
                console.warn('LayerStateStore is not available; layers panel disabled.');
                return;
            }

            this._layerStateStore = new LayerStateStoreCtor();
            this._unsubLayerState = this._layerStateStore.onStateChanged((event) => {
                this.dispatchEvent(new CustomEvent('layer-state-changed', {
                    detail: event,
                    bubbles: true,
                    composed: true,
                }));
            });
            this._panel = new LayersPanel(this._selectionManager, this._layerStateStore);
            this._panel.mount(this);
            this._panel.setShowTagPills(this._showTagPills);
            this._panel.setHierarchy(this._hierarchy);
            this._emitLayerStateSync();
        }

        _disposePanel() {
            if (!this._panel) {
                return;
            }
            if (this._unsubLayerState) {
                this._unsubLayerState();
                this._unsubLayerState = null;
            }
            this._panel.destroy();
            this._panel = null;
        }

        _emitLayerStateSync() {
            if (!this._layerStateStore) {
                return;
            }
            const keys = new Set();
            for (const timber of (this._hierarchy.timbers || [])) {
                if (timber && typeof timber.key === 'string') {
                    keys.add(timber.key);
                }
            }
            for (const joint of (this._hierarchy.joints || [])) {
                for (const timberKey of (joint && joint.timberKeys) || []) {
                    if (typeof timberKey === 'string') {
                        keys.add(timberKey);
                    }
                }
                for (const accessoryKey of (joint && joint.accessoryKeys) || []) {
                    if (typeof accessoryKey === 'string') {
                        keys.add(accessoryKey);
                    }
                }
            }

            const states = {};
            for (const key of keys) {
                states[key] = this._layerStateStore.getState(key);
            }

            this.dispatchEvent(new CustomEvent('layer-state-sync', {
                detail: { states },
                bubbles: true,
                composed: true,
            }));
        }

        _convertRunnerPayload(payload) {
            const timbers = Array.isArray(payload.timbers) ? payload.timbers : [];
            const accessories = Array.isArray(payload.accessories) ? payload.accessories : [];
            const joints = Array.isArray(payload.joints) ? payload.joints : [];

            const timberKeyByKumikiId = new Map();
            for (const t of timbers) {
                if (typeof t.kumikiId === 'number' && typeof t.memberKey === 'string') {
                    timberKeyByKumikiId.set(t.kumikiId, t.memberKey);
                }
            }

            const accessoryKeyByKumikiId = new Map();
            for (const a of accessories) {
                if (typeof a.kumikiId === 'number' && typeof a.memberKey === 'string') {
                    accessoryKeyByKumikiId.set(a.kumikiId, a.memberKey);
                }
            }

            const hierarchyTimbers = timbers.map((t) => ({
                key: t.memberKey,
                name: t.name || t.memberKey,
                tags: Array.isArray(t.tags) ? t.tags : [],
            })).filter((t) => typeof t.key === 'string' && t.key.length > 0);

            const hierarchyJoints = joints.map((j) => ({
                id: String(j.kumikiId != null ? j.kumikiId : j.name || 'joint'),
                name: j.name || 'joint',
                tags: Array.isArray(j.tags) ? j.tags : [],
                timberKeys: (Array.isArray(j.members) ? j.members : [])
                    .map((m) => timberKeyByKumikiId.get(m.timberKumikiId))
                    .filter((key) => typeof key === 'string'),
                accessoryKeys: (Array.isArray(j.accessoryKumikiIds) ? j.accessoryKumikiIds : [])
                    .map((kid) => accessoryKeyByKumikiId.get(kid))
                    .filter((key) => typeof key === 'string'),
            }));

            return {
                timbers: hierarchyTimbers,
                joints: hierarchyJoints,
            };
        }
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { LayersPanel, KigumiLayersView };
    }
    globalScope.LayersPanel = LayersPanel;
    globalScope.KigumiLayersView = KigumiLayersView;
    if (globalScope.customElements && !globalScope.customElements.get('kigumi-layers-view')) {
        globalScope.customElements.define('kigumi-layers-view', KigumiLayersView);
    }
})(typeof window !== 'undefined' ? window : globalThis);
