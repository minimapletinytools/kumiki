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
    const bypassToggle = $('setting-bypass');
    const startupToggle = $('setting-startup');
    const bypassBanner = $('bypass-banner');
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
        const bubble = last && last.classList.contains('assistant') ? last : add('message-bubble assistant', '');
        bubble.textContent += text;
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
        body.appendChild(pre('tool-input', JSON.stringify(input || {}, null, 2).slice(0, 4000)));
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
        const detail = document.createElement('pre');
        detail.textContent = JSON.stringify(input, null, 2).slice(0, 1200);
        const buttons = document.createElement('div');
        buttons.className = 'permission-buttons';
        for (const [label, allow] of [['Allow', true], ['Deny', false]]) {
            const button = document.createElement('button');
            button.textContent = label;
            button.className = allow ? 'allow' : 'deny';
            button.addEventListener('click', () => {
                vscode.postMessage({ type: 'agent:permissionAnswer', requestId, allow });
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

    function sendPrompt(text) {
        const prompt = (text !== undefined ? text : inputEl.value).trim();
        if (!prompt || busy) return;
        add('message-bubble user', prompt);
        inputEl.value = '';
        inputEl.style.height = 'auto';
        vscode.postMessage({ type: 'agent:prompt', text: prompt });
    }

    inputEl.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendPrompt();
        }
    });
    inputEl.addEventListener('input', () => {
        inputEl.style.height = 'auto';
        inputEl.style.height = `${Math.min(inputEl.scrollHeight, 200)}px`;
    });

    sendBtn.addEventListener('click', () => (busy ? vscode.postMessage({ type: 'agent:stop' }) : sendPrompt()));

    clearBtn.addEventListener('click', () => {
        vscode.postMessage({ type: 'agent:clear' });
        toolChips.clear();
        messagesEl.innerHTML = welcomeHtml;
    });

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
        settingsMenu.hidden = !settingsMenu.hidden;
        settingsBtn.setAttribute('aria-expanded', String(!settingsMenu.hidden));
    });
    bypassToggle.addEventListener('change', () => vscode.postMessage({
        type: 'agent:setSetting', key: 'agent.bypassPermissions', value: bypassToggle.checked,
    }));
    startupToggle.addEventListener('change', () => vscode.postMessage({
        type: 'agent:setSetting', key: 'agent.showOnStartup', value: startupToggle.checked,
    }));

    function showSettings(settings) {
        bypassToggle.checked = settings['agent.bypassPermissions'] === true;
        startupToggle.checked = settings['agent.showOnStartup'] !== false;
        bypassBanner.hidden = !bypassToggle.checked;
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

    window.addEventListener('message', (event) => {
        const message = event.data;
        if (!message || typeof message.type !== 'string') return;
        switch (message.type) {
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
                }
                else if (message.isError) add('agent-error', message.error || 'The agent stopped with an error.');
                break;
            case 'agent:error':
                add('agent-error', message.message || 'Something went wrong.');
                break;
            default:
                break;
        }
    });

    vscode.postMessage({ type: 'agent:ready' });
})();
