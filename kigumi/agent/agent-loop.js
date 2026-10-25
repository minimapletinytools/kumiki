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
/** Per step. Unset, a provider may reserve its maximum (64k for Haiku) against the balance. */
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
            // An image the user attached counts too.
            out[i] = { ...message, content: message.content.map((part) => {
                if (!part || part.type !== 'image') return part;
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
    + 'numbers exact. Plain text, as short as it can be while keeping all of that.';

/**
 * `history` summarised by the model into one exchange, when it is large; else as it is. Returns
 * { history, summarised, costUsd }.
 */
async function summariseIfLarge(model, system, history, abortSignal) {
    if (estimateTokens(history) < SUMMARISE_AT_TOKENS) return { history, summarised: false };
    // Streamed like every other request, which is all the backend carries cost reports for.
    const result = streamText({
        model, system, abortSignal, maxRetries: 2, maxOutputTokens: MAX_OUTPUT_TOKENS,
        messages: [...trimOldToolResults(onlyLatestImage(history), 0), { role: 'user', content: SUMMARY_REQUEST }],
    });
    const summary = await result.text;
    const metadata = await result.providerMetadata;
    const openrouter = metadata && metadata.openrouter;
    return {
        history: [
            { role: 'user', content: `[A summary of our conversation so far]\n${summary}` },
            { role: 'assistant', content: 'Understood; I will carry on from there.' },
        ],
        summarised: true,
        costUsd: openrouter && openrouter.usage && openrouter.usage.cost,
    };
}

/** Kigumi's tools as an AI SDK tool set. */
function toToolSet(tools, { images, askPermission }) {
    return Object.fromEntries(tools.map((kigumiTool) => [kigumiTool.name, tool({
        description: kigumiTool.description,
        inputSchema: z.object(kigumiTool.shape),
        execute: async (input, { toolCallId } = {}) => {
            if (!kigumiTool.readOnly && !(await askPermission(kigumiTool.name, input))) {
                throw new Error('The user did not allow this.');
            }
            return kigumiTool.run(input || {}, { toolCallId });
        },
        toModelOutput: ({ output }) => toModelContent(output, images),
    })]));
}

/** Why a turn ended other than by the model finishing, for the panel; or null. */
function earlyEnd(steps) {
    const last = steps[steps.length - 1];
    if (!last) return null;
    if (last.finishReason === 'tool-calls' && steps.length >= MAX_STEPS) {
        return `Stopped after ${MAX_STEPS} steps. Say "continue" to carry on.`;
    }
    if (last.finishReason === 'length') {
        return 'Stopped at the output limit for one step. Say "continue" to carry on.';
    }
    if (['stop', 'tool-calls'].includes(last.finishReason)) return null;
    return `The model stopped unexpectedly (${last.rawFinishReason || last.finishReason}). Say "continue" to carry on.`;
}

/**
 * Run one user turn.
 *
 * @param {object} options
 * @param {object} options.model         an AI SDK language model (languageModelFor)
 * @param {boolean} options.images       whether the model can look at images
 * @param {boolean} [options.cacheMarks] whether to mark where its prompt cache should hold (models.js)
 * @param {number} [options.contextWindow] the model's, for the panel's context meter
 * @param {object[]} options.tools       Kigumi tools
 * @param {string} options.system
 * @param {object[]} options.history     the conversation so far, as model messages
 * @param {string|object[]} options.prompt  text, or content parts (text and images)
 * @param {AbortSignal} [options.abortSignal]
 * @param {(toolName: string, input: object) => Promise<boolean>} options.askPermission
 * @param {(event: object) => void} options.onEvent   panel events
 * @returns {Promise<{ history: object[], costUsd?: number }>} the conversation after the turn. A turn
 *     that fails throws, with the conversation as far as it got as the error's `history`.
 */
async function runTurn({ model, images, cacheMarks = false, contextWindow, tools, system, history, prompt, abortSignal,
    askPermission, onEvent }) {
    const compacted = await summariseIfLarge(model, system, history, abortSignal);
    if (compacted.summarised) {
        onEvent({ type: 'agent:notice', text: 'The earlier conversation was summarised, to keep each step small.' });
    }
    const messages = [...compacted.history, { role: 'user', content: prompt }];
    const steps = [];
    let failure = null;
    const result = streamText({
        model,
        system,
        messages,
        tools: toToolSet(tools, { images, askPermission }),
        stopWhen: stepCountIs(MAX_STEPS),
        maxOutputTokens: MAX_OUTPUT_TOKENS,
        abortSignal,
        // A request refused or failed (busy, rate limited, an upstream error) is never charged, so
        // retrying one costs nothing.
        maxRetries: 2,
        prepareStep: ({ messages: sending }) => {
            const trimmed = trimOldToolResults(onlyLatestImage(sending));
            return { messages: cacheMarks ? cacheMarked(trimmed) : trimmed };
        },
        onStepEnd: (step) => {
            steps.push(step);
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
    const notice = earlyEnd(steps);
    if (notice) onEvent({ type: 'agent:notice', text: notice });
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
