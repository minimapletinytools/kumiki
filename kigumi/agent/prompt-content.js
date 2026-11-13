/**
 * What a user's request adds to the log: a note of what they are looking at, then their message,
 * with each @-mentioned file attached and any images they attached.
 */

const path = require('path');

/** The most of the active panel's description sent with a message. */
const MAX_CONTEXT_CHARS = 2000;
/** Most of a file an @-mention attaches, in characters. */
const MAX_MENTIONED_CHARS = 40000;

/**
 * Where the user is: the project open (its folder's name) and the file the active panel shows,
 * relative to the project when inside it.
 */
function focusOf(described, root) {
    const filePath = described && described.filePath;
    const inside = filePath && root && !path.relative(root, filePath).startsWith('..') && !path.isAbsolute(path.relative(root, filePath));
    return {
        project: root ? path.basename(root) : null,
        file: filePath ? (inside ? path.relative(root, filePath) : filePath) : null,
    };
}

/** The focus the latest context note in `log` recorded, or null. */
function lastFocus(log) {
    for (let i = log.length - 1; i >= 0; i--) {
        if (log[i].note === 'context' && log[i].focus) return log[i].focus;
    }
    return null;
}

const named = ({ project, file }) => `${file ? `${file} in ` : 'no file, in '}${project ? `the project ${project}` : 'no project'}`;

/**
 * A note of what the user is looking at, or null: the project open, the active panel's file and what
 * it shows; and, when the project or file differs from `previous` (the last note's focus), that the
 * user has switched, so the request is read as being about what they look at now.
 */
function contextNote(described, { root = null, previous = null } = {}) {
    if (!described && !root) return null;
    const focus = focusOf(described, root);
    const context = JSON.stringify({ project: focus.project, file: focus.file, panel: described || null });
    const shown = context.length > MAX_CONTEXT_CHARS ? `${context.slice(0, MAX_CONTEXT_CHARS)}…` : context;
    const switched = previous && (previous.project !== focus.project || previous.file !== focus.file)
        ? ` Since their last message the user has switched from ${named(previous)} to ${named(focus)}: `
            + 'take this request to be about what they are looking at now, unless it says otherwise.'
        : '';
    return { note: 'context', focus, text: `What the user is looking at in Kigumi: ${shown}${switched}` };
}

/**
 * `text` with each @-mentioned project file attached, and for @selection what is selected in full.
 * Mentions of anything outside the project, or of no file, attach nothing.
 */
async function withMentions(text, { files, describe }) {
    const attached = [];
    for (const [, written] of text.matchAll(/(?:^|\s)@([\w./-]+)/g)) {
        const mention = written.replace(/[.]+$/, ''); // the end of a sentence
        if (mention === 'selection') {
            const described = await describe().catch(() => null);
            if (described) attached.push(`[What I have selected]\n${JSON.stringify(described, null, 1)}`);
            continue;
        }
        let content = null;
        try {
            if (files.root() && await files.isFile(mention)) content = await files.read(mention);
        } catch (_error) {
            content = null; // outside the project
        }
        if (content === null) continue;
        const shown = content.length > MAX_MENTIONED_CHARS ? `${content.slice(0, MAX_MENTIONED_CHARS)}\n[…cut off]` : content;
        attached.push(`[The file ${files.relative(files.resolve(mention))}]\n\`\`\`\n${shown}\n\`\`\``);
    }
    return attached.length ? `${text}\n\n${attached.join('\n\n')}` : text;
}

/**
 * A request's log entries: a note of what is in view (and whether the user switched since `previous`, the last
 * note's focus), then the user's message (mentions attached,
 * then images, or a note for a model that can't see them). The message's `shown` is what the panel shows.
 */
async function promptEntries({ text, images = [], files, describe, modelSeesImages, previous = null }) {
    const note = contextNote(await describe().catch(() => null), { root: files.root(), previous });
    const full = await withMentions(text, { files, describe });
    const shown = { text, images: images.length };
    let content = full;
    if (images.length && !modelSeesImages) {
        content = `${full}\n\n[${images.length} image${images.length === 1 ? '' : 's'} attached, which this model can't see.]`;
    } else if (images.length) {
        content = [{ type: 'text', text: full },
            ...images.map((image) => ({ type: 'image', image: image.data, mediaType: image.mediaType || 'image/png' }))];
    }
    return [...(note ? [note] : []), { role: 'user', content, shown }];
}

module.exports = { contextNote, lastFocus, withMentions, promptEntries };
