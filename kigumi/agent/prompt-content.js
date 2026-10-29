/**
 * What a user's request adds to the log: a note of what they are looking at, then their message,
 * with each @-mentioned file attached and any images they attached.
 */

/** The most of the active panel's description sent with a message. */
const MAX_CONTEXT_CHARS = 2000;
/** Most of a file an @-mention attaches, in characters. */
const MAX_MENTIONED_CHARS = 40000;

/** A note of what the user is looking at, or null. */
function contextNote(described) {
    if (!described) return null;
    const context = JSON.stringify(described);
    const shown = context.length > MAX_CONTEXT_CHARS ? `${context.slice(0, MAX_CONTEXT_CHARS)}…` : context;
    return { note: 'context', text: `What the user is looking at in Kigumi: ${shown}` };
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
 * A request's log entries: a note of what is in view, then the user's message (mentions attached,
 * then images, or a note for a model that can't see them). The message's `shown` is what the panel shows.
 */
async function promptEntries({ text, images = [], files, describe, modelSeesImages }) {
    const note = contextNote(await describe().catch(() => null));
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

module.exports = { contextNote, withMentions, promptEntries };
