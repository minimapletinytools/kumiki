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

const EARLIER_IMAGE = '[An earlier screenshot, dropped: only the latest is kept. Take another to look again.]';

/**
 * `messages` with every image but the latest replaced by a note. A screenshot is about a megabyte,
 * and each step resends the whole conversation: kept, they made steps 2.5 MB and cost 40 times more.
 */
function onlyLatestImage(messages) {
    let kept = false;
    const out = [...messages];
    for (let i = out.length - 1; i >= 0; i--) {
        const message = out[i];
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

/** Kigumi's tools as an AI SDK tool set. */
function toToolSet(tools, { images, askPermission }) {
    return Object.fromEntries(tools.map((kigumiTool) => [kigumiTool.name, tool({
        description: kigumiTool.description,
        inputSchema: z.object(kigumiTool.shape),
        execute: async (input) => {
            if (!kigumiTool.readOnly && !(await askPermission(kigumiTool.name, input))) {
                throw new Error('The user did not allow this.');
            }
            return kigumiTool.run(input || {});
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
 * @param {object[]} options.tools       Kigumi tools
 * @param {string} options.system
 * @param {object[]} options.history     the conversation so far, as model messages
 * @param {string} options.prompt
 * @param {AbortSignal} [options.abortSignal]
 * @param {(toolName: string, input: object) => Promise<boolean>} options.askPermission
 * @param {(event: object) => void} options.onEvent   panel events
 * @returns {Promise<{ history: object[], costUsd?: number }>} the conversation after the turn. A turn
 *     that fails throws, with the conversation as far as it got as the error's `history`.
 */
async function runTurn({ model, images, tools, system, history, prompt, abortSignal, askPermission, onEvent }) {
    const messages = [...history, { role: 'user', content: prompt }];
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
        prepareStep: ({ messages: sending }) => ({ messages: onlyLatestImage(sending) }),
        onStepEnd: (step) => { steps.push(step); },
        onError: ({ error }) => { failure = error; },
    });
    const sofar = () => onlyLatestImage([...messages, ...steps.flatMap((step) => step.response.messages)]);
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
    return {
        history: sofar(),
        costUsd: costs.length ? costs.reduce((sum, cost) => sum + cost, 0) : undefined,
    };
}

module.exports = { runTurn, languageModelFor, toModelContent, summarise, onlyLatestImage, MAX_STEPS, MAX_OUTPUT_TOKENS };
