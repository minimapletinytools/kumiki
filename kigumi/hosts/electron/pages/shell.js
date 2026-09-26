// The standalone window's chrome: reports where the sidebar and content views
// go, and draws the tab bar, welcome screen and status bar from main's state.

(function () {
    'use strict';

    const api = window.kigumiShell;
    const $ = (id) => document.getElementById(id);
    const isMac = navigator.platform.toUpperCase().includes('MAC');
    const MIN_SIDEBAR = 180;
    const MAX_SIDEBAR = 600;

    let state = { tabs: [], activeId: null };

    function rectOf(element) {
        const box = element.getBoundingClientRect();
        return { x: box.left, y: box.top, width: box.width, height: box.height };
    }

    function reportLayout() {
        api.send('shell:layout', { sidebar: rectOf($('sidebar-slot')), content: rectOf($('content-slot')) });
    }

    function setSidebarWidth(width) {
        const clamped = Math.max(MIN_SIDEBAR, Math.min(MAX_SIDEBAR, Math.round(width)));
        document.documentElement.style.setProperty('--sidebar-width', `${clamped}px`);
        try {
            localStorage.setItem('kigumi.sidebarWidth', String(clamped));
        } catch (_error) {
            // Width just isn't remembered.
        }
    }

    function el(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    }

    function icon(name) {
        return el('span', `codicon codicon-${name}`);
    }

    function renderTabs() {
        const bar = $('tabs');
        bar.replaceChildren(...state.tabs.map((tab) => {
            const button = el('div', `tab${tab.id === state.activeId ? ' is-active' : ''}`);
            button.setAttribute('role', 'tab');
            button.setAttribute('tabindex', '0');
            button.setAttribute('aria-selected', tab.id === state.activeId ? 'true' : 'false');
            button.title = tab.title;
            button.append(icon(tab.kind === 'log' ? 'output' : 'fish2-very-sad'), el('span', 'tab-title', tab.title || 'Kigumi'));
            const close = el('span', 'tab-close');
            close.setAttribute('role', 'button');
            close.setAttribute('aria-label', `Close ${tab.title}`);
            close.append(icon('close'));
            close.addEventListener('click', (event) => {
                event.stopPropagation();
                api.send('shell:closeTab', tab.id);
            });
            button.append(close);
            button.addEventListener('click', () => api.send('shell:activateTab', tab.id));
            button.addEventListener('auxclick', (event) => {
                if (event.button === 1) api.send('shell:closeTab', tab.id);
            });
            button.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    api.send('shell:activateTab', tab.id);
                }
            });
            return button;
        }));
    }

    function renderWelcome() {
        const welcome = $('welcome');
        welcome.hidden = state.tabs.length > 0;
        const actions = $('welcome-actions');
        const button = (label, onClick, secondary) => {
            const element = el('button', secondary ? 'secondary' : '', label);
            element.addEventListener('click', onClick);
            return element;
        };
        if (state.workspace) {
            $('welcome-lead').textContent = `Open a frame or pattern from the explorer to view it. Project: ${state.workspace.name}`;
            actions.replaceChildren(
                button('Open Frame File…', () => api.send('shell:command', 'openFrameFile')),
                button('Browse Patterns…', () => api.send('shell:command', 'run', 'kigumi.browsePatterns'), true),
            );
        } else {
            $('welcome-lead').textContent = 'Open a project folder to find its frames and patterns.';
            actions.replaceChildren(button('Open Folder…', () => api.send('shell:command', 'openFolder')));
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

        const autoRefresh = $('status-autorefresh');
        autoRefresh.replaceChildren(icon(state.autoRefresh ? 'sync' : 'sync-ignored'), document.createTextNode(state.autoRefresh ? 'Auto refresh' : 'Manual refresh'));

        $('status-log-badge').hidden = !state.logBadge;
        $('status-version').textContent = state.version ? `v${state.version}` : '';
    }

    function render() {
        renderTabs();
        renderWelcome();
        renderStatus();
    }

    function setupSplitter() {
        const splitter = $('splitter');
        splitter.addEventListener('pointerdown', (event) => {
            splitter.setPointerCapture(event.pointerId);
            splitter.classList.add('is-dragging');
            const move = (moveEvent) => setSidebarWidth(moveEvent.clientX);
            const up = () => {
                splitter.classList.remove('is-dragging');
                splitter.removeEventListener('pointermove', move);
                splitter.removeEventListener('pointerup', up);
            };
            splitter.addEventListener('pointermove', move);
            splitter.addEventListener('pointerup', up);
        });
    }

    function init() {
        let savedWidth = null;
        try {
            savedWidth = Number(localStorage.getItem('kigumi.sidebarWidth'));
        } catch (_error) {
            savedWidth = null;
        }
        if (savedWidth) setSidebarWidth(savedWidth);

        if (!isMac) {
            $('key-open-folder').textContent = 'Ctrl+O';
            $('key-open-frame').textContent = 'Ctrl+Shift+O';
            $('key-browse').textContent = 'Ctrl+P';
        }

        $('status-workspace').addEventListener('click', () => api.send('shell:command', 'openFolder'));
        $('status-log').addEventListener('click', () => api.send('shell:command', 'openLog'));
        $('status-autorefresh').addEventListener('click', () => api.send('shell:command', 'run', 'kigumi.toggleAutoRefreshOnFileChange'));
        setupSplitter();

        const observer = new ResizeObserver(reportLayout);
        observer.observe($('sidebar-slot'));
        observer.observe($('content-slot'));
        window.addEventListener('resize', reportLayout);

        api.on('shell:state', (next) => {
            state = next;
            render();
            reportLayout();
        });
        render();
        reportLayout();
        api.send('shell:ready');
    }

    init();
})();
