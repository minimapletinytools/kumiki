// The Log tab: every line of the Kigumi log, live, with a filter.

(function () {
    'use strict';

    const api = acquireVsCodeApi();
    const linesElement = document.getElementById('lines');
    const filter = document.getElementById('filter');
    const follow = document.getElementById('follow');
    let lines = [];

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
        const needle = filter.value.trim().toLowerCase();
        return !needle || line.toLowerCase().includes(needle);
    }

    function scrollToEnd() {
        if (follow.checked) linesElement.scrollTop = linesElement.scrollHeight;
    }

    function renderAll() {
        linesElement.replaceChildren(...lines.filter(matches).map(lineElement));
        scrollToEnd();
    }

    window.addEventListener('message', (event) => {
        const message = event.data;
        if (!message) return;
        if (message.type === 'logLines') {
            lines = message.lines || [];
            renderAll();
        } else if (message.type === 'logLine') {
            lines.push(message.line);
            if (matches(message.line)) {
                linesElement.append(lineElement(message.line));
                scrollToEnd();
            }
        }
    });

    filter.addEventListener('input', renderAll);
    document.getElementById('open-file').addEventListener('click', () => api.postMessage({ type: 'openLogFile' }));
    api.postMessage({ type: 'logReady' });
})();
