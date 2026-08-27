(function (globalScope) {
    // LayersPanel renders a collapsible overlay tree on the left edge of the viewport.
    // It syncs bidirectionally with SelectionStore: canvas clicks highlight the
    // corresponding row, and clicking a row updates the canvas selection.
    const _i18nStrings = (globalScope.__KIGUMI_INITIAL_PAYLOAD__
        && globalScope.__KIGUMI_INITIAL_PAYLOAD__.i18n
        && globalScope.__KIGUMI_INITIAL_PAYLOAD__.i18n.strings) || {};
    const t = globalScope.KigumiI18n
        ? globalScope.KigumiI18n.createTranslator(_i18nStrings)
        : (key) => key;
    // The model behind the embedded CSG trees. viewer.html loads it ahead of
    // this file; capturing it here makes that ordering a stated dependency
    // rather than something the rows happen to get away with at click time.
    const CsgTreeView = globalScope.CsgTreeView;

    // CSG rows indent from where the member rows leave off (.lp-depth-0 is
    // 18px), one step per level. The old 10px step started shallower than the
    // timber row above it, so a tree read as a sibling of its own timber.
    const CSG_INDENT_BASE_PX = 18;
    const CSG_INDENT_STEP_PX = 14;
    // What .lp-depth-0 / .lp-depth-1 / .lp-depth-2 indent member rows by, kept
    // here so the guard test can check CSG rows nest deeper than their parent.
    const MEMBER_ROW_INDENT_PX = [18, 22, 34];

    function csgIndentPx(depth) {
        return CSG_INDENT_BASE_PX + depth * CSG_INDENT_STEP_PX;
    }

    class LayersPanel {
        constructor(selectionManager, layerStateStore) {
            this.selectionManager = selectionManager;
            this.layerStateStore = layerStateStore;
            this.hierarchy = null;
            this.collapsed = true;
            // Default: top-level sections open, individual nodes closed
            this.expandedNodes = new Set(['section:timbers', 'section:joints']);
            // Per-timber CSG payloads, fetched lazily when a row is expanded.
            this.csgTreesByKey = new Map();
            this.requestedCsgTrees = new Set();
            this._pendingReveal = null;
            this._focusedCsgNodeId = null;
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
                if (!this.selectionManager.csgFocus) {
                    this._focusedCsgNodeId = null;
                }
                this._syncHighlight();
            });
            this._unsubLayerState = this.layerStateStore.onStateChanged(() => {
                this._updateStateIcons();
            });
        }

        setHierarchy(hierarchy) {
            this.hierarchy = hierarchy || { timbers: [], joints: [] };
            // New frame data means the cached CSG could be stale -- an edit to
            // the source is exactly when the tree changes shape -- so it is
            // dropped and refetched on the next expand rather than shown as if
            // it still described the model on screen.
            this.csgTreesByKey.clear();
            this.requestedCsgTrees.clear();
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
            toggleBtn.title = this.collapsed ? t('viewer.layers.expand.title') : t('viewer.layers.collapse.title');
            if (this.collapsed) {
                toggleBtn.innerHTML = `<span class="lp-toggle-chev">▸</span><span class="lp-toggle-label">${t('viewer.layers.toggleLabel')}</span>`;
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
            header.textContent = t('viewer.layers.header');
            this.el.appendChild(header);

            // Search input
            const filterBar = document.createElement('div');
            filterBar.className = 'lp-filter-bar';
            const filterInput = document.createElement('input');
            filterInput.className = 'lp-filter-input';
            filterInput.type = 'text';
            filterInput.placeholder = t('viewer.layers.search.placeholder');
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
            this._renderSection(this._treeEl, 'timbers', t('viewer.layers.section.timbers'), () => this._buildTimberRows());
            this._renderSection(this._treeEl, 'joints', t('viewer.layers.section.joints'), () => this._buildJointRows());
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

            if (memberKey && rowType === 'timber') {
                row.addEventListener('contextmenu', (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    row.dispatchEvent(new CustomEvent('kigumi-member-contextmenu', {
                        detail: { memberKey, clientX: event.clientX, clientY: event.clientY },
                        bubbles: true,
                        composed: true,
                    }));
                });
            }

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
                lockBtn.title = t('viewer.layers.lock.title');
                lockBtn.textContent = '🔒';
                lockBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.layerStateStore.toggleLocked(memberKey);
                });
                icons.appendChild(lockBtn);

                const hideBtn = document.createElement('button');
                hideBtn.className = 'lp-icon-btn lp-btn-hide';
                hideBtn.dataset.action = 'hide';
                hideBtn.title = t('viewer.layers.hide.title');
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
                    this._applySelection(selectNode, !!event.shiftKey);
                });
            }

            return row;
        }

        /** Apply a row click to the selection store. */
        _applySelection(node, additive) {
            const selection = this.selectionManager;
            if (node.type === 'timber' || node.type === 'accessory') {
                if (additive) {
                    selection.toggleTimber(node.key);
                } else {
                    selection.selectTimber(node.key, false);
                }
                return;
            }
            if (node.type === 'joint') {
                selection.selectJoint(node.jointId, node.timberKeys || [], additive);
            }
        }

        _buildTimberRows() {
            const rows = [];
            if (!this.hierarchy) return rows;

            for (const timber of this.hierarchy.timbers) {
                if (!this._matchesFilter(timber.name, timber.tags)) continue;
                const nodeId = 'timber:' + timber.key;
                rows.push(this._makeRow({
                    nodeId,
                    rowType: 'timber',
                    depth: 0,
                    label: timber.name,
                    tags: timber.tags || [],
                    // Every timber has a CSG tree, even an uncut one -- it is
                    // still a body with faces worth naming.
                    hasChildren: true,
                    memberKey: timber.key,
                    selectNode: { type: 'timber', key: timber.key },
                }));
                if (!this.expandedNodes.has(nodeId)) continue;
                rows.push(...this._buildCsgRows({
                    timberKey: timber.key,
                    context: { section: 'timbers' },
                    depth: 1,
                }));
            }
            return rows;
        }

        // ------------------------------------------------------------------
        // The CSG trees embedded in both sections
        // ------------------------------------------------------------------

        /**
         * Rows for one timber's CSG tree.
         *
         * In the timber section this is the body with every cutting beneath
         * it; in a joint section it is the body with just that joint's
         * cutting, so the cutting can be read against what it cuts into.
         */
        _buildCsgRows({ timberKey, context, depth, jointId, cutIndex }) {
            const payload = this.csgTreesByKey.get(timberKey);
            if (!payload) {
                this._requestCsgTree(timberKey);
                return [this._makeCsgPlaceholderRow(depth, t('viewer.layers.csg.loading'))];
            }

            const tree = context.section === 'joints'
                ? CsgTreeView.jointCuttingTree(payload, timberKey, jointId, cutIndex)
                : CsgTreeView.timberTree(payload, timberKey);
            if (!tree) {
                return [this._makeCsgPlaceholderRow(depth, t('viewer.layers.csg.empty'))];
            }

            return CsgTreeView.flatten(tree, this.expandedNodes).map((row) => (
                this._makeCsgRow(row, { timberKey, context, baseDepth: depth })
            ));
        }

        _makeCsgPlaceholderRow(depth, text) {
            const row = document.createElement('div');
            row.className = 'lp-row lp-row-csg lp-csg-placeholder';
            // Indented the same way the rows it stands in for will be, so the
            // list does not jump sideways when the tree arrives.
            row.style.paddingLeft = csgIndentPx(depth) + 'px';
            row.textContent = text;
            return row;
        }

        /** One CSG node row: its base type, its tag, and what it does. */
        _makeCsgRow(node, { timberKey, context, baseDepth }) {
            const row = document.createElement('div');
            const depth = baseDepth + node.depth;
            row.className = 'lp-row lp-row-csg lp-selectable'
                + (node.role === 'cut' ? ' lp-csg-cut' : '')
                + (node.role === 'base' ? ' lp-csg-base' : '');
            row.dataset.nodeId = node.id;
            row.style.paddingLeft = csgIndentPx(depth) + 'px';

            const chev = document.createElement('span');
            chev.className = 'lp-chev' + (node.hasChildren ? ' lp-has-children' : ' lp-leaf');
            chev.textContent = node.hasChildren ? (node.expanded ? '\u25be' : '\u25b8') : '';
            if (node.hasChildren) {
                chev.addEventListener('click', (event) => {
                    event.stopPropagation();
                    this._toggle(node.id);
                });
            }
            row.appendChild(chev);

            // A difference reads as arithmetic: the base is the material you
            // start with and the cuts come off it, so both sides are signed
            // rather than leaving the positive one to look like any other child.
            if (node.role === 'cut' || node.role === 'base') {
                const sign = document.createElement('span');
                const isCut = node.role === 'cut';
                sign.className = isCut ? 'lp-csg-minus' : 'lp-csg-plus';
                sign.textContent = isCut ? '\u2212' : '+';
                row.appendChild(sign);
            }

            const kind = document.createElement('span');
            kind.className = 'lp-csg-kind';
            kind.textContent = node.displayName || node.kind;
            row.appendChild(kind);

            if (node.label) {
                const label = document.createElement('span');
                label.className = 'lp-csg-label';
                label.textContent = node.label;
                row.appendChild(label);
            }

            // Which joint made this cut is the useful fact in the timber
            // section; under a joint it is already known, so it is left off.
            if (context.section === 'timbers' && node.role === 'cut' && node.jointName) {
                const joint = document.createElement('span');
                joint.className = 'lp-csg-joint';
                joint.textContent = node.jointName;
                row.appendChild(joint);
            }

            if (node.features && node.features.length) {
                const feats = document.createElement('span');
                feats.className = 'lp-csg-features';
                feats.textContent = String(node.features.length);
                feats.title = node.features
                    .map((f) => f.name + ' (' + String(f.type).toLowerCase() + ')')
                    .join('\n');
                row.appendChild(feats);
            }

            row.addEventListener('click', () => {
                this._focusCsgNode(node, timberKey, context);
            });
            return row;
        }

        /** Clicking a CSG row focuses it, and drives the 3D highlight. */
        _focusCsgNode(node, timberKey, context) {
            this.selectionManager.setCsgFocus({
                timberKey,
                path: node.path,
                featureLabel: null,
                cutIndex: node.cutIndex,
                context,
            });
            this.selectionManager.setFocusedNodeId(node.id);
            this._focusedCsgNodeId = node.id;
            this._renderTree();
            if (node.path && node.path.length) {
                this._emit('kigumi-request-csg-by-path', { memberKey: timberKey, path: node.path });
            }
        }

        _requestCsgTree(timberKey) {
            if (this.requestedCsgTrees.has(timberKey)) {
                return;
            }
            this.requestedCsgTrees.add(timberKey);
            this._emit('kigumi-request-csg-tree', { memberKey: timberKey });
        }

        _emit(type, detail) {
            if (!this.el) return;
            this.el.dispatchEvent(new CustomEvent(type, {
                detail, bubbles: true, composed: true,
            }));
        }

        /** A tree came back from the runner. */
        setCsgTree(timberKey, payload) {
            if (!timberKey || !payload) return;
            this.csgTreesByKey.set(timberKey, payload);
            this.requestedCsgTrees.delete(timberKey);
            const pending = this._pendingReveal;
            if (pending && pending.timberKey === timberKey) {
                this._pendingReveal = null;
                this.revealCsg(pending);
                return;
            }
            this._renderTree();
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

                // One row per cutting rather than per member: a joint that
                // cuts the same timber twice has two things to show, and each
                // gets its own tree.
                const cuttings = joint.cuttings && joint.cuttings.length
                    ? joint.cuttings
                    : (joint.timberKeys || []).map((timberKey) => ({ timberKey, cutIndex: null }));
                const cutsPerTimber = new Map();
                for (const cutting of cuttings) {
                    cutsPerTimber.set(cutting.timberKey, (cutsPerTimber.get(cutting.timberKey) || 0) + 1);
                }

                for (const cutting of cuttings) {
                    const { timberKey, cutIndex } = cutting;
                    const cuttingNodeId = 'jcut:' + joint.id + ':' + timberKey + ':' + cutIndex;
                    const name = nameByKey[timberKey] || timberKey;
                    // The cut number only earns its space when there is more
                    // than one cut on this timber to tell apart.
                    const label = cutsPerTimber.get(timberKey) > 1 && cutIndex !== null
                        ? t('viewer.layers.csg.cutOn', { timber: name, cut: cutIndex + 1 })
                        : name;
                    rows.push(this._makeRow({
                        nodeId: cuttingNodeId,
                        rowType: 'jointMember',
                        depth: 1,
                        label,
                        tags: [],
                        hasChildren: true,
                        memberKey: timberKey,
                        selectNode: { type: 'timber', key: timberKey },
                    }));
                    if (!this.expandedNodes.has(cuttingNodeId)) continue;
                    rows.push(...this._buildCsgRows({
                        timberKey,
                        context: { section: 'joints', jointId: joint.id, cutIndex },
                        depth: 2,
                        jointId: joint.id,
                        cutIndex,
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

            // The focused CSG row, if it is currently rendered.
            const focusedId = this._focusedCsgNodeId;
            if (focusedId) {
                const row = this.el.querySelector(
                    '.lp-row-csg[data-node-id="' + CSS.escape(focusedId) + '"]');
                if (row) {
                    row.classList.add('lp-selected');
                    row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                }
            } else if (selectedTimbers.size === 1) {
                // Scroll to selected timber row (canvas click)
                const key = Array.from(selectedTimbers)[0];
                const row = this.el.querySelector('.lp-row[data-node-id="timber:' + CSS.escape(key) + '"]');
                if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        }

        /**
         * Show a CSG node in the list: open the sections and rows above it,
         * mark it, and scroll to it. Called when a 3D pick needs the list to
         * follow. Fetches the tree first if it is not in yet.
         */
        revealCsg({ section, timberKey, jointId, cutIndex, path }) {
            const payload = this.csgTreesByKey.get(timberKey);
            if (!payload) {
                this._pendingReveal = { section, timberKey, jointId, cutIndex, path };
                this._requestCsgTree(timberKey);
                return;
            }

            const inJoints = section === 'joints';
            const tree = inJoints
                ? CsgTreeView.jointCuttingTree(payload, timberKey, jointId, cutIndex)
                : CsgTreeView.timberTree(payload, timberKey);
            if (!tree) {
                return;
            }

            // Everything between the section header and the node itself.
            this.expandedNodes.add(inJoints ? 'section:joints' : 'section:timbers');
            if (inJoints) {
                this.expandedNodes.add('joint:' + jointId);
                this.expandedNodes.add('jcut:' + jointId + ':' + timberKey + ':' + cutIndex);
            } else {
                this.expandedNodes.add('timber:' + timberKey);
            }

            const target = CsgTreeView.findByPath(tree, path || []);
            if (target) {
                // Expand down to the node, but not the node itself: revealing
                // something should not unfold everything beneath it.
                const chain = CsgTreeView.ancestorIds(tree, target.id);
                for (const id of chain.slice(0, -1)) {
                    this.expandedNodes.add(id);
                }
                this._focusedCsgNodeId = target.id;
                this.selectionManager.setFocusedNodeId(target.id);
            }
            this._renderTree();
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
                btn.textContent = t('viewer.layers.footer.showAll');
                btn.addEventListener('click', () => this.layerStateStore.showAll());
                this._footerEl.appendChild(btn);
            }
            if (anyLocked) {
                const btn = document.createElement('button');
                btn.className = 'lp-footer-btn';
                btn.textContent = t('viewer.layers.footer.unlockAll');
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
                    lockBtn.title = state.locked ? t('viewer.layers.unlock.title') : t('viewer.layers.lock.title');
                }
                if (hideBtn) {
                    hideBtn.classList.toggle('lp-active', state.hidden);
                    hideBtn.title = state.hidden ? t('viewer.layers.show.title') : t('viewer.layers.hide.title');
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

        /** Hand a fetched CSG tree to the panel. */
        setCsgTree(memberKey, payload) {
            if (this._panel) {
                this._panel.setCsgTree(memberKey, payload);
            }
        }

        /** Show a CSG node in the list, opening whatever is above it. */
        revealCsg(target) {
            if (this._panel) {
                this._panel.revealCsg(target);
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

            const timberKeyByKumikiEphemeralId = new Map();
            for (const t of timbers) {
                if (typeof t.kumikiEphemeralId === 'number' && typeof t.memberKey === 'string') {
                    timberKeyByKumikiEphemeralId.set(t.kumikiEphemeralId, t.memberKey);
                }
            }

            const accessoryKeyByKumikiEphemeralId = new Map();
            for (const a of accessories) {
                if (typeof a.kumikiEphemeralId === 'number' && typeof a.memberKey === 'string') {
                    accessoryKeyByKumikiEphemeralId.set(a.kumikiEphemeralId, a.memberKey);
                }
            }

            const hierarchyTimbers = timbers.map((t) => ({
                key: t.memberKey,
                name: t.name || t.memberKey,
                tags: Array.isArray(t.tags) ? t.tags : [],
            })).filter((t) => typeof t.key === 'string' && t.key.length > 0);

            const hierarchyJoints = joints.map((j) => ({
                id: String(j.kumikiEphemeralId != null ? j.kumikiEphemeralId : j.name || 'joint'),
                name: j.name || 'joint',
                tags: Array.isArray(j.tags) ? j.tags : [],
                timberKeys: (Array.isArray(j.members) ? j.members : [])
                    .map((m) => timberKeyByKumikiEphemeralId.get(m.timberKumikiEphemeralId))
                    .filter((key) => typeof key === 'string'),
                // One entry per cutting, which is what the joint section shows:
                // a member cut twice by the same joint gets a row per cut.
                cuttings: (Array.isArray(j.members) ? j.members : []).flatMap((m) => {
                    const key = timberKeyByKumikiEphemeralId.get(m.timberKumikiEphemeralId);
                    if (typeof key !== 'string') {
                        return [];
                    }
                    return (Array.isArray(m.cutIndices) ? m.cutIndices : [])
                        .map((cutIndex) => ({ timberKey: key, cutIndex }));
                }),
                accessoryKeys: (Array.isArray(j.accessoryKumikiEphemeralIds) ? j.accessoryKumikiEphemeralIds : [])
                    .map((kid) => accessoryKeyByKumikiEphemeralId.get(kid))
                    .filter((key) => typeof key === 'string'),
            }));

            return {
                timbers: hierarchyTimbers,
                joints: hierarchyJoints,
            };
        }
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { LayersPanel, KigumiLayersView, csgIndentPx, MEMBER_ROW_INDENT_PX };
    }
    globalScope.LayersPanel = LayersPanel;
    globalScope.KigumiLayersView = KigumiLayersView;
    if (globalScope.customElements && !globalScope.customElements.get('kigumi-layers-view')) {
        globalScope.customElements.define('kigumi-layers-view', KigumiLayersView);
    }
})(typeof window !== 'undefined' ? window : globalThis);
