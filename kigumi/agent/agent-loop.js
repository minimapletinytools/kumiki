/**
 * The built-in agent's loop: one user turn, as many model steps and tool calls as it takes, on the
 * Vercel AI SDK. Host-neutral (no Node APIs), so the desktop app and the web page run the same loop.
 *
 * The turn appends to the conversation's log (agent/conversation.js) as it goes, and each step's
 * request is built from the log (agent/request.js). Tools are Kigumi's ({ name, description, shape,
 * effect, run }, agent/agent.js); one that does more than read waits on `askPermission` first. What
 * happens is reported as panel events (see agent/agent-session.js).
 */

// require() of these ES modules needs Node 22.12+ (Electron 44 has it).
const { streamText, stepCountIs, tool } = require('ai');
// The same zod the tools' shapes are made with (agent/tools.js).
const { z } = require('zod');
const { backendFetch } = require('./backend-fetch');
const { buildRequest, estimateTokens } = require('./request');

/** Steps in one turn, each a model call and the tools it asks for. */
const MAX_STEPS = 40;
/** Per step, unless the user's setting says more. Unset, a provider may reserve its maximum (64k for Haiku) against the balance. */
const MAX_OUTPUT_TOKENS = 8000;
/** Continuations after a stream closes without a completion signal, within the turn's step limit. */
const MAX_STREAM_CONTINUATIONS = 2;
/** Past this many tokens (estimated) at the start of a turn, the conversation before it is summarised. */
const SUMMARISE_AT_TOKENS = 100000;

/** What Kigumi tells the model, by note kind. */
const NOTES = {
    continuation: () => 'The previous response stream ended without a completion signal. Continue from where you left '
        + 'off, using the tool results already in this conversation. Do not repeat completed changes.',
    nudge: (looks) => `You have made ${looks} tool calls this turn without changing anything. If the current request is `
        + 'to write or change a frame, write a first version now. Use kumiki_api for specific signatures and let actual '
        + 'build errors guide further lookups. Do not reread files you already have. Only report writing, running, or '
        + 'building after the corresponding tool has actually done it.',
    repeat: (call) => `Your call ${call} gave the same result as the same call earlier this turn. To see something else, `
        + 'change the arguments: read_file reads on from `offset`.',
};

/** Return the AI SDK language model a route (agent/models.js routeModel) names. */
async function languageModelFor(route, { fetch, onWait } = {}) {
    const { createOpenRouter } = require('@openrouter/ai-sdk-provider');
    const provider = createOpenRouter({
        // Through the backend, `fetch` puts the account's token in instead.
        apiKey: route.apiKey || 'kigumi-account', compatibility: 'strict',
        fetch: route.via === 'backend' ? backendFetch(fetch || globalThis.fetch, { onWait }) : fetch,
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

/** Tool calls in a turn without a write or edit between progress reminders. */
const LOOKS_BEFORE_NUDGE = 6;
const WRITE_TOOLS = new Set(['write_file', 'edit_file']);

const SUMMARY_REQUEST = 'Summarise our conversation so far for carrying on the work: what the user wants, what '
    + 'has been done (files changed and how), what was found, and what is left. Keep file paths, names and '
    + 'numbers exact. Say only what the conversation shows; mark anything you did not confirm as a guess. Plain '
    + 'text, as short as it can be while keeping all of that.';

/** The most of each changed file, and of all of them, a summary carries. */
const MAX_CHANGED_FILE_CHARS = 20000;
const MAX_CHANGED_CHARS = 60000;

/** The files the log's write_file and edit_file calls changed. */
function changedFiles(log) {
    const files = new Set();
    for (const entry of log) {
        if (entry.role !== 'assistant' || !Array.isArray(entry.content)) continue;
        for (const part of entry.content) {
            if (part.type === 'tool-call' && WRITE_TOOLS.has(part.toolName) && part.input && part.input.file_path) {
                files.add(part.input.file_path);
            }
        }
    }
    return [...files];
}

/** The changed files as they are now, for a summary: it can be wrong about what is in them, and the model goes by it. */
async function changedFilesNow(log, files) {
    if (!files) return '';
    const shown = [];
    let total = 0;
    for (const file of changedFiles(log)) {
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
 * When the request `log` would send is large, have the model summarise it and append the summary,
 * with the files the conversation changed as they are now (`files`, project-files.js). Returns the
 * summary's cost, or undefined.
 */
async function summariseIfLarge({ model, system, log, abortSignal, files = null, cacheMarks = false }) {
    if (estimateTokens(buildRequest(log, { cacheMarks })) < SUMMARISE_AT_TOKENS) return undefined;
    // Streamed like every other request, which is all the backend carries cost reports for.
    const result = streamText({
        model, system, abortSignal, maxRetries: 2, maxOutputTokens: MAX_OUTPUT_TOKENS,
        messages: [...buildRequest(log, { keep: 0 }), { role: 'user', content: SUMMARY_REQUEST }],
    });
    const summary = await result.text;
    const metadata = await result.providerMetadata;
    log.push({ summary: `${summary}${await changedFilesNow(log, files)}` });
    const openrouter = metadata && metadata.openrouter;
    return openrouter && openrouter.usage && openrouter.usage.cost;
}

/** Kigumi's tools as an AI SDK tool set; a look repeated with the same result calls `onRepeat(call)`. */
function toToolSet(tools, { images, askPermission, onRepeat }) {
    // This turn's looks and what each gave: a small model repeats one, e.g. read_file without the offset it meant.
    const looked = new Map();
    const noteRepeat = (name, input, output) => {
        if (!Array.isArray(output) || output.some((part) => part.type === 'image')) return;
        const call = `${name} ${JSON.stringify(input)}`;
        const result = JSON.stringify(output);
        if (looked.get(call) === result) onRepeat(call);
        looked.set(call, result);
    };
    return Object.fromEntries(tools.map((kigumiTool) => [kigumiTool.name, tool({
        description: kigumiTool.description,
        inputSchema: z.object(kigumiTool.shape),
        execute: async (input, { toolCallId } = {}) => {
            if (kigumiTool.effect !== 'read' && !(await askPermission(kigumiTool.name, input))) {
                throw new Error('The user did not allow this.');
            }
            const output = await kigumiTool.run(input || {}, { toolCallId });
            if (kigumiTool.effect !== 'edit') noteRepeat(kigumiTool.name, input || {}, output);
            return output;
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
 * Run one user turn, appending to `log` as it goes: a summary first if the conversation is large,
 * then `prompt`, then each step's messages and Kigumi's notes. A turn that fails throws, and the log
 * keeps the steps it finished.
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
 * @param {object[]} options.log         the conversation's log
 * @param {object[]} options.prompt      the entries the user's request adds (agent/prompt-content.js)
 * @param {AbortSignal} [options.abortSignal]
 * @param {(toolName: string, input: object) => Promise<boolean>} options.askPermission
 * @param {(event: object) => void} options.onEvent   panel events
 * @returns {Promise<{ costUsd?: number }>}
 */
async function runTurn({ model, images, cacheMarks = false, contextWindow, maxOutputTokens = MAX_OUTPUT_TOKENS, maxSteps = MAX_STEPS, tools, files = null,
    system, log, prompt, abortSignal, askPermission, onEvent }) {
    const costs = [];
    const summaryCost = await summariseIfLarge({ model, system, log, abortSignal, files, cacheMarks });
    if (log.at(-1) && log.at(-1).summary !== undefined) {
        if (typeof summaryCost === 'number') costs.push(summaryCost);
        onEvent({ type: 'agent:notice', key: 'agent.notice.summarised', text: 'The earlier conversation was summarised, to keep each step small.' });
    }
    log.push(...prompt);
    const steps = [];
    let looks = 0;
    let nudgedAt = null;
    // Repeated looks this step, noted after its tool results.
    let repeats = [];
    const toolSet = toToolSet(tools, { images, askPermission, onRepeat: (call) => repeats.push(call) });
    const request = () => buildRequest(log, { cacheMarks });
    for (let continuations = 0; ; continuations++) {
        const before = steps.length;
        let failure = null;
        const result = streamText({
            model,
            system,
            messages: request(),
            tools: toolSet,
            stopWhen: stepCountIs(maxSteps - steps.length),
            maxOutputTokens,
            abortSignal,
            // Retry transient request failures before streaming begins.
            maxRetries: 2,
            prepareStep: () => {
                if (looks >= LOOKS_BEFORE_NUDGE && (nudgedAt === null || looks - nudgedAt >= LOOKS_BEFORE_NUDGE)) {
                    nudgedAt = looks;
                    log.push({ note: 'nudge', text: NOTES.nudge(looks) });
                }
                return { messages: request() };
            },
            onStepEnd: (step) => {
                steps.push(step);
                log.push(...step.response.messages);
                log.push(...repeats.map((call) => ({ note: 'repeat', text: NOTES.repeat(call) })));
                repeats = [];
                for (const call of step.toolCalls || []) {
                    if (WRITE_TOOLS.has(call.toolName)) {
                        looks = 0;
                        nudgedAt = null;
                    } else {
                        looks += 1;
                    }
                }
                const tokens = step.usage && step.usage.inputTokens;
                if (typeof tokens === 'number') onEvent({ type: 'agent:context', tokens, window: contextWindow || null });
            },
            onError: ({ error }) => { failure = error; },
        });
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
        if (failure) throw failure;
        const last = steps.at(-1);
        if (abortSignal?.aborted || steps.length === before || last.finishReason !== 'other'
            || (last.rawFinishReason && last.rawFinishReason !== 'other') || last.toolCalls.length || steps.length >= maxSteps
            || continuations >= MAX_STREAM_CONTINUATIONS) break;
        log.push({ note: 'continuation', text: NOTES.continuation() });
        onEvent({ type: 'agent:notice', key: 'agent.notice.continuing',
            params: { attempt: continuations + 1, attempts: MAX_STREAM_CONTINUATIONS },
            text: `The response stream ended early. Continuing automatically (${continuations + 1}/${MAX_STREAM_CONTINUATIONS}).` });
    }
    const notice = earlyEnd(steps, maxSteps);
    if (notice && !abortSignal?.aborted) onEvent({ type: 'agent:notice', ...notice });
    for (const step of steps) {
        const cost = step.providerMetadata && step.providerMetadata.openrouter
            && step.providerMetadata.openrouter.usage && step.providerMetadata.openrouter.usage.cost;
        if (typeof cost === 'number') costs.push(cost);
    }
    return { costUsd: costs.length ? costs.reduce((sum, cost) => sum + cost, 0) : undefined };
}

module.exports = { runTurn, languageModelFor, toModelContent, summarise, summariseIfLarge, changedFiles,
    NOTES, SUMMARISE_AT_TOKENS, MAX_STEPS, MAX_OUTPUT_TOKENS };
