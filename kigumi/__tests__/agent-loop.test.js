const fs = require('fs');
const os = require('os');
const path = require('path');

const { MockLanguageModelV4, convertArrayToReadableStream } = require('ai/test');
const { runTurn, languageModelFor, toModelContent } = require('../agent/agent-loop');
const { cacheMarked, trimOldToolResults, estimateTokens, logMessages, isMessage } = require('../agent/request');
const { MODELS, HARNESS, findModel, harnessOf, createModelList, routeModel } = require('../agent/models');

const SUMMARISE_AT_TOKENS = HARNESS.summariseAt;
const { createFileTools } = require('../agent/file-tools');
const { createProjectFiles } = require('../agent/project-files');
const { contextNote, withMentions, promptEntries } = require('../agent/prompt-content');
const { AgentSession, RETRY_PROMPT, describeFailure, describeBuild } = require('../agent/agent-session');
const { viewHost } = require('../agent/agent');
const { z } = require('zod');

const USAGE = { inputTokens: { total: 10, noCache: 10, cacheRead: 0, cacheWrite: 0 }, outputTokens: { total: 5, text: 5, reasoning: 0 } };

function finish(reason, cost) {
    return {
        type: 'finish', finishReason: { unified: reason, raw: reason }, usage: USAGE,
        providerMetadata: cost === undefined ? undefined : { openrouter: { usage: { cost } } },
    };
}

/** A model that replies with each step's parts in turn. */
function scripted(...steps) {
    return new MockLanguageModelV4({ doStream: steps.map((parts) => ({ stream: convertArrayToReadableStream(parts) })) });
}

const say = (id, text) => [{ type: 'text-start', id }, { type: 'text-delta', id, delta: text }, { type: 'text-end', id }];
const call = (id, name, input = {}) => ({ type: 'tool-call', toolCallId: id, toolName: name, input: JSON.stringify(input) });

const lookTool = {
    name: 'look', description: 'Look.', shape: {}, effect: 'read',
    run: async () => [{ type: 'text', text: 'a frame' }, { type: 'image', data: 'AAAA', mimeType: 'image/png' }],
};
const changeTool = {
    name: 'change', description: 'Change.', shape: { what: z.string() }, effect: 'edit',
    run: jest.fn(async ({ what }) => [{ type: 'text', text: `changed ${what}` }]),
};

/** A user's request "go", as log entries. */
const go = () => [{ role: 'user', content: 'go', shown: { text: 'go', images: 0 } }];
/** The roles of the log's model messages. */
const roles = (log) => log.filter(isMessage).map((message) => message.role);

async function turn(model, { askPermission = async () => true, log = [], images = true } = {}) {
    const events = [];
    const result = await runTurn({
        model, images, tools: [lookTool, changeTool], system: 'sys', log, prompt: go(),
        askPermission, onEvent: (event) => events.push(event),
    });
    return { ...result, events, log };
}

describe('the model table', () => {
    test('every model has an OpenRouter id, and an unknown id finds the default', () => {
        expect(MODELS.every((model) => model.openrouter)).toBe(true);
        expect(findModel('nonsense')).toBe(MODELS[0]);
    });

    test("the user's OpenRouter key wins over the account", () => {
        const deepseek = findModel('deepseek-v4.1-flash');
        const backend = { url: 'https://api.example/' };

        expect(routeModel(deepseek, { backend })).toEqual(
            { via: 'backend', modelId: 'deepseek/deepseek-v4.1-flash', baseURL: 'https://api.example/v1' });
        expect(routeModel(deepseek, { openrouterKey: 'sk-or', backend }).via).toBe('openrouter');
        expect(routeModel(deepseek, {})).toBeNull();
    });

    test("the list is the backend's once heard, kept for next time; the saved one, else the bundled one, till then", async () => {
        const listed = [{ id: 'new-model', label: 'New', openrouter: 'x/new', images: false, contextWindow: 1000, maxPrice: 9 },
            { id: 'broken' }];
        let saved = null;
        const onChange = jest.fn();
        const fetch = jest.fn(async () => ({ ok: true, json: async () => ({ models: listed }) }));
        const models = createModelList({ backendUrl: 'https://api.example/', fetch, storage: { load: () => saved, save: (list) => { saved = list; } }, onChange });

        expect(models.list()).toBe(MODELS);
        await models.refresh();
        expect(fetch).toHaveBeenCalledWith('https://api.example/models');
        expect(models.list()).toEqual([{ id: 'new-model', label: 'New', openrouter: 'x/new', images: false, contextWindow: 1000 }]);
        expect(saved).toEqual(models.list());
        expect(onChange).toHaveBeenCalledTimes(1);
        await models.refresh();
        expect(onChange).toHaveBeenCalledTimes(1);
        expect(findModel('claude-haiku-4.5', models.list()).id).toBe('new-model');

        const offline = createModelList({ backendUrl: 'https://api.example', fetch: async () => { throw new Error('offline'); },
            storage: { load: () => saved, save: () => {} } });
        expect(offline.list()).toEqual(saved);
        await expect(offline.refresh()).rejects.toThrow('offline');
        expect(offline.list()).toEqual(saved);
    });

    test("a model's harness is the defaults with what the backend sets, of the right types", async () => {
        const listed = [{ id: 'm', label: 'M', openrouter: 'x/m', images: true, contextWindow: 1000,
            harness: { nudgeAfter: 0, keepToolResults: 'many', summariseAt: -1, imagesInToolResults: true, unknown: 1 } }];
        const models = createModelList({ backendUrl: 'https://api.example', fetch: async () => ({ ok: true, json: async () => ({ models: listed }) }) });
        await models.refresh();

        expect(models.list()[0].harness).toEqual({ nudgeAfter: 0, imagesInToolResults: true });
        expect(harnessOf(models.list()[0])).toEqual({ ...HARNESS, nudgeAfter: 0, imagesInToolResults: true });
        expect(harnessOf(MODELS[0])).toEqual(HARNESS);
    });
});

describe('the agent loop', () => {
    test('streams text, runs the tools the model asks for, and keeps the whole conversation', async () => {
        const model = scripted(
            [...say('1', 'Looking. '), call('c1', 'look'), finish('tool-calls', 0.001)],
            [...say('2', 'A frame.'), finish('stop', 0.002)],
        );

        const { events, log, costUsd } = await turn(model);

        expect(events.filter((event) => event.type !== 'agent:context')).toEqual([
            { type: 'agent:text', text: 'Looking. ' },
            { type: 'agent:tool', id: 'c1', name: 'look', input: {} },
            { type: 'agent:toolResult', id: 'c1', isError: false, text: 'a frame\n[image]' },
            { type: 'agent:text', text: 'A frame.' },
        ]);
        expect(roles(log)).toEqual(['user', 'assistant', 'tool', 'assistant']);
        expect(costUsd).toBeCloseTo(0.003);
        // The second step saw the screenshot as an image, in a user message after the tool result.
        const prompt = model.doStreamCalls[1].prompt;
        const tool = prompt.findIndex((message) => message.role === 'tool');
        expect(prompt[tool].content[0].output.value[1]).toEqual({ type: 'text', text: '[The image is in the next message.]' });
        expect(prompt[tool + 1].role).toBe('user');
        expect(prompt[tool + 1].content[1]).toMatchObject({ type: 'file', mediaType: 'image/png' });
    });

    test('a tool that changes something waits for permission; refused, the model is told so', async () => {
        const asked = [];
        const model = scripted(
            [call('c1', 'change', { what: 'the brace' }), finish('tool-calls')],
            [...say('2', 'OK, I will not.'), finish('stop')],
        );

        const { events } = await turn(model, { askPermission: async (name, input) => { asked.push([name, input]); return false; } });

        expect(asked).toEqual([['change', { what: 'the brace' }]]);
        expect(changeTool.run).not.toHaveBeenCalled();
        expect(events).toContainEqual({ type: 'agent:toolResult', id: 'c1', isError: true, text: 'The user did not allow this.' });
    });

    test('a later turn carries on from the log', async () => {
        const first = await turn(scripted([...say('1', 'Hello.'), finish('stop')]));
        const model = scripted([...say('2', 'Again.'), finish('stop')]);

        await turn(model, { log: first.log });

        expect(model.doStreamCalls[0].prompt.map((message) => message.role)).toEqual(['system', 'user', 'assistant', 'user']);
    });

    test('the model\'s reasoning is passed on as it streams', async () => {
        const model = scripted([
            { type: 'reasoning-start', id: 'r' }, { type: 'reasoning-delta', id: 'r', delta: 'Hmm.' }, { type: 'reasoning-end', id: 'r' },
            ...say('1', 'Done.'), finish('stop'),
        ]);
        const { events } = await turn(model);
        expect(events[0]).toEqual({ type: 'agent:reasoning', text: 'Hmm.' });
    });

    test('a turn cut short says so', async () => {
        const { events } = await turn(scripted([...say('1', 'Half a'), finish('length')]));
        expect(events.at(-1)).toMatchObject({ type: 'agent:notice', key: 'agent.notice.outputLimit', text: expect.stringContaining('output limit') });
    });

    test('an OpenRouter stream closed mid-reasoning continues from its partial response', async () => {
        const chunk = (delta, finish_reason = null) => `data: ${JSON.stringify({
            id: 'gen-test', model: 'deepseek/deepseek-v4.1-flash', created: 0,
            choices: [{ index: 0, delta, finish_reason }],
        })}\n\n`;
        const replies = [chunk({ reasoning: 'I need to inspect the' }),
            chunk({ content: 'The frame is ready.' }) + chunk({}, 'stop') + 'data: [DONE]\n\n'];
        const fetch = jest.fn(async () => new Response(replies.shift(), { headers: { 'Content-Type': 'text/event-stream' } }));
        const model = await languageModelFor({ via: 'openrouter', modelId: 'deepseek/deepseek-v4.1-flash', apiKey: 'test' }, { fetch });

        const { events, log } = await turn(model);

        expect(fetch).toHaveBeenCalledTimes(2);
        const continued = JSON.parse(fetch.mock.calls[1][1].body).messages;
        expect(log.filter(isMessage)[1].content).toContainEqual(expect.objectContaining({ type: 'reasoning', text: 'I need to inspect the' }));
        expect(continued.at(-1).content).toContain('Continue from where you left off');
        expect(events).toContainEqual(expect.objectContaining({ key: 'agent.notice.continuing' }));
        expect(events).not.toContainEqual(expect.objectContaining({ key: 'agent.notice.unexpected' }));
        expect(log.at(-1).content).toContainEqual(expect.objectContaining({ type: 'text', text: 'The frame is ready.' }));
        expect(log.filter((entry) => entry.note).map((entry) => entry.note)).toEqual(['continuation']);
    });

    test('continuing preserves completed tool results and accounts for every step without replaying edits', async () => {
        const interrupted = { ...finish('other', 0.002), finishReason: { unified: 'other' } };
        const model = scripted(
            [call('c1', 'change', { what: 'the leg' }), finish('tool-calls', 0.001)],
            [...say('1', 'Checking the'), interrupted],
            [...say('2', 'The leg is ready.'), finish('stop', 0.003)],
        );
        const previousCalls = changeTool.run.mock.calls.length;

        const { log, costUsd } = await turn(model);

        expect(changeTool.run.mock.calls.length - previousCalls).toBe(1);
        expect(costUsd).toBeCloseTo(0.006);
        // The continuation note goes as a user message.
        expect(logMessages(log).map((message) => message.role)).toEqual(['user', 'assistant', 'tool', 'assistant', 'user', 'assistant']);
        expect(JSON.stringify(model.doStreamCalls[2].prompt)).toContain('changed the leg');
    });

    test('an interrupted turn through the backend finishes without replaying its edit', async () => {
        const event = (delta, finish_reason = null) => `data: ${JSON.stringify({ id: 'gen-recovery', created: 0,
            model: 'deepseek/deepseek-v4.1-flash', choices: [{ index: 0, delta, finish_reason }] })}\n\n`;
        const stream = (text) => new Response(text, { headers: { 'Content-Type': 'text/event-stream' } });
        const replies = [
            stream(event({ tool_calls: [{ index: 0, id: 'edit-once', type: 'function',
                function: { name: 'change', arguments: '{"what":"the bookshelf"}' } }] }) + event({}, 'tool_calls') + 'data: [DONE]\n\n'),
            stream(event({ reasoning: 'Checking the bookshelf' })),
            stream(event({ content: 'The bookshelf is ready.' }) + event({}, 'stop') + 'data: [DONE]\n\n'),
        ];
        const fetch = jest.fn(async () => replies.shift());
        const model = await languageModelFor({ via: 'backend', modelId: 'deepseek/deepseek-v4.1-flash', baseURL: 'https://api.test/v1' },
            { fetch });
        const previousCalls = changeTool.run.mock.calls.length;

        const { events, log } = await turn(model);

        expect(fetch).toHaveBeenCalledTimes(3);
        expect(changeTool.run.mock.calls.length - previousCalls).toBe(1);
        expect(events).toContainEqual({ type: 'agent:text', text: 'The bookshelf is ready.' });
        expect(events).not.toContainEqual(expect.objectContaining({ key: 'agent.notice.unexpected' }));
        expect(JSON.stringify(log)).toContain('changed the bookshelf');
    });

    test.each([undefined, 'other'])('repeated incomplete streams (%s) stop after two continuations', async (raw) => {
        const interrupted = () => [...say('1', 'Thinking'), { ...finish('other'), finishReason: { unified: 'other', raw } }];
        const model = scripted(interrupted(), interrupted(), interrupted());

        const { events } = await turn(model);

        expect(model.doStreamCalls).toHaveLength(3);
        expect(events.filter((event) => event.key === 'agent.notice.continuing')).toHaveLength(2);
        expect(events.at(-1)).toMatchObject({ key: 'agent.notice.unexpected' });
    });

    test('the step limit includes steps before a continuation', async () => {
        const model = scripted(
            [{ ...finish('other'), finishReason: { unified: 'other' } }],
            [call('c1', 'look'), finish('tool-calls')],
            [call('c2', 'look'), finish('tool-calls')],
        );
        const events = [];

        await runTurn({ model, images: true, maxSteps: 3, tools: [lookTool], system: 'sys', log: [], prompt: go(),
            askPermission: async () => true, onEvent: (event) => events.push(event) });

        expect(model.doStreamCalls).toHaveLength(3);
        expect(events.at(-1)).toMatchObject({ key: 'agent.notice.maxSteps', params: { steps: 3 } });
    });

    test.each(['length', 'content-filter', 'error'])('an explicit %s finish is not continued automatically', async (reason) => {
        const model = scripted([...say('1', 'Partial'), finish(reason)]);

        const { events } = await turn(model);

        expect(model.doStreamCalls).toHaveLength(1);
        expect(events).not.toContainEqual(expect.objectContaining({ key: 'agent.notice.continuing' }));
    });

    test('stopping a response prevents automatic continuation', async () => {
        const abort = new AbortController();
        const model = scripted([...say('1', 'Partial'), { ...finish('other'), finishReason: { unified: 'other' } }]);
        const events = [];

        await runTurn({ model, images: true, tools: [], system: 'sys', log: [], prompt: go(), abortSignal: abort.signal,
            askPermission: async () => true, onEvent: (event) => {
                events.push(event);
                if (event.type === 'agent:context') abort.abort();
            } });

        expect(model.doStreamCalls).toHaveLength(1);
        expect(events).not.toContainEqual(expect.objectContaining({ key: 'agent.notice.continuing' }));
        expect(events).not.toContainEqual(expect.objectContaining({ key: 'agent.notice.unexpected' }));
    });

    test('a failed continuation preserves the partial response for retrying later', async () => {
        const model = new MockLanguageModelV4({ doStream: async () => {
            if (model.doStreamCalls.length > 1) throw Object.assign(new Error('Provider refused the continuation.'), { statusCode: 400 });
            return { stream: convertArrayToReadableStream([...say('1', 'Partial answer'),
                { ...finish('other'), finishReason: { unified: 'other' } }]) };
        } });

        const log = [];
        const failure = await turn(model, { log }).catch((error) => error);

        expect(failure.message).toBe('Provider refused the continuation.');
        expect(JSON.stringify(log)).toContain('Partial answer');
        expect(log.at(-1)).toMatchObject({ note: 'continuation', text: expect.stringContaining('Continue from where you left off') });
    });

    test('a failing step keeps the steps before it, for asking again', async () => {
        let calls = 0;
        const model = new MockLanguageModelV4({ doStream: async () => {
            calls += 1;
            if (calls > 1) throw Object.assign(new Error('One request at a time.'), { statusCode: 400 });
            return { stream: convertArrayToReadableStream([call('c1', 'look'), finish('tool-calls')]) };
        } });
        const log = [];
        const failed = await turn(model, { log }).catch((error) => error);
        expect(failed.message).toContain('One request at a time');
        expect(roles(log)).toEqual(['user', 'assistant', 'tool']);
    });

    test('a look repeated with the same arguments and result is told so; a changed result or arguments is not', async () => {
        let content = 'line 1';
        const readTool = { name: 'read', description: 'Read.', shape: { offset: z.number().optional() }, effect: 'read',
            run: async () => [{ type: 'text', text: content }] };
        const model = scripted(
            [call('c1', 'read'), finish('tool-calls')],
            [call('c2', 'read'), finish('tool-calls')],
            [call('c3', 'read', { offset: 5 }), finish('tool-calls')],
            [call('c4', 'read'), finish('tool-calls')],
            [...say('1', 'Done.'), finish('stop')],
        );
        const log = [];
        let results = 0;
        await runTurn({ model, images: true, tools: [readTool], system: 'sys', log, prompt: go(), askPermission: async () => true,
            onEvent: (event) => {
                // Changed after the third read: the fourth repeats the first's arguments, not its result.
                if (event.type === 'agent:toolResult' && ++results === 3) content = 'line 1 changed';
            } });
        // Noted once, after the second read's result.
        expect(log.filter((entry) => entry.note === 'repeat')).toEqual([{ note: 'repeat', text: expect.stringContaining('read {}') }]);
        expect(log.findIndex((entry) => entry.note === 'repeat')).toBe(log.findIndex((entry) => entry.role === 'tool'
            && entry.content[0].toolCallId === 'c2') + 1);
        expect(JSON.stringify(model.doStreamCalls[2].prompt)).toContain('[Kigumi note: Your call read {}');
    });

    test('after six looks without writing, progress reminders repeat every six calls', async () => {
        const readTool = { name: 'read', description: 'Read.', shape: { n: z.number().optional() }, effect: 'read',
            run: async ({ n }) => [{ type: 'text', text: `line ${n}` }] };
        const looks = (from, count) => Array.from({ length: count }, (_, i) => [call(`c${from + i}`, 'read', { n: from + i }), finish('tool-calls')]);
        const model = scripted(...looks(0, 30), [...say('1', 'Done.'), finish('stop')]);
        await runTurn({ model, images: true, tools: [readTool], system: 'sys', log: [], prompt: go(), askPermission: async () => true,
            onEvent: () => {} });
        const told = (i) => (JSON.stringify(model.doStreamCalls[i].prompt).match(/without changing anything/g) || []).length;
        expect(told(5)).toBe(0);
        expect(told(6)).toBe(1);
        expect(told(11)).toBe(1);
        expect(told(12)).toBe(2);
        expect(told(30)).toBe(5);

        // A model whose harness says none gets none.
        const quiet = scripted(...looks(0, 8), [...say('1', 'Done.'), finish('stop')]);
        await runTurn({ model: quiet, images: true, harness: { ...HARNESS, nudgeAfter: 0 }, tools: [readTool], system: 'sys', log: [],
            prompt: go(), askPermission: async () => true, onEvent: () => {} });
        expect(JSON.stringify(quiet.doStreamCalls)).not.toContain('without changing anything');
    });

    test('research in earlier turns does not count toward a reminder', async () => {
        const prior = await turn(scripted(...Array.from({ length: 8 }, (_, i) => [call(`c${i}`, 'look'), finish('tool-calls')]),
            [...say('1', 'Still researching.'), finish('stop')]));
        const model = scripted([call('c8', 'look'), finish('tool-calls')], [...say('2', 'It looks fine.'), finish('stop')]);

        const { log } = await turn(model, { log: prior.log });

        // The first turn's reminder stays in the log; the second turn adds none.
        expect(log.filter((entry) => entry.note === 'nudge')).toHaveLength(1);
    });

    test('only the latest screenshot is sent; earlier ones become a note', async () => {
        const model = scripted(
            [call('c1', 'look'), finish('tool-calls')],
            [call('c2', 'look'), finish('tool-calls')],
            [...say('1', 'Done.'), finish('stop')],
        );
        const { log } = await turn(model);

        const imagesIn = (messages) => messages.filter((message) => message.role === 'tool')
            .flatMap((message) => message.content).flatMap((part) => part.output.value)
            .filter((item) => item.type === 'file').length;
        const sent = model.doStreamCalls[2].prompt;
        // Sent in a user message after the tool result, as hosts take images only from the user.
        expect(imagesIn(sent)).toBe(0);
        const shown = sent.filter((message) => message.role === 'user' && Array.isArray(message.content))
            .flatMap((message) => message.content).filter((part) => part.type === 'file');
        expect(shown).toHaveLength(1);
        expect(shown[0].mediaType).toBe('image/png');
        expect(sent.map((message) => message.role)).toEqual(['system', 'user', 'assistant', 'tool', 'assistant', 'tool', 'user']);
        // The log keeps every image; only what is sent drops them.
        expect(imagesIn(log.filter(isMessage))).toBe(2);
        expect(JSON.stringify(sent)).toContain('An earlier image, dropped');
    });

        test('Claude models get a cache mark on the last two messages only, however many steps pass', () => {
        const marked = (messages) => messages.filter((message) => message.providerOptions
            && message.providerOptions.openrouter && message.providerOptions.openrouter.cacheControl).length;
        let messages = [1, 2, 3].map((n) => ({ role: 'user', content: `m${n}` }));
        for (let step = 0; step < 3; step++) {
            messages = cacheMarked([...messages, { role: 'assistant', content: `a${step}` }]);
        }
        expect(marked(messages)).toBe(2);
        expect(messages.at(-1).providerOptions.openrouter.cacheControl).toEqual({ type: 'ephemeral' });
        expect(messages[0].providerOptions).toBeUndefined();
    });

    test('Claude models are marked for caching; the others cache by themselves', async () => {
        const model = scripted([...say('1', 'Hi.'), finish('stop')]);
        const events = [];
        await runTurn({ model, images: true, cacheMarks: true, tools: [], system: 's', log: [], prompt: go(),
            askPermission: async () => true, onEvent: (event) => events.push(event) });
        expect(model.doStreamCalls[0].prompt.at(-1).providerOptions.openrouter.cacheControl).toEqual({ type: 'ephemeral' });
    });

    test('older tool results are cut down eight at a time, so the cut moves only every eight results', () => {
        const result = (id, text) => ({ role: 'tool', content: [{ type: 'tool-result', toolCallId: id, toolName: 'read_file',
            output: { type: 'content', value: [{ type: 'text', text }] } }] });
        const long = 'x'.repeat(5000);
        const lengths = (count) => trimOldToolResults(Array.from({ length: count }, (_, i) => result(`c${i}`, long)))
            .map((message) => message.content[0].output.value[0].text.length);

        expect(lengths(15)).toEqual(Array(15).fill(5000));
        expect(lengths(16).slice(8)).toEqual(Array(8).fill(5000));
        expect(lengths(16)[7]).toBeLessThan(500);
        // The results cut at 16 are cut the same way at 23: what was sent before is unchanged.
        expect(lengths(23).slice(0, 8)).toEqual(lengths(16).slice(0, 8));
        expect(lengths(23).slice(8)).toEqual(Array(15).fill(5000));

        const messages = Array.from({ length: 16 }, (_, i) => result(`c${i}`, long));
        const trimmed = trimOldToolResults(messages);
        expect(trimmed[0].content[0].output.value[0].text).toContain('run the tool again');
        expect(estimateTokens(trimmed)).toBeLessThan(estimateTokens(messages));
        expect(trimOldToolResults(trimmed)).toEqual(trimmed);
    });

    test('a large conversation is summarised at the start of a turn; the new request is kept as it is', async () => {
        const model = scripted(
            [...say('s', 'They want a sawhorse; frame.py has legs.'), finish('stop', 0.001)],
            [...say('1', 'Carrying on.'), finish('stop', 0.002)],
        );
        const big = [{ role: 'user', content: 'x'.repeat(SUMMARISE_AT_TOKENS * 4 + 100) }, { role: 'assistant', content: 'ok' }];

        const { events, log, costUsd } = await turn(model, { log: [...big] });

        expect(events).toContainEqual(expect.objectContaining({ type: 'agent:notice', key: 'agent.notice.summarised' }));
        // The log keeps what came before; what is sent starts from the summary.
        expect(log.slice(0, 2)).toEqual(big);
        expect(log[2].summary).toContain('They want a sawhorse');
        const sent = model.doStreamCalls[1].prompt;
        expect(sent.map((message) => message.role)).toEqual(['system', 'user', 'user']);
        expect(sent[1].content[0].text).toContain('[A summary of our conversation so far]');
        expect(sent[2].content).toEqual([{ type: 'text', text: 'go' }]);
        expect(costUsd).toBeCloseTo(0.003);
    });

    test('a request whose summary fails stays in the log, for asking again', async () => {
        const model = new MockLanguageModelV4({ doStream: async () => { throw Object.assign(new Error('Summary refused.'), { statusCode: 400 }); } });
        const log = [{ role: 'user', content: 'x'.repeat(SUMMARISE_AT_TOKENS * 4 + 100) }, { role: 'assistant', content: 'ok' }];

        await expect(turn(model, { log })).rejects.toThrow('Summary refused.');

        expect(log.at(-1)).toEqual(go()[0]);
    });

    test('a summary carries the files the conversation changed, as they are now, and again at the next summary', async () => {
        const model = scripted(
            [...say('s', 'Line 98 still reads bottom_position.'), finish('stop')],
            [...say('1', 'Carrying on.'), finish('stop')],
            [...say('s2', 'Still on the sawhorse.'), finish('stop')],
            [...say('2', 'Carrying on.'), finish('stop')],
        );
        const disk = { 'frame.py': 'x_pos = x\n', 'gone.py': null };
        const files = { read: async (file) => disk[file] ?? null };
        const edit = (id, file) => [
            { role: 'assistant', content: [{ type: 'tool-call', toolCallId: id, toolName: 'edit_file', input: { file_path: file } }] },
            { role: 'tool', content: [{ type: 'tool-result', toolCallId: id, toolName: 'edit_file', output: { type: 'text', value: 'Edited.' } }] },
        ];
        const big = [{ role: 'user', content: 'x'.repeat(SUMMARISE_AT_TOKENS * 4 + 100) }, ...edit('e1', 'frame.py'), ...edit('e2', 'gone.py'),
            { role: 'assistant', content: 'ok' }];
        const log = [...big];
        const run = () => runTurn({ model, images: true, tools: [], files, system: 's', log, prompt: go(),
            askPermission: async () => true, onEvent: () => {} });
        const summaries = () => log.filter((entry) => entry.summary !== undefined).map((entry) => entry.summary);

        await run();
        expect(summaries()[0]).toContain('Line 98 still reads bottom_position.');
        expect(summaries()[0]).toContain('Where the summary disagrees with them, they are right.');
        expect(summaries()[0]).toContain('[The file frame.py as it is now]\n```\nx_pos = x\n');
        expect(summaries()[0]).not.toContain('gone.py');

        // Large again: the next summary carries the file as it is then, from the edit before the first summary.
        disk['frame.py'] = 'x_pos = x  # newer\n';
        log.push({ role: 'user', content: 'y'.repeat(SUMMARISE_AT_TOKENS * 4) });
        await run();
        expect(summaries()).toHaveLength(2);
        expect(summaries()[1]).toContain('x_pos = x  # newer');
    });

    test('each step reports how full the conversation is', async () => {
        const events = [];
        await runTurn({ model: scripted([...say('1', 'Hi.'), finish('stop')]), images: true, contextWindow: 200000, tools: [],
            system: 's', log: [], prompt: go(), askPermission: async () => true, onEvent: (event) => events.push(event) });
        expect(events).toContainEqual({ type: 'agent:context', tokens: 10, window: 200000, cached: 0 });
    });

        test('an image the user attached is dropped like a screenshot once a later one comes', () => {
        const { onlyLatestImage } = require('../agent/request');
        const user = { role: 'user', content: [{ type: 'text', text: 'this' }, { type: 'image', image: 'AAAA', mediaType: 'image/png' }] };
        const shot = { role: 'tool', content: [{ type: 'tool-result', toolCallId: 'c', toolName: 'screenshot',
            output: { type: 'content', value: [{ type: 'file', data: { type: 'data', data: 'BBBB' }, mediaType: 'image/png' }] } }] };
        const [kept, latest] = onlyLatestImage([user, shot]);
        expect(kept.content[1]).toEqual({ type: 'text', text: expect.stringContaining('earlier image') });
        expect(latest.content[0].output.value[0].type).toBe('file');
    });

        test('an image counts for its tokens, not its encoded size, in the size that decides summarising', () => {
        const image = { role: 'user', content: [{ type: 'image', image: 'A'.repeat(800000), mediaType: 'image/png' }] };
        expect(estimateTokens([image])).toBeLessThan(5000);
        expect(estimateTokens([{ role: 'user', content: 'x'.repeat(400000) }])).toBeGreaterThan(SUMMARISE_AT_TOKENS - 1);
    });

        test('a model that cannot see gets a note instead of an image', () => {
        const content = [{ type: 'image', data: 'AAAA', mimeType: 'image/png' }];
        expect(toModelContent(content, false).value[0]).toMatchObject({ type: 'text' });
        expect(toModelContent(content, true).value[0]).toMatchObject({ type: 'file' });
    });
});

describe('the file tools', () => {
    let root;
    let tools;
    const named = (name) => tools.find((tool) => tool.name === name);

    beforeEach(() => {
        root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-files-'));
        fs.writeFileSync(path.join(root, 'frame.py'), 'a = 1\nb = 2\nb = 2\n');
        fs.mkdirSync(path.join(root, 'node_modules'));
        fs.writeFileSync(path.join(root, 'node_modules', 'x.js'), '');
        tools = createFileTools({ files: createProjectFiles({ root: () => root }) });
    });

    afterEach(() => fs.rmSync(root, { recursive: true, force: true }));

    test('read and list only read; write and edit edit', () => {
        expect(tools.map((tool) => [tool.name, tool.effect])).toEqual([
            ['list_files', 'read'], ['search_files', 'read'], ['read_file', 'read'], ['write_file', 'edit'], ['edit_file', 'edit'],
        ]);
    });

    test('nothing outside the project folder', async () => {
        await expect(named('read_file').run({ file_path: '../elsewhere.txt' })).rejects.toThrow('outside the project');
        await expect(named('write_file').run({ file_path: '/etc/hosts', content: '' })).rejects.toThrow('outside the project');
    });

    test('edits asked for at once all land, one after another', async () => {
        fs.writeFileSync(path.join(root, 'frame.py'), `legs.append(leg)\n${'# padding\n'.repeat(2000)}x = leg.bottom\nexample = build_frame\n`);
        const edit = (before, after) => named('edit_file').run({ file_path: 'frame.py', old_string: before, new_string: after });
        await Promise.all([edit('legs.append(leg)', 'legs.append((leg, x))'), edit('x = leg.bottom', 'x = x_pos'),
            edit('example = build_frame', 'example = build_frame  # the frame')]);
        expect(fs.readFileSync(path.join(root, 'frame.py'), 'utf8'))
            .toBe(`legs.append((leg, x))\n${'# padding\n'.repeat(2000)}x = x_pos\nexample = build_frame  # the frame\n`);
    });

    test('a read-only folder outside the project can be read and searched, never written', async () => {
        const library = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-lib-'));
        fs.writeFileSync(path.join(library, 'timber.py'), 'def create_axis_aligned_timber(bottom_position, length):\n');
        tools = createFileTools({ files: createProjectFiles({ root: () => root, readOnly: () => [library] }) });
        const source = fs.realpathSync(path.join(library, 'timber.py'));

        const [found] = await named('search_files').run({ pattern: 'def create_axis', folder: library });
        expect(found.text).toBe(`${source}:1: def create_axis_aligned_timber(bottom_position, length):`);
        const [read] = await named('read_file').run({ file_path: source });
        expect(read.text).toContain('bottom_position');
        await expect(named('write_file').run({ file_path: source, content: '' })).rejects.toThrow('outside the project');
        await expect(named('edit_file').run({ file_path: source, old_string: 'def', new_string: 'x' })).rejects.toThrow('outside the project');
        fs.rmSync(library, { recursive: true, force: true });
    });

    test('lists the project, leaving out dependency folders', async () => {
        const [listed] = await named('list_files').run({});
        expect(listed.text).toBe('frame.py');
    });

    test('an edit must be unambiguous, unless it is meant for every match', async () => {
        await expect(named('edit_file').run({ file_path: 'frame.py', old_string: 'b = 2', new_string: 'b = 3' }))
            .rejects.toThrow('appears 2 times');
        await named('edit_file').run({ file_path: 'frame.py', old_string: 'a = 1', new_string: 'a = 5' });
        await named('edit_file').run({ file_path: 'frame.py', old_string: 'b = 2', new_string: 'b = 3', replace_all: true });
        expect(fs.readFileSync(path.join(root, 'frame.py'), 'utf8')).toBe('a = 5\nb = 3\nb = 3\n');
    });

    test('searches the project for a pattern, by file name too, leaving out dependency folders', async () => {
        fs.writeFileSync(path.join(root, 'notes.md'), 'b = 2 in notes\n');
        fs.writeFileSync(path.join(root, 'node_modules', 'x.js'), 'b = 2\n');
        const [all] = await named('search_files').run({ pattern: 'b = \\d' });
        expect(all.text.split('\n').sort()).toEqual(['frame.py:2: b = 2', 'frame.py:3: b = 2', 'notes.md:1: b = 2 in notes']);
        const [python] = await named('search_files').run({ pattern: 'B = 2', ignore_case: true, file_glob: '*.py' });
        expect(python.text).toBe('frame.py:2: b = 2\nframe.py:3: b = 2');
        const [none] = await named('search_files').run({ pattern: 'nothing like this' });
        expect(none.text).toBe('No matches.');
    });

        test('never writes in .git, .venv, node_modules or .kigumi', async () => {
        fs.mkdirSync(path.join(root, '.git'));
        await expect(named('write_file').run({ file_path: '.git/hooks/pre-commit', content: 'rm -rf ~' }))
            .rejects.toThrow("which the agent doesn't change");
        await expect(named('write_file').run({ file_path: 'pkg/.venv/lib/x.py', content: '' })).rejects.toThrow('.venv/');
        expect(fs.existsSync(path.join(root, '.git', 'hooks'))).toBe(false);
    });

    test('a link out of the project is outside it', async () => {
        const outside = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-outside-'));
        fs.writeFileSync(path.join(outside, 'secret.txt'), 'secret');
        fs.symlinkSync(outside, path.join(root, 'linked'));
        await expect(named('read_file').run({ file_path: 'linked/secret.txt' })).rejects.toThrow('outside the project');
        await expect(named('write_file').run({ file_path: 'linked/new.txt', content: '' })).rejects.toThrow('outside the project');
        fs.rmSync(outside, { recursive: true, force: true });
    });

    test('a pathological search pattern is stopped rather than hanging the app', async () => {
        fs.writeFileSync(path.join(root, 'long.txt'), `${'a'.repeat(1900)}!\n`);
        const started = Date.now();
        let ticks = 0;
        const timer = setInterval(() => { ticks += 1; }, 50);
        const search = named('search_files').run({ pattern: '^(a+)+$' }).catch((error) => error);
        await new Promise((resolve) => setTimeout(resolve, 300));
        clearInterval(timer);
        // The main thread kept running while it searched.
        expect(ticks).toBeGreaterThan(2);
        const result = await search;
        expect(result.message || result[0].text).toMatch(/stopped|No matches/);
        expect(Date.now() - started).toBeLessThan(20000);
    }, 25000);

        test('reads with line numbers', async () => {
        const [read] = await named('read_file').run({ file_path: 'frame.py', offset: 2, limit: 1 });
        expect(read.text).toBe('2\tb = 2\n(4 lines in all; read on from line 3)');
    });

    test('a long file is read a part at a time, saying where to go on', async () => {
        fs.writeFileSync(path.join(root, 'big.py'), Array.from({ length: 1500 }, () => 'x'.repeat(60)).join('\n'));
        const [read] = await named('read_file').run({ file_path: 'big.py' });
        expect(read.text.length).toBeLessThan(45000);
        expect(read.text).toMatch(/1500 lines in all; read on from line \d+\)$/);
    });
});

/** Project files that only resolve paths (for sessions whose tools are fakes). */
function fakeFiles(root) {
    return { root: () => root, resolve: (file) => path.resolve(root, file), relative: (file) => path.relative(root, file),
        read: async () => null, list: async () => [] };
}

describe('the agent session', () => {
    const panels = { list: () => [], active: () => null, describe: async () => null, viewSession: () => null };
    const hostOf = ({ panels: shown = panels, run = async () => ({}), files = { root: () => null } } = {}) =>
        viewHost({ panels: shown, run, files });

    /** An account that is signed in, as far as the session can tell. */
    const signedIn = () => ({
        state: () => ({ configured: true, signedIn: true, email: 'maple@example.com', balanceUsd: 1 }),
        backend: () => ({ url: 'https://api.example' }),
        fetchWithToken: async () => new Response(),
        refreshBalance: jest.fn(async () => {}),
    });

    function session({ settings = {}, account = null, model } = {}) {
        const posted = [];
        const values = { ...settings };
        const created = [];
        const agent = new AgentSession({
            host: hostOf(), post: (message) => posted.push(message),
            setting: (key, fallback) => (key in values ? values[key] : fallback),
            setSetting: (key, value) => { values[key] = value; },
            account, createModel: async (route, options) => { created.push([route, options]); return model; },
        });
        return { agent, posted, values, created };
    }

    test('says what to do when nothing can carry a request, and keeps none of it in the conversation', async () => {
        const { agent, posted } = session();
        await agent.prompt('hi');
        expect(posted).toEqual([{ type: 'agent:error', key: 'agent.route.setKey', message: expect.stringContaining('Sign in') }]);
        expect(agent.conversation.log).toEqual([]);
    });

    test('tells the panel the models, the one chosen, and where its requests go', () => {
        const { agent, posted, values } = session({ settings: { 'agent.openrouterApiKey': 'sk-or' } });

        agent.handle({ type: 'agent:setModel', id: 'claude-sonnet-5' });

        expect(values['agent.model']).toBe('claude-sonnet-5');
        expect(posted.pop()).toEqual({
            type: 'agent:state', models: MODELS.map(({ id, label }) => ({ id, label })), model: 'claude-sonnet-5', via: 'openrouter',
            account: { configured: false },
            settings: { 'agent.permissionMode': 'ask', 'agent.alwaysAllow': [], 'agent.showOnStartup': true, 'agent.planMode': false,
                'agent.maxOutputTokens': 8000 },
            strings: {},
        });
    });

    test('signed in, requests carry the account\'s token; a turn ends with its cost and the balance is fetched again', async () => {
        const account = signedIn();
        const { agent, posted, created } = session({ account, model: scripted([...say('1', 'Hi.'), finish('stop', 0.0005)]) });

        await agent.prompt('hi');

        expect(created[0][0].via).toBe('backend');
        expect(created[0][1].fetch).toBe(account.fetchWithToken);
        expect(posted).toContainEqual({ type: 'agent:done', isError: false, costUsd: 0.0005 });
        expect(account.refreshBalance).toHaveBeenCalled();
    });

    test('a request goes with a note of what the user is looking at', async () => {
        expect(contextNote({ kind: 'viewer', fileName: 'a.py' }))
            .toEqual({ note: 'context', text: 'What the user is looking at in Kigumi: {"kind":"viewer","fileName":"a.py"}' });
        expect(contextNote(null)).toBeNull();
        expect(contextNote({ text: 'x'.repeat(5000) }).text.length).toBeLessThan(2100);
        const entries = await promptEntries({ text: 'fix this', files: { root: () => null }, describe: async () => ({ kind: 'viewer' }) });
        expect(entries).toEqual([{ note: 'context', text: expect.stringContaining('viewer') },
            { role: 'user', content: 'fix this', shown: { text: 'fix this', images: 0 } }]);
    });

    test('editing a file a view shows rebuilds it, and the edit says whether it built', async () => {
        const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-rebuild-')));
        fs.writeFileSync(path.join(root, 'a.py'), 'x = 1\n');
        fs.writeFileSync(path.join(root, 'b.py'), 'x = 1\n');
        const reports = [];
        const agent = new AgentSession({
            host: hostOf({
                panels: { ...panels, list: () => [{ kind: 'viewer', filePath: path.join(root, 'a.py') }] },
                run: async (id, args) => {
                    if (id === 'kigumi.captureScreenshot') throw new Error('no view to picture here');
                    reports.push([id, args.filePath]);
                    return { ok: false, entries: [{ level: 'error', message: 'NameError: brace' }] };
                },
                files: createProjectFiles({ root: () => root }),
            }),
            post: () => {}, setting: (key, fallback) => fallback,
        });
        const edit = agent.tools.find((tool) => tool.name === 'edit_file');

        expect(await edit.run({ file_path: 'a.py', old_string: 'x = 1', new_string: 'x = 2' })).toEqual([
            { type: 'text', text: 'Edited a.py (1 replacement).' },
            { type: 'text', text: 'The view of this file rebuilt with errors:\nerror: NameError: brace' },
        ]);
        expect(reports).toEqual([['kigumi.automationBuildReport', path.join(root, 'a.py')]]);
        // A file no view shows is just edited.
        reports.length = 0;
        await edit.run({ file_path: 'b.py', old_string: 'x = 1', new_string: 'x = 2' });
        expect(reports).toEqual([]);
        expect(describeBuild({ ok: true, entries: [] })).toBe('The view of this file rebuilt without errors.');
        fs.rmSync(root, { recursive: true, force: true });
    });

        test('a conversation is saved after each turn, and comes back when the panel opens again', async () => {
        const saved = new Map();
        const conversations = {
            list: () => [...saved.values()].map(({ id, title, updatedAt }) => ({ id, title, updatedAt })),
            load: (_project, id) => JSON.parse(JSON.stringify(saved.get(id) || null)),
            save: (_project, conversation) => saved.set(conversation.id, JSON.parse(JSON.stringify(conversation))),
            remove: (_project, id) => saved.delete(id),
        };
        const posted = [];
        const make = (model) => new AgentSession({
            host: hostOf({ files: fakeFiles('/project') }), post: (message) => posted.push(message),
            setting: (key, fallback) => (key === 'agent.openrouterApiKey' ? 'sk-or' : fallback), conversations,
            createModel: async () => model,
        });

        await make(scripted([...say('1', 'A sawhorse, then.'), finish('stop')])).prompt('make me a sawhorse');

        const [only] = saved.values();
        expect(only.title).toBe('make me a sawhorse');
        expect(only.version).toBe(2);
        expect(only.log.filter((entry) => entry.role).map((entry) => entry.role)).toEqual(['user', 'assistant']);

        // A new session, as after a restart: the panel gets the conversation drawn again.
        posted.length = 0;
        const again = make(scripted([...say('2', 'Longer legs.'), finish('stop')]));
        again.handle({ type: 'agent:ready' });
        const replay = posted.find((message) => message.type === 'agent:replay');
        expect(replay.events[0]).toEqual({ type: 'agent:userMessage', text: 'make me a sawhorse', images: 0 });
        expect(replay.events).toContainEqual({ type: 'agent:text', text: 'A sawhorse, then.' });

        // It carries on the same conversation; a new one starts empty.
        await again.prompt('longer legs');
        expect(saved.size).toBe(1);
        expect(saved.get(only.id).log.filter((entry) => entry.role)).toHaveLength(4);
        again.handle({ type: 'agent:clear' });
        expect(again.conversation.log).toEqual([]);
        await again.prompt('something else').catch(() => {});
        expect(saved.size).toBe(2);
    });

        test('a request made while the agent works waits, then runs; one can be taken back', async () => {
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        const prompts = [];
        let calls = 0;
        const model = new MockLanguageModelV4({ doStream: async ({ prompt }) => {
            calls += 1;
            prompts.push(prompt.filter((message) => message.role === 'user').at(-1).content[0].text);
            if (calls === 1) await gate;
            return { stream: convertArrayToReadableStream([...say(String(calls), 'ok'), finish('stop')]) };
        } });
        const { agent, posted } = session({ settings: { 'agent.openrouterApiKey': 'sk-or' }, model });

        const first = agent.prompt('first');
        await new Promise((resolve) => setTimeout(resolve, 10));
        agent.handle({ type: 'agent:prompt', text: 'second' });
        agent.handle({ type: 'agent:prompt', text: 'third' });
        const third = posted.filter((message) => message.type === 'agent:queued')[1];
        agent.handle({ type: 'agent:unqueue', id: third.id });
        release();
        await first;
        await new Promise((resolve) => setTimeout(resolve, 50));

        expect(prompts).toEqual(['first', 'second']);
        expect(posted).toContainEqual({ type: 'agent:userMessage', text: 'second', images: 0 });
        expect(posted).toContainEqual({ type: 'agent:dequeued', id: third.id });
    });

    test('a turn that changed files can be undone, putting them back as they were', async () => {
        const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-undo-'));
        fs.writeFileSync(path.join(root, 'frame.py'), 'legs = 4\n');
        const projectFiles = createProjectFiles({ root: () => root });
        const model = scripted(
            [call('c1', 'edit_file', { file_path: 'frame.py', old_string: 'legs = 4', new_string: 'legs = 3' }),
                call('c2', 'write_file', { file_path: 'brace.py', content: 'brace = 1\n' }), finish('tool-calls')],
            [...say('1', 'Done.'), finish('stop')],
        );
        const posted = [];
        const agent = new AgentSession({
            host: hostOf({ files: projectFiles }), post: (message) => posted.push(message),
            setting: (key, fallback) => ({ 'agent.openrouterApiKey': 'sk-or', 'agent.permissionMode': 'auto' }[key] ?? fallback),
            createModel: async () => model,
        });

        await agent.prompt('three legs and a brace');

        expect(fs.readFileSync(path.join(root, 'frame.py'), 'utf8')).toBe('legs = 3\n');
        const checkpoint = posted.find((message) => message.type === 'agent:checkpoint');
        expect({ ...checkpoint, files: checkpoint.files.sort() }).toEqual({ type: 'agent:checkpoint', turn: 1, files: ['brace.py', 'frame.py'] });

        // Changed since the agent left it: held back, and listed, until asked again.
        fs.writeFileSync(path.join(root, 'frame.py'), 'legs = 3\n# mine\n');
        await agent.restore(1);
        expect(posted).toContainEqual({ type: 'agent:restoreConflict', turn: 1, files: ['frame.py'] });
        expect(fs.readFileSync(path.join(root, 'frame.py'), 'utf8')).toBe('legs = 3\n# mine\n');

        await agent.restore(1, { force: true });

        expect(fs.readFileSync(path.join(root, 'frame.py'), 'utf8')).toBe('legs = 4\n');
        expect(fs.existsSync(path.join(root, 'brace.py'))).toBe(false);
        expect(posted).toContainEqual({ type: 'agent:restored', turn: 1 });
        expect(agent.conversation.log.at(-1)).toEqual({ note: 'undo',
            text: expect.stringMatching(/undid your changes to (frame\.py, brace\.py|brace\.py, frame\.py)/) });
        fs.rmSync(root, { recursive: true, force: true });
    });

    test('after a failed turn, trying again carries on', async () => {
        const { agent } = session({ settings: { 'agent.openrouterApiKey': 'sk-or' } });
        const asked = [];
        agent.prompt = async (text) => { asked.push(text); };
        agent.handle({ type: 'agent:retry' });
        expect(asked).toEqual([RETRY_PROMPT]);
    });

        test('the agent keeps a to-do list, shown in the panel and kept with the conversation', async () => {
        const { agent, posted } = session();
        const todos = agent.tools.find((tool) => tool.name === 'update_todos');
        expect(todos.effect).toBe('read');
        const [result] = await todos.run({ items: [{ text: 'legs', done: true }, { text: 'beam' }] });
        expect(result.text).toBe('To-do list updated: 1 of 2 left.');
        expect(posted).toContainEqual({ type: 'agent:todos', items: [{ text: 'legs', done: true }, { text: 'beam', done: false }] });
        expect(agent.conversation.log.at(-1).event.type).toBe('agent:todos');
    });

    test('the longest step is the setting, if it is one offered; else 8k', async () => {
        for (const [setting, sent] of [[32000, 32000], [999999, 8000]]) {
            const model = scripted([...say('1', 'ok'), finish('stop')]);
            const { agent } = session({ settings: { 'agent.openrouterApiKey': 'sk-or', 'agent.maxOutputTokens': setting }, model });
            await agent.prompt('hi');
            expect(model.doStreamCalls[0].maxOutputTokens).toBe(sent);
        }
    });

    test('in plan mode, no file is edited, and the model is told why; the camera still moves', async () => {
        const { agent, posted } = session({ settings: { 'agent.planMode': true, 'agent.permissionMode': 'auto' } });
        await expect(agent.permissions.ask('edit_file', {})).rejects.toThrow('Plan mode is on');
        await expect(agent.permissions.ask('set_camera', {})).resolves.toBe(true);
        expect(posted.some((message) => message.type === 'agent:permission')).toBe(false);
    });

    test('an @-mentioned file goes with the request; anything outside the project does not', async () => {
        const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-mention-'));
        fs.writeFileSync(path.join(root, 'frame.py'), 'legs = 4\n');
        const sent = await withMentions('fix @frame.py. and @../secret.txt and @missing.py',
            { files: createProjectFiles({ root: () => root }), describe: async () => null });

        expect(sent).toContain('[The file frame.py]\n```\nlegs = 4\n');
        expect(sent).not.toContain('[The file ../secret.txt]');
        expect(sent).not.toContain('[The file missing.py]');
        fs.rmSync(root, { recursive: true, force: true });
    });

    test('images go with a request to a model that can see; one that can\'t is told they were there', async () => {
        const common = { text: 'this joint', files: { root: () => null }, describe: async () => null };
        const [seen] = await promptEntries({ ...common, images: [{ mediaType: 'image/jpeg', data: 'AAAA' }], modelSeesImages: true });
        expect(seen.content[1]).toEqual({ type: 'image', image: 'AAAA', mediaType: 'image/jpeg' });
        expect(seen.shown).toEqual({ text: 'this joint', images: 1 });

        const [unseen] = await promptEntries({ ...common, images: [{ mediaType: 'image/png', data: 'AAAA' }], modelSeesImages: false });
        expect(unseen.content).toContain("1 image attached, which this model can't see");
    });

    test('an edit to a file a view shows puts the view before and after on its chip', async () => {
        const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-shots-'));
        const shot = path.join(root, 'shot.png');
        fs.writeFileSync(shot, 'png');
        fs.writeFileSync(path.join(root, 'a.py'), 'x = 1\n');
        const posted = [];
        const agent = new AgentSession({
            host: hostOf({
                panels: { ...panels, list: () => [{ kind: 'viewer', filePath: path.join(root, 'a.py') }] },
                run: async (id) => (id === 'kigumi.captureScreenshot' ? { data: Buffer.from('png').toString('base64') } : { ok: true, entries: [] }),
                files: createProjectFiles({ root: () => root }),
            }),
            post: (message) => posted.push(message), setting: (key, fallback) => fallback,
        });

        await agent.tools.find((tool) => tool.name === 'edit_file').run({ file_path: 'a.py', old_string: 'x = 1', new_string: 'x = 2' },
            { toolCallId: 'c9' });

        const pictures = posted.find((message) => message.type === 'agent:toolImages');
        expect(pictures).toEqual({ type: 'agent:toolImages', id: 'c9',
            before: `data:image/png;base64,${Buffer.from('png').toString('base64')}`, after: expect.stringMatching(/^data:image\/png/) });
        // For the panel only: not kept in the conversation.
        expect(agent.conversation.log.some((entry) => entry.event && entry.event.type === 'agent:toolImages')).toBe(false);
        fs.rmSync(root, { recursive: true, force: true });
    });

        test('a new conversation started while a turn runs stays new', async () => {
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        const model = new MockLanguageModelV4({ doStream: async ({ abortSignal }) => {
            await Promise.race([gate, new Promise((resolve) => abortSignal && abortSignal.addEventListener('abort', resolve))]);
            if (abortSignal && abortSignal.aborted) throw Object.assign(new Error('aborted'), { name: 'AbortError' });
            return { stream: convertArrayToReadableStream([...say('1', 'old answer'), finish('stop')]) };
        } });
        const saved = [];
        const { agent } = session({ settings: { 'agent.openrouterApiKey': 'sk-or' }, model });
        agent.conversations = { list: () => [], save: (_project, conversation) => saved.push(JSON.parse(JSON.stringify(conversation))) };
        agent.files = fakeFiles('/project');

        const turn = agent.prompt('the old request');
        await new Promise((resolve) => setTimeout(resolve, 10));
        agent.handle({ type: 'agent:clear' });
        release();
        await turn;

        expect(agent.conversation.log).toEqual([]);
        expect(saved).toEqual([]);
    });

    test('through the account, a turn shows what it was charged: the cost times the markup', async () => {
        const account = { ...signedIn(), state: () => ({ configured: true, signedIn: true, markup: 1.5 }) };
        const { agent, posted } = session({ account, model: scripted([...say('1', 'Hi.'), finish('stop', 0.002)]) });
        await agent.prompt('hi');
        expect(posted.find((message) => message.type === 'agent:done').costUsd).toBeCloseTo(0.003);
    });

        test('out of credit says so', () => {
        expect(describeFailure({ statusCode: 402, message: 'Payment Required' })).toEqual({ key: 'agent.error.noCredit', text: 'Out of credit.' });
    });

    test('permission modes: ask before edits, or never ask', async () => {
        const { agent, posted, values } = session();
        const asked = () => posted.filter((message) => message.type === 'agent:permission').length;

        void agent.permissions.ask('edit_file', {});
        expect(asked()).toBe(1);
        // Moving the camera only changes what the user sees.
        await expect(agent.permissions.ask('set_camera', {})).resolves.toBe(true);

        agent.handle({ type: 'agent:setSetting', key: 'agent.permissionMode', value: 'auto' });
        await expect(agent.permissions.ask('edit_file', {})).resolves.toBe(true);
        await expect(agent.permissions.ask('check_frame', { file_path: 'other.py' })).resolves.toBe(true);
        expect(asked()).toBe(1);

        // Only the panel's own settings, and only sensible values.
        agent.handle({ type: 'agent:setSetting', key: 'agent.permissionMode', value: 'whatever' });
        agent.handle({ type: 'agent:setSetting', key: 'agent.apiKey', value: 'not one the panel sets' });
        expect(values['agent.permissionMode']).toBe('auto');
        expect(values['agent.apiKey']).toBeUndefined();
    });

    test('the old modes and the old bypass switch read as auto', () => {
        for (const settings of [{ 'agent.bypassPermissions': true }, { 'agent.permissionMode': 'edits' }, { 'agent.permissionMode': 'all' }]) {
            expect(session({ settings }).agent.panelSetting('agent.permissionMode')).toBe('auto');
        }
    });

    test('asking, building a file runs freely when a view shows it or the agent wrote it, else asks', async () => {
        const viewed = { ...panels, list: () => [{ kind: 'viewer', filePath: '/project/shown.py' }] };
        const agent = new AgentSession({ host: hostOf({ panels: viewed, files: fakeFiles('/project') }), post: () => {},
            setting: (key, fallback) => fallback });
        agent.conversation.checkpoints.begin(1);
        await agent.conversation.checkpoints.beforeWrite('/project/written.py');

        await expect(agent.permissions.ask('check_frame', { file_path: 'shown.py' })).resolves.toBe(true);
        await expect(agent.permissions.ask('check_frame', { file_path: 'written.py' })).resolves.toBe(true);
        await expect(agent.permissions.ask('refresh_view', {})).resolves.toBe(true);
        void agent.permissions.ask('check_frame', { file_path: 'cleanup.py' });
        expect(agent.permissions.pending.size).toBe(1);
    });

    test('"always allow" from a permission card holds for that tool from then on', async () => {
        const { agent, posted, values } = session();
        const first = agent.permissions.ask('check_frame', { file_path: 'a.py' });
        const { requestId } = posted.find((message) => message.type === 'agent:permission');
        agent.handle({ type: 'agent:permissionAnswer', requestId, allow: true, always: true });

        await expect(first).resolves.toBe(true);
        expect(values['agent.alwaysAllow']).toEqual(['check_frame']);
        await expect(agent.permissions.ask('check_frame', { file_path: 'b.py' })).resolves.toBe(true);
        expect(posted.filter((message) => message.type === 'agent:permission')).toHaveLength(1);
    });

    test('a tool waiting for the user is answered from the panel, and stopping says no', async () => {
        const { agent, posted } = session();

        const first = agent.permissions.ask('edit_file', { file_path: 'a.py' });
        const { requestId } = posted.find((message) => message.type === 'agent:permission');
        agent.handle({ type: 'agent:permissionAnswer', requestId, allow: true });
        await expect(first).resolves.toBe(true);

        const second = agent.permissions.ask('write_file', {});
        agent.stop();
        await expect(second).resolves.toBe(false);
    });

    test('a panel reloaded while the agent works is told it is busy', async () => {
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        const model = new MockLanguageModelV4({ doStream: async () => {
            await gate;
            return { stream: convertArrayToReadableStream([...say('1', 'Done.'), finish('stop')]) };
        } });
        const { agent, posted } = session({ settings: { 'agent.openrouterApiKey': 'sk-or' }, model });
        const turn = agent.prompt('go');
        await new Promise((resolve) => setTimeout(resolve, 10));
        posted.length = 0;

        agent.handle({ type: 'agent:ready' });

        expect(posted.map((message) => message.type)).toEqual(['agent:state', 'agent:replay', 'agent:busy']);
        expect(posted.at(-1).busy).toBe(true);
        release();
        await turn;
    });

    test('a turn stopped after an edit leaves a note of the files it changed', async () => {
        const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-stopped-'));
        fs.writeFileSync(path.join(root, 'frame.py'), 'legs = 4\n');
        const abort = { agent: null };
        const model = new MockLanguageModelV4({ doStream: async ({ abortSignal }) => {
            if (model.doStreamCalls.length > 1) {
                abort.agent.stop();
                throw Object.assign(new Error('aborted'), { name: 'AbortError' });
            }
            return { stream: convertArrayToReadableStream([
                call('c1', 'edit_file', { file_path: 'frame.py', old_string: 'legs = 4', new_string: 'legs = 3' }), finish('tool-calls')]) };
        } });
        const agent = new AgentSession({ host: hostOf({ files: createProjectFiles({ root: () => root }) }), post: () => {},
            setting: (key, fallback) => ({ 'agent.openrouterApiKey': 'sk-or', 'agent.permissionMode': 'auto' }[key] ?? fallback),
            createModel: async () => model });
        abort.agent = agent;

        await agent.prompt('three legs');

        expect(agent.conversation.log.at(-1)).toEqual({ note: 'interrupted', text: expect.stringContaining('changed frame.py') });
        fs.rmSync(root, { recursive: true, force: true });
    });
});
