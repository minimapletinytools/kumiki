/**
 * The Kigumi log for the standalone app: kept in memory for the Log tab and
 * appended to a file. Has the OutputChannel shape sessions use.
 *
 * Besides lines (for the file), it keeps entries for the Log tab: each with its time, level and
 * source (the view's file, from the "[name.py]" sessions start their lines with, or "app"). An
 * appendLine of several lines, a traceback, is one entry; a level given with it beats the guess.
 */

const fs = require('fs');
const path = require('path');

const MAX_LINES = 5000;
const MAX_ENTRIES = 5000;

/** An entry's level and source, read from its text. */
function classify(text) {
    const source = /^\[([^\]]+\.py)\]/.exec(text);
    let level = 'info';
    if (/\[error\]|Traceback \(most recent call last\)|failed:/i.test(text)) level = 'error';
    else if (/\[warn(ing)?\]/i.test(text)) level = 'warn';
    else if (/\[(timing|debug)\]/i.test(text)) level = 'debug';
    return { level, source: source ? source[1] : 'app' };
}
const MAX_FILE_BYTES = 5 * 1024 * 1024;

// Moves an oversized log aside as kigumi.1.log, replacing the previous one.
function rotateIfLarge(filePath, maxBytes = MAX_FILE_BYTES) {
    try {
        if (fs.statSync(filePath).size > maxBytes) {
            const rotated = filePath.replace(/\.log$/, '.1.log');
            fs.rmSync(rotated, { force: true });
            fs.renameSync(filePath, rotated);
            return rotated;
        }
    } catch (_error) {
        // No log yet.
    }
    return null;
}

class LogChannel {
    constructor(filePath, { onShow = () => {} } = {}) {
        this.filePath = filePath;
        this.onShow = onShow;
        this.lines = [];
        this.entries = [];
        this.partial = '';
        this.listeners = new Set();
        this.entryListeners = new Set();
        fs.mkdirSync(path.dirname(filePath), { recursive: true });
        rotateIfLarge(filePath);
    }

    append(text) {
        const parts = (this.partial + String(text)).split('\n');
        this.partial = parts.pop();
        for (const line of parts) {
            this._push(line);
            this._entry(line);
        }
    }

    appendLine(text, level) {
        const whole = this.partial + String(text);
        this.partial = '';
        for (const line of whole.split('\n')) {
            this._push(line);
        }
        this._entry(whole, level);
    }

    _entry(text, level) {
        const entry = { timestamp: new Date().toISOString(), text, ...classify(text), ...(level ? { level } : {}) };
        this.entries.push(entry);
        if (this.entries.length > MAX_ENTRIES) {
            this.entries.splice(0, this.entries.length - MAX_ENTRIES);
        }
        for (const listener of [...this.entryListeners]) {
            listener(entry);
        }
    }

    /** Each entry as it comes: { timestamp, level, source, text }. */
    onEntry(listener) {
        this.entryListeners.add(listener);
        return { dispose: () => this.entryListeners.delete(listener) };
    }

    _push(line) {
        this.lines.push(line);
        if (this.lines.length > MAX_LINES) {
            this.lines.splice(0, this.lines.length - MAX_LINES);
        }
        try {
            fs.appendFileSync(this.filePath, `${line}\n`, 'utf8');
        } catch (_error) {
            // The in-memory log still has it.
        }
        for (const listener of [...this.listeners]) {
            listener(line);
        }
    }

    onLine(listener) {
        this.listeners.add(listener);
        return { dispose: () => this.listeners.delete(listener) };
    }

    // Sessions call show(true) to point at new output; the app decides how.
    show(preserveFocus) {
        this.onShow(preserveFocus === true);
    }

    dispose() {
        this.listeners.clear();
        this.entryListeners.clear();
    }
}

module.exports = { LogChannel, rotateIfLarge, classify };
