/**
 * The built-in agent's loop: one user turn, as many model steps and tool calls as it takes, on the
 * Vercel AI SDK. Host-neutral (no Node APIs), so the desktop app and the web page run the same loop.
 *
 * Tools are Kigumi's ({ name, description, shape, readOnly, run }, agent/tools.js); one that changes
 * something waits on `askPermission` first. What happens is reported as panel events (see
 * agent/agent-session.js).
 */

// require() of these ES modules needs Node 22.12+ (Electron 44 has it).
const { streamText, stepCountIs, tool } = require('ai');
// The same zod the tools' shapes are made with (agent/tools.js).
const { z } = require('zod');

/** Steps in one turn, each a model call and the tools it asks for. */
const MAX_STEPS = 40;
/** Per step, unless the user's setting says more. Unset, a provider may reserve its maximum (64k for Haiku) against the balance. */
const MAX_OUTPUT_TOKENS = 8000;

/** Return the AI SDK language model a route (agent/models.js routeModel) names. */
async function languageModelFor(route, { fetch } = {}) {
    if (route.via === 'anthropic') {
        const { createAnthropic } = require('@ai-sdk/anthropic');
        return createAnthropic({ apiKey: route.apiKey, fetch })(route.modelId);
    }
    const { createOpenRouter } = require('@openrouter/ai-sdk-provider');
    const provider = createOpenRouter({
        // Through the backend, `fetch` puts the account's token in instead.
        apiKey: route.apiKey || 'kigumi-account', compatibility: 'strict', fetch,
        ...(route.baseURL ? { baseURL: route.baseURL } : {}),
        headers: { 'X-Title': 'Kigumi' },
    });
    // Usage accounting reports each request's cost, which the backend charges by.
    return provider.chat(route.modelId, { usage: { include: true } });
}

/** A tool result (MCP content) as text for the panel. */
function summarise(content) {
    if (!Array.isArray(content)) {
        return typeof content === 'string' ? content : JSON.stringify(content);
    }
    return content.map((part) => (part.type === 'text' ? part.text : part.type === 'image' ? '[image]' : ''))
        .filter(Boolean).join('\n');
}

/** MCP content as what the model is sent: images as files, or a note for a model that can't see. */
function toModelContent(content, images) {
    const parts = (Array.isArray(content) ? content : [{ type: 'text', text: summarise(content) }]).map((part) => {
        if (part.type !== 'image') {
            return { type: 'text', text: part.text || '' };
        }
        return images
            ? { type: 'file', data: { type: 'data', data: part.data }, mediaType: part.mimeType }
            : { type: 'text', text: '[An image this model cannot see. Describe the view with describe_panel instead.]' };
    });
    return { type: 'content', value: parts };
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

/** Tool calls in a row without a write or edit before the model is nudged to write. */
const LOOKS_BEFORE_NUDGE = 25;
const WRITE_TOOLS = new Set(['write_file', 'edit_file']);
const WRITE_EARLY = `[From Kigumi: that's ${LOOKS_BEFORE_NUDGE} tool calls without changing anything. If the task is to `
    + 'write or change a frame, write a first version now, from the nearest example, and let the build\'s errors '
    + 'show what to look up next.]';

/**
 * Whether the model has looked `LOOKS_BEFORE_NUDGE` times since it last wrote (or since the turn
 * began). A model given a library to learn can read for 60 steps before writing a line, where a
 * first version's build errors would have shown what it needed.
 */
function lookedTooLong(steps) {
    let looks = 0;
    for (let i = steps.length - 1; i >= 0; i--) {
        const calls = steps[i].toolCalls || [];
        if (calls.some((call) => WRITE_TOOLS.has(call.toolName))) break;
        looks += calls.length;
    }
    return looks >= LOOKS_BEFORE_NUDGE;
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
 * conversation so far from the cache. Marks carry forward between steps, and Anthropic takes four.
 */
function cacheMarked(messages) {
    return messages.map((message, i) => {
        const { openrouter, anthropic, ...others } = message.providerOptions || {};
        const rest = Object.keys(others).length ? others : undefined;
        if (i < messages.length - 2) {
            return { ...message, providerOptions: rest };
        }
        return { ...message, providerOptions: { ...others, openrouter: { cacheControl: CACHE_HERE }, anthropic: { cacheControl: CACHE_HERE } } };
    });
}

/** Tool results kept whole; older ones are cut down (trimOldToolResults). */
const KEEP_TOOL_RESULTS = 8;
/** What an older tool result is cut to, in characters. */
const TRIMMED_TO = 300;
/** Past this many tokens (estimated) at the start of a turn, the conversation before it is summarised. */
const SUMMARISE_AT_TOKENS = 100000;

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
 * `messages` with all but the last few tool results cut down. Every step resends the whole
 * conversation, and tool results (files read, logs) are most of it.
 */
function trimOldToolResults(messages, keep = KEEP_TOOL_RESULTS) {
    let seen = 0;
    const out = [...messages];
    for (let i = out.length - 1; i >= 0; i--) {
        const message = out[i];
        if (message.role !== 'tool' || !Array.isArray(message.content)) continue;
        out[i] = { ...message, content: message.content.map((part) => {
            if (!part || part.type !== 'tool-result' || !part.output) return part;
            seen += 1;
            return seen > keep ? { ...part, output: trimmedOutput(part.output) } : part;
        }) };
    }
    return out;
}

const SUMMARY_REQUEST = 'Summarise our conversation so far for carrying on the work: what the user wants, what '
    + 'has been done (files changed and how), what was found, and what is left. Keep file paths, names and '
    + 'numbers exact. Say only what the conversation shows; mark anything you did not confirm as a guess. Plain '
    + 'text, as short as it can be while keeping all of that.';

/** The most of each changed file, and of all of them, a summary carries. */
const MAX_CHANGED_FILE_CHARS = 20000;
const MAX_CHANGED_CHARS = 60000;
const CHANGED_FILE_HEADING = /^\[The file (.+) as it is now\]$/gm;

/**
 * The files `history` wrote or edited: by write_file and edit_file calls, and in an earlier
 * summary, by the files it carried.
 */
function changedFiles(history) {
    const files = new Set();
    for (const message of history) {
        if (message.role === 'assistant' && Array.isArray(message.content)) {
            for (const part of message.content) {
                if (part.type === 'tool-call' && ['write_file', 'edit_file'].includes(part.toolName) && part.input && part.input.file_path) {
                    files.add(part.input.file_path);
                }
            }
        } else if (message.role === 'user' && typeof message.content === 'string') {
            for (const [, file] of message.content.matchAll(CHANGED_FILE_HEADING)) files.add(file);
        }
    }
    return [...files];
}

/**
 * The changed files as they are now, for a summary: it can be wrong about what is in them (one
 * said a bug was still there after it was fixed), and this is what the model goes by.
 */
async function changedFilesNow(history, files) {
    if (!files) return '';
    const shown = [];
    let total = 0;
    for (const file of changedFiles(history)) {
        const content = await files.read(file).catch(() => null);
        if (content === null || total >= MAX_CHANGED_CHARS) continue;
        const cut = content.length > MAX_CHANGED_FILE_CHARS ? `${content.slice(0, MAX_CHANGED_FILE_CHARS)}\n[…cut off]` : content;
        total += cut.length;
        shown.push(`[The file ${file} as it is now]\n\`\`\`\n${cut}\n\`\`\``);
    }
    return shown.length
        ? `\n\n[The files changed so far, as they are now. Where the summary disagrees with them, they are right.]\n\n${shown.join('\n\n')}`
        : '';
}

/**
 * `history` summarised by the model into one exchange, when it is large; else as it is, with the
 * files it changed as they are now (`files`, project-files.js). Returns { history, summarised, costUsd }.
 */
async function summariseIfLarge(model, system, history, abortSignal, files = null) {
    if (estimateTokens(history) < SUMMARISE_AT_TOKENS) return { history, summarised: false };
    // Streamed like every other request, which is all the backend carries cost reports for.
    const result = streamText({
        model, system, abortSignal, maxRetries: 2, maxOutputTokens: MAX_OUTPUT_TOKENS,
        messages: [...imagesAfterToolResults(trimOldToolResults(onlyLatestImage(history), 0)), { role: 'user', content: SUMMARY_REQUEST }],
    });
    const summary = await result.text;
    const metadata = await result.providerMetadata;
    const openrouter = metadata && metadata.openrouter;
    return {
        history: [
            { role: 'user', content: `[A summary of our conversation so far]\n${summary}${await changedFilesNow(history, files)}` },
            { role: 'assistant', content: 'Understood; I will carry on from there.' },
        ],
        summarised: true,
        costUsd: openrouter && openrouter.usage && openrouter.usage.cost,
    };
}

/** Kigumi's tools as an AI SDK tool set. */
/** Put before a look that repeats one from earlier in the turn, with the same result. */
const REPEATED_LOOK = '[You made this same call earlier in this turn and got this same result. To see something else, '
    + 'change the arguments: read_file reads on from `offset`.]';

function toToolSet(tools, { images, askPermission }) {
    // This turn's looks and what each gave: a small model repeats one, e.g. read_file without the offset it meant.
    const looked = new Map();
    const noteRepeat = (name, input, output) => {
        if (!Array.isArray(output) || output.some((part) => part.type === 'image')) return output;
        const call = `${name} ${JSON.stringify(input)}`;
        const result = JSON.stringify(output);
        const repeated = looked.get(call) === result;
        looked.set(call, result);
        return repeated ? [{ type: 'text', text: REPEATED_LOOK }, ...output] : output;
    };
    return Object.fromEntries(tools.map((kigumiTool) => [kigumiTool.name, tool({
        description: kigumiTool.description,
        inputSchema: z.object(kigumiTool.shape),
        execute: async (input, { toolCallId } = {}) => {
            if (!kigumiTool.readOnly && !(await askPermission(kigumiTool.name, input))) {
                throw new Error('The user did not allow this.');
            }
            const output = await kigumiTool.run(input || {}, { toolCallId });
            return kigumiTool.readOnly ? noteRepeat(kigumiTool.name, input || {}, output) : output;
        },
        toModelOutput: ({ output }) => toModelContent(output, images),
    })]));
}

/** Why a turn ended other than by the model finishing, for the panel ({key, params, text}); or null. */
function earlyEnd(steps, maxSteps = MAX_STEPS) {
    const last = steps[steps.length - 1];
    if (!last) return null;
    if (last.finishReason === 'tool-calls' && steps.length >= maxSteps) {
        return { key: 'agent.notice.maxSteps', params: { steps: maxSteps }, text: `Stopped after ${maxSteps} steps. Say "continue" to carry on.` };
    }
    if (last.finishReason === 'length') {
        return { key: 'agent.notice.outputLimit', text: 'Stopped at the output limit for one step. Say "continue" to carry on, or raise the limit in settings.' };
    }
    if (['stop', 'tool-calls'].includes(last.finishReason)) return null;
    const reason = last.rawFinishReason || last.finishReason;
    return { key: 'agent.notice.unexpected', params: { reason }, text: `The model stopped unexpectedly (${reason}). Say "continue" to carry on.` };
}

/**
 * Run one user turn.
 *
 * @param {object} options
 * @param {object} options.model         an AI SDK language model (languageModelFor)
 * @param {boolean} options.images       whether the model can look at images
 * @param {boolean} [options.cacheMarks] whether to mark where its prompt cache should hold (models.js)
 * @param {number} [options.contextWindow] the model's, for the panel's context meter
 * @param {number} [options.maxOutputTokens] the most one step may write
 * @param {number} [options.maxSteps]    the most steps in the turn
 * @param {object[]} options.tools       Kigumi tools
 * @param {object} [options.files]       the project's files (project-files.js), for a summary to carry changed ones
 * @param {string} options.system
 * @param {object[]} options.history     the conversation so far, as model messages
 * @param {string|object[]} options.prompt  text, or content parts (text and images)
 * @param {AbortSignal} [options.abortSignal]
 * @param {(toolName: string, input: object) => Promise<boolean>} options.askPermission
 * @param {(event: object) => void} options.onEvent   panel events
 * @returns {Promise<{ history: object[], costUsd?: number }>} the conversation after the turn. A turn
 *     that fails throws, with the conversation as far as it got as the error's `history`.
 */
async function runTurn({ model, images, cacheMarks = false, contextWindow, maxOutputTokens = MAX_OUTPUT_TOKENS, maxSteps = MAX_STEPS, tools, files = null,
    system, history, prompt, abortSignal, askPermission, onEvent }) {
    const compacted = await summariseIfLarge(model, system, history, abortSignal, files);
    if (compacted.summarised) {
        onEvent({ type: 'agent:notice', key: 'agent.notice.summarised', text: 'The earlier conversation was summarised, to keep each step small.' });
    }
    const messages = [...compacted.history, { role: 'user', content: prompt }];
    const steps = [];
    let nudged = false;
    let failure = null;
    const result = streamText({
        model,
        system,
        messages,
        tools: toToolSet(tools, { images, askPermission }),
        stopWhen: stepCountIs(maxSteps),
        maxOutputTokens,
        abortSignal,
        // A request refused or failed (busy, rate limited, an upstream error) is never charged, so
        // retrying one costs nothing.
        maxRetries: 2,
        prepareStep: ({ messages: sending }) => {
            const trimmed = imagesAfterToolResults(trimOldToolResults(onlyLatestImage(sending)));
            // Once in each stretch of looking: the note stays in the conversation, so it isn't added again.
            if (!nudged && lookedTooLong(steps)) {
                nudged = true;
                trimmed.push({ role: 'user', content: WRITE_EARLY });
            }
            return { messages: cacheMarks ? cacheMarked(trimmed) : trimmed };
        },
        onStepEnd: (step) => {
            steps.push(step);
            if ((step.toolCalls || []).some((call) => WRITE_TOOLS.has(call.toolName))) nudged = false;
            const tokens = step.usage && step.usage.inputTokens;
            if (typeof tokens === 'number') onEvent({ type: 'agent:context', tokens, window: contextWindow || null });
        },
        onError: ({ error }) => { failure = error; },
    });
    const sofar = () => trimOldToolResults(onlyLatestImage([...messages, ...steps.flatMap((step) => step.response.messages)]));
    try {
        for await (const part of result.fullStream) {
            if (part.type === 'text-delta') {
                onEvent({ type: 'agent:text', text: part.text });
            } else if (part.type === 'reasoning-delta') {
                onEvent({ type: 'agent:reasoning', text: part.text });
            } else if (part.type === 'tool-call') {
                onEvent({ type: 'agent:tool', id: part.toolCallId, name: part.toolName, input: part.input });
            } else if (part.type === 'tool-result') {
                onEvent({ type: 'agent:toolResult', id: part.toolCallId, isError: false, text: summarise(part.output).slice(0, 2000) });
            } else if (part.type === 'tool-error') {
                const error = part.error;
                onEvent({ type: 'agent:toolResult', id: part.toolCallId, isError: true, text: String((error && error.message) || error) });
            } else if (part.type === 'error') {
                failure = failure || part.error;
            }
        }
    } catch (error) {
        failure = failure || error;
    }
    if (failure) {
        throw Object.assign(failure, { history: sofar() });
    }
    const notice = earlyEnd(steps, maxSteps);
    if (notice) onEvent({ type: 'agent:notice', ...notice });
    const costs = steps.map((step) => step.providerMetadata && step.providerMetadata.openrouter
        && step.providerMetadata.openrouter.usage && step.providerMetadata.openrouter.usage.cost)
        .filter((cost) => typeof cost === 'number');
    if (typeof compacted.costUsd === 'number') costs.push(compacted.costUsd);
    return {
        history: sofar(),
        costUsd: costs.length ? costs.reduce((sum, cost) => sum + cost, 0) : undefined,
    };
}

module.exports = { runTurn, languageModelFor, toModelContent, summarise, onlyLatestImage, cacheMarked, trimOldToolResults,
    estimateTokens, summariseIfLarge, SUMMARISE_AT_TOKENS, MAX_STEPS, MAX_OUTPUT_TOKENS };
