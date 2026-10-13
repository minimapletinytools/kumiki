// The agent panel's page: the conversation as it streams in, tool calls as chips, and asking
// before a tool that changes something runs. The conversation itself lives in the app (see
// agent/agent-session.js); this only draws it and sends what the user types.
(function () {
    'use strict';

    const vscode = window.acquireVsCodeApi();
    const $ = (id) => document.getElementById(id);

    const messagesEl = $('messages');
    const inputEl = $('prompt-input');
    const sendBtn = $('send-btn');
    const clearBtn = $('btn-clear');
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

    // Streamed text joins the reply being written, until something else (a tool) comes between.
    function appendText(text) {
        const last = messagesEl.lastElementChild;
        const bubble = last && last.classList.contains('assistant') ? last : add('message-bubble assistant', '');
        bubble.textContent += text;
        scrollToEnd();
    }

    function summarise(input) {
        if (!input || typeof input !== 'object') return '';
        const first = Object.values(input).find((value) => typeof value === 'string');
        return first ? first.split('\n')[0].slice(0, 80) : '';
    }

    function addTool(id, name, input) {
        const chip = add('tool-chip');
        const label = document.createElement('span');
        label.className = 'tool-name';
        label.textContent = name.replace(/^mcp__kigumi__/, '');
        const detail = document.createElement('span');
        detail.className = 'tool-detail';
        detail.textContent = summarise(input);
        chip.append(label, detail);
        toolChips.set(id, chip);
    }

    function finishTool(id, isError, text) {
        const chip = toolChips.get(id);
        if (!chip) return;
        chip.classList.add(isError ? 'is-error' : 'is-done');
        chip.title = text || '';
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
                card.classList.add(allow ? 'is-allowed' : 'is-denied');
                buttons.remove();
            });
            buttons.appendChild(button);
        }
        card.append(question, detail, buttons);
    }

    function setBusy(next) {
        busy = next;
        sendBtn.title = busy ? 'Stop' : 'Send message';
        sendBtn.firstElementChild.className = `codicon codicon-${busy ? 'debug-stop' : 'send'}`;
        messagesEl.classList.toggle('is-busy', busy);
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

    messagesEl.addEventListener('click', (event) => {
        if (event.target.classList.contains('suggestion-chip')) {
            sendPrompt(event.target.textContent);
        }
    });

    window.addEventListener('message', (event) => {
        const message = event.data;
        if (!message || typeof message.type !== 'string') return;
        switch (message.type) {
            case 'agent:busy':
                setBusy(Boolean(message.busy));
                break;
            case 'agent:text':
                appendText(message.text || '');
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
                else if (message.isError) add('agent-error', message.error || 'The agent stopped with an error.');
                break;
            case 'agent:error':
                add('agent-error', message.message || 'Something went wrong.');
                break;
            default:
                break;
        }
    });
})();
