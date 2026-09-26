// The app shell: a fixed layout (left panel, center tabs, right panel, status
// bar) whose panels are iframes. Everything it shows comes from the core as
// `shell:state`; it talks to the core only through window.kigumiShell
// ({ send, onMessage }), which the host provides. See app-shell/.

(function () {
    'use strict';

    const core = window.kigumiShell;
    const $ = (id) => document.getElementById(id);
    const isMac = navigator.platform.toUpperCase().includes('MAC');
    const SIDE_LIMITS = { left: [180, 600], right: [240, 800] };

    let state = { panels: [], activeId: null };
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
            $(`slot-${panel.slot}`).append(iframe);
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
            frame.iframe.hidden = panel.slot === 'center' && panel.id !== state.activeId;
        }
        const hasRight = state.panels.some((panel) => panel.slot === 'right');
        $('slot-right').hidden = !hasRight;
        $('splitter-right').hidden = !hasRight;
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

    function renderTabs() {
        const tabs = state.panels.filter((panel) => panel.slot === 'center');
        $('tabs').replaceChildren(...tabs.map((tab) => {
            const active = tab.id === state.activeId;
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
        }));
    }

    function renderWelcome() {
        const hasTabs = state.panels.some((panel) => panel.slot === 'center');
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

    function render() {
        renderPanels();
        renderTabs();
        renderWelcome();
        renderStatus();
    }

    // ---------------------------------------------------------------------
    // Splitters
    // ---------------------------------------------------------------------

    function setSideWidth(side, width) {
        const [min, max] = SIDE_LIMITS[side];
        const clamped = Math.max(min, Math.min(max, Math.round(width)));
        document.documentElement.style.setProperty(`--${side}-width`, `${clamped}px`);
        try {
            localStorage.setItem(`kigumi.${side}Width`, String(clamped));
        } catch (_error) {
            // Width just isn't remembered.
        }
    }

    function setupSplitter(side) {
        const splitter = $(`splitter-${side}`);
        splitter.addEventListener('pointerdown', (event) => {
            splitter.setPointerCapture(event.pointerId);
            splitter.classList.add('is-dragging');
            $('shell').classList.add('is-resizing');
            const move = (moveEvent) => setSideWidth(side, side === 'left' ? moveEvent.clientX : window.innerWidth - moveEvent.clientX);
            const up = () => {
                splitter.classList.remove('is-dragging');
                $('shell').classList.remove('is-resizing');
                splitter.removeEventListener('pointermove', move);
                splitter.removeEventListener('pointerup', up);
            };
            splitter.addEventListener('pointermove', move);
            splitter.addEventListener('pointerup', up);
        });
        let saved = null;
        try {
            saved = Number(localStorage.getItem(`kigumi.${side}Width`));
        } catch (_error) {
            saved = null;
        }
        if (saved) setSideWidth(side, saved);
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
        setupSplitter('left');
        setupSplitter('right');
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
