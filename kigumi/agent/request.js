/**
 * What a step sends the model, built from the conversation's log (agent/conversation.js): the
 * entries since the latest summary, with Kigumi's notes as user messages, older tool results cut
 * down, only the latest image, images moved out of tool results, and prompt-cache marks.
 */

/** Whether a log entry is a model message. */
const isMessage = (entry) => Boolean(entry && entry.role);

/** A note entry as the message the model reads. */
function noteMessage({ text }) {
    return { role: 'user', content: `[Kigumi note: ${text}]` };
}

/** A summary entry as the message the model reads. */
function summaryMessage({ summary }) {
    return { role: 'user', content: `[A summary of our conversation so far]\n${summary}` };
}

/** The log's entries from its latest summary on, as model messages (without `shown`); panel events left out. */
function logMessages(log) {
    let start = 0;
    for (let i = log.length - 1; i >= 0; i--) {
        if (log[i].summary !== undefined) {
            start = i;
            break;
        }
    }
    const messages = [];
    for (const entry of log.slice(start)) {
        if (entry.summary !== undefined) messages.push(summaryMessage(entry));
        else if (entry.note) messages.push(noteMessage(entry));
        else if (isMessage(entry)) {
            const { shown, ...message } = entry;
            messages.push(message);
        }
    }
    return messages;
}

/**
 * The messages a step sends for `log`. `keep`: tool results kept whole (trimOldToolResults);
 * `imagesInToolResults`: leave images where they are (imagesAfterToolResults otherwise);
 * `cacheMarks`: mark where the prompt cache should hold (cacheMarked).
 */
function buildRequest(log, { keep = KEEP_TOOL_RESULTS, imagesInToolResults = false, cacheMarks = false } = {}) {
    const trimmed = trimOldToolResults(onlyLatestImage(logMessages(log)), keep);
    const messages = imagesInToolResults ? trimmed : imagesAfterToolResults(trimmed);
    return cacheMarks ? cacheMarked(messages) : messages;
}

const EARLIER_IMAGE = '[An earlier image, dropped: only the latest is kept. Take a screenshot to look again.]';

/**
 * `messages` with every image but the latest replaced by a note. A screenshot is about a megabyte,
 * and each step resends the whole conversation: kept, they made steps 2.5 MB and cost 40 times more.
 */
function onlyLatestImage(messages) {
    let kept = false;
    const out = [...messages];
    for (let i = out.length - 1; i >= 0; i--) {
        const message = out[i];
        if (message.role === 'user' && Array.isArray(message.content)) {
            // An image the user attached counts too, and one moved out of a tool result (imagesAfterToolResults).
            out[i] = { ...message, content: message.content.map((part) => {
                const image = part && (part.type === 'image' || (part.type === 'file' && /^image\//.test(part.mediaType || '')));
                if (!image) return part;
                if (!kept) {
                    kept = true;
                    return part;
                }
                return { type: 'text', text: EARLIER_IMAGE };
            }) };
            continue;
        }
        if (message.role !== 'tool' || !Array.isArray(message.content)) continue;
        const content = message.content.map((part) => {
            const output = part && part.type === 'tool-result' && part.output;
            if (!output || output.type !== 'content' || !output.value.some((item) => item.type === 'file')) return part;
            if (!kept) {
                kept = true;
                return part;
            }
            const value = output.value.map((item) => (item.type === 'file' ? { type: 'text', text: EARLIER_IMAGE } : item));
            return { ...part, output: { ...output, value } };
        });
        out[i] = { ...message, content };
    }
    return out;
}

const IMAGE_BELOW = '[The image is in the next message.]';

/**
 * `messages` with each tool result's images moved into a user message after it. Chat-completions
 * hosts take images only from the user: one in a tool result reaches DeepSeek's cheapest host as
 * nothing at all.
 */
function imagesAfterToolResults(messages) {
    const out = [];
    for (const message of messages) {
        if (message.role !== 'tool' || !Array.isArray(message.content)) {
            out.push(message);
            continue;
        }
        const images = [];
        const content = message.content.map((part) => {
            const output = part && part.type === 'tool-result' && part.output;
            if (!output || output.type !== 'content' || !output.value.some((item) => item.type === 'file')) return part;
            const value = output.value.map((item) => {
                if (item.type !== 'file') return item;
                images.push({ type: 'file', data: item.data, mediaType: item.mediaType });
                return { type: 'text', text: IMAGE_BELOW };
            });
            return { ...part, output: { ...output, value } };
        });
        out.push({ ...message, content });
        if (images.length) out.push({ role: 'user', content: [{ type: 'text', text: '[The image from the tool result above.]' }, ...images] });
    }
    return out;
}

const CACHE_HERE = { type: 'ephemeral' };

/**
 * `messages` with a prompt-cache mark on the last two and none elsewhere: each step then reads the
 * conversation so far from the cache. Anthropic takes four marks. A message's other options stay.
 */
function cacheMarked(messages) {
    return messages.map((message, i) => {
        const { openrouter = {}, ...others } = message.providerOptions || {};
        const { cacheControl, ...kept } = openrouter;
        const options = i < messages.length - 2 ? kept : { ...kept, cacheControl: CACHE_HERE };
        const providerOptions = Object.keys(options).length ? { ...others, openrouter: options } : others;
        const { providerOptions: _old, ...bare } = message;
        return Object.keys(providerOptions).length ? { ...bare, providerOptions } : bare;
    });
}

/** Tool results kept whole at the least; older ones are cut down, this many at a time (trimOldToolResults). */
const KEEP_TOOL_RESULTS = 8;
/** What an older tool result is cut to, in characters. */
const TRIMMED_TO = 300;

/** What an image counts for in estimateTokens: about what a model reads one as, not its encoded size. */
const IMAGE_TOKENS = 1500;

/** A rough token count: about four characters a token, and images at what a model reads them as. */
function estimateTokens(messages) {
    let images = 0;
    const text = JSON.stringify(messages, (key, value) => {
        // An image's data (a user's image, or a screenshot sent as a file) is hundreds of KB encoded.
        if ((key === 'image' || key === 'data') && typeof value === 'string' && value.length > 1000) {
            images += 1;
            return '';
        }
        return value;
    });
    return Math.round(text.length / 4) + images * IMAGE_TOKENS;
}

const TRIMMED_NOTE = '\n[… cut down to keep the conversation small; run the tool again if you need the rest.]';

/** A tool result's output cut to its first characters. */
function trimmedOutput(output) {
    const parts = output.type === 'content' ? output.value : [{ type: 'text', text: typeof output.value === 'string' ? output.value : JSON.stringify(output.value) }];
    const text = parts.filter((part) => part.type === 'text').map((part) => part.text).join('\n');
    if (text.length <= TRIMMED_TO + TRIMMED_NOTE.length) return output;
    return { type: 'content', value: [{ type: 'text', text: text.slice(0, TRIMMED_TO) + TRIMMED_NOTE }] };
}

/**
 * `messages` with older tool results cut down, `keep` at a time: between `keep` and `2 * keep - 1`
 * of the latest stay whole, so the cut moves only every `keep` results. `keep` 0 cuts them all.
 */
function trimOldToolResults(messages, keep = KEEP_TOOL_RESULTS) {
    const isResult = (part) => part && part.type === 'tool-result' && part.output;
    const total = messages.reduce((count, message) => count
        + (message.role === 'tool' && Array.isArray(message.content) ? message.content.filter(isResult).length : 0), 0);
    const cut = keep === 0 ? total : Math.floor(Math.max(0, total - keep) / keep) * keep;
    let seen = 0;
    return messages.map((message) => {
        if (seen >= cut || message.role !== 'tool' || !Array.isArray(message.content)) return message;
        return { ...message, content: message.content.map((part) => {
            if (!isResult(part)) return part;
            seen += 1;
            return seen <= cut ? { ...part, output: trimmedOutput(part.output) } : part;
        }) };
    });
}

module.exports = { buildRequest, logMessages, isMessage, onlyLatestImage, imagesAfterToolResults, cacheMarked,
    trimOldToolResults, estimateTokens, KEEP_TOOL_RESULTS };
