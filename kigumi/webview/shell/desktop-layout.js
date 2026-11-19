// The desktop layout: left panel, center tabs, bottom panel, right panel and status bar, in the
// markup shell.html holds, with splitters between them.

const $ = (id) => document.getElementById(id);
const isMac = navigator.platform.toUpperCase().includes('MAC');
// The right side's least width is the agent panel's (agent.css, .agent-panel).
const SIDE_LIMITS = { left: [180, 600], right: [280, 800], bottom: [80, 800] };

export function el(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

export function icon(name) {
    return el('span', `codicon codicon-${name}`);
}

/**
 * @param {object} options
 * @param {{send: Function, renderWelcome?: Function}} options.core
 * @param {(name: string, ...args: any[]) => void} options.command  a shell command for the core
 */
export function createDesktopLayout({ core, command }) {
    // ---------------------------------------------------------------------
    // Splitters
    // ---------------------------------------------------------------------

    // The bottom panel's size is its height; a side's, its width.
    function sizeKey(side) {
        return side === 'bottom' ? 'Height' : 'Width';
    }

    function setSideWidth(side, width) {
        const [min, max] = SIDE_LIMITS[side];
        const clamped = Math.max(min, Math.min(max, Math.round(width)));
        document.documentElement.style.setProperty(`--${side}-${sizeKey(side).toLowerCase()}`, `${clamped}px`);
        try {
            localStorage.setItem(`kigumi.${side}${sizeKey(side)}`, String(clamped));
        } catch (_error) {
            // Width just isn't remembered.
        }
    }

    // The drag in progress, if any: ends it. While one is in progress the panels take no clicks
    // (.is-resizing), so every way a drag can end has to end it.
    let endDrag = null;

    function setupSplitter(side) {
        const splitter = $(`splitter-${side}`);
        splitter.addEventListener('pointerdown', (event) => {
            if (endDrag) endDrag();
            splitter.setPointerCapture(event.pointerId);
            splitter.classList.add('is-dragging');
            $('shell').classList.add('is-resizing');
            const move = (moveEvent) => {
                // The button came up somewhere this never heard about.
                if (moveEvent.buttons === 0) return end();
                setSideWidth(side, {
                    left: () => moveEvent.clientX,
                    right: () => window.innerWidth - moveEvent.clientX,
                    bottom: () => document.querySelector('.main').getBoundingClientRect().bottom - moveEvent.clientY,
                }[side]());
            };
            const ends = ['pointerup', 'pointercancel', 'lostpointercapture'];
            const end = () => {
                endDrag = null;
                splitter.classList.remove('is-dragging');
                $('shell').classList.remove('is-resizing');
                splitter.removeEventListener('pointermove', move);
                for (const name of ends) splitter.removeEventListener(name, end);
                window.removeEventListener('blur', end);
                if (splitter.hasPointerCapture(event.pointerId)) splitter.releasePointerCapture(event.pointerId);
            };
            endDrag = end;
            splitter.addEventListener('pointermove', move);
            for (const name of ends) splitter.addEventListener(name, end);
            // Switching away mid-drag: the release goes to another window.
            window.addEventListener('blur', end);
        });
        let saved = null;
        try {
            saved = Number(localStorage.getItem(`kigumi.${side}${sizeKey(side)}`));
        } catch (_error) {
            saved = null;
        }
        if (saved) setSideWidth(side, saved);
    }

    // ---------------------------------------------------------------------
    // Rendering
    // ---------------------------------------------------------------------

    function renderSlots(state) {
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
        $('update-available').hidden = !state.update;
        $('update-available').title = state.update ? `Kigumi ${state.update.version} is available` : '';

        const hasBottom = state.panels.some((panel) => panel.slot === 'bottom');
        const showBottom = hasBottom && layout.bottom;
        $('slot-bottom').hidden = !showBottom;
        $('splitter-bottom').hidden = !showBottom;
        $('toggle-bottom').hidden = !hasBottom;
        $('toggle-bottom').classList.toggle('is-active', showBottom);
    }

    function renderTabs(state) {
        const tabs = state.panels.filter((panel) => panel.slot === 'center');
        // No tabs, no strip: the welcome page fills the space.
        $('tabs').parentElement.hidden = tabs.length === 0;
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

    function renderWelcome(state) {
        const hasTabs = state.panels.some((panel) => panel.slot === 'center');
        $('welcome').hidden = hasTabs;
        // A host may draw its own page here: the browser version's projects (hosts/pyodide/page/web-projects.js).
        if (core.renderWelcome && core.renderWelcome(state, { el, command })) {
            return;
        }
        const button = (label, onClick, secondary) => {
            const element = el('button', secondary ? 'secondary' : '', label);
            element.addEventListener('click', onClick);
            return element;
        };
        if (state.workspace) {
            $('welcome-lead').textContent = `Open a frame or pattern from the explorer to view it. Project: ${state.workspace.name}`;
            $('welcome-actions').replaceChildren(
                button('Browse Patterns', () => command('browsePatterns')),
                button('Browse Examples', () => command('browseExamples'), true),
            );
        } else {
            $('welcome-lead').textContent = 'Make a new project, or open one, to find its frames and patterns.';
            $('welcome-actions').replaceChildren(
                button('New Project…', () => command('newProject')),
                button('Open Project…', () => command('openFolder'), true),
            );
        }
        const recent = state.recentFolders || [];
        $('welcome-recent').hidden = recent.length === 0;
        $('welcome-recent-list').replaceChildren(...recent.map((folder) => {
            const item = el('li');
            const link = el('button', 'welcome-recent-folder', folder.name);
            link.title = folder.path;
            link.addEventListener('click', () => command('openRecentFolder', folder.path));
            item.append(link, el('span', 'welcome-recent-path', folder.shown || folder.path));
            return item;
        }));
    }

    function renderStatus(state) {
        const workspace = $('status-workspace');
        workspace.replaceChildren(icon('folder'), document.createTextNode(state.workspace ? state.workspace.name : 'Open Project…'));
        workspace.title = state.workspace ? state.workspace.path : 'Open project';

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
        // The browser version: what it is, and where to find out more.
        $('status-about').hidden = !state.web;
    }

    function renderTitlebar(state) {
        const active = state.panels.find((panel) => panel.slot === 'center' && panel.id === state.activeId);
        const parts = [];
        if (active && active.title) parts.push(active.title);
        if (state.workspace && state.workspace.name) parts.push(state.workspace.name);
        parts.push('Kigumi');
        $('titlebar-title').textContent = parts.join(' — ');
    }

    // The welcome page's shortcut labels: the core's, or hidden where it has none.
    function renderKeyLabels(state) {
        const keys = state.keys || null;
        const labels = (keys && keys.labels) || {};
        for (const element of document.querySelectorAll('.welcome-keys [data-command]')) {
            const label = labels[element.dataset.command];
            element.hidden = keys !== null && !label;
            const kbd = element.querySelector('kbd');
            if (kbd && label) kbd.textContent = label;
        }
    }

    // ---------------------------------------------------------------------

    if (!isMac) {
        $('key-go-to-file').textContent = 'Ctrl+P';
        $('key-open-in-viewer').textContent = 'Ctrl+Shift+O';
        $('key-open-current-in-viewer').textContent = 'Ctrl+O';
    }
    $('status-workspace').addEventListener('click', () => command('openFolder'));
    $('status-log').addEventListener('click', () => command('openLog'));
    $('status-about').addEventListener('click', () => command('web:about'));
    $('status-settings').addEventListener('click', () => command('openSettings'));
    $('status-autorefresh').addEventListener('click', () => command('run', 'kigumi.toggleAutoRefreshOnFileChange'));
    // The window is frameless only on macOS (hiddenInset); elsewhere the native title bar stays.
    document.body.classList.toggle('is-mac', /Mac/i.test(navigator.platform || navigator.userAgent));
    $('toggle-left').addEventListener('click', () => core.send({ type: 'layout:toggle', side: 'left' }));
    $('toggle-right').addEventListener('click', () => command('toggleAgent'));
    $('toggle-bottom').addEventListener('click', () => core.send({ type: 'layout:toggle', side: 'bottom' }));
    $('update-available').addEventListener('click', () => command('showUpdate'));
    setupSplitter('left');
    setupSplitter('right');
    setupSplitter('bottom');

    return {
        place(panel, iframe) {
            $(`slot-${panel.slot}`).append(iframe);
        },
        shown(panel, state) {
            return panel.slot !== 'center' || panel.id === state.activeId;
        },
        render(state) {
            renderTitlebar(state);
            renderSlots(state);
            renderTabs(state);
            renderWelcome(state);
            renderStatus(state);
            renderKeyLabels(state);
        },
    };
}
