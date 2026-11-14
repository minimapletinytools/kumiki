// The Keyboard Shortcuts tab: each command with its keys, to change, reset or remove. The core
// (app-shell/keyboard-shortcuts.js) keeps them in the app.keybindings setting and sends them back.
import { keyFromEvent } from '../key-match.js';

const vscode = acquireVsCodeApi();
const $ = (id) => document.getElementById(id);

const SECTIONS = [
    { scope: 'app', title: 'Anywhere in Kigumi' },
    { scope: 'viewer', title: 'In a 3D view or drawing' },
];

let entries = [];
let clashes = {};
let recording = null;

function el(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

function button(text, onClick) {
    const element = el('button', '', text);
    element.type = 'button';
    element.addEventListener('click', onClick);
    return element;
}

function setKeys(command, keys) {
    vscode.postMessage({ type: 'setKeys', command, keys });
}

/** Wait for the next key, for `command`; Escape gives up. */
function record(command) {
    recording = command;
    // The app's own shortcuts mustn't take the key on its way here (panel-bridge.js, and the menus).
    window.kigumiTakeAllKeys = true;
    vscode.postMessage({ type: 'recording', on: true });
    render();
}

function stopRecording() {
    recording = null;
    window.kigumiTakeAllKeys = false;
    vscode.postMessage({ type: 'recording', on: false });
    render();
}

window.addEventListener('keydown', (event) => {
    if (!recording) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.key === 'Escape') {
        stopRecording();
        return;
    }
    const key = keyFromEvent(event);
    if (!key) return; // only modifiers so far
    const command = recording;
    stopRecording();
    setKeys(command, [key]);
}, true);

function clashesOf(entry) {
    const others = new Set();
    for (const label of entry.labels) {
        for (const command of clashes[label] || []) {
            if (command !== entry.command) others.add(command);
        }
    }
    return [...others].map((command) => (entries.find((one) => one.command === command) || { title: command }).title);
}

function row(entry) {
    const tr = el('tr');
    tr.dataset.search = `${entry.title} ${entry.labels.join(' ')}`.toLowerCase();
    const title = el('td', 'keys-title');
    title.append(el('span', entry.changed ? 'is-changed' : '', entry.title));
    const others = clashesOf(entry);
    if (others.length) title.append(el('span', 'keys-clash', `Same key as: ${others.join(', ')}`));

    const keys = el('td');
    if (recording === entry.command) {
        keys.append(el('span', 'keys-recording', 'Press the new keys… (Escape to cancel)'));
    } else if (entry.labels.length) {
        for (const label of entry.labels) keys.append(el('kbd', '', label));
    } else {
        keys.append(el('span', 'keys-none', 'No shortcut'));
    }

    const actions = el('td', 'keys-actions');
    actions.append(button('Change', () => record(entry.command)));
    if (entry.labels.length) actions.append(button('Remove', () => setKeys(entry.command, [])));
    if (entry.changed) {
        const reset = button('Reset', () => setKeys(entry.command, null));
        reset.title = entry.defaultLabels.length ? `Back to ${entry.defaultLabels.join(' or ')}` : 'Back to no shortcut';
        actions.append(reset);
    }
    tr.append(title, keys, actions);
    return tr;
}

function render() {
    const query = $('filter').value.trim().toLowerCase();
    $('sections').replaceChildren(...SECTIONS.map(({ scope, title }) => {
        const section = el('section', 'keys-section');
        const table = el('table', 'keys-table');
        for (const entry of entries.filter((one) => one.scope === scope)) {
            const tr = row(entry);
            tr.hidden = Boolean(query) && !tr.dataset.search.includes(query);
            table.append(tr);
        }
        section.append(el('h2', '', title), table);
        return section;
    }));
    const changed = entries.filter((one) => one.changed).length;
    $('note').textContent = changed ? `${changed} changed from the defaults` : '';
    $('reset-all').disabled = changed === 0;
}

window.addEventListener('message', (event) => {
    const message = event.data;
    if (!message || message.type !== 'keys') return;
    entries = message.entries || [];
    clashes = message.conflicts || {};
    render();
});

$('filter').addEventListener('input', render);
$('reset-all').addEventListener('click', () => vscode.postMessage({ type: 'resetAllKeys' }));
vscode.postMessage({ type: 'keysReady' });
