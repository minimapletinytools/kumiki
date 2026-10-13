// The app shell: a fixed layout (left panel, two center tab groups -- sources and
// views -- a bottom panel, a right panel, status bar) whose panels are iframes. Everything it shows comes from the core as
// `shell:state`; it talks to the core only through window.kigumiShell
// ({ send, onMessage }), which the host provides. See app-shell/.

(function () {
    'use strict';

    const core = window.kigumiShell;
    const $ = (id) => document.getElementById(id);
    const isMac = navigator.platform.toUpperCase().includes('MAC');
    const SIDE_LIMITS = { left: [180, 600], right: [240, 800], bottom: [80, 800] };

    let state = { panels: [], activeId: null, shown: {} };
    const frames = new Map(); // panel id -> { iframe, url, loaded, queue }

    // ---------------------------------------------------------------------
    // Panels as iframes
    // ---------------------------------------------------------------------

    function frameSource(panel) {
        const hash = panel.state === undefined ? '' : `#${encodeURIComponent(JSON.stringify(panel.state))}`;
        return panel.url + hash;
    }

    function ensureFrame(panel) {
        let frame = frames.get(panel.id);
        if (!frame) {
            const iframe = document.createElement('iframe');
            iframe.className = 'panel-frame';
            iframe.name = panel.id;
            iframe.title = panel.title || panel.type;
            frame = { iframe, url: null, loaded: false, queue: [] };
            iframe.addEventListener('load', () => {
                if (!frame.url) return;
                frame.loaded = true;
                for (const message of frame.queue.splice(0)) {
                    iframe.contentWindow.postMessage(message, '*');
                }
                core.send({ type: 'panel:loaded', id: panel.id });
            });
            frames.set(panel.id, frame);
            $(`slot-${panel.group || panel.slot}`).append(iframe);
        }
        if (panel.url && panel.url !== frame.url) {
            frame.url = panel.url;
            frame.loaded = false;
            frame.queue = [];
            frame.iframe.src = frameSource(panel);
        }
        frame.iframe.title = panel.title || panel.type;
        return frame;
    }

    function toPanel(id, message) {
        const frame = frames.get(id);
        if (!frame) return;
        if (frame.loaded) {
            frame.iframe.contentWindow.postMessage(message, '*');
        } else {
            frame.queue.push(message);
        }
    }

    function panelForSource(source) {
        for (const [id, frame] of frames) {
            if (frame.iframe.contentWindow === source) return id;
        }
        return null;
    }

    window.addEventListener('message', (event) => {
        const data = event.data;
        if (!data || data.kigumiPanel !== true) return;
        const id = panelForSource(event.source);
        if (!id) return;
        if (data.type === 'message') {
            core.send({ type: 'panel:message', id, message: data.message });
        } else if (data.type === 'state') {
            core.send({ type: 'panel:state', id, state: data.state });
        }
    });

    function renderPanels() {
        const live = new Set(state.panels.map((panel) => panel.id));
        for (const [id, frame] of frames) {
            if (!live.has(id)) {
                frame.iframe.remove();
                frames.delete(id);
            }
        }
        for (const panel of state.panels) {
            const frame = ensureFrame(panel);
            frame.iframe.hidden = Boolean(panel.group) && panel.id !== state.shown[panel.group];
        }
        const groupHas = (group) => state.panels.some((panel) => panel.group === group);
        const split = groupHas('code') && groupHas('view');
        for (const group of ['code', 'view']) {
            $(`group-${group}`).hidden = !groupHas(group);
            $(`group-${group}`).classList.toggle('is-focused', split && state.focusedGroup === group);
        }
        $('groups').classList.toggle('is-split', split);
        $('splitter-group').hidden = !split;

        const hasLeft = state.panels.some((panel) => panel.slot === 'left');
        const layout = state.layout || { left: true, bottom: true, right: true };
        const showLeft = hasLeft && layout.left;
        $('slot-left').hidden = !showLeft;
        $('splitter-left').hidden = !showLeft;
        $('shell').classList.toggle('is-left-hidden', !showLeft);
        $('toggle-left').classList.toggle('is-active', showLeft);

        const showRight = state.panels.some((panel) => panel.slot === 'right') && layout.right;
        $('slot-right').hidden = !showRight;
        $('splitter-right').hidden = !showRight;
        $('toggle-right').classList.toggle('is-active', showRight);

        const hasBottom = state.panels.some((panel) => panel.slot === 'bottom');
        const showBottom = hasBottom && layout.bottom;
        $('slot-bottom').hidden = !showBottom;
        $('splitter-bottom').hidden = !showBottom;
        $('toggle-bottom').hidden = !hasBottom;
        $('toggle-bottom').classList.toggle('is-active', showBottom);
    }

    // ---------------------------------------------------------------------
    // Chrome
    // ---------------------------------------------------------------------

    function el(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    }

    function icon(name) {
        return el('span', `codicon codicon-${name}`);
    }

    function command(name, ...args) {
        core.send({ type: 'shell:command', command: name, args });
    }

    function renderTab(tab) {
        const active = tab.id === state.shown[tab.group];
        const element = el('div', `tab${active ? ' is-active' : ''}`);
        element.setAttribute('role', 'tab');
        element.setAttribute('tabindex', '0');
        element.setAttribute('aria-selected', active ? 'true' : 'false');
        element.title = tab.title;
        element.append(icon(tab.icon || 'file'), el('span', 'tab-title', tab.title || 'Kigumi'));
        const close = el('span', 'tab-close');
        close.setAttribute('role', 'button');
        close.setAttribute('aria-label', `Close ${tab.title}`);
        close.append(icon('close'));
        close.addEventListener('click', (event) => {
            event.stopPropagation();
            core.send({ type: 'tab:close', id: tab.id });
        });
        element.append(close);
        element.addEventListener('click', () => core.send({ type: 'tab:activate', id: tab.id }));
        element.addEventListener('auxclick', (event) => {
            if (event.button === 1) core.send({ type: 'tab:close', id: tab.id });
        });
        element.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                core.send({ type: 'tab:activate', id: tab.id });
            }
        });
        return element;
    }

    function shownPanel(group) {
        return state.panels.find((panel) => panel.id === state.shown[group]) || null;
    }

    function renderTabs() {
        for (const group of ['code', 'view']) {
            $(`tabs-${group}`).replaceChildren(...state.panels.filter((panel) => panel.group === group).map(renderTab));
        }
        // Each group offers the other half of what it shows: a view its source, a source its view.
        const view = shownPanel('view');
        $('open-source').hidden = !(view && view.filePath);
        const code = shownPanel('code');
        $('open-view').hidden = !(code && code.type === 'editor' && /\.py$/.test(code.filePath || ''));
    }

    function renderWelcome() {
        const hasTabs = state.panels.some((panel) => panel.group);
        $('welcome').hidden = hasTabs;
        const button = (label, onClick, secondary) => {
            const element = el('button', secondary ? 'secondary' : '', label);
            element.addEventListener('click', onClick);
            return element;
        };
        if (state.workspace) {
            $('welcome-lead').textContent = `Open a frame or pattern from the explorer to view it. Project: ${state.workspace.name}`;
            $('welcome-actions').replaceChildren(
                button('Open Frame File…', () => command('openFrameFile')),
                button('Browse Patterns…', () => command('run', 'kigumi.browsePatterns'), true),
            );
        } else {
            $('welcome-lead').textContent = 'Open a project folder to find its frames and patterns.';
            $('welcome-actions').replaceChildren(button('Open Folder…', () => command('openFolder')));
        }
    }

    function renderStatus() {
        const workspace = $('status-workspace');
        workspace.replaceChildren(icon('folder'), document.createTextNode(state.workspace ? state.workspace.name : 'Open Folder…'));
        workspace.title = state.workspace ? state.workspace.path : 'Open folder';

        const progress = $('status-progress');
        progress.hidden = !state.progress;
        progress.replaceChildren(icon('loading codicon-modifier-spin'), document.createTextNode(state.progress || ''));

        const message = $('status-message');
        message.hidden = !state.status;
        message.className = `status-item status-message${state.status ? ` is-${state.status.level}` : ''}`;
        message.textContent = state.status ? state.status.message : '';
        message.title = message.textContent;

        $('status-autorefresh').replaceChildren(
            icon(state.autoRefresh ? 'sync' : 'sync-ignored'),
            document.createTextNode(state.autoRefresh ? 'Auto refresh' : 'Manual refresh'),
        );
        $('status-log-badge').hidden = !state.logBadge;
        $('status-version').textContent = state.version ? `v${state.version}` : '';
    }

    function renderTitlebar() {
        const active = state.panels.find((panel) => panel.group && panel.id === state.activeId);
        const parts = [];
        if (active && active.title) parts.push(active.title);
        if (state.workspace && state.workspace.name) parts.push(state.workspace.name);
        parts.push('Kigumi');
        $('titlebar-title').textContent = parts.join(' — ');
    }

    function render() {
        renderTitlebar();
        renderPanels();
        renderTabs();
        renderWelcome();
        renderStatus();
    }

    // ---------------------------------------------------------------------
    // Splitters
    // ---------------------------------------------------------------------

    function remember(key, value) {
        try {
            localStorage.setItem(key, String(value));
        } catch (_error) {
            // Not remembered, then.
        }
    }

    function recall(key) {
        try {
            return Number(localStorage.getItem(key)) || null;
        } catch (_error) {
            return null;
        }
    }

    function setSideSize(side, size) {
        const [min, max] = SIDE_LIMITS[side];
        const clamped = Math.max(min, Math.min(max, Math.round(size)));
        const dimension = side === 'bottom' ? 'height' : 'width';
        document.documentElement.style.setProperty(`--${side}-${dimension}`, `${clamped}px`);
        remember(`kigumi.${side}${dimension === 'height' ? 'Height' : 'Width'}`, clamped);
    }

    // The sources group's share of the center, as a percentage.
    function setCodeShare(percent) {
        const clamped = Math.max(15, Math.min(85, percent));
        document.documentElement.style.setProperty('--code-width', `${clamped}%`);
        remember('kigumi.codeShare', clamped);
    }

    function dragSplitter(splitter, onMove) {
        splitter.addEventListener('pointerdown', (event) => {
            splitter.setPointerCapture(event.pointerId);
            splitter.classList.add('is-dragging');
            $('shell').classList.add('is-resizing');
            const up = () => {
                splitter.classList.remove('is-dragging');
                $('shell').classList.remove('is-resizing');
                splitter.removeEventListener('pointermove', onMove);
                splitter.removeEventListener('pointerup', up);
            };
            splitter.addEventListener('pointermove', onMove);
            splitter.addEventListener('pointerup', up);
        });
    }

    function setupSplitters() {
        dragSplitter($('splitter-left'), (event) => setSideSize('left', event.clientX));
        dragSplitter($('splitter-right'), (event) => setSideSize('right', window.innerWidth - event.clientX));
        dragSplitter($('splitter-bottom'), (event) => setSideSize('bottom', $('main').getBoundingClientRect().bottom - event.clientY));
        dragSplitter($('splitter-group'), (event) => {
            const rect = $('groups').getBoundingClientRect();
            setCodeShare(((event.clientX - rect.left) / rect.width) * 100);
        });
        for (const side of ['left', 'right', 'bottom']) {
            const saved = recall(`kigumi.${side}${side === 'bottom' ? 'Height' : 'Width'}`);
            if (saved) setSideSize(side, saved);
        }
        const share = recall('kigumi.codeShare');
        if (share) setCodeShare(share);
    }

    // A click inside a panel's page goes to the iframe, never to the shell: notice the focus
    // moving into one, so the group it is in becomes the focused one.
    function followFrameFocus() {
        window.addEventListener('blur', () => setTimeout(() => {
            const focused = document.activeElement;
            if (!focused || focused.tagName !== 'IFRAME') return;
            const panel = state.panels.find((candidate) => candidate.id === focused.name);
            if (panel && panel.group && panel.group !== state.focusedGroup) {
                core.send({ type: 'tab:activate', id: panel.id });
            }
        }, 0));
    }

    // ---------------------------------------------------------------------
    // Quick pick
    // ---------------------------------------------------------------------

    const quickpick = { requestId: null, items: [], visible: [], selected: 0 };

    function closeQuickPick(index) {
        if (quickpick.requestId === null) return;
        core.send({ type: 'quickpick:result', requestId: quickpick.requestId, index });
        quickpick.requestId = null;
        $('quickpick').hidden = true;
    }

    function renderQuickPick() {
        const needle = $('quickpick-filter').value.trim().toLowerCase();
        quickpick.visible = [];
        let pendingSeparator = null;
        quickpick.items.forEach((item, index) => {
            if (item.separator) {
                pendingSeparator = item;
                return;
            }
            const text = `${item.label} ${item.description || ''} ${item.detail || ''}`.toLowerCase();
            if (needle && !text.includes(needle)) return;
            if (pendingSeparator) {
                quickpick.visible.push({ separator: pendingSeparator });
                pendingSeparator = null;
            }
            quickpick.visible.push({ item, index });
        });
        const choices = quickpick.visible.filter((row) => !row.separator);
        quickpick.selected = Math.max(0, Math.min(quickpick.selected, choices.length - 1));

        let choice = 0;
        const list = $('quickpick-list');
        list.replaceChildren(...quickpick.visible.map((row) => {
            if (row.separator) return el('div', 'separator', row.separator.label);
            const current = choice;
            choice += 1;
            const element = el('div', `item${current === quickpick.selected ? ' is-selected' : ''}`);
            element.setAttribute('role', 'option');
            element.setAttribute('aria-selected', current === quickpick.selected ? 'true' : 'false');
            element.append(el('span', 'item-label', row.item.label), el('span', 'item-description', row.item.description || ''));
            if (row.item.detail) element.append(el('span', 'item-detail', row.item.detail));
            element.addEventListener('click', () => closeQuickPick(row.index));
            return element;
        }));
        if (choices.length === 0) list.append(el('div', 'empty', 'No matching items'));
        const selected = list.querySelector('.is-selected');
        if (selected) selected.scrollIntoView({ block: 'nearest' });
    }

    function showQuickPick({ requestId, placeholder, items }) {
        if (quickpick.requestId !== null) closeQuickPick(null);
        Object.assign(quickpick, { requestId, items: items || [], selected: 0 });
        const filter = $('quickpick-filter');
        filter.placeholder = placeholder || '';
        filter.value = '';
        $('quickpick').hidden = false;
        renderQuickPick();
        filter.focus();
    }

    function setupQuickPick() {
        const filter = $('quickpick-filter');
        filter.addEventListener('input', () => {
            quickpick.selected = 0;
            renderQuickPick();
        });
        filter.addEventListener('keydown', (event) => {
            const choices = quickpick.visible.filter((row) => !row.separator);
            if (event.key === 'ArrowDown') {
                event.preventDefault();
                quickpick.selected = Math.min(choices.length - 1, quickpick.selected + 1);
                renderQuickPick();
            } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                quickpick.selected = Math.max(0, quickpick.selected - 1);
                renderQuickPick();
            } else if (event.key === 'Enter') {
                event.preventDefault();
                if (choices[quickpick.selected]) closeQuickPick(choices[quickpick.selected].index);
            } else if (event.key === 'Escape') {
                event.preventDefault();
                closeQuickPick(null);
            }
        });
        $('quickpick').addEventListener('pointerdown', (event) => {
            if (!event.target.closest('.picker')) closeQuickPick(null);
        });
    }

    // ---------------------------------------------------------------------

    function init() {
        if (!isMac) {
            $('key-open-folder').textContent = 'Ctrl+O';
            $('key-open-frame').textContent = 'Ctrl+Shift+O';
            $('key-browse').textContent = 'Ctrl+P';
        }
        $('status-workspace').addEventListener('click', () => command('openFolder'));
        $('status-log').addEventListener('click', () => command('openLog'));
        $('status-settings').addEventListener('click', () => command('openSettings'));
        $('status-autorefresh').addEventListener('click', () => command('run', 'kigumi.toggleAutoRefreshOnFileChange'));
        // The window is frameless only on macOS (hiddenInset); elsewhere the native title bar stays.
        document.body.classList.toggle('is-mac', /Mac/i.test(navigator.platform || navigator.userAgent));
        $('toggle-left').addEventListener('click', () => core.send({ type: 'layout:toggle', side: 'left' }));
        $('toggle-right').addEventListener('click', () => command('toggleAgent'));
        $('toggle-bottom').addEventListener('click', () => core.send({ type: 'layout:toggle', side: 'bottom' }));
        $('open-source').addEventListener('click', () => command('openSource', state.shown.view));
        $('open-view').addEventListener('click', () => command('openView', state.shown.code));
        setupSplitters();
        followFrameFocus();
        setupQuickPick();

        core.onMessage((message) => {
            if (!message) return;
            if (message.type === 'shell:state') {
                state = message;
                render();
            } else if (message.type === 'panel:message') {
                toPanel(message.id, message.message);
            } else if (message.type === 'quickpick:show') {
                showQuickPick(message);
            }
        });
        render();
        core.send({ type: 'shell:ready' });
    }

    init();
})();
