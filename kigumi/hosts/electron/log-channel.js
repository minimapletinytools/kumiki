/**
 * The Kigumi log for the standalone app: kept in memory for the Log tab and
 * appended to a file. Has the OutputChannel shape sessions use.
 */

const fs = require('fs');
const path = require('path');

const MAX_LINES = 5000;
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
        this.partial = '';
        this.listeners = new Set();
        fs.mkdirSync(path.dirname(filePath), { recursive: true });
        rotateIfLarge(filePath);
    }

    append(text) {
        const parts = (this.partial + String(text)).split('\n');
        this.partial = parts.pop();
        for (const line of parts) {
            this._push(line);
        }
    }

    appendLine(text) {
        this.append(`${text}\n`);
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
    }
}

module.exports = { LogChannel, rotateIfLarge };
