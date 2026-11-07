/**
 * The web version end to end, in Chromium: make a project in the browser, view its starter frame,
 * see a change on the server reach the browser's copy, edit, close, reload, export it as a .zip,
 * open it again from the browser's copy, and delete it.
 *
 * Electron is only the test's Chromium: the page has no preload or Node in it. The server runs in
 * this process, on a fresh data folder, with this checkout's .venv as its Python.
 *
 *   env -u ELECTRON_RUN_AS_NODE node_modules/.bin/electron test/web/browser-smoke.js
 */
const { app, BrowserWindow, session } = require('electron');
const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { start } = require('../../hosts/web/server');
const { getHost } = require('../../host');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const results = [];
function check(name, ok, detail = '') {
    results.push(ok);
    console.log(`${ok ? 'PASS' : 'FAIL'} [web] ${name}${detail ? ` -- ${detail}` : ''}`);
}

app.whenReady().then(async () => {
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-web-smoke-'));
    const downloads = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-web-downloads-'));
    const running = await start({ port: 0, dataDir });
    const window = new BrowserWindow({ width: 1440, height: 1000, show: false, webPreferences: { backgroundThrottling: false } });
    const violations = [];
    window.webContents.on('console-message', (event) => {
        const text = String(event.message || '');
        if (text.includes('Content Security Policy')) violations.push(text);
    });
    const downloaded = [];
    session.defaultSession.on('will-download', (_event, item) => {
        const target = path.join(downloads, item.getFilename());
        item.setSavePath(target);
        item.once('done', (_e, state) => downloaded.push({ target, state }));
    });
    const js = (code) => window.webContents.executeJavaScript(code);
    async function wait(code, timeoutMs = 60000) {
        const deadline = Date.now() + timeoutMs;
        for (;;) {
            const result = await js(code).catch(() => null);
            if (result) return result;
            if (Date.now() > deadline) return null;
            await sleep(250);
        }
    }
    const projects = () => js('window.kigumiWeb.listProjects()');
    const workspaceName = () => js("document.querySelector('#status-workspace')?.textContent || ''");
    try {
        await window.loadURL(running.origin);
        window.showInactive();
        const page = await wait(`(() => {
            const warning = document.querySelector('#web-storage-warning');
            const form = document.querySelector('.web-new-project');
            return warning && !warning.hidden && form ? warning.textContent : null;
        })()`);
        check('the projects page warns that files live in the browser only', Boolean(page && page.includes('NOT to disk and NOT to the cloud')), page);

        await js(`(() => {
            document.querySelector('.web-new-project input').value = 'Shed';
            document.querySelector('.web-new-project button').click();
        })()`);
        const made = await wait(`(() => {
            const list = window.kigumiWeb.listProjects();
            const one = list.find((p) => p.name === 'Shed');
            return one && one.files.includes('my_cute_frame.py') ? one : null;
        })()`);
        check('New Project makes a project in the browser with the starter frame', Boolean(made), JSON.stringify(made && made.files));
        check('the new project opens', await wait(`document.querySelector('#status-workspace')?.textContent === 'Shed'`, 20000) === true,
            await workspaceName());

        const dir = running.project.dir;
        const frame = path.join(dir, 'my_cute_frame.py');
        await js(`window.kigumiShell.send({ type: 'shell:command', command: 'run', args: ['kigumi.openFrameFromSidebar', ${JSON.stringify(frame)}] })`);
        const doc = 'document.querySelector("#slot-center iframe:not([hidden])")?.contentDocument';
        const canvas = await wait(`${doc}?.querySelector('canvas')?.width`, 120000);
        const timbers = await wait(`${doc}?.querySelectorAll('.lp-row-timber').length`, 60000);
        check('the starter frame builds in a view', canvas > 100 && timbers > 0, `canvas ${canvas}, ${timbers} timbers`);
        fs.mkdirSync(path.join(__dirname, '..', '..', '.artifacts', 'web'), { recursive: true });
        fs.writeFileSync(path.join(__dirname, '..', '..', '.artifacts', 'web', 'browser.png'), (await window.webContents.capturePage()).toPNG());

        const marker = '# edited on the server';
        fs.appendFileSync(frame, `\n${marker}\n`);
        const synced = await wait(`(async () => {
            const db = await new Promise((resolve) => { const r = indexedDB.open('kigumi-web', 1); r.onsuccess = () => resolve(r.result); });
            const record = await new Promise((resolve) => { const r = db.transaction('projects').objectStore('projects').getAll(); r.onsuccess = () => resolve(r.result.find((p) => p.name === 'Shed')); });
            db.close();
            return record && record.files['my_cute_frame.py'].includes(${JSON.stringify(marker)});
        })()`, 10000);
        check('a change on the server reaches the browser\'s copy', synced === true);

        await getHost().openFileAt(frame, 1);
        const editor = await wait(`[...document.querySelectorAll('.tab')].some((tab) => tab.textContent.includes('my_cute_frame.py') && !tab.textContent.includes('Explorer'))
            && !!document.querySelector('#slot-center iframe:not([hidden])')?.contentDocument?.querySelector('.monaco-editor')`, 30000);
        check('a file opens in an editor tab', editor === true);

        await js("document.querySelector('#status-workspace').click()");
        check('the status bar\'s project button goes back to the projects page',
            await wait(`!!document.querySelector('.web-project') && !document.querySelector('#web-storage-warning').hidden`, 20000) === true);

        await window.reload();
        const listed = await wait(`document.querySelector('.web-project .welcome-recent-folder')?.textContent`, 20000);
        check('after a reload the browser still has the project', listed === 'Shed', listed);
        fs.writeFileSync(path.join(__dirname, '..', '..', '.artifacts', 'web', 'projects.png'), (await window.webContents.capturePage()).toPNG());

        await js("document.querySelector('.web-project .web-project-action').click()");
        const zip = await (async () => {
            const deadline = Date.now() + 10000;
            while (Date.now() < deadline && downloaded.length === 0) await sleep(200);
            return downloaded[0];
        })();
        let names = [];
        if (zip && zip.state === 'completed') {
            names = JSON.parse(execFileSync('python3', ['-c',
                'import json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; print(json.dumps(z.namelist()))',
                zip.target]).toString());
        }
        check('Export .zip downloads the project', names.includes('Shed/my_cute_frame.py') && names.includes('Shed/.kigumi/kumiki.yaml'),
            JSON.stringify(names));

        await js("document.querySelector('.web-project .welcome-recent-folder').click()");
        const reopened = await wait(`document.querySelector('#status-workspace')?.textContent === 'Shed'`, 20000);
        const reopenedDir = running.project && running.project.dir;
        check('opening it again gives the server the browser\'s copy, edits included', reopened === true
            && fs.readFileSync(path.join(reopenedDir, 'my_cute_frame.py'), 'utf8').includes(marker));

        await js("document.querySelector('#status-workspace').click()");
        await wait("!!document.querySelector('.web-project')", 20000);
        await js("window.confirm = () => true; [...document.querySelectorAll('.web-project .web-project-action')].find((b) => b.textContent === 'Delete').click()");
        check('Delete removes the project from the browser',
            await wait("window.kigumiWeb.listProjects().length === 0 && !document.querySelector('.web-project')", 10000) === true);

        check('no content security policy violations', violations.length === 0, violations.slice(0, 2).join(' | '));
    } catch (error) {
        console.error(error);
        results.push(false);
    }
    const failed = results.filter((ok) => !ok).length;
    console.log(`${results.length - failed} passed, ${failed} failed`);
    await running.close().catch(() => {});
    fs.rmSync(dataDir, { recursive: true, force: true });
    fs.rmSync(downloads, { recursive: true, force: true });
    app.exit(failed ? 1 : 0);
});
