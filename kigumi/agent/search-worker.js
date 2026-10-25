/**
 * search_files' search (project-files.js search), in a worker thread so a slow pattern can be
 * stopped without the app's main process hanging on it.
 */

const fs = require('fs');
const path = require('path');
const { parentPort, workerData } = require('worker_threads');

/** Files larger than this are skipped (generated output, not source); lines are matched up to this long. */
const MAX_FILE_BYTES = 1024 * 1024;
const MAX_LINE_CHARS = 2000;
const MAX_PATTERN_CHARS = 500;

function search({ files, root, pattern, ignoreCase, maxMatches }) {
    if (pattern.length > MAX_PATTERN_CHARS) throw new Error(`The pattern is longer than ${MAX_PATTERN_CHARS} characters.`);
    const matcher = new RegExp(pattern, ignoreCase ? 'i' : '');
    const matches = [];
    // Relative in the project, else absolute (a read-only folder outside it).
    const shown = (file) => (path.relative(root, file).startsWith('..') ? file : path.relative(root, file));
    for (const file of files) {
        if (fs.statSync(file).size > MAX_FILE_BYTES) continue;
        const content = fs.readFileSync(file, 'utf8');
        if (content.includes('\u0000')) continue; // binary
        const lines = content.split('\n');
        for (let i = 0; i < lines.length; i++) {
            if (matcher.test(lines[i].slice(0, MAX_LINE_CHARS))) {
                matches.push(`${shown(file)}:${i + 1}: ${lines[i].trim().slice(0, 200)}`);
                if (matches.length >= maxMatches) return matches;
            }
        }
    }
    return matches;
}

try {
    parentPort.postMessage({ matches: search(workerData) });
} catch (error) {
    parentPort.postMessage({ error: error.message });
}
