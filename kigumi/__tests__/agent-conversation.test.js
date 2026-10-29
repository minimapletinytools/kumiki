const fs = require('fs');
const os = require('os');
const path = require('path');

const { Conversation } = require('../agent/conversation');
const { createConversationStore, BLOB_AT } = require('../agent/conversation-store');
const { buildRequest } = require('../agent/request');

const files = { root: () => '/project', read: async () => null };
const user = (text) => ({ role: 'user', content: text, shown: { text, images: 0 } });
const toolCall = (id, name) => ({ role: 'assistant', content: [{ type: 'tool-call', toolCallId: id, toolName: name, input: {} }] });
const toolResult = (id, name, output) => ({ role: 'tool', content: [{ type: 'tool-result', toolCallId: id, toolName: name, output }] });

describe('a request built from the log', () => {
    test('notes go as user messages, panel events not at all, and what the panel shows is left out', () => {
        const log = [
            { note: 'context', text: 'Looking at a.py' },
            user('fix it'),
            { event: { type: 'agent:done', costUsd: 0.01 } },
            { role: 'assistant', content: 'Done.' },
        ];
        expect(buildRequest(log)).toEqual([
            { role: 'user', content: '[Kigumi note: Looking at a.py]' },
            { role: 'user', content: 'fix it' },
            { role: 'assistant', content: 'Done.' },
        ]);
    });

    test('starts from the latest summary', () => {
        const log = [user('first'), { role: 'assistant', content: 'one' }, { summary: 'They asked first.' }, user('second')];
        expect(buildRequest(log)).toEqual([
            { role: 'user', content: '[A summary of our conversation so far]\nThey asked first.' },
            { role: 'user', content: 'second' },
        ]);
    });

    test('images stay in tool results only for a model whose harness says so', () => {
        const shot = toolResult('c1', 'screenshot', { type: 'content', value: [{ type: 'file', mediaType: 'image/png', data: { type: 'data', data: 'AAAA' } }] });
        const log = [user('look'), toolCall('c1', 'screenshot'), shot];
        expect(buildRequest(log).map((message) => message.role)).toEqual(['user', 'assistant', 'tool', 'user']);
        expect(buildRequest(log, { imagesInToolResults: true })).toEqual([{ role: 'user', content: 'look' }, toolCall('c1', 'screenshot'), shot]);
    });

    test('cache marks go on the last two messages, and a message\'s other options stay', () => {
        const reasoning = { openrouter: { reasoning_details: [{ type: 'reasoning.text', text: 'Hmm.' }] } };
        const sent = buildRequest([user('a'), { role: 'assistant', content: 'b', providerOptions: reasoning }, user('c'), { role: 'assistant', content: 'd' }],
            { cacheMarks: true });
        expect(sent[0]).toEqual({ role: 'user', content: 'a' });
        expect(sent[1].providerOptions).toEqual(reasoning);
        expect(sent[2].providerOptions).toEqual({ openrouter: { cacheControl: { type: 'ephemeral' } } });
        expect(sent[3].providerOptions).toEqual({ openrouter: { cacheControl: { type: 'ephemeral' } } });
    });
});

describe('a conversation', () => {
    test('the panel draws it again from the log', () => {
        const conversation = new Conversation(files, { log: [
            { note: 'context', text: 'Looking at a.py' },
            user('look'),
            { role: 'assistant', content: [{ type: 'reasoning', text: 'Hmm.' }, { type: 'text', text: 'Looking.' }, ...toolCall('c1', 'screenshot').content] },
            toolResult('c1', 'screenshot', { type: 'content', value: [{ type: 'text', text: 'a view' }, { type: 'file', mediaType: 'image/png', data: {} }] }),
            toolResult('c2', 'edit_file', { type: 'error-text', value: 'The user did not allow this.' }),
            { event: { type: 'agent:done', isError: false, costUsd: 0.01 } },
        ] });
        expect(conversation.render()).toEqual([
            { type: 'agent:userMessage', text: 'look', images: 0 },
            { type: 'agent:reasoning', text: 'Hmm.' },
            { type: 'agent:text', text: 'Looking.' },
            { type: 'agent:tool', id: 'c1', name: 'screenshot', input: {} },
            { type: 'agent:toolResult', id: 'c1', isError: false, text: 'a view\n[image]' },
            { type: 'agent:toolResult', id: 'c2', isError: true, text: 'The user did not allow this.' },
            { type: 'agent:done', isError: false, costUsd: 0.01 },
        ]);
    });

    test('keeps the panel events the messages do not hold', () => {
        const conversation = new Conversation(files);
        conversation.keep({ type: 'agent:text', text: 'streamed' });
        conversation.keep({ type: 'agent:notice', text: 'Summarised.' });
        expect(conversation.log).toEqual([{ event: { type: 'agent:notice', text: 'Summarised.' } }]);
    });

    test('one saved in the first format opens: its summary and undo pairs become entries, and the panel shows its transcript', () => {
        const transcript = [{ type: 'agent:userMessage', text: 'go', images: 0 }, { type: 'agent:text', text: 'Hi.' }];
        const conversation = Conversation.load(files, {
            id: 'old', title: 'go', turn: 2, checkpoints: [], transcript,
            history: [
                { role: 'user', content: '[A summary of our conversation so far]\nThey want a sawhorse.' },
                { role: 'assistant', content: 'Understood; I will carry on from there.' },
                { role: 'user', content: '[I undid your changes to a.py: those files are back as they were before.]' },
                { role: 'assistant', content: 'Understood.' },
                { role: 'user', content: 'go' },
                { role: 'assistant', content: 'Hi.' },
            ],
        });

        expect(conversation.log).toEqual([
            { summary: 'They want a sawhorse.' },
            { note: 'undo', text: 'I undid your changes to a.py: those files are back as they were before.' },
            { role: 'user', content: 'go' },
            { role: 'assistant', content: 'Hi.' },
        ]);
        expect(conversation.turn).toBe(2);
        conversation.log.push(user('more'));
        expect(conversation.render()).toEqual([...transcript, { type: 'agent:userMessage', text: 'more', images: 0 }]);
        // Saved again, it is in this format and opens the same.
        const reopened = Conversation.load(files, JSON.parse(JSON.stringify(conversation)));
        expect(reopened.render()).toEqual(conversation.render());
    });
});

describe('the conversation store', () => {
    let base;
    beforeEach(() => { base = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-store-')); });
    afterEach(() => fs.rmSync(base, { recursive: true, force: true }));

    test('long strings go in blobs, shared between conversations, and those no conversation uses are deleted', () => {
        const store = createConversationStore(base);
        const shot = 'A'.repeat(BLOB_AT);
        const conversation = (id, log) => ({ version: 2, id, title: id, updatedAt: new Date().toISOString(), log });
        store.save('/project', conversation('a', [{ role: 'user', content: shot }]));
        store.save('/project', conversation('b', [{ role: 'user', content: shot }, { role: 'user', content: 'B'.repeat(BLOB_AT) }]));

        const [folder] = fs.readdirSync(base);
        const blobs = () => fs.readdirSync(path.join(base, folder, 'blobs')).length;
        expect(blobs()).toBe(2);
        expect(fs.statSync(path.join(base, folder, 'a.json')).size).toBeLessThan(500);
        expect(store.load('/project', 'a').log[0].content).toBe(shot);

        store.remove('/project', 'b');
        expect(blobs()).toBe(1);
        expect(store.load('/project', 'a').log[0].content).toBe(shot);
    });
});
