// Edits shown as line diffs, in permission cards and tool chips.
import { t } from './i18n.js';

/** A line diff of `before` and `after` (longest common subsequence): [[' '|'-'|'+', line], ...]. */
export function lineDiff(before, after) {
    const a = before.split('\n');
    const b = after.split('\n');
    if (a.length * b.length > 250000) {
        return [...a.map((line) => ['-', line]), ...b.map((line) => ['+', line])];
    }
    const common = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
    for (let i = a.length - 1; i >= 0; i--) {
        for (let j = b.length - 1; j >= 0; j--) {
            common[i][j] = a[i] === b[j] ? common[i + 1][j + 1] + 1 : Math.max(common[i + 1][j], common[i][j + 1]);
        }
    }
    const out = [];
    let i = 0;
    let j = 0;
    while (i < a.length || j < b.length) {
        if (i < a.length && j < b.length && a[i] === b[j]) {
            out.push([' ', a[i++]]);
            j++;
        } else if (j < b.length && (i === a.length || common[i][j + 1] > common[i + 1][j])) {
            // On a tie the removed line goes first, as diffs are read.
            out.push(['+', b[j++]]);
        } else {
            out.push(['-', a[i++]]);
        }
    }
    return out;
}

function diffView(before, after, heading) {
    const view = document.createElement('div');
    view.className = 'diff';
    view.appendChild(Object.assign(document.createElement('div'), { className: 'diff-file', textContent: heading }));
    for (const [op, line] of lineDiff(before, after).slice(0, 400)) {
        const row = document.createElement('div');
        row.className = op === '+' ? 'diff-add' : op === '-' ? 'diff-del' : 'diff-same';
        row.textContent = `${op} ${line}`;
        view.appendChild(row);
    }
    return view;
}

export function pre(className, text) {
    return Object.assign(document.createElement('pre'), { className, textContent: text });
}

/** What a tool was given: an edit as a diff, a written file as its text, else the input. */
export function toolInputView(name, input) {
    if (name === 'edit_file' && input && typeof input.old_string === 'string') {
        return diffView(input.old_string, input.new_string || '', input.file_path || '');
    }
    if (name === 'write_file' && input && typeof input.content === 'string') {
        return diffView('', input.content, t('agent.diff.wholeFile', { file: input.file_path || '' }));
    }
    return pre('tool-input', JSON.stringify(input || {}, null, 2).slice(0, 4000));
}
