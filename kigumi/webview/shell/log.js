// The Log tab: everything Kigumi has logged, by level and by source (the app, or each view's file),
// with search, following the newest, tracebacks whose frames open their file at the line, and
// copying. A view's "view log" opens it showing that view.

const api = acquireVsCodeApi();
const $ = (id) => document.getElementById(id);
const LEVELS = ['debug', 'info', 'warn', 'error'];
const MAX_ENTRIES = 5000;
// A Python traceback's frame: `File "/path/frame.py", line 12, in build`.
const TRACEBACK_FRAME = /File "([^"]+)", line (\d+)/g;

const list = $('entries');
const search = $('filter');
const follow = $('follow');
const sourceSelect = $('source');
const counts = $('counts');
let entries = [];
let minLevel = 'info';
let source = '';

function shows(entry) {
    const needle = search.value.trim().toLowerCase();
    return LEVELS.indexOf(entry.level) >= LEVELS.indexOf(minLevel)
        && (!source || entry.source === source)
        && (!needle || entry.text.toLowerCase().includes(needle));
}

/** `text` into `into`, each traceback frame's file and line a link that opens it there. */
function withLocations(text, into) {
    let last = 0;
    for (const match of text.matchAll(TRACEBACK_FRAME)) {
        into.appendChild(document.createTextNode(text.slice(last, match.index)));
        const link = Object.assign(document.createElement('span'), { className: 'log-location', textContent: match[0],
            title: 'Open the file at this line', tabIndex: 0 });
        link.setAttribute('role', 'link');
        const [, filePath, line] = match;
        const open = () => api.postMessage({ type: 'openLogLocation', filePath, lineNumber: Number(line) });
        link.addEventListener('click', open);
        link.addEventListener('keydown', (event) => { if (event.key === 'Enter') open(); });
        into.appendChild(link);
        last = match.index + match[0].length;
    }
    into.appendChild(document.createTextNode(text.slice(last)));
}

function row(entry) {
    const element = Object.assign(document.createElement('div'), { className: `log-line log-${entry.level}` });
    element.hidden = !shows(entry);
    const message = Object.assign(document.createElement('span'), { className: 'log-message' });
    withLocations(entry.text, message);
    element.append(Object.assign(document.createElement('span'), { className: 'log-time', textContent: entry.timestamp.slice(11, 19) }), message);
    return element;
}

function scrollToEnd() {
    if (follow.checked) list.scrollTop = list.scrollHeight;
}

function showCounts() {
    const shown = entries.filter((entry) => !source || entry.source === source);
    const errors = shown.filter((entry) => entry.level === 'error').length;
    const warnings = shown.filter((entry) => entry.level === 'warn').length;
    counts.textContent = `${errors} errors · ${warnings} warnings`;
}

/** The sources there are, as choices, keeping the one chosen. */
function showSources() {
    const names = [...new Set(entries.map((entry) => entry.source))].sort((a, b) => (a === 'app' ? -1 : b === 'app' ? 1 : a.localeCompare(b)));
    if (source && !names.includes(source)) names.push(source);
    sourceSelect.replaceChildren(Object.assign(document.createElement('option'), { value: '', textContent: 'Everything' }),
        ...names.map((name) => Object.assign(document.createElement('option'), { value: name, textContent: name === 'app' ? 'The app' : name })));
    sourceSelect.value = source;
}

function renderAll() {
    list.replaceChildren(...entries.map(row));
    showCounts();
    showSources();
    scrollToEnd();
}

function refilter() {
    entries.forEach((entry, index) => { list.children[index].hidden = !shows(entry); });
    showCounts();
    scrollToEnd();
}

function add(entry) {
    const isNewSource = !entries.some((one) => one.source === entry.source);
    entries.push(entry);
    if (entries.length > MAX_ENTRIES) {
        entries.shift();
        if (list.firstChild) list.firstChild.remove();
    }
    list.appendChild(row(entry));
    if (isNewSource) showSources();
    showCounts();
    scrollToEnd();
}

$('levels').addEventListener('click', (event) => {
    const level = event.target.dataset && event.target.dataset.level;
    if (!level) return;
    minLevel = level;
    for (const button of $('levels').querySelectorAll('button')) button.classList.toggle('is-on', button.dataset.level === level);
    refilter();
});
search.addEventListener('input', refilter);
sourceSelect.addEventListener('change', () => {
    source = sourceSelect.value;
    refilter();
});
follow.addEventListener('change', scrollToEnd);
// Scrolling up to read stops following; back at the end, it follows again.
list.addEventListener('scroll', () => {
    follow.checked = list.scrollTop + list.clientHeight >= list.scrollHeight - 4;
});
$('copy').addEventListener('click', () => {
    const text = entries.filter(shows).map((entry) => `${entry.timestamp} ${entry.level.toUpperCase()} ${entry.text}`).join('\n');
    navigator.clipboard.writeText(text).catch(() => {});
});
$('clear').addEventListener('click', () => {
    entries = [];
    renderAll();
});
$('open-file').addEventListener('click', () => api.postMessage({ type: 'openLogFile' }));

window.addEventListener('message', (event) => {
    const message = event.data;
    if (!message) return;
    if (message.type === 'logEntries') {
        entries = (message.entries || []).slice(-MAX_ENTRIES);
        if (typeof message.source === 'string') source = message.source;
        renderAll();
    } else if (message.type === 'logEntry') {
        add(message.entry);
    } else if (message.type === 'logShowSource') {
        source = message.source || '';
        showSources();
        refilter();
    }
});
api.postMessage({ type: 'logReady' });
