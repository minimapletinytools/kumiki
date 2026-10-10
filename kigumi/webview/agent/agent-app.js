// Agent panel script
(function () {
    'use strict';

    const vscode = window.acquireVsCodeApi();
    const $ = (id) => document.getElementById(id);

    const messagesEl = $('messages');
    const inputEl = $('prompt-input');
    const sendBtn = $('send-btn');
    const clearBtn = $('btn-clear');

    function appendMessage(role, text) {
        const bubble = document.createElement('div');
        bubble.className = `message-bubble ${role}`;
        bubble.textContent = text;
        messagesEl.appendChild(bubble);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return bubble;
    }

    function sendPrompt() {
        const text = inputEl.value.trim();
        if (!text) return;
        appendMessage('user', text);
        inputEl.value = '';
        inputEl.style.height = 'auto';

        vscode.postMessage({ type: 'agentPrompt', prompt: text });
    }

    inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendPrompt();
        }
    });

    sendBtn.addEventListener('click', sendPrompt);

    clearBtn.addEventListener('click', () => {
        messagesEl.innerHTML = `
            <div class="agent-welcome">
                <h3>Kumiki Assistant</h3>
                <p>Ask questions about your timber structures, request joint or frame edits, or diagnose runner errors.</p>
                <div class="suggestions">
                    <button class="suggestion-chip">Explain active frame parameters</button>
                    <button class="suggestion-chip">Check for joint errors</button>
                    <button class="suggestion-chip">List available joint patterns</button>
                </div>
            </div>`;
    });

    messagesEl.addEventListener('click', (e) => {
        if (e.target.classList.contains('suggestion-chip')) {
            inputEl.value = e.target.textContent;
            sendPrompt();
        }
    });

    window.addEventListener('message', (event) => {
        const msg = event.data;
        if (!msg) return;
        if (msg.type === 'agentResponse') {
            appendMessage('assistant', msg.text);
        }
    });
})();
