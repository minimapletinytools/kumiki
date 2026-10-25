import { html } from 'lit';

/** Kept in the panel; the oldest go past this. */
const MAX_ENTRIES = 2000;
const LEVELS = ['debug', 'info', 'warn', 'error'];
// A Python traceback's frame: `File "/path/frame.py", line 12, in build`.
const TRACEBACK_FRAME = /File "([^"]+)", line (\d+)/g;

/**
 * The view's log, where the host has no log of its own (the standalone app; VS Code has its Output
 * panel): what building the frame said, by level, with search, tracebacks whose files open at the
 * line, copying, and following the latest.
 *
 * Follows the viewer's panel shape (render, bindEvents). Entries are added to the DOM as they come
 * rather than through render, since there can be thousands.
 */
export class LogPanel {
    constructor(app, { t, post }) {
        this.app = app;
        this.t = t;
        this.post = post;
        this.entries = [];
        this.minLevel = 'info';
        this.search = '';
        this.searchText = '';
        this.follow = true;
        this.container = null;
    }

    /** How many errors and warnings there are, for the Log tab's badge. */
    get counts() {
        let errors = 0;
        let warnings = 0;
        for (const entry of this.entries) {
            if (entry.level === 'error') errors += 1;
            else if (entry.level === 'warn') warnings += 1;
        }
        return { errors, warnings };
    }

    render() {
        const t = this.t;
        const { errors, warnings } = this.counts;
        return html`
            <div id="log-panel-box" class="panel-box log-panel">
                <div class="log-toolbar">
                    <div class="log-levels" role="group" aria-label=${t('viewer.log.levels')}>
                        ${[['debug', t('viewer.log.level.all')], ['info', t('viewer.log.level.info')],
                            ['warn', t('viewer.log.level.warn')], ['error', t('viewer.log.level.error')]].map(([level, label]) => html`
                            <button type="button" class=${this.minLevel === level ? 'is-on' : ''} data-level=${level}>${label}</button>`)}
                    </div>
                    <input id="log-filter" type="search" placeholder=${t('viewer.log.filter.placeholder')} .value=${this.searchText}>
                </div>
                <div class="log-toolbar log-toolbar-secondary">
                    <span class="log-counts">${t('viewer.log.counts', { errors, warnings })}</span>
                    <label class="log-follow"><input id="log-follow" type="checkbox" .checked=${this.follow}> ${t('viewer.log.follow')}</label>
                    <button id="log-copy-btn" type="button">${t('viewer.log.copy')}</button>
                    <button id="log-clear-btn" type="button">${t('viewer.log.clear')}</button>
                </div>
                <div id="log-output" class="log-output"></div>
            </div>`;
    }

    bindEvents(renderRoot) {
        this.container = renderRoot.querySelector('#log-output');
        renderRoot.querySelector('.log-levels').addEventListener('click', (event) => {
            const level = event.target && event.target.dataset && event.target.dataset.level;
            if (!level) return;
            this.minLevel = level;
            this.refilter();
            this.app.requestUpdate();
        });
        renderRoot.querySelector('#log-filter').addEventListener('input', (event) => {
            this.searchText = event.target.value;
            this.search = this.searchText.toLowerCase();
            this.refilter();
        });
        renderRoot.querySelector('#log-follow').addEventListener('change', (event) => {
            this.follow = event.target.checked;
            if (this.follow) this.scrollToEnd();
        });
        renderRoot.querySelector('#log-copy-btn').addEventListener('click', () => {
            const shown = this.entries.filter((entry) => this.shows(entry));
            navigator.clipboard.writeText(shown.map((entry) => `${entry.timestamp} ${entry.level.toUpperCase()} ${entry.text}`).join('\n'))
                .catch(() => {});
        });
        renderRoot.querySelector('#log-clear-btn').addEventListener('click', () => this.clear());
        // Scrolling up to read stops following; back at the end, it follows again.
        this.container.addEventListener('scroll', () => {
            const atEnd = this.container.scrollTop + this.container.clientHeight >= this.container.scrollHeight - 4;
            if (atEnd !== this.follow) {
                this.follow = atEnd;
                const box = renderRoot.querySelector('#log-follow');
                if (box) box.checked = atEnd;
            }
        });
        for (const entry of this.entries) this.container.appendChild(this.row(entry));
        // Entries come while the Log tab is hidden, when it can't scroll; following, show the end once it shows.
        new ResizeObserver(() => { if (this.follow) this.scrollToEnd(); }).observe(this.container);
    }

    /** @param {{text: string, level?: string, timestamp?: string}} entry */
    add({ text, level, timestamp }) {
        const entry = {
            text: String(text),
            level: LEVELS.includes(level) ? level : 'info',
            timestamp: timestamp || new Date().toISOString(),
        };
        const before = this.counts;
        this.entries.push(entry);
        if (this.entries.length > MAX_ENTRIES) {
            this.entries.shift();
            if (this.container && this.container.firstChild) this.container.firstChild.remove();
        }
        if (this.container) {
            this.container.appendChild(this.row(entry));
            if (this.follow) this.scrollToEnd();
        }
        const after = this.counts;
        if (after.errors !== before.errors || after.warnings !== before.warnings) this.app.requestUpdate();
    }

    clear() {
        this.entries = [];
        if (this.container) this.container.replaceChildren();
        this.app.requestUpdate();
    }

    /** Everything logged, as text (for snapshots and tests). */
    text() {
        return this.entries.map((entry) => entry.text).join('\n');
    }

    shows(entry) {
        return LEVELS.indexOf(entry.level) >= LEVELS.indexOf(this.minLevel)
            && (!this.search || entry.text.toLowerCase().includes(this.search));
    }

    refilter() {
        if (!this.container) return;
        this.entries.forEach((entry, index) => {
            const row = this.container.children[index];
            if (row) row.hidden = !this.shows(entry);
        });
        if (this.follow) this.scrollToEnd();
    }

    scrollToEnd() {
        if (this.container) this.container.scrollTop = this.container.scrollHeight;
    }

    row(entry) {
        const row = document.createElement('div');
        row.className = `log-line log-${entry.level}`;
        row.hidden = !this.shows(entry);
        const time = document.createElement('span');
        time.className = 'log-time';
        time.textContent = entry.timestamp.slice(11, 19);
        const message = document.createElement('span');
        message.className = 'log-message';
        this.withLocations(entry.text, message);
        row.append(time, message);
        return row;
    }

    /** `text` into `into`, each traceback frame's file and line a link that opens it there. */
    withLocations(text, into) {
        let last = 0;
        for (const match of text.matchAll(TRACEBACK_FRAME)) {
            into.appendChild(document.createTextNode(text.slice(last, match.index)));
            // Text, not a button: a button can't wrap with the line around it.
            const link = document.createElement('span');
            link.setAttribute('role', 'link');
            link.tabIndex = 0;
            link.className = 'log-location';
            link.textContent = match[0];
            link.title = this.t('viewer.log.openAt');
            const [, filePath, line] = match;
            const open = () => this.post({ type: 'openLogLocation', filePath, lineNumber: Number(line) });
            link.addEventListener('click', open);
            link.addEventListener('keydown', (event) => { if (event.key === 'Enter') open(); });
            into.appendChild(link);
            last = match.index + match[0].length;
        }
        into.appendChild(document.createTextNode(text.slice(last)));
    }
}
