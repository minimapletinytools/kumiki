// The phone layout: one file filling the screen, the project menu (the explorer, in its phone form)
// behind a button at the top right, and the agent in a sheet along the bottom. With no file open the
// project menu fills the screen; with no project open, the projects page does (the welcome area).
//
// Panels are told they are on a phone with `shell-ui:form` once they load; the viewer, explorer and
// agent each lay themselves out for it. A panel asks the layout for things with `shell-ui:` messages
// (panel-frames.js intercept).

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

/** Whether `filePath` is one of the open project's own files. */
export function inProject(filePath, workspace) {
    if (!filePath || !workspace || !workspace.path) return false;
    const root = workspace.path.endsWith('/') ? workspace.path : `${workspace.path}/`;
    return filePath.startsWith(root);
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

    const activePanel = () => state.panels.find((panel) => panel.slot === 'center' && panel.id === state.activeId) || null;

    function setMenuOpen(open) {
        menuOpen = open;
        render(state);
    }

    function setAgentExpanded(expanded) {
        agentExpanded = expanded;
        if (agentId) frames.send(agentId, { type: 'shell-ui:agent-sheet', expanded });
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
            const covered = Math.max(0, window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop);
            root.style.setProperty('--phone-keyboard', `${covered}px`);
        };
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
        back.hidden = !hasFile || inProject(active.filePath, workspace) || !active.filePath;
        $('welcome').hidden = hasFile || home;
        if (!hasFile && core.renderWelcome) core.renderWelcome(state, { el, command });

        const message = state.progress || (state.status && state.status.message) || '';
        status.textContent = message;
        status.hidden = !message;

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
            frames.send(panel.id, { type: 'shell-ui:form', form: 'phone' });
        },
        shown(panel, current) {
            if (panel.slot === 'center') return panel.id === current.activeId;
            return panel.slot === 'left' || panel.slot === 'right';
        },
        intercept(type, message) {
            if (type === 'shell-ui:agent-expand') {
                if (!agentExpanded) setAgentExpanded(true);
                return true;
            }
            if (type === 'shell-ui:agent-collapse') {
                if (agentExpanded) setAgentExpanded(false);
                return true;
            }
            if (type === 'shell-ui:close-menu') {
                setMenuOpen(false);
                return true;
            }
            return false;
        },
        render,
    };
}
