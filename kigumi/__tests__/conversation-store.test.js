const fs = require('fs');
const os = require('os');
const path = require('path');

const { createConversationStore, MAX_CONVERSATIONS, BLOB_AT } = require('../agent/conversation-store');

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

    test('drops conversations past the retention, on save and on prune', () => {
        let days = 0;
        const kept = createConversationStore(base, { retentionDays: () => days });
        const old = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString();
        const recent = new Date().toISOString();
        kept.save('/a', conversation('old', old));
        kept.save('/b', { ...conversation('blobbed', old), transcript: ['x'.repeat(BLOB_AT)] });
        kept.save('/a', conversation('new', recent));
        expect(kept.list('/a').map((entry) => entry.id)).toEqual(['new', 'old']);

        days = 7;
        expect(kept.list('/a').map((entry) => entry.id)).toEqual(['new']);
        kept.prune();
        expect(kept.load('/a', 'old')).toBeNull();
        expect(kept.load('/b', 'blobbed')).toBeNull();
        expect(kept.load('/a', 'new')).not.toBeNull();
        const blobs = fs.readdirSync(base).flatMap((name) => (fs.existsSync(path.join(base, name, 'blobs'))
            ? fs.readdirSync(path.join(base, name, 'blobs')) : []));
        expect(blobs).toEqual([]);
    });

    test('clears everything, and says how much it takes', () => {
        store.save('/a', conversation('one', '2026-10-24T10:00:00.000Z'));
        expect(store.usage()).toBeGreaterThan(0);
        store.clear();
        expect(store.list('/a')).toEqual([]);
        expect(store.usage()).toBe(0);
    });

    test('tells onFiles each write and delete, relative to the base', () => {
        const updates = [];
        const mirrored = createConversationStore(base, { onFiles: (update) => updates.push(update) });
        mirrored.save('/a', conversation('one', '2026-10-24T10:00:00.000Z'));
        const written = updates.flatMap((update) => Object.keys(update.changed));
        expect(written).toEqual(expect.arrayContaining([expect.stringMatching(/^[0-9a-f]{16}\/one\.json$/),
            expect.stringMatching(/^[0-9a-f]{16}\/index\.json$/)]));
        mirrored.clear();
        expect(updates[updates.length - 1].deleted).toEqual([expect.stringMatching(/^[0-9a-f]{16}$/)]);
    });
});
