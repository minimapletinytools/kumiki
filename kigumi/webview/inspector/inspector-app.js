// The inspector's page: the current view's member list, parameters, options and log, drawn from
// what the app relays (view-inspector.js). Clicking a member selects it in the view; shift or cmd
// adds to the selection. The parameters and options are the view's own panels
// (viewer-panels.js), drawn against a stand-in that sends each change back to the view.

import { html, render } from '../vendor/lit.min.js';
import {
    ViewerSettingsPanel, ViewerKiwariPanel, usePanelRuntime, panelStandIn,
} from '../viewer-panels.js';

{
    const TABS = ['options', 'parameters', 'members', 'log'];
    const api = acquireVsCodeApi();
    const $ = (id) => document.getElementById(id);
    const saved = api.getState() || {};

    const ui = {
        tab: TABS.includes(saved.tab) ? saved.tab : 'options',
        options: { roughLength: false, nominal: false, csg: false, tags: false, ...(saved.options || {}) },
    };
    let state = null;
    let logLines = [];

    function remember() {
        api.setState({ tab: ui.tab, options: ui.options });
    }

    // ---------------------------------------------------------------------
    // Tabs

    function showTab(tab) {
        ui.tab = tab;
        for (const button of document.querySelectorAll('.inspector-tab')) {
            button.classList.toggle('is-active', button.dataset.tab === tab);
        }
        for (const element of document.querySelectorAll('[data-for]')) {
            element.hidden = element.dataset.for !== tab;
        }
        for (const element of document.querySelectorAll('.inspector-body')) {
            element.hidden = element.dataset.tab !== tab;
        }
        if (tab === 'log') scrollLogToEnd();
        remember();
    }

    // ---------------------------------------------------------------------
    // Members

    function cell(text, className) {
        const td = document.createElement('td');
        td.textContent = text === null || text === undefined ? '—' : String(text);
        if (className) td.className = className;
        return td;
    }

    function renderMembers() {
        const members = (state && state.members) || [];
        const selected = new Set((state && state.selection) || []);
        $('members-empty').hidden = members.length > 0;
        $('members').hidden = members.length === 0;
        $('members-count').textContent = members.length ? String(members.length) : '';

        const { roughLength, nominal } = ui.options;
        $('col-length').textContent = roughLength ? 'Rough length' : 'Length';
        $('col-width').textContent = nominal ? 'Width (nominal)' : 'Width';
        $('col-height').textContent = nominal ? 'Height (nominal)' : 'Height';
        $('members').classList.toggle('hide-tags', !ui.options.tags);
        $('members').classList.toggle('hide-csg', !ui.options.csg);

        $('member-rows').replaceChildren(...members.map((member, index) => {
            const row = document.createElement('tr');
            row.dataset.key = member.key;
            row.classList.toggle('is-selected', selected.has(member.key));
            const tags = cell(member.tags.length ? member.tags.join(', ') : null, 'dim');
            tags.dataset.col = 'tags';
            const csg = cell(member.csgNodes, 'dim');
            csg.dataset.col = 'csg';
            const features = cell(member.csgFeatures, 'dim');
            features.dataset.col = 'csg';
            row.append(
                cell(index + 1, 'dim'),
                cell(member.type === 'accessory' ? 'Accessory' : 'Timber'),
                cell(member.name),
                tags,
                cell(roughLength ? member.roughLength : member.length),
                cell(nominal ? member.nominalWidth : member.width),
                cell(nominal ? member.nominalHeight : member.height),
                csg,
                features,
            );
            return row;
        }));
    }

    $('member-rows').addEventListener('click', (event) => {
        const row = event.target.closest('tr[data-key]');
        if (!row) return;
        api.postMessage({
            type: 'inspector:select',
            memberKeys: [row.dataset.key],
            additive: event.shiftKey || event.metaKey || event.ctrlKey,
        });
    });

    for (const input of document.querySelectorAll('[data-option]')) {
        input.checked = Boolean(ui.options[input.dataset.option]);
        input.addEventListener('change', () => {
            ui.options[input.dataset.option] = input.checked;
            remember();
            renderMembers();
        });
    }

    // ---------------------------------------------------------------------
    // Parameters and options

    let t = window.KigumiI18n.createTranslator({});
    let panelsSnapshot = null;
    let settingsPanel = null;
    // The last call sent to the view on show. An answer older than that is to an earlier
    // keystroke, and drawing it would undo what was typed since.
    let nextCallSeq = 0;
    let awaitedSeq = 0;

    function useStrings(strings) {
        t = window.KigumiI18n.createTranslator(strings || {});
        usePanelRuntime({ html, t, KigumiUnits: window.KigumiUnits, KigumiKiwariValues: window.KigumiKiwariValues });
    }

    function callView(method, args) {
        nextCallSeq = Math.max(nextCallSeq + 1, Date.now());
        awaitedSeq = nextCallSeq;
        api.postMessage({ type: 'inspector:call', method, args, seq: nextCallSeq });
    }

    function renderViewPanels() {
        if (!panelsSnapshot) {
            settingsPanel = null;
            render(html`<p class="empty">Open a frame to see its parameters.</p>`, $('parameters-panel'));
            render(html`<p class="empty">Open a frame to see its options.</p>`, $('options-panel'));
            return;
        }
        const app = panelStandIn(panelsSnapshot, callView);
        settingsPanel = new ViewerSettingsPanel(app);
        render(settingsPanel.render(), $('options-panel'));
        settingsPanel.syncControls($('options-panel'));
        const parameters = new ViewerKiwariPanel(app).render();
        render(parameters || html`<p class="empty">This frame takes no parameters.</p>`, $('parameters-panel'));
    }

    for (const type of ['change', 'input', 'click']) {
        $('options-panel').addEventListener(type, (event) => {
            if (settingsPanel) settingsPanel.handleEvent(event);
        });
    }

    function takeState(nextState, { fresh = false } = {}) {
        state = nextState || null;
        const panels = state && state.panels;
        if (fresh || !panels || (state.panelCallSeq || 0) >= awaitedSeq) {
            panelsSnapshot = panels || null;
            renderViewPanels();
        }
        renderMembers();
    }

    // ---------------------------------------------------------------------
    // Log

    function classFor(line) {
        if (/error|traceback|failed/i.test(line)) return 'line-error';
        if (/warn/i.test(line)) return 'line-warn';
        return '';
    }

    function lineElement(line) {
        const element = document.createElement('div');
        element.textContent = line;
        const className = classFor(line);
        if (className) element.className = className;
        return element;
    }

    function matches(line) {
        const needle = $('log-filter').value.trim().toLowerCase();
        return !needle || line.toLowerCase().includes(needle);
    }

    function scrollLogToEnd() {
        const body = $('log-lines').parentElement;
        if ($('log-follow').checked) body.scrollTop = body.scrollHeight;
    }

    function renderLog() {
        $('log-lines').replaceChildren(...logLines.filter(matches).map(lineElement));
        scrollLogToEnd();
    }

    $('log-filter').addEventListener('input', renderLog);
    $('log-clear').addEventListener('click', () => {
        logLines = [];
        renderLog();
        api.postMessage({ type: 'inspector:clearLog' });
    });

    // ---------------------------------------------------------------------

    window.addEventListener('message', (event) => {
        const message = event.data;
        if (!message || typeof message.type !== 'string') return;
        if (message.type === 'inspector:view') {
            $('view-title').textContent = message.view ? message.view.title : '';
            $('view-title').title = message.view ? message.view.filePath : '';
            $('members-empty').textContent = message.view
                ? 'Waiting for the view to build…'
                : 'Open a frame to see its members.';
            useStrings(message.strings);
            awaitedSeq = 0;
            takeState(message.state, { fresh: true });
            logLines = [...(message.log || [])];
            renderLog();
        } else if (message.type === 'inspector:state') {
            takeState(message.state);
        } else if (message.type === 'inspector:log') {
            logLines.push(message.line);
            if (logLines.length > 5000) logLines.splice(0, logLines.length - 5000);
            if (matches(message.line)) {
                $('log-lines').append(lineElement(message.line));
                scrollLogToEnd();
            }
        }
    });

    for (const button of document.querySelectorAll('.inspector-tab')) {
        button.addEventListener('click', () => showTab(button.dataset.tab));
    }
    useStrings({});
    showTab(ui.tab);
    renderMembers();
    renderViewPanels();
    api.postMessage({ type: 'inspector:ready' });
}
