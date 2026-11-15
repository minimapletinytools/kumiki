const fs = require('fs');
const os = require('os');
const path = require('path');

const { createPublishes, parsePublishLink, findLocalDependencies } = require('../publishes');
const { SidebarModel } = require('../sidebar-model');
const { setHost } = require('../host');

const ID = 'Abcdefghijklmnopqrstuv';
const FRAME = 'from kumiki import *\n\ndef build_frame():\n    return Frame(cut_timbers=[])\n';

function tempDir() {
    return fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-publishes-'));
}

function settings() {
    const values = {};
    return {
        values,
        getConfig: (key, fallback) => (key in values ? values[key] : fallback),
        updateConfig: async (key, value) => { values[key] = value; },
    };
}

describe('share links', () => {
    test.each([
        [ID, ID],
        [`https://kumiki.build/p/#${ID}`, ID],
        [`kumiki.build/p#${ID}`, ID],
        [`kigumi://publish/${ID}`, ID],
        [`https://kumiki.build/try/#publish=${ID}`, ID],
        [`  https://kumiki.build/p/#${ID}  `, ID],
        ['https://kumiki.build/p/#short', null],
        [`https://kumiki.build/p/#${ID}x`, null],
        ['hello', null],
    ])('%s is %s', (text, id) => {
        expect(parsePublishLink(text)).toBe(id);
    });
});

describe('what a frame uses from its project', () => {
    test('kumiki and the standard library are fine; project modules, relative imports and named files are not', () => {
        const root = tempDir();
        fs.writeFileSync(path.join(root, 'parts.py'), '');
        fs.mkdirSync(path.join(root, 'joinery'));
        fs.writeFileSync(path.join(root, 'leg.stl'), 'solid');
        fs.mkdirSync(path.join(root, 'kumiki'));
        const frame = path.join(root, 'frame.py');
        fs.writeFileSync(frame, [
            'import math, os.path as osp',
            'from kumiki import *',
            'from kumiki.timber import Frame',
            'import parts',
            'from joinery.corner import miter',
            'from . import helpers',
            "leg = create_stl_timber(ref, 'leg.stl')",
            "name = 'frame.py'",
            "units = 'mm'",
        ].join('\n'));
        expect(findLocalDependencies(frame, root)).toEqual([
            { kind: 'import', name: 'parts' },
            { kind: 'import', name: 'joinery.corner' },
            { kind: 'import', name: '.' },
            { kind: 'file', name: 'leg.stl' },
        ]);
    });

    test('a frame of kumiki alone uses nothing', () => {
        const root = tempDir();
        fs.writeFileSync(path.join(root, 'frame.py'), FRAME);
        expect(findLocalDependencies(path.join(root, 'frame.py'), root)).toEqual([]);
    });
});

describe('publishing', () => {
    function account(signedIn = true) {
        const calls = [];
        return {
            calls,
            state: () => ({ signedIn }),
            fetchWithToken: async (url, init) => {
                calls.push({ url, body: JSON.parse(init.body) });
                return new Response(JSON.stringify({ id: ID, title: 'frame', entry: 'frame.py', kumikiVersion: '0.9.6', files: [] }), { status: 201 });
            },
        };
    }

    test('sends the frame and the kumiki version it is built with, and gives the link', async () => {
        const root = tempDir();
        const frame = path.join(root, 'frame.py');
        fs.writeFileSync(frame, FRAME);
        const signedIn = account();
        const publishes = createPublishes({ backendUrl: 'https://backend.test/', libraryRoot: tempDir(), account: () => signedIn, ...settings() });
        const { link } = await publishes.publish(frame, { projectRoot: root, kumikiVersion: '0.9.6', kigumiVersion: '0.9.7' });
        expect(link).toBe(`https://kumiki.build/p/#${ID}`);
        expect(signedIn.calls).toEqual([{ url: 'https://backend.test/publishes', body: {
            title: 'frame', entry: 'frame.py', kumikiVersion: '0.9.6', kigumiVersion: '0.9.7', files: [{ path: 'frame.py', text: FRAME }],
        } }]);
    });

    test('refuses a frame that uses other project files, before asking anything of the server', async () => {
        const root = tempDir();
        fs.writeFileSync(path.join(root, 'parts.py'), '');
        fs.writeFileSync(path.join(root, 'frame.py'), `import parts\n${FRAME}`);
        const signedIn = account();
        const publishes = createPublishes({ backendUrl: 'https://backend.test', libraryRoot: tempDir(), account: () => signedIn, ...settings() });
        await expect(publishes.publish(path.join(root, 'frame.py'), { projectRoot: root, kumikiVersion: '0.9.6' }))
            .rejects.toMatchObject({ dependencies: [{ kind: 'import', name: 'parts' }] });
        expect(signedIn.calls).toEqual([]);
    });

    test('asks to sign in first', async () => {
        const root = tempDir();
        fs.writeFileSync(path.join(root, 'frame.py'), FRAME);
        const publishes = createPublishes({ backendUrl: 'https://backend.test', libraryRoot: tempDir(), account: () => account(false), ...settings() });
        await expect(publishes.publish(path.join(root, 'frame.py'), { projectRoot: root, kumikiVersion: '0.9.6' }))
            .rejects.toMatchObject({ code: 'SIGN_IN' });
    });
});

describe('opening a shared frame', () => {
    const manifest = { id: ID, title: 'Little shed', entry: 'shed.py', kumikiVersion: '0.9.6', createdAt: '2026-11-15T00:00:00Z',
        role: 'view', files: [{ path: 'shed.py', sha256: 'a'.repeat(64), size: FRAME.length }] };

    function backend() {
        const requests = [];
        const fetch = async (url) => {
            requests.push(url);
            if (url.endsWith(`/publishes/${ID}`)) return new Response(JSON.stringify(manifest));
            if (url.endsWith(`/files/${'a'.repeat(64)}`)) return new Response(FRAME);
            return new Response('{}', { status: 404 });
        };
        return { requests, fetch };
    }

    test('downloads it once into the library, lists it as shared, and its files are read-only', async () => {
        const library = tempDir();
        const config = settings();
        const { requests, fetch } = backend();
        const publishes = createPublishes({ backendUrl: 'https://backend.test', libraryRoot: library, fetch, ...config });
        const { entryPath } = await publishes.open(ID);
        expect(entryPath).toBe(path.join(library, 'publishes', ID, 'shed.py'));
        expect(fs.readFileSync(entryPath, 'utf8')).toBe(FRAME);
        expect(publishes.list()).toEqual([{ id: ID, title: 'Little shed', entry: 'shed.py', kumikiVersion: '0.9.6', createdAt: '2026-11-15T00:00:00Z' }]);
        expect(publishes.idForPath(entryPath)).toBe(ID);
        expect(publishes.idForPath(path.join(library, 'other.py'))).toBeNull();

        await publishes.open(ID);
        expect(requests).toHaveLength(2);

        await publishes.remove(ID);
        expect(publishes.list()).toEqual([]);
        expect(fs.existsSync(entryPath)).toBe(false);
    });

    test('says when nothing is shared at a link', async () => {
        const publishes = createPublishes({ backendUrl: 'https://backend.test', libraryRoot: tempDir(),
            fetch: async () => new Response('{}', { status: 404 }), ...settings() });
        await expect(publishes.open('Zbcdefghijklmnopqrstuv')).rejects.toThrow(/Nothing is shared/);
    });
});

describe('the explorer\'s Shared section', () => {
    afterEach(() => setHost(null));

    test('lists what was opened, with the kumiki version each was built with, and a row to add one', async () => {
        setHost({ locale: 'en', workspaceRoots: () => [], getConfig: (_key, fallback) => fallback, projects: { open: async () => {} } });
        const model = new SidebarModel({
            publishes: () => [{ id: ID, title: 'Little shed', entry: 'shed.py', kumikiVersion: '0.9.6', createdAt: '2026-11-15T00:00:00Z' }],
            library: { root: '/library', ready: () => false, preparing: false },
        });
        await model.refresh(true);
        const tree = model.getTree();
        const shared = tree.find((row) => row.key === 'shared-root');
        expect(shared.children.map((row) => [row.label, row.description])).toEqual([['Little shed', 'kumiki 0.9.6'], ['Add from Link…', undefined]]);
        expect(shared.children[0].action).toEqual({ command: 'kigumi.openPublish', arguments: [ID] });
        expect(shared.children[0].rowActions).toEqual(['copyToProject', 'copyShareLink', 'removeShared']);
        // With no project and no library yet: a row that sets it up.
        expect(tree.find((row) => row.key === 'library-prepare').action).toEqual({ command: 'kigumi.prepareLibrary', arguments: [] });
    });
});
