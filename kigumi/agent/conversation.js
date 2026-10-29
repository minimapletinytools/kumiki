/**
 * A conversation: its log, which keeps everything said and done, and the files its turns changed
 * (agent/checkpoints.js). Saved whole (agent/conversation-store.js); the panel draws it again from
 * the log.
 *
 * Log entries:
 *   a model message  { role, content }; a user's request also has `shown: { text, images }`
 *   a note           { note, text }: something Kigumi told the model (agent-loop.js NOTES)
 *   a summary        { summary }: the conversation before it, summarised; requests start from it
 *   a panel event    { event }: what the panel showed that the messages don't hold
 */

const { Checkpoints } = require('./checkpoints');

/** Panel events kept in the log. */
const KEPT_EVENTS = new Set(['agent:notice', 'agent:done', 'agent:error', 'agent:checkpoint', 'agent:restored', 'agent:todos']);

/** Most of a tool result the panel shows. */
const MAX_RESULT_CHARS = 2000;

/** A tool result's output (as the model is sent it) as text for the panel. */
function outputText(output) {
    if (!output) return '';
    if (output.type === 'content') {
        return output.value.map((part) => (part.type === 'text' ? part.text : '[image]')).join('\n');
    }
    return typeof output.value === 'string' ? output.value : JSON.stringify(output.value);
}

/** Log entries as the panel events that draw them. */
function renderLog(entries) {
    const events = [];
    for (const entry of entries) {
        if (entry.event) {
            events.push(entry.event);
        } else if (entry.role === 'user' && entry.shown) {
            events.push({ type: 'agent:userMessage', text: entry.shown.text, images: entry.shown.images || 0 });
        } else if (entry.role === 'assistant') {
            const parts = typeof entry.content === 'string' ? [{ type: 'text', text: entry.content }] : entry.content;
            for (const part of parts) {
                if (part.type === 'reasoning') events.push({ type: 'agent:reasoning', text: part.text });
                else if (part.type === 'text') events.push({ type: 'agent:text', text: part.text });
                else if (part.type === 'tool-call') events.push({ type: 'agent:tool', id: part.toolCallId, name: part.toolName, input: part.input });
            }
        } else if (entry.role === 'tool') {
            for (const part of entry.content) {
                if (part.type !== 'tool-result') continue;
                events.push({ type: 'agent:toolResult', id: part.toolCallId, isError: /^error/.test(part.output && part.output.type),
                    text: outputText(part.output).slice(0, MAX_RESULT_CHARS) });
            }
        }
    }
    return events;
}

const SUMMARY_PREFIX = '[A summary of our conversation so far]\n';
const UNDO_PREFIX = '[I undid your changes to ';

/**
 * A conversation saved in the first format ({ history, transcript }) as this one's fields. Its
 * history becomes the log, and its transcript what the panel shows for those entries (`earlier`).
 */
function fromFirstFormat({ history = [], transcript = [], ...rest }) {
    const log = [];
    for (let i = 0; i < history.length; i++) {
        const message = history[i];
        const reply = history[i + 1];
        const text = message.role === 'user' && typeof message.content === 'string' ? message.content : null;
        if (text && text.startsWith(SUMMARY_PREFIX) && reply && reply.role === 'assistant') {
            log.push({ summary: text.slice(SUMMARY_PREFIX.length) });
            i += 1;
        } else if (text && text.startsWith(UNDO_PREFIX) && reply && reply.content === 'Understood.') {
            log.push({ note: 'undo', text: text.slice(1, -1) });
            i += 1;
        } else {
            log.push(message);
        }
    }
    return { ...rest, log, earlier: { transcript, entries: log.length } };
}

class Conversation {
    /**
     * @param {object} files  the project's files (agent/project-files.js)
     * @param {object} [saved]  as toJSON gives it
     */
    constructor(files, { id = null, title = '', createdAt = null, log = [], checkpoints = [], turn = 0, earlier = null } = {}) {
        Object.assign(this, { id, title, createdAt, log, turn, earlier });
        this.checkpoints = new Checkpoints(files, checkpoints);
    }

    /** A saved conversation, in this format or the first. */
    static load(files, saved) {
        return new Conversation(files, saved.version === 2 ? saved : fromFirstFormat(saved));
    }

    /** Keep a panel event in the log, if it is one the messages don't hold. */
    keep(event) {
        if (KEPT_EVENTS.has(event.type)) this.log.push({ event });
    }

    /** What the panel shows of the conversation, as panel events. */
    render() {
        const earlier = this.earlier || { transcript: [], entries: 0 };
        return [...earlier.transcript, ...renderLog(this.log.slice(earlier.entries))];
    }

    toJSON() {
        return { version: 2, id: this.id, title: this.title, createdAt: this.createdAt, log: this.log,
            checkpoints: this.checkpoints.toJSON(), turn: this.turn, ...(this.earlier ? { earlier: this.earlier } : {}) };
    }
}

module.exports = { Conversation, renderLog, KEPT_EVENTS };
