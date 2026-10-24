const fs = require('fs');
const os = require('os');
const path = require('path');

const { createConversationStore, MAX_CONVERSATIONS } = require('../agent/conversation-store');

describe('the conversation store', () => {
    let base;
    let store;
    beforeEach(() => {
        base = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-conversations-'));
        store = createConversationStore(base);
    });
    afterEach(() => fs.rmSync(base, { recursive: true, force: true }));

    const conversation = (id, updatedAt) => ({ id, title: `about ${id}`, updatedAt, history: [{ role: 'user', content: id }], transcript: [] });

    test('keeps each project\'s conversations apart, newest first', () => {
        store.save('/projects/a', conversation('one', '2026-10-24T10:00:00.000Z'));
        store.save('/projects/a', conversation('two', '2026-10-24T11:00:00.000Z'));
        store.save('/projects/b', conversation('three', '2026-10-24T12:00:00.000Z'));

        expect(store.list('/projects/a').map((entry) => entry.id)).toEqual(['two', 'one']);
        expect(store.list('/projects/b').map((entry) => entry.id)).toEqual(['three']);
        expect(store.load('/projects/a', 'one').history).toEqual([{ role: 'user', content: 'one' }]);
    });

    test('saving again updates it; removing forgets it', () => {
        store.save('/p', conversation('one', '2026-10-24T10:00:00.000Z'));
        store.save('/p', { ...conversation('one', '2026-10-24T12:00:00.000Z'), title: 'renamed' });
        expect(store.list('/p')).toEqual([{ id: 'one', title: 'renamed', updatedAt: '2026-10-24T12:00:00.000Z' }]);

        store.remove('/p', 'one');
        expect(store.list('/p')).toEqual([]);
        expect(store.load('/p', 'one')).toBeNull();
    });

    test(`keeps the newest ${MAX_CONVERSATIONS}`, () => {
        for (let i = 0; i <= MAX_CONVERSATIONS; i++) {
            store.save('/p', conversation(`c${i}`, new Date(Date.UTC(2026, 0, 1, 0, i)).toISOString()));
        }
        expect(store.list('/p')).toHaveLength(MAX_CONVERSATIONS);
        expect(store.load('/p', 'c0')).toBeNull();
    });
});
