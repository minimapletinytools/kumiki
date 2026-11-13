// The agent panel's page: the conversation as it streams in, and the controls around it. The
// conversation itself lives in the app (agent/agent-session.js); this only draws it and sends what
// the user does. Messages each way are listed in protocol.js; HANDLERS handles each one the session sends.
import { setStrings, t, textOf, translatePage } from './i18n.js';
import { Conversation } from './conversation.js';
import { Composer } from './composer.js';
import { Menus } from './menus.js';
import { Status } from './status.js';

const vscode = window.acquireVsCodeApi();
const post = (message) => vscode.postMessage(message);
const $ = (id) => document.getElementById(id);

let busy = false;

const status = new Status({
    activity: $('activity'), activityLabel: $('activity-label'), modelSelect: $('model-select'),
    routeNote: $('route-note'), contextMeter: $('context-meter'), todos: $('todos'),
}, { post });
const conversation = new Conversation($('messages'), { post, setActivity: (label) => status.setActivity(label) });
const composer = new Composer({
    input: $('prompt-input'), sendButton: $('send-btn'), attachments: $('attachments'), mentions: $('mentions'), planToggle: $('plan-toggle'),
}, { post, isBusy: () => busy, onSent: (text, imageUrls) => {
    status.hideFinishedTodos();
    conversation.userBubble(text, imageUrls);
} });
const menus = new Menus({
    settingsToggle: $('settings-toggle'), settingsMenu: $('settings-menu'), historyButton: $('btn-history'), historyMenu: $('history-menu'),
    historyList: $('history-list'), alwaysAllowed: $('always-allowed'), startupToggle: $('setting-startup'), outputLimit: $('setting-output-limit'),
    retention: $('setting-retention'), usage: $('conversation-usage'), clearButton: $('clear-conversations'),
    mcpSettings: $('mcp-settings'), mcpToggle: $('setting-mcp'), mcpDetails: $('mcp-details'),
    agentToggle: $('setting-agent-enabled'), agentSettings: $('agent-settings'),
    keyInput: $('setting-openrouter-key'), keyNote: $('setting-openrouter-key-note'), banner: $('bypass-banner'),
}, {
    post,
    saved: vscode.getState() || {},
    save: (values) => vscode.setState({ ...(vscode.getState() || {}), ...values }),
});
let mcpState = null;
let signedIn = false;
let via = null; // how requests go: through the backend on the signed-in account, or to OpenRouter on a key

function reset() {
    conversation.reset();
    status.showTodos([]);
    status.clearContext();
    composer.forgetFiles();
}

$('btn-clear').addEventListener('click', () => {
    post({ type: 'agent:clear' });
    reset();
    menus.closeHistory();
});
// In the browser version the panel says how the agent can be run there (agent.html, .web-agent-notice).
if (new URLSearchParams(location.search).get('host') === 'web') document.body.classList.add('host-web');

$('messages').addEventListener('click', (event) => {
    if (event.target.classList.contains('sign-in-chip')) post({ type: 'agent:signIn', provider: event.target.dataset.provider });
    else if (event.target.classList.contains('suggestion-chip')) composer.send(event.target.textContent);
});

// A reopened conversation: drawn again from what the panel showed.
function replay(events) {
    reset();
    for (const event of events) handle(event);
    conversation.settle();
}

/** What to do with each message the session sends (protocol.js SESSION_TO_PANEL). */
const HANDLERS = {
    'agent:state': (message) => {
        setStrings(message.strings);
        translatePage();
        menus.showSettings(message.settings || {}, message.conversationBytes);
        composer.setPlanMode((message.settings || {})['agent.planMode'] === true);
        status.showModels(message.models || [], message.model);
        status.showRoute(message.via, message.account || { configured: false });
        signedIn = Boolean(message.account && message.account.signedIn);
        via = message.via;
        menus.showMcp(mcpState, { signedIn });
    },
    'agent:mcp': (message) => {
        mcpState = message.state || null;
        menus.showMcp(mcpState, { signedIn });
    },
    'agent:busy': (message) => {
        busy = Boolean(message.busy);
        composer.setBusy(busy);
        status.setBusy(busy);
        if (!busy) conversation.endThinking();
    },
    'agent:replay': (message) => replay(message.events || []),
    'agent:conversations': (message) => menus.showConversations(message),
    'agent:context': (message) => status.showContext(message),
    'agent:text': (message) => conversation.appendText(message.text || ''),
    'agent:reasoning': (message) => conversation.appendReasoning(message.text || ''),
    'agent:notice': (message) => conversation.note(textOf(message.key, message.params, message.text || '')),
    'agent:tool': (message) => conversation.addTool(message.id, message.name || 'tool', message.input),
    'agent:toolResult': (message) => conversation.finishTool(message.id, message.isError, message.text),
    'agent:toolImages': (message) => conversation.showToolImages(message.id, message.before, message.after),
    'agent:permission': (message) => conversation.askPermission(message.requestId, message.toolName || 'tool', message.input || {}),
    'agent:done': (message) => conversation.done({ ...message, error: textOf(message.errorKey, null, message.error),
        outOfTokens: message.errorKey === 'agent.error.noCredit' && via === 'backend' && document.body.classList.contains('host-web') }),
    'agent:error': (message) => conversation.error(textOf(message.key, message.params, message.message || t('agent.failed'))),
    'agent:userMessage': (message) => {
        status.hideFinishedTodos();
        conversation.userBubble(message.text || '', [], message.images || 0);
    },
    'agent:todos': (message) => status.showTodos(message.items || []),
    'agent:files': (message) => composer.setFiles(message.files || []),
    'agent:queued': (message) => conversation.showQueued(message.id, message.text || ''),
    'agent:dequeued': (message) => conversation.dropQueued(message.id),
    'agent:checkpoint': (message) => conversation.showCheckpoint(message.turn, message.files || []),
    'agent:restored': (message) => conversation.showRestored(message.turn),
    'agent:restoreConflict': (message) => conversation.showRestoreConflict(message.turn, message.files || []),
};

function handle(message) {
    const handler = HANDLERS[message.type];
    if (handler) handler(message);
}

window.addEventListener('message', (event) => {
    const message = event.data;
    if (message && typeof message.type === 'string') handle(message);
});

post({ type: 'agent:ready' });
