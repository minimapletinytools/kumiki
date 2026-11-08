const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const { execFileSync } = require('child_process');
const { PageStore } = require('../app-shell/page-store');
const { webviewDir } = require('../webview-html');
const { createWebServer, browserPage, prepareProjectDir } = require('../hosts/web/server');
const { isProjectFile, checkRelativePath, writeProjectFiles, readProjectFiles, watchProjectFiles, LIMITS } = require('../hosts/web/project-files');
const { makeZip } = require('../hosts/web/zip');

const tempDir = (prefix) => fs.mkdtempSync(path.join(os.tmpdir(), prefix));

test('allows template style attributes without relaxing the script policy', () => {
    const html = '<head><meta content="script-src \'nonce-abc123\'; style-src http://127.0.0.1:7346;"><script nonce="abc123"></script>';
    expect(browserPage(html)).toContain('style-src http://127.0.0.1:7346; style-src-attr \'unsafe-inline\';');
    expect(browserPage(html)).toContain('script-src \'nonce-abc123\';');
});

describe('browser host HTTP boundary', () => {
    let web;
    let origin;
    let receive;
    let controller;

    beforeEach(async () => {
        receive = jest.fn();
        web = createWebServer({ pages: new PageStore({ origin: '', webviewDir }), onMessage: receive });
        origin = await web.listen(0);
        controller = new AbortController();
    });
    afterEach(async () => {
        controller.abort();
        await web.close();
    });

    test('serves the shared shell with the web scripts, before shell.js, and its stylesheet', async () => {
        const html = await (await fetch(origin)).text();
        expect(html).toContain('<base href="/webview/shell/">');
        expect(html).toContain('connect-src \'self\'');
        const at = (name) => html.indexOf(`/web-host/${name}`);
        expect(at('zip.js')).toBeLessThan(at('web-projects.js'));
        expect(at('web-projects.js')).toBeLessThan(at('transport.js'));
        expect(at('transport.js')).toBeLessThan(html.indexOf('src="shell.js"'));
        expect(html).toContain('/web-host/web.css');
        for (const name of ['zip.js', 'web-projects.js', 'transport.js', 'web.css']) {
            expect((await fetch(`${origin}/web-host/${name}`)).status).toBe(200);
        }
        expect((await fetch(`${origin}/webview/editor/editor.html`)).status).toBe(200);
    });

    test('rejects foreign origins, DNS rebinding hosts, and unauthenticated messages', async () => {
        expect((await fetch(origin, { headers: { Origin: 'https://example.com' } })).status).toBe(403);
        const reboundStatus = await new Promise((resolve) => {
            http.get(origin, { headers: { Host: 'example.com' } }, (response) => {
                response.resume();
                resolve(response.statusCode);
            });
        });
        expect(reboundStatus).toBe(403);
        expect((await fetch(`${origin}/message`, {
            method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json' }, body: '{}',
        })).status).toBe(403);
        expect(receive).not.toHaveBeenCalled();
    });

    test('delivers messages both ways; a second tab takes over, and the first is told', async () => {
        const response = await fetch(`${origin}/events?client=first`, { signal: controller.signal });
        const reader = response.body.getReader();
        await reader.read();
        web.send({ type: 'shell:state', panels: [] });
        expect(new TextDecoder().decode((await reader.read()).value)).toContain('"type":"shell:state"');

        const second = await fetch(`${origin}/events?client=second`, { signal: controller.signal });
        expect(second.status).toBe(200);
        let told = '';
        for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            told += new TextDecoder().decode(value);
        }
        expect(told).toContain('"type":"web:takenOver"');
        const secondReader = second.body.getReader();
        await secondReader.read();
        web.send({ type: 'shell:state', panels: [] });
        expect(new TextDecoder().decode((await secondReader.read()).value)).toContain('"type":"shell:state"');
        const post = (body, extra = {}) => fetch(`${origin}/message`, {
            method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json', 'X-Kigumi-Client': 'first', ...extra }, body,
        });
        expect((await post('{', { 'X-Kigumi-Client': 'second' })).status).toBe(400);
        expect((await post('{}', { 'X-Kigumi-Client': 'second' })).status).toBe(400);
        // Only the tab in charge is listened to.
        expect((await post('{"type":"shell:ready"}')).status).toBe(403);
        expect((await post('{"type":"shell:ready"}', { 'X-Kigumi-Client': 'second' })).status).toBe(204);
        expect(receive).toHaveBeenCalledWith({ type: 'shell:ready' });
        expect((await post(JSON.stringify({ type: 'panel:message', data: 'x'.repeat(25 * 1024 * 1024) }), { 'X-Kigumi-Client': 'second' })).status).toBe(413);
    });

    test('serves nothing outside the webview assets and its own files', async () => {
        expect((await fetch(`${origin}/webview/%2e%2e%2fpackage.json`)).status).toBe(404);
        expect((await fetch(`${origin}/web-host/server.js`)).status).toBe(404);
        expect((await fetch(`${origin}/web-host/project-files.js`)).status).toBe(404);
        const temp = tempDir('kigumi-web-');
        const link = path.join(webviewDir, `test-link-${process.pid}`);
        try {
            fs.writeFileSync(path.join(temp, 'secret.txt'), 'private');
            fs.symlinkSync(path.join(temp, 'secret.txt'), link);
            expect((await fetch(`${origin}/webview/${path.basename(link)}`)).status).toBe(404);
        } finally {
            fs.rmSync(link, { force: true });
            fs.rmSync(temp, { recursive: true, force: true });
        }
    });
});

describe('a web project\'s files', () => {
    test('only the project\'s own text files travel', () => {
        expect(isProjectFile('my_frame.py')).toBe(true);
        expect(isProjectFile('.kigumi/drawings/my_frame.json')).toBe(true);
        expect(isProjectFile('.kigumi/kumiki.yaml')).toBe(true);
        for (const skipped of ['.venv/lib/x.py', 'sub/__pycache__/a.py', 'kigumi_exports/a.json', '.kigumi/docs/concepts.md',
            '.kigumi/logs/a.txt', '.kigumi/kigumi.yaml', '.kigumi/refresh-stats.json', 'model.stl']) {
            expect(isProjectFile(skipped)).toBe(false);
        }
    });

    test('a path that leaves the project is refused', () => {
        for (const bad of ['../x.py', '/etc/passwd', 'a/../../x', 'a//b.py', 'C:/x.py', 'a\\b.py', '']) {
            expect(() => checkRelativePath(bad)).toThrow('Not a path inside the project');
        }
        expect(checkRelativePath('a/b.py')).toBe('a/b.py');
    });

    test('written files read back, leaving out what does not travel; too much is refused', () => {
        const dir = tempDir('kigumi-web-files-');
        try {
            writeProjectFiles(dir, { 'shed.py': 'x = 1\n', 'parts/leg.py': 'y = 2\n', '.kigumi/drawings/shed.json': '{}' });
            fs.mkdirSync(path.join(dir, '.kigumi', 'logs'), { recursive: true });
            fs.writeFileSync(path.join(dir, '.kigumi', 'logs', 'run.txt'), 'log');
            expect(readProjectFiles(dir)).toEqual({ 'shed.py': 'x = 1\n', 'parts/leg.py': 'y = 2\n', '.kigumi/drawings/shed.json': '{}' });
            expect(() => writeProjectFiles(dir, { '../out.py': '' })).toThrow();
            expect(() => writeProjectFiles(dir, { 'big.py': 'x'.repeat(LIMITS.fileBytes + 1) })).toThrow('larger than');
            expect(fs.existsSync(path.join(dir, '..', 'out.py'))).toBe(false);
        } finally {
            fs.rmSync(dir, { recursive: true, force: true });
        }
    });

    test('changes made in the working folder are reported together; exports separately', async () => {
        const dir = tempDir('kigumi-web-watch-');
        writeProjectFiles(dir, { 'a.py': '1', 'b.py': '2' });
        const reports = [];
        const exports = [];
        const watch = watchProjectFiles(dir, { onFiles: (update) => reports.push(update), onExport: (relative) => exports.push(relative), delayMs: 100 });
        try {
            await new Promise((resolve) => setTimeout(resolve, 100));
            fs.writeFileSync(path.join(dir, 'a.py'), 'changed');
            fs.rmSync(path.join(dir, 'b.py'));
            fs.mkdirSync(path.join(dir, 'kigumi_exports'));
            fs.writeFileSync(path.join(dir, 'kigumi_exports', 'shed.stl'), 'solid');
            await new Promise((resolve) => setTimeout(resolve, 600));
            const merged = reports.reduce((all, one) => ({ changed: { ...all.changed, ...one.changed }, deleted: [...all.deleted, ...one.deleted] }),
                { changed: {}, deleted: [] });
            expect(merged.changed).toEqual({ 'a.py': 'changed' });
            // macOS may report a delete twice; the browser's copy takes it either way.
            expect([...new Set(merged.deleted)]).toEqual(['b.py']);
            expect(exports).toContain('kigumi_exports/shed.stl');
        } finally {
            watch.dispose();
            fs.rmSync(dir, { recursive: true, force: true });
        }
    });

    test('a working folder runs on the shared Python and is marked a kumiki project', () => {
        const root = tempDir('kigumi-web-prep-');
        const venv = path.join(root, 'shared-venv');
        fs.mkdirSync(venv);
        const dir = path.join(root, 'project');
        try {
            prepareProjectDir(dir, venv);
            expect(fs.realpathSync(path.join(dir, '.venv'))).toBe(fs.realpathSync(venv));
            expect(fs.existsSync(path.join(dir, '.kigumi', 'kumiki.yaml'))).toBe(true);
            expect(fs.readFileSync(path.join(dir, '.kigumi', 'kigumi.yaml'), 'utf8')).toContain('web: true');
        } finally {
            fs.rmSync(root, { recursive: true, force: true });
        }
    });
});

test('an exported .zip opens, with every file as it was', () => {
    const dir = tempDir('kigumi-web-zip-');
    try {
        const file = path.join(dir, 'shed.zip');
        fs.writeFileSync(file, makeZip({ 'Shed/shed.py': 'print("木組")\n', 'Shed/.kigumi/kumiki.yaml': 'kumiki_version: latest\n' }));
        const read = JSON.parse(execFileSync('python3', ['-c',
            'import json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; '
            + 'print(json.dumps({n: z.read(n).decode() for n in z.namelist()}))', file]).toString());
        expect(read).toEqual({ 'Shed/shed.py': 'print("木組")\n', 'Shed/.kigumi/kumiki.yaml': 'kumiki_version: latest\n' });
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});
