// The agent panel's page: the conversation as it streams in, the model's thinking and tool calls
// (each opens to show what went in and came out), what it is doing now, and asking before a tool
// that changes something runs. The conversation itself lives in the app (see
// agent/agent-session.js); this only draws it and sends what the user types.
(function () {
    'use strict';

    const vscode = window.acquireVsCodeApi();
    const $ = (id) => document.getElementById(id);

    const messagesEl = $('messages');
    const inputEl = $('prompt-input');
    const sendBtn = $('send-btn');
    const clearBtn = $('btn-clear');
    const modelSelect = $('model-select');
    const routeNote = $('route-note');
    const activity = $('activity');
    const settingsBtn = $('btn-settings');
    const settingsMenu = $('settings-menu');
    const modeRadios = [...document.querySelectorAll('input[name="permission-mode"]')];
    const alwaysAllowed = $('always-allowed');
    const startupToggle = $('setting-startup');
    const bypassBanner = $('bypass-banner');
    const historyBtn = $('btn-history');
    const historyMenu = $('history-menu');
    const historyList = $('history-list');
    const contextMeter = $('context-meter');
    const activityLabel = $('activity-label');
    const welcomeHtml = $('welcome').outerHTML;

    let busy = false;
    const toolChips = new Map();

    function scrollToEnd() {
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function add(className, text) {
        const welcome = $('welcome');
        if (welcome) welcome.remove();
        const element = document.createElement('div');
        element.className = className;
        if (text !== undefined) element.textContent = text;
        messagesEl.appendChild(element);
        scrollToEnd();
        return element;
    }

    /** What the agent is doing now, under the conversation while it works. */
    function setActivity(label) {
        activityLabel.textContent = label;
    }

    // Thinking streamed in a row is one block, closed unless opened, until something else comes.
    let thinking = null;

    function endThinking() {
        if (!thinking) return;
        thinking.querySelector('summary').textContent = 'Thought';
        thinking.classList.remove('is-live');
        thinking = null;
    }

    function appendReasoning(text) {
        if (!thinking) {
            thinking = add('thinking is-live');
            const details = document.createElement('details');
            const summary = document.createElement('summary');
            summary.textContent = 'Thinking';
            const body = document.createElement('div');
            body.className = 'thinking-body';
            details.append(summary, body);
            thinking.appendChild(details);
        }
        thinking.querySelector('.thinking-body').textContent += text;
        setActivity('Thinking');
        scrollToEnd();
    }

    // Streamed text joins the reply being written, until something else (a tool) comes between.
    function appendText(text) {
        endThinking();
        const last = messagesEl.lastElementChild;
        const bubble = last && last.classList.contains('assistant') ? last : add('message-bubble assistant md', '');
        // The reply so far, rendered again as it grows (window.KigumiMarkdown, markdown.js).
        bubble.dataset.raw = (bubble.dataset.raw || '') + text;
        bubble.replaceChildren(window.KigumiMarkdown.render(bubble.dataset.raw));
        setActivity('Writing');
        scrollToEnd();
    }

    function summarise(input) {
        if (!input || typeof input !== 'object') return '';
        const first = Object.values(input).find((value) => typeof value === 'string');
        return first ? first.split('\n')[0].slice(0, 80) : '';
    }

    function pre(className, text) {
        const element = document.createElement('pre');
        element.className = className;
        element.textContent = text;
        return element;
    }

    /** A line diff of `before` and `after` (longest common subsequence): [[' '|'-'|'+', line], ...]. */
    function lineDiff(before, after) {
        const a = before.split('\n');
        const b = after.split('\n');
        if (a.length * b.length > 250000) {
            return [...a.map((line) => ['-', line]), ...b.map((line) => ['+', line])];
        }
        const common = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
        for (let i = a.length - 1; i >= 0; i--) {
            for (let j = b.length - 1; j >= 0; j--) {
                common[i][j] = a[i] === b[j] ? common[i + 1][j + 1] + 1 : Math.max(common[i + 1][j], common[i][j + 1]);
            }
        }
        const out = [];
        let i = 0;
        let j = 0;
        while (i < a.length || j < b.length) {
            if (i < a.length && j < b.length && a[i] === b[j]) {
                out.push([' ', a[i++]]);
                j++;
            } else if (j < b.length && (i === a.length || common[i][j + 1] > common[i + 1][j])) {
                // On a tie the removed line goes first, as diffs are read.
                out.push(['+', b[j++]]);
            } else {
                out.push(['-', a[i++]]);
            }
        }
        return out;
    }

    function diffView(before, after) {
        const view = document.createElement('div');
        view.className = 'diff';
        for (const [op, line] of lineDiff(before, after).slice(0, 400)) {
            const row = document.createElement('div');
            row.className = op === '+' ? 'diff-add' : op === '-' ? 'diff-del' : 'diff-same';
            row.textContent = `${op} ${line}`;
            view.appendChild(row);
        }
        return view;
    }

    /** What a tool was given: an edit as a diff, a written file as its text, else the input. */
    function toolInputView(name, input) {
        if (name === 'edit_file' && input && typeof input.old_string === 'string') {
            const view = diffView(input.old_string, input.new_string || '');
            view.prepend(Object.assign(document.createElement('div'), { className: 'diff-file', textContent: input.file_path || '' }));
            return view;
        }
        if (name === 'write_file' && input && typeof input.content === 'string') {
            const view = diffView('', input.content);
            view.prepend(Object.assign(document.createElement('div'), { className: 'diff-file', textContent: `${input.file_path || ''} (whole file)` }));
            return view;
        }
        return pre('tool-input', JSON.stringify(input || {}, null, 2).slice(0, 4000));
    }

    // A chip that opens to show what the tool was given and what it gave back.
    function addTool(id, name, input) {
        endThinking();
        const shown = name.replace(/^mcp__kigumi__/, '');
        const chip = add('tool-chip is-running');
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        const label = document.createElement('span');
        label.className = 'tool-name';
        label.textContent = shown;
        const detail = document.createElement('span');
        detail.className = 'tool-detail';
        detail.textContent = summarise(input);
        summary.append(label, detail);
        const body = document.createElement('div');
        body.className = 'tool-body';
        body.appendChild(toolInputView(shown, input));
        details.append(summary, body);
        chip.appendChild(details);
        toolChips.set(id, chip);
        setActivity(`Running ${shown}`);
    }

    function finishTool(id, isError, text) {
        const chip = toolChips.get(id);
        if (!chip) return;
        chip.classList.remove('is-running');
        chip.classList.add(isError ? 'is-error' : 'is-done');
        chip.querySelector('.tool-body').appendChild(pre('tool-output', text || '(nothing)'));
        setActivity('Thinking');
    }

    function askPermission(requestId, toolName, input) {
        const card = add('permission-card');
        const question = document.createElement('div');
        question.textContent = `Allow ${toolName.replace(/^mcp__kigumi__/, '')}?`;
        const shown = toolName.replace(/^mcp__kigumi__/, '');
        const detail = toolInputView(shown, input);
        const buttons = document.createElement('div');
        buttons.className = 'permission-buttons';
        for (const [label, allow, always] of [['Allow', true, false], [`Always allow ${shown}`, true, true], ['Deny', false, false]]) {
            const button = document.createElement('button');
            button.textContent = label;
            button.className = always ? 'always' : allow ? 'allow' : 'deny';
            button.addEventListener('click', () => {
                vscode.postMessage({ type: 'agent:permissionAnswer', requestId, allow, always });
                setActivity('Thinking');
                card.classList.add(allow ? 'is-allowed' : 'is-denied');
                buttons.remove();
            });
            buttons.appendChild(button);
        }
        card.append(question, detail, buttons);
        setActivity('Waiting for you');
    }

    function setBusy(next) {
        busy = next;
        sendBtn.title = busy ? 'Stop' : 'Send message';
        sendBtn.firstElementChild.className = `codicon codicon-${busy ? 'debug-stop' : 'send'}`;
        activity.hidden = !busy;
        if (busy) setActivity('Thinking');
        else endThinking();
    }

    let lastSent = '';

    // While the agent works, a request waits its turn (agent:queued) rather than starting.
    function sendPrompt(text) {
        const prompt = (text !== undefined ? text : inputEl.value).trim();
        if (!prompt) return;
        if (!busy) add('message-bubble user', prompt);
        lastSent = prompt;
        inputEl.value = '';
        inputEl.style.height = 'auto';
        vscode.postMessage({ type: 'agent:prompt', text: prompt });
    }

    // Enter sends; Escape stops the agent; Up, in an empty box, brings back the last request to edit.
    inputEl.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendPrompt();
        } else if (event.key === 'Escape' && busy) {
            event.preventDefault();
            vscode.postMessage({ type: 'agent:stop' });
        } else if (event.key === 'ArrowUp' && !inputEl.value && lastSent) {
            event.preventDefault();
            inputEl.value = lastSent;
        }
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && busy && event.target !== inputEl) vscode.postMessage({ type: 'agent:stop' });
    });

    const queuedBubbles = new Map();

    function showQueued(id, text) {
        const bubble = add('message-bubble user is-queued', '');
        const label = Object.assign(document.createElement('span'), { textContent: text });
        const tag = Object.assign(document.createElement('span'), { className: 'queued-tag', textContent: 'waiting' });
        const cancel = Object.assign(document.createElement('button'), { type: 'button', className: 'queued-cancel', title: 'Don\'t send', textContent: '×' });
        cancel.addEventListener('click', () => vscode.postMessage({ type: 'agent:unqueue', id }));
        bubble.append(label, tag, cancel);
        queuedBubbles.set(id, bubble);
    }

    // A request that has started, or that was dropped: no longer shown as waiting.
    function dropQueued(id) {
        const bubble = queuedBubbles.get(id);
        if (bubble) bubble.remove();
        queuedBubbles.delete(id);
    }

    // After a turn that changed files: a way to put them back.
    const undoNotes = new Map();

    function showCheckpoint(turn, files) {
        endThinking();
        const note = add('checkpoint-note');
        const text = Object.assign(document.createElement('span'), {
            textContent: `Changed ${files.length} file${files.length === 1 ? '' : 's'}: ${files.join(', ')}`,
        });
        const undo = Object.assign(document.createElement('button'), { type: 'button', className: 'link-btn', textContent: 'Undo' });
        undo.title = 'Put these files back as they were before this request (and undo later requests\' changes too)';
        undo.addEventListener('click', () => vscode.postMessage({ type: 'agent:restore', turn }));
        note.append(text, ' · ', undo);
        undoNotes.set(turn, note);
    }

    function showRestored(turn) {
        for (const [noted, note] of undoNotes) {
            if (noted >= turn) {
                note.classList.add('is-undone');
                const button = note.querySelector('button');
                if (button) button.remove();
                undoNotes.delete(noted);
            }
        }
    }
    inputEl.addEventListener('input', () => {
        inputEl.style.height = 'auto';
        inputEl.style.height = `${Math.min(inputEl.scrollHeight, 200)}px`;
    });

    sendBtn.addEventListener('click', () => (busy ? vscode.postMessage({ type: 'agent:stop' }) : sendPrompt()));

    function resetMessages() {
        toolChips.clear();
        thinking = null;
        messagesEl.innerHTML = welcomeHtml;
    }

    clearBtn.addEventListener('click', () => {
        vscode.postMessage({ type: 'agent:clear' });
        resetMessages();
        historyMenu.hidden = true;
    });

    // Past conversations: open one, or delete it.
    historyBtn.addEventListener('click', () => {
        historyMenu.hidden = !historyMenu.hidden;
        settingsMenu.hidden = true;
        if (!historyMenu.hidden) vscode.postMessage({ type: 'agent:listConversations' });
    });

    function ago(time) {
        const minutes = Math.round((Date.now() - new Date(time).getTime()) / 60000);
        if (minutes < 1) return 'just now';
        if (minutes < 60) return `${minutes} min ago`;
        if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
        return new Date(time).toLocaleDateString();
    }

    function showConversations({ items = [], current }) {
        if (!items.length) {
            historyList.replaceChildren(Object.assign(document.createElement('div'), { className: 'history-empty', textContent: 'No past conversations yet.' }));
            return;
        }
        historyList.replaceChildren(...items.map((item) => {
            const row = document.createElement('div');
            row.className = 'history-item' + (item.id === current ? ' is-current' : '');
            const open = document.createElement('button');
            open.type = 'button';
            open.className = 'history-open';
            const title = Object.assign(document.createElement('span'), { className: 'history-title', textContent: item.title || 'Untitled' });
            const when = Object.assign(document.createElement('span'), { className: 'history-when', textContent: ago(item.updatedAt) });
            open.append(title, when);
            open.addEventListener('click', () => {
                vscode.postMessage({ type: 'agent:openConversation', id: item.id });
                historyMenu.hidden = true;
            });
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'icon-btn history-delete';
            remove.title = 'Delete';
            remove.innerHTML = '<span class="codicon codicon-trash"></span>';
            remove.addEventListener('click', () => vscode.postMessage({ type: 'agent:deleteConversation', id: item.id }));
            row.append(open, remove);
            return row;
        }));
    }

    /** How full the conversation is, from the last step's input tokens. */
    function showContext({ tokens, window: size }) {
        const short = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n));
        contextMeter.textContent = size ? `Context ${short(tokens)} / ${short(size)}` : `Context ${short(tokens)}`;
        contextMeter.title = 'Tokens the last step sent: the whole conversation goes with every step.';
        contextMeter.classList.toggle('is-high', Boolean(size) && tokens > size * 0.5);
    }

    modelSelect.addEventListener('change', () => vscode.postMessage({ type: 'agent:setModel', id: modelSelect.value }));

    function linkButton(label, onClick) {
        const button = document.createElement('button');
        button.className = 'link-btn';
        button.textContent = label;
        button.addEventListener('click', onClick);
        return button;
    }

    // Where requests go: the user's own key, or the Kigumi account (signed in, or a way to sign in).
    function showRoute(via, account) {
        const parts = [];
        if (via === 'anthropic') parts.push('Using your Anthropic key.');
        else if (via === 'openrouter') parts.push('Using your OpenRouter key.');
        else if (account.signedIn) {
            const left = typeof account.balanceUsd === 'number' ? ` · $${account.balanceUsd.toFixed(2)} left` : '';
            parts.push(`${account.email || 'Signed in'}${left} · `,
                linkButton('Sign out', () => vscode.postMessage({ type: 'agent:signOut' })));
        } else if (account.configured) {
            parts.push('Sign in to use the agent, with free usage to start: ',
                linkButton('GitHub', () => vscode.postMessage({ type: 'agent:signIn', provider: 'github' })),
                ' · ',
                linkButton('Google', () => vscode.postMessage({ type: 'agent:signIn', provider: 'google' })));
        } else {
            parts.push('Set agent.openrouterApiKey (or agent.apiKey, an Anthropic key) in settings to use the agent.');
        }
        routeNote.replaceChildren(...parts);
    }

    settingsBtn.addEventListener('click', () => {
        historyMenu.hidden = true;
        settingsMenu.hidden = !settingsMenu.hidden;
        settingsBtn.setAttribute('aria-expanded', String(!settingsMenu.hidden));
    });
    for (const radio of modeRadios) {
        radio.addEventListener('change', () => vscode.postMessage({ type: 'agent:setSetting', key: 'agent.permissionMode', value: radio.value }));
    }
    let allowedTools = [];
    startupToggle.addEventListener('change', () => vscode.postMessage({
        type: 'agent:setSetting', key: 'agent.showOnStartup', value: startupToggle.checked,
    }));

    const MODE_BANNERS = { edits: 'Editing files without asking', all: 'Not asking before changes' };

    function showSettings(settings) {
        const mode = settings['agent.permissionMode'] || 'ask';
        for (const radio of modeRadios) radio.checked = radio.value === mode;
        startupToggle.checked = settings['agent.showOnStartup'] !== false;
        bypassBanner.hidden = mode === 'ask';
        bypassBanner.textContent = MODE_BANNERS[mode] || '';
        // Tools allowed for good from a permission card, each with a way to take it back.
        allowedTools = settings['agent.alwaysAllow'] || [];
        alwaysAllowed.replaceChildren(...(allowedTools.length ? [Object.assign(document.createElement('div'), {
            className: 'settings-hint', textContent: 'Always allowed:' })] : []), ...allowedTools.map((name) => {
            const chip = Object.assign(document.createElement('span'), { className: 'allowed-tool', textContent: name });
            const remove = Object.assign(document.createElement('button'), { type: 'button', textContent: '×', title: `Ask again before ${name}` });
            remove.addEventListener('click', () => vscode.postMessage({
                type: 'agent:setSetting', key: 'agent.alwaysAllow', value: allowedTools.filter((tool) => tool !== name),
            }));
            chip.appendChild(remove);
            return chip;
        }));
    }

    // The models to choose from, and where requests for the chosen one go.
    function showState({ models = [], model, via, account = { configured: false }, settings = {} }) {
        showSettings(settings);
        modelSelect.replaceChildren(...models.map(({ id, label }) => {
            const option = document.createElement('option');
            option.value = id;
            option.textContent = label;
            return option;
        }));
        modelSelect.value = model;
        showRoute(via, account);
    }

    messagesEl.addEventListener('click', (event) => {
        if (event.target.classList.contains('suggestion-chip')) {
            sendPrompt(event.target.textContent);
        }
    });

    // A reopened conversation: drawn again from what the panel showed.
    function replay(events) {
        resetMessages();
        contextMeter.textContent = '';
        undoNotes.clear();
        for (const event of events) handle(event);
        for (const chip of toolChips.values()) chip.classList.remove('is-running');
        // Only the latest failure can be tried again.
        const retries = [...messagesEl.querySelectorAll('.retry-btn')];
        for (const button of retries.slice(0, -1)) button.remove();
        endThinking();
    }

    window.addEventListener('message', (event) => {
        const message = event.data;
        if (message && typeof message.type === 'string') handle(message);
    });

    function handle(message) {
        switch (message.type) {
            case 'agent:replay':
                replay(message.events || []);
                break;
            case 'agent:conversations':
                showConversations(message);
                break;
            case 'agent:context':
                showContext(message);
                break;
            case 'agent:state':
                showState(message);
                break;
            case 'agent:busy':
                setBusy(Boolean(message.busy));
                break;
            case 'agent:text':
                appendText(message.text || '');
                break;
            case 'agent:reasoning':
                appendReasoning(message.text || '');
                break;
            case 'agent:notice':
                endThinking();
                add('agent-note', message.text || '');
                break;
            case 'agent:tool':
                addTool(message.id, message.name || 'tool', message.input);
                break;
            case 'agent:toolResult':
                finishTool(message.id, message.isError, message.text);
                break;
            case 'agent:permission':
                askPermission(message.requestId, message.toolName || 'tool', message.input || {});
                break;
            case 'agent:done':
                if (message.stopped) add('agent-note', 'Stopped.');
                else if (!message.isError && typeof message.costUsd === 'number') {
                    add('agent-note', `$${message.costUsd < 0.01 ? message.costUsd.toFixed(4) : message.costUsd.toFixed(2)}`);
                } else if (message.isError) {
                    const failed = add('agent-error', message.error || 'The agent stopped with an error.');
                    const again = Object.assign(document.createElement('button'), { type: 'button', className: 'link-btn retry-btn', textContent: 'Try again' });
                    again.addEventListener('click', () => {
                        again.remove();
                        vscode.postMessage({ type: 'agent:retry' });
                    });
                    failed.append(' ', again);
                }
                break;
            case 'agent:userMessage':
                endThinking();
                add('message-bubble user', message.text || '');
                break;
            case 'agent:queued':
                showQueued(message.id, message.text || '');
                break;
            case 'agent:dequeued':
                dropQueued(message.id);
                break;
            case 'agent:checkpoint':
                showCheckpoint(message.turn, message.files || []);
                break;
            case 'agent:restored':
                showRestored(message.turn);
                break;
            case 'agent:error':
                add('agent-error', message.message || 'Something went wrong.');
                break;
            default:
                break;
        }
    }

    vscode.postMessage({ type: 'agent:ready' });
})();
