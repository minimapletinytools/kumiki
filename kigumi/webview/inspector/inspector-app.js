// The inspector's page: the current view's member list and log, drawn from what the app relays
// (view-inspector.js). Clicking a member selects it in the view; shift or cmd adds to the selection.

(function () {
    'use strict';

    const api = acquireVsCodeApi();
    const $ = (id) => document.getElementById(id);
    const saved = api.getState() || {};

    const ui = {
        tab: saved.tab === 'log' ? 'log' : 'members',
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
            state = message.state || null;
            logLines = [...(message.log || [])];
            renderMembers();
            renderLog();
        } else if (message.type === 'inspector:state') {
            state = message.state || null;
            renderMembers();
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
    showTab(ui.tab);
    renderMembers();
    api.postMessage({ type: 'inspector:ready' });
})();
