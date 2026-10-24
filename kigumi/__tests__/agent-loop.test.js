const fs = require('fs');
const os = require('os');
const path = require('path');

const { MockLanguageModelV4, convertArrayToReadableStream } = require('ai/test');
const { runTurn, toModelContent, cacheMarked, trimOldToolResults, estimateTokens, SUMMARISE_AT_TOKENS } = require('../agent/agent-loop');
const { MODELS, findModel, routeModel } = require('../agent/models');
const { createFileTools } = require('../agent/file-tools');
const { AgentSession, RETRY_PROMPT, describeFailure, withContext, describeBuild } = require('../agent/agent-session');
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
        const backend = { url: 'https://api.example/' };

        expect(routeModel(haiku, { anthropicKey: 'sk-ant', backend })).toEqual(
            { via: 'anthropic', modelId: 'claude-haiku-4-5', apiKey: 'sk-ant' });
        expect(routeModel(deepseek, { anthropicKey: 'sk-ant', backend })).toEqual(
            { via: 'backend', modelId: 'deepseek/deepseek-v4.1-flash', baseURL: 'https://api.example/v1' });
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

        expect(events.filter((event) => event.type !== 'agent:context')).toEqual([
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
        expect(events.at(-1)).toEqual({ type: 'agent:notice', text: expect.stringContaining('output limit') });
    });

    test('a failing step keeps the steps before it, for asking again', async () => {
        let calls = 0;
        const model = new MockLanguageModelV4({ doStream: async () => {
            calls += 1;
            if (calls > 1) throw Object.assign(new Error('One request at a time.'), { statusCode: 400 });
            return { stream: convertArrayToReadableStream([call('c1', 'look'), finish('tool-calls')]) };
        } });
        const failed = await turn(model).catch((error) => error);
        expect(failed.message).toContain('One request at a time');
        expect(failed.history.map((message) => message.role)).toEqual(['user', 'assistant', 'tool']);
    });

    test('only the latest screenshot is sent; earlier ones become a note', async () => {
        const model = scripted(
            [call('c1', 'look'), finish('tool-calls')],
            [call('c2', 'look'), finish('tool-calls')],
            [...say('1', 'Done.'), finish('stop')],
        );
        const { history } = await turn(model);

        const imagesIn = (messages) => messages.filter((message) => message.role === 'tool')
            .flatMap((message) => message.content).flatMap((part) => part.output.value)
            .filter((item) => item.type === 'file').length;
        expect(imagesIn(model.doStreamCalls[2].prompt)).toBe(1);
        expect(imagesIn(history)).toBe(1);
        expect(JSON.stringify(history)).toContain('earlier screenshot');
    });

        test('Claude models get a cache mark on the last two messages only, however many steps pass', () => {
        const marked = (messages) => messages.filter((message) => message.providerOptions
            && message.providerOptions.openrouter && message.providerOptions.openrouter.cacheControl).length;
        let messages = [1, 2, 3].map((n) => ({ role: 'user', content: `m${n}` }));
        for (let step = 0; step < 3; step++) {
            messages = cacheMarked([...messages, { role: 'assistant', content: `a${step}` }]);
        }
        expect(marked(messages)).toBe(2);
        expect(messages.at(-1).providerOptions.anthropic.cacheControl).toEqual({ type: 'ephemeral' });
        expect(messages[0].providerOptions).toBeUndefined();
    });

    test('Claude models are marked for caching; the others cache by themselves', async () => {
        const model = scripted([...say('1', 'Hi.'), finish('stop')]);
        const events = [];
        await runTurn({ model, images: true, cacheMarks: true, tools: [], system: 's', history: [], prompt: 'go',
            askPermission: async () => true, onEvent: (event) => events.push(event) });
        expect(model.doStreamCalls[0].prompt.at(-1).providerOptions.openrouter.cacheControl).toEqual({ type: 'ephemeral' });
    });

        test('older tool results are cut down; the last few stay whole', () => {
        const result = (id, text) => ({ role: 'tool', content: [{ type: 'tool-result', toolCallId: id, toolName: 'read_file',
            output: { type: 'content', value: [{ type: 'text', text }] } }] });
        const long = 'x'.repeat(5000);
        const messages = Array.from({ length: 10 }, (_, i) => result(`c${i}`, long));

        const trimmed = trimOldToolResults(messages);

        const lengths = trimmed.map((message) => message.content[0].output.value[0].text.length);
        expect(lengths.slice(2)).toEqual(Array(8).fill(5000));
        expect(lengths[0]).toBeLessThan(500);
        expect(trimmed[0].content[0].output.value[0].text).toContain('run the tool again');
        expect(estimateTokens(trimmed)).toBeLessThan(estimateTokens(messages));
    });

    test('a large conversation is summarised at the start of a turn; the new request is kept as it is', async () => {
        const model = scripted(
            [...say('s', 'They want a sawhorse; frame.py has legs.'), finish('stop', 0.001)],
            [...say('1', 'Carrying on.'), finish('stop', 0.002)],
        );
        const big = [{ role: 'user', content: 'x'.repeat(SUMMARISE_AT_TOKENS * 4 + 100) }, { role: 'assistant', content: 'ok' }];

        const { events, history, costUsd } = await turn(model, { history: big });

        expect(events).toContainEqual({ type: 'agent:notice', text: expect.stringContaining('summarised') });
        expect(history[0].content).toContain('They want a sawhorse');
        expect(history[2]).toEqual({ role: 'user', content: 'go' });
        expect(costUsd).toBeCloseTo(0.003);
    });

    test('each step reports how full the conversation is', async () => {
        const events = [];
        await runTurn({ model: scripted([...say('1', 'Hi.'), finish('stop')]), images: true, contextWindow: 200000, tools: [],
            system: 's', history: [], prompt: 'go', askPermission: async () => true, onEvent: (event) => events.push(event) });
        expect(events).toContainEqual({ type: 'agent:context', tokens: 10, window: 200000 });
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
            ['list_files', true], ['search_files', true], ['read_file', true], ['write_file', false], ['edit_file', false],
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

describe('the agent session', () => {
    const panels = { list: () => [], active: () => null, describe: async () => null, viewSession: () => null };

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
            panels, run: async () => ({}), post: (message) => posted.push(message), cwd: () => null,
            setting: (key, fallback) => (key in values ? values[key] : fallback),
            setSetting: (key, value) => { values[key] = value; },
            account, createModel: async (route, options) => { created.push([route, options]); return model; },
        });
        return { agent, posted, values, created };
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
            account: { configured: false },
            settings: { 'agent.permissionMode': 'ask', 'agent.alwaysAllow': [], 'agent.showOnStartup': true },
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

    test('a message goes with what the user is looking at', () => {
        expect(withContext('fix this', { kind: 'viewer', fileName: 'a.py' }))
            .toBe('[What I\'m looking at in Kigumi: {"kind":"viewer","fileName":"a.py"}]\n\nfix this');
        expect(withContext('hi', null)).toBe('hi');
        expect(withContext('hi', { text: 'x'.repeat(5000) }).length).toBeLessThan(2100);
    });

    test('editing a file a view shows rebuilds it, and the edit says whether it built', async () => {
        const reports = [];
        const editTool = { name: 'edit_file', shape: {}, readOnly: false, run: async () => [{ type: 'text', text: 'Edited a.py.' }] };
        const agent = new AgentSession({
            panels: { ...panels, list: () => [{ kind: 'viewer', filePath: '/project/a.py' }] },
            run: async (id, args) => {
                reports.push([id, args.filePath]);
                return { ok: false, entries: [{ level: 'error', message: 'NameError: brace' }] };
            },
            post: () => {}, cwd: () => '/project', setting: (key, fallback) => fallback, fileTools: [editTool],
        });
        const edit = agent.tools.find((tool) => tool.name === 'edit_file');

        expect(await edit.run({ file_path: 'a.py' })).toEqual([
            { type: 'text', text: 'Edited a.py.' },
            { type: 'text', text: 'The view of this file rebuilt with errors:\nerror: NameError: brace' },
        ]);
        expect(reports).toEqual([['kigumi.automationBuildReport', '/project/a.py']]);
        // A file no view shows is just edited.
        reports.length = 0;
        await edit.run({ file_path: 'b.py' });
        expect(reports).toEqual([]);
        expect(describeBuild({ ok: true, entries: [] })).toBe('The view of this file rebuilt without errors.');
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
            panels, run: async () => ({}), post: (message) => posted.push(message), cwd: () => '/project',
            setting: (key, fallback) => (key === 'agent.openrouterApiKey' ? 'sk-or' : fallback), conversations,
            createModel: async () => model,
        });

        await make(scripted([...say('1', 'A sawhorse, then.'), finish('stop')])).prompt('make me a sawhorse');

        const [only] = saved.values();
        expect(only.title).toBe('make me a sawhorse');
        expect(only.history.map((message) => message.role)).toEqual(['user', 'assistant']);

        // A new session, as after a restart: the panel gets the conversation drawn again.
        posted.length = 0;
        const again = make(scripted([...say('2', 'Longer legs.'), finish('stop')]));
        again.handle({ type: 'agent:ready' });
        const replay = posted.find((message) => message.type === 'agent:replay');
        expect(replay.events[0]).toEqual({ type: 'agent:userMessage', text: 'make me a sawhorse' });
        expect(replay.events).toContainEqual({ type: 'agent:text', text: 'A sawhorse, then.' });

        // It carries on the same conversation; a new one starts empty.
        await again.prompt('longer legs');
        expect(saved.size).toBe(1);
        expect(saved.get(only.id).history).toHaveLength(4);
        again.handle({ type: 'agent:clear' });
        expect(again.history).toEqual([]);
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
        expect(posted).toContainEqual({ type: 'agent:userMessage', text: 'second' });
        expect(posted).toContainEqual({ type: 'agent:dequeued', id: third.id });
    });

    test('a turn that changed files can be undone, putting them back as they were', async () => {
        const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-undo-'));
        fs.writeFileSync(path.join(root, 'frame.py'), 'legs = 4\n');
        const model = scripted(
            [call('c1', 'edit_file', { file_path: 'frame.py', old_string: 'legs = 4', new_string: 'legs = 3' }),
                call('c2', 'write_file', { file_path: 'brace.py', content: 'brace = 1\n' }), finish('tool-calls')],
            [...say('1', 'Done.'), finish('stop')],
        );
        const posted = [];
        const agent = new AgentSession({
            panels, run: async () => ({}), post: (message) => posted.push(message), cwd: () => root,
            setting: (key, fallback) => ({ 'agent.openrouterApiKey': 'sk-or', 'agent.permissionMode': 'all' }[key] ?? fallback),
            fileTools: createFileTools({ root: () => root }), createModel: async () => model,
        });

        await agent.prompt('three legs and a brace');

        expect(fs.readFileSync(path.join(root, 'frame.py'), 'utf8')).toBe('legs = 3\n');
        const checkpoint = posted.find((message) => message.type === 'agent:checkpoint');
        expect(checkpoint).toEqual({ type: 'agent:checkpoint', turn: 1, files: ['frame.py', 'brace.py'] });

        agent.handle({ type: 'agent:restore', turn: 1 });

        expect(fs.readFileSync(path.join(root, 'frame.py'), 'utf8')).toBe('legs = 4\n');
        expect(fs.existsSync(path.join(root, 'brace.py'))).toBe(false);
        expect(posted).toContainEqual({ type: 'agent:restored', turn: 1 });
        expect(agent.history.at(-2).content).toContain('I undid your changes to frame.py, brace.py');
        fs.rmSync(root, { recursive: true, force: true });
    });

    test('after a failed turn, trying again carries on', async () => {
        const { agent } = session({ settings: { 'agent.openrouterApiKey': 'sk-or' } });
        const asked = [];
        agent.prompt = async (text) => { asked.push(text); };
        agent.handle({ type: 'agent:retry' });
        expect(asked).toEqual([RETRY_PROMPT]);
    });

        test('out of credit says so', () => {
        expect(describeFailure({ statusCode: 402, message: 'Payment Required' })).toBe('Out of credit.');
    });

    test('permission modes: ask every time, edit files without asking, or do everything', async () => {
        const { agent, posted, values } = session();
        const asked = () => posted.filter((message) => message.type === 'agent:permission').length;

        void agent._askPermission('edit_file', {});
        expect(asked()).toBe(1);

        agent.handle({ type: 'agent:setSetting', key: 'agent.permissionMode', value: 'edits' });
        await expect(agent._askPermission('edit_file', {})).resolves.toBe(true);
        void agent._askPermission('set_camera', {});
        expect(asked()).toBe(2);

        agent.handle({ type: 'agent:setSetting', key: 'agent.permissionMode', value: 'all' });
        await expect(agent._askPermission('set_camera', {})).resolves.toBe(true);
        expect(asked()).toBe(2);

        // Only the panel's own settings, and only sensible values.
        agent.handle({ type: 'agent:setSetting', key: 'agent.permissionMode', value: 'whatever' });
        agent.handle({ type: 'agent:setSetting', key: 'agent.apiKey', value: 'not one the panel sets' });
        expect(values['agent.permissionMode']).toBe('all');
        expect(values['agent.apiKey']).toBeUndefined();
    });

    test('the old bypass switch reads as doing everything without asking', () => {
        const { agent } = session({ settings: { 'agent.bypassPermissions': true } });
        expect(agent.panelSetting('agent.permissionMode')).toBe('all');
    });

    test('"always allow" from a permission card holds for that tool from then on', async () => {
        const { agent, posted, values } = session();
        const first = agent._askPermission('set_camera', {});
        const { requestId } = posted.find((message) => message.type === 'agent:permission');
        agent.handle({ type: 'agent:permissionAnswer', requestId, allow: true, always: true });

        await expect(first).resolves.toBe(true);
        expect(values['agent.alwaysAllow']).toEqual(['set_camera']);
        await expect(agent._askPermission('set_camera', {})).resolves.toBe(true);
        expect(posted.filter((message) => message.type === 'agent:permission')).toHaveLength(1);
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
