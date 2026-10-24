const fs = require('fs');
const os = require('os');
const path = require('path');

const { MockLanguageModelV4, convertArrayToReadableStream } = require('ai/test');
const { runTurn, toModelContent } = require('../agent/agent-loop');
const { MODELS, findModel, routeModel } = require('../agent/models');
const { createFileTools } = require('../agent/file-tools');
const { AgentSession, describeFailure } = require('../agent/agent-session');
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
    name: 'look', description: 'Look.', shape: {}, readOnly: true,
    run: async () => [{ type: 'text', text: 'a frame' }, { type: 'image', data: 'AAAA', mimeType: 'image/png' }],
};
const changeTool = {
    name: 'change', description: 'Change.', shape: { what: z.string() }, readOnly: false,
    run: jest.fn(async ({ what }) => [{ type: 'text', text: `changed ${what}` }]),
};

async function turn(model, { askPermission = async () => true, history = [], images = true } = {}) {
    const events = [];
    const result = await runTurn({
        model, images, tools: [lookTool, changeTool], system: 'sys', history, prompt: 'go',
        askPermission, onEvent: (event) => events.push(event),
    });
    return { ...result, events };
}

describe('the model table', () => {
    test('every model has an OpenRouter id, and an unknown id finds the default', () => {
        expect(MODELS.every((model) => model.openrouter)).toBe(true);
        expect(findModel('nonsense')).toBe(MODELS[0]);
    });

    test('a key the user set wins over the account; an Anthropic key only for Anthropic models', () => {
        const haiku = findModel('claude-haiku-4.5');
        const deepseek = findModel('deepseek-v4.1-flash');
        const backend = { url: 'https://api.example/', token: 'jwt' };

        expect(routeModel(haiku, { anthropicKey: 'sk-ant', backend })).toEqual(
            { via: 'anthropic', modelId: 'claude-haiku-4-5', apiKey: 'sk-ant' });
        expect(routeModel(deepseek, { anthropicKey: 'sk-ant', backend })).toEqual(
            { via: 'backend', modelId: 'deepseek/deepseek-v4.1-flash', apiKey: 'jwt', baseURL: 'https://api.example/v1' });
        expect(routeModel(deepseek, { openrouterKey: 'sk-or', backend }).via).toBe('openrouter');
        expect(routeModel(deepseek, {})).toBeNull();
    });
});

describe('the agent loop', () => {
    test('streams text, runs the tools the model asks for, and keeps the whole conversation', async () => {
        const model = scripted(
            [...say('1', 'Looking. '), call('c1', 'look'), finish('tool-calls', 0.001)],
            [...say('2', 'A frame.'), finish('stop', 0.002)],
        );

        const { events, history, costUsd } = await turn(model);

        expect(events).toEqual([
            { type: 'agent:text', text: 'Looking. ' },
            { type: 'agent:tool', id: 'c1', name: 'look', input: {} },
            { type: 'agent:toolResult', id: 'c1', isError: false, text: 'a frame\n[image]' },
            { type: 'agent:text', text: 'A frame.' },
        ]);
        expect(history.map((message) => message.role)).toEqual(['user', 'assistant', 'tool', 'assistant']);
        expect(costUsd).toBeCloseTo(0.003);
        // The second step saw the screenshot as an image.
        const sent = model.doStreamCalls[1].prompt.find((message) => message.role === 'tool').content[0].output;
        expect(sent.value[1]).toMatchObject({ type: 'file', mediaType: 'image/png' });
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

    test('a later turn carries on from the history', async () => {
        const first = await turn(scripted([...say('1', 'Hello.'), finish('stop')]));
        const model = scripted([...say('2', 'Again.'), finish('stop')]);

        await turn(model, { history: first.history });

        expect(model.doStreamCalls[0].prompt.map((message) => message.role)).toEqual(['system', 'user', 'assistant', 'user']);
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
        tools = createFileTools({ root: () => root });
    });

    afterEach(() => fs.rmSync(root, { recursive: true, force: true }));

    test('read and list only look; write and edit ask', () => {
        expect(tools.map((tool) => [tool.name, tool.readOnly])).toEqual([
            ['list_files', true], ['read_file', true], ['write_file', false], ['edit_file', false],
        ]);
    });

    test('nothing outside the project folder', async () => {
        await expect(named('read_file').run({ file_path: '../elsewhere.txt' })).rejects.toThrow('outside the project');
        await expect(named('write_file').run({ file_path: '/etc/hosts', content: '' })).rejects.toThrow('outside the project');
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

    test('reads with line numbers', async () => {
        const [read] = await named('read_file').run({ file_path: 'frame.py', offset: 2, limit: 1 });
        expect(read.text).toBe('2\tb = 2\n(4 lines in all)');
    });
});

describe('the agent session', () => {
    const panels = { list: () => [], active: () => null, describe: async () => null, viewSession: () => null };

    function session({ settings = {}, backend = () => null, model } = {}) {
        const posted = [];
        const values = { ...settings };
        const agent = new AgentSession({
            panels, run: async () => ({}), post: (message) => posted.push(message), cwd: () => null,
            setting: (key, fallback) => (key in values ? values[key] : fallback),
            setSetting: (key, value) => { values[key] = value; },
            backend, createModel: async () => model,
        });
        return { agent, posted, values };
    }

    test('says what to do when nothing can carry a request', async () => {
        const { agent, posted } = session();
        await agent.prompt('hi');
        expect(posted).toEqual([{ type: 'agent:error', message: expect.stringContaining('Sign in') }]);
    });

    test('tells the panel the models, the one chosen, and where its requests go', () => {
        const { agent, posted, values } = session({ settings: { 'agent.openrouterApiKey': 'sk-or' } });

        agent.handle({ type: 'agent:setModel', id: 'claude-sonnet-5' });

        expect(values['agent.model']).toBe('claude-sonnet-5');
        expect(posted.pop()).toEqual({
            type: 'agent:state', models: MODELS.map(({ id, label }) => ({ id, label })), model: 'claude-sonnet-5', via: 'openrouter',
        });
    });

    test('a turn ends with its cost; out of credit says so', async () => {
        const { agent, posted } = session({
            backend: () => ({ url: 'https://api.example', token: 'jwt' }),
            model: scripted([...say('1', 'Hi.'), finish('stop', 0.0005)]),
        });
        await agent.prompt('hi');
        expect(posted).toContainEqual({ type: 'agent:done', isError: false, costUsd: 0.0005 });

        expect(describeFailure({ statusCode: 402, message: 'Payment Required' })).toBe('Out of credit.');
    });

    test('a tool waiting for the user is answered from the panel, and stopping says no', async () => {
        const { agent, posted } = session();

        const first = agent._askPermission('edit_file', { file_path: 'a.py' });
        const { requestId } = posted.find((message) => message.type === 'agent:permission');
        agent.handle({ type: 'agent:permissionAnswer', requestId, allow: true });
        await expect(first).resolves.toBe(true);

        const second = agent._askPermission('write_file', {});
        agent.stop();
        await expect(second).resolves.toBe(false);
    });
});
