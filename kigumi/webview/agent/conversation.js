// The conversation as the panel draws it: requests, streamed replies (Markdown) and reasoning, tool
// chips that open to what went in and came out, permission cards, undo notes, and requests waiting
// their turn.
import { t, textOf, translatePage, withLink } from './i18n.js';
import { render } from './markdown.js';
import { pre, toolInputView } from './diff.js';

const shownName = (name) => name.replace(/^mcp__kigumi__/, '');

const baseName = (value) => String(value).replace(/^[a-z]+:/, '').split(/[\\/]/).pop();

/** What a tool's input names: a file, a view's file, an API name or what is searched for. */
function targetOf(input) {
    if (!input || typeof input !== 'object') return '';
    for (const key of ['file_path', 'panel_id', 'path']) {
        if (typeof input[key] === 'string' && input[key]) return baseName(input[key]);
    }
    for (const key of ['name', 'search', 'pattern']) {
        if (typeof input[key] === 'string' && input[key]) return input[key];
    }
    return '';
}

/** What a tool call is doing, in words ("Working on shed.py"), or the tool's name for one without any. */
export function describeTool(name, input) {
    const target = targetOf(input) || t('agent.tool.say.default');
    return textOf(`agent.tool.say.${name}`, { target }, name);
}

/** The first string the tool was given, for the chip's one-line summary. */
function summarise(input) {
    if (!input || typeof input !== 'object') return '';
    const first = Object.values(input).find((value) => typeof value === 'string');
    return first ? first.split('\n')[0].slice(0, 80) : '';
}

export class Conversation {
    /**
     * @param {HTMLElement} element  where messages go
     * @param {{post: (message: object) => void, setActivity: (label: string) => void}} deps
     */
    constructor(element, { post, setActivity, scrollDown }) {
        this.element = element;
        this.post = post;
        this.setActivity = setActivity;
        // Whether new output keeps the view at the end: not while the user has scrolled up to read.
        this.following = true;
        this.scrollDown = scrollDown;
        element.addEventListener('scroll', () => {
            this.following = element.scrollHeight - element.scrollTop - element.clientHeight < 40;
            scrollDown.hidden = this.following;
        });
        scrollDown.addEventListener('click', () => this.scrollToEnd(true));
        this.welcomeHtml = element.querySelector('#welcome').outerHTML;
        this.toolChips = new Map();
        this.queued = new Map();
        this.undoNotes = new Map();
        this.thinking = null;
    }

    /** To the end, if following it (or `force`). */
    scrollToEnd(force = false) {
        if (force) this.following = true;
        if (!this.following) return;
        this.element.scrollTop = this.element.scrollHeight;
        this.scrollDown.hidden = true;
    }

    add(className, text) {
        const welcome = this.element.querySelector('#welcome');
        if (welcome) welcome.remove();
        const node = Object.assign(document.createElement('div'), { className });
        if (text !== undefined) node.textContent = text;
        this.element.appendChild(node);
        this.scrollToEnd();
        return node;
    }

    reset() {
        this.toolChips.clear();
        this.undoNotes.clear();
        this.queued.clear();
        this.thinking = null;
        this.following = true;
        this.scrollDown.hidden = true;
        this.element.innerHTML = this.welcomeHtml;
        translatePage(this.element);
    }

    /** After a replay: nothing is running, and only the latest failure can be tried again. */
    settle() {
        for (const chip of this.toolChips.values()) chip.classList.remove('is-running');
        const retries = [...this.element.querySelectorAll('.retry-btn')];
        for (const button of retries.slice(0, -1)) button.remove();
        this.endThinking();
    }

    /** A request as the user sees it: its text, and thumbnails of images sent with it (or how many). */
    userBubble(text, imageUrls = [], imageCount = 0) {
        this.endThinking();
        // A new request: back to the end, to follow its answer.
        this.following = true;
        const bubble = this.add('message-bubble user', text);
        if (imageUrls.length) {
            const row = Object.assign(document.createElement('div'), { className: 'bubble-images' });
            for (const url of imageUrls) row.appendChild(Object.assign(document.createElement('img'), { src: url, alt: '' }));
            bubble.appendChild(row);
        } else if (imageCount) {
            bubble.appendChild(Object.assign(document.createElement('div'), { className: 'bubble-images-note',
                textContent: t('agent.images.count', { count: imageCount }) }));
        }
        return bubble;
    }

    // Thinking streamed in a row is one block, closed unless opened, until something else comes.
    endThinking() {
        if (!this.thinking) return;
        this.thinking.querySelector('summary').textContent = t('agent.thought');
        this.thinking.classList.remove('is-live');
        this.thinking = null;
    }

    appendReasoning(text) {
        if (!this.thinking) {
            this.thinking = this.add('thinking is-live');
            const details = document.createElement('details');
            details.append(Object.assign(document.createElement('summary'), { textContent: t('agent.thinking') }),
                Object.assign(document.createElement('div'), { className: 'thinking-body' }));
            this.thinking.appendChild(details);
        }
        this.thinking.querySelector('.thinking-body').textContent += text;
        this.setActivity(t('agent.activity.thinking'));
        this.scrollToEnd();
    }

    // Streamed text joins the reply being written, until something else (a tool) comes between.
    appendText(text) {
        this.endThinking();
        const last = this.element.lastElementChild;
        const bubble = last && last.classList.contains('assistant') ? last : this.add('message-bubble assistant md', '');
        bubble.dataset.raw = (bubble.dataset.raw || '') + text;
        bubble.replaceChildren(render(bubble.dataset.raw));
        this.setActivity(t('agent.activity.writing'));
        this.scrollToEnd();
    }

    note(text) {
        this.endThinking();
        return this.add('agent-note', text);
    }

    error(text) {
        return this.add('agent-error', text);
    }

    linkButton(label, onClick, className = '') {
        const button = Object.assign(document.createElement('button'), { type: 'button', className: `link-btn ${className}`.trim(), textContent: label });
        button.addEventListener('click', onClick);
        return button;
    }

    // A chip that opens to show what the tool was given and what it gave back.
    addTool(id, name, input) {
        this.endThinking();
        const shown = shownName(name);
        const chip = this.add('tool-chip is-running');
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        const said = describeTool(shown, input);
        summary.appendChild(Object.assign(document.createElement('span'), { className: 'tool-name', textContent: said }));
        // The tool's own name and the start of its input, opened, for anyone who wants them.
        const body = Object.assign(document.createElement('div'), { className: 'tool-body' });
        body.appendChild(Object.assign(document.createElement('div'), { className: 'tool-detail',
            textContent: [shown, summarise(input)].filter(Boolean).join(' · ') }));
        body.appendChild(toolInputView(shown, input));
        details.append(summary, body);
        chip.appendChild(details);
        this.toolChips.set(id, chip);
        this.setActivity(said);
    }

    finishTool(id, isError, text) {
        const chip = this.toolChips.get(id);
        if (!chip) return;
        chip.classList.remove('is-running');
        chip.classList.add(isError ? 'is-error' : 'is-done');
        chip.querySelector('.tool-body').appendChild(pre('tool-output', text || t('agent.tool.nothing')));
        this.setActivity(t('agent.activity.thinking'));
    }

    /** The view before and after an edit, on its chip. */
    showToolImages(id, before, after) {
        const chip = this.toolChips.get(id);
        if (!chip) return;
        const row = Object.assign(document.createElement('div'), { className: 'before-after' });
        for (const [label, url] of [[t('agent.before'), before], [t('agent.after'), after]]) {
            const figure = document.createElement('figure');
            figure.append(Object.assign(document.createElement('img'), { src: url, alt: label }),
                Object.assign(document.createElement('figcaption'), { textContent: label }));
            row.appendChild(figure);
        }
        chip.querySelector('.tool-body').appendChild(row);
    }

    askPermission(requestId, toolName, input) {
        const shown = shownName(toolName);
        const card = this.add('permission-card');
        const buttons = Object.assign(document.createElement('div'), { className: 'permission-buttons' });
        for (const [label, allow, always] of [[t('agent.permission.allow'), true, false],
            [t('agent.permission.always', { tool: shown }), true, true], [t('agent.permission.deny'), false, false]]) {
            const button = Object.assign(document.createElement('button'), { textContent: label,
                className: always ? 'always' : allow ? 'allow' : 'deny' });
            button.addEventListener('click', () => {
                this.post({ type: 'agent:permissionAnswer', requestId, allow, always });
                this.setActivity(t('agent.activity.thinking'));
                card.classList.add(allow ? 'is-allowed' : 'is-denied');
                buttons.remove();
            });
            buttons.appendChild(button);
        }
        card.append(Object.assign(document.createElement('div'), { textContent: t('agent.permission.question', { tool: shown }) }),
            toolInputView(shown, input), buttons);
        this.setActivity(t('agent.activity.waiting'));
    }

    /** `outOfTokens`: the browser version's promo credit is spent, which can't be topped up. */
    done({ stopped, isError, error, outOfTokens, costUsd }) {
        // A question the turn ended without an answer to can no longer be answered.
        for (const buttons of this.element.querySelectorAll('.permission-card .permission-buttons')) {
            buttons.closest('.permission-card').classList.add('is-denied');
            buttons.remove();
        }
        if (stopped) {
            this.note(t('agent.stopped'));
        } else if (isError && outOfTokens) {
            this.add('agent-error').append(withLink('agent.error.outOfTokens', 'agent.error.outOfTokensLink', 'https://kumiki.build/install'));
        } else if (isError) {
            const failed = this.error(error || t('agent.failed'));
            const again = this.linkButton(t('agent.retry'), () => {
                again.remove();
                this.post({ type: 'agent:retry' });
            }, 'retry-btn');
            failed.append(' ', again);
        } else if (typeof costUsd === 'number') {
            this.note(`$${costUsd < 0.01 ? costUsd.toFixed(4) : costUsd.toFixed(2)}`);
        }
    }

    showQueued(id, text) {
        const bubble = this.add('message-bubble user is-queued', '');
        const cancel = Object.assign(document.createElement('button'), { type: 'button', className: 'queued-cancel',
            title: t('agent.queued.cancel'), textContent: '×' });
        cancel.addEventListener('click', () => this.post({ type: 'agent:unqueue', id }));
        bubble.append(Object.assign(document.createElement('span'), { textContent: text }),
            Object.assign(document.createElement('span'), { className: 'queued-tag', textContent: t('agent.queued.waiting') }), cancel);
        this.queued.set(id, bubble);
    }

    // A request that has started, or that was dropped: no longer shown as waiting.
    dropQueued(id) {
        const bubble = this.queued.get(id);
        if (bubble) bubble.remove();
        this.queued.delete(id);
    }

    // After a turn that changed files: a way to put them back.
    showCheckpoint(turn, files) {
        const note = this.note('');
        note.className = 'checkpoint-note';
        const undo = this.linkButton(t('agent.undo'), () => this.post({ type: 'agent:restore', turn }));
        undo.title = t('agent.undo.title');
        note.append(Object.assign(document.createElement('span'), { textContent: t('agent.changed', { count: files.length, files: files.join(', ') }) }),
            ' · ', undo);
        this.undoNotes.set(turn, note);
    }

    showRestored(turn) {
        for (const [noted, note] of this.undoNotes) {
            if (noted < turn) continue;
            note.classList.add('is-undone');
            const button = note.querySelector('button');
            if (button) button.remove();
            this.undoNotes.delete(noted);
        }
    }

    // Files changed since the agent left them: undoing would lose those changes.
    showRestoreConflict(turn, files) {
        const note = this.note(`${t('agent.undo.conflict', { files: files.join(', ') })} `);
        const anyway = this.linkButton(t('agent.undo.anyway'), () => {
            anyway.remove();
            this.post({ type: 'agent:restore', turn, force: true });
        });
        note.appendChild(anyway);
    }
}
