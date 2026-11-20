// The phone layout: one file filling the screen, the project menu (the explorer, in its phone form)
// behind a button at the top right, and the agent in a sheet along the bottom. With no file open the
// project menu fills the screen; with no project open, the projects page does (the welcome area).
//
// Panels are told they are on a phone with `shell-ui:form` once they load; the viewer, explorer and
// agent each lay themselves out for it. A panel asks the layout for things with `shell-ui:` messages
// (panel-frames.js intercept).

import { SHELL_UI } from '../shell-ui.js';

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

function icon(name) {
    return el('span', `codicon codicon-${name}`);
}

/** Whether `filePath` is one of the open project's own files. `workspace.root` is its folder, where a
 * host shows something else as its `path` (the browser version shows the project's name). */
export function inProject(filePath, workspace) {
    const folder = workspace && (workspace.root || workspace.path);
    if (!filePath || !folder) return false;
    return filePath.startsWith(folder.endsWith('/') ? folder : `${folder}/`);
}

/**
 * @param {object} options
 * @param {{send: Function, renderWelcome?: Function}} options.core
 * @param {(name: string, ...args: any[]) => void} options.command
 * @param {object} options.frames  panel-frames.js
 */
export function createPhoneLayout({ core, command, frames }) {
    const root = el('div', 'phone');
    root.id = 'phone';
    const main = el('div', 'phone-main');
    const menu = el('div', 'phone-menu');
    const backdrop = el('div', 'phone-backdrop');
    const agent = el('div', 'phone-agent');
    const status = el('div', 'phone-status');
    status.hidden = true;
    status.setAttribute('role', 'status');
    const controls = el('div', 'phone-controls');
    const back = el('button', 'phone-button phone-back');
    back.type = 'button';
    back.append(icon('arrow-left'), el('span', '', 'Back'));
    const menuButton = el('button', 'phone-button phone-menu-button');
    menuButton.type = 'button';
    menuButton.setAttribute('aria-label', 'Project menu');
    menuButton.append(icon('menu'));
    const closeFile = el('button', 'phone-close-file');
    closeFile.type = 'button';
    closeFile.append(icon('close'), el('span', '', 'Close this frame'));
    menu.append(closeFile);
    controls.append(back, menuButton);
    root.append(main, menu, backdrop, agent, controls, status);
    document.body.append(root);
    // The projects page, drawn into the welcome area by the host (web-projects.js).
    main.append($('welcome'));

    let state = { panels: [], activeId: null };
    let menuOpen = false;
    let agentExpanded = false;
    let agentId = null;
    let agentAsked = false;
    // The last project file shown: where Back goes from an example, pattern or shared frame.
    let lastProjectFile = null;
    let lastActiveId = null;
    let pageZoomed = false;
    let statusTimer;

    const activePanel = () => state.panels.find((panel) => panel.slot === 'center' && panel.id === state.activeId) || null;

    function setMenuOpen(open) {
        menuOpen = open;
        render(state);
    }

    function setAgentExpanded(expanded) {
        agentExpanded = expanded;
        if (agentId) frames.send(agentId, { type: SHELL_UI.agentSheet, expanded });
        render(state);
    }

    menuButton.addEventListener('click', () => setMenuOpen(!menuOpen));
    backdrop.addEventListener('click', () => {
        if (agentExpanded) setAgentExpanded(false);
        if (menuOpen) setMenuOpen(false);
    });
    closeFile.addEventListener('click', () => {
        const active = activePanel();
        if (active) core.send({ type: 'tab:close', id: active.id });
        setMenuOpen(false);
    });
    back.addEventListener('click', () => {
        const active = activePanel();
        if (lastProjectFile) {
            command('run', 'kigumi.openFrameFromSidebar', lastProjectFile);
        } else if (active) {
            core.send({ type: 'tab:close', id: active.id });
        }
    });

    // The keyboard takes the bottom of the screen: keep the agent sheet above it.
    if (window.visualViewport) {
        const fit = () => {
            const zoomed = window.visualViewport.scale > 1.01;
            if (zoomed !== pageZoomed) {
                pageZoomed = zoomed;
                for (const panel of state.panels.filter((one) => one.slot === 'center')) {
                    frames.send(panel.id, { type: SHELL_UI.pageZoom, zoomed });
                }
            }
            const covered = zoomed ? 0 : Math.max(0, window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop);
            root.style.setProperty('--phone-keyboard', `${covered}px`);
        };
        fit();
        window.visualViewport.addEventListener('resize', fit);
        window.visualViewport.addEventListener('scroll', fit);
    }

    function render(next) {
        state = next;
        const active = activePanel();
        const hasFile = Boolean(active);
        const workspace = state.workspace || null;
        if (active && inProject(active.filePath, workspace)) lastProjectFile = active.filePath;
        if (!workspace) lastProjectFile = null;
        // Opening a file from the menu closes it.
        if (hasFile && menuOpen && active.id !== lastActiveId) menuOpen = false;
        lastActiveId = active ? active.id : null;

        const home = !hasFile && Boolean(workspace);
        root.classList.toggle('is-home', home);
        root.classList.toggle('is-menu-open', menuOpen && hasFile);
        root.classList.toggle('is-agent-expanded', agentExpanded);
        root.classList.toggle('has-file', hasFile);
        root.classList.toggle('has-agent', Boolean(agentId));
        backdrop.hidden = !(agentExpanded || (menuOpen && hasFile));
        menuButton.hidden = !hasFile;
        closeFile.hidden = !hasFile;
        back.hidden = menuOpen || !hasFile || inProject(active.filePath, workspace) || !active.filePath;
        $('welcome').hidden = hasFile || home;
        if (!hasFile && core.renderWelcome) core.renderWelcome(state, { el, command });

        const message = state.progress || (state.status && state.status.message) || '';
        const progress = Boolean(state.progress);
        if (status.textContent !== message || status.classList.contains('is-progress') !== progress) {
            clearTimeout(statusTimer);
            status.textContent = message;
            status.classList.toggle('is-progress', progress);
            status.hidden = !message;
            if (message && !progress) statusTimer = setTimeout(() => { status.hidden = true; }, 6000);
        }

        // The agent is always there on a phone: ask for it once a project is open.
        agentId = (state.panels.find((panel) => panel.slot === 'right') || {}).id || null;
        if (!agentId && workspace && !agentAsked) {
            agentAsked = true;
            command('toggleAgent');
        }
    }

    return {
        place(panel, iframe) {
            if (panel.slot === 'left') menu.prepend(iframe);
            else if (panel.slot === 'right') agent.append(iframe);
            else if (panel.slot === 'center') main.append(iframe);
            else { iframe.hidden = true; root.append(iframe); }
        },
        loaded(panel) {
            frames.send(panel.id, { type: SHELL_UI.form, form: 'phone' });
            if (panel.slot === 'center') frames.send(panel.id, { type: SHELL_UI.pageZoom, zoomed: pageZoomed });
            if (panel.slot === 'right') frames.send(panel.id, { type: SHELL_UI.agentSheet, expanded: agentExpanded });
        },
        shown(panel, current) {
            if (panel.slot === 'center') return panel.id === current.activeId;
            return panel.slot === 'left' || panel.slot === 'right';
        },
        intercept(type, message) {
            if (type === SHELL_UI.agentExpand) {
                if (!agentExpanded) setAgentExpanded(true);
                return true;
            }
            if (type === SHELL_UI.agentCollapse) {
                if (agentExpanded) setAgentExpanded(false);
                return true;
            }
            if (type === SHELL_UI.closeMenu) {
                setMenuOpen(false);
                return true;
            }
            if (type === SHELL_UI.agentDraft) {
                setMenuOpen(false);
                if (!agentExpanded) setAgentExpanded(true);
                if (agentId) frames.send(agentId, { type: SHELL_UI.agentDraft, text: String(message.text || '') });
                return true;
            }
            return false;
        },
        render,
    };
}
