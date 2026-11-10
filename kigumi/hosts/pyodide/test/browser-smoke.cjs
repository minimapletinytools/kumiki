/**
 * Kigumi in a browser, end to end, in Chromium (Electron is only the browser here): serve dist/ as a
 * static site, make a project, build its starter frame in a view, see a change reach the browser's
 * copy, reload, export it as a .zip, open it again, and delete it.
 *
 *   npm run build && env -u ELECTRON_RUN_AS_NODE ../../node_modules/.bin/electron test/browser-smoke.cjs
 */
const { app, BrowserWindow, session } = require('electron');
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const HERE = path.join(__dirname, '..');
const ARTIFACTS = path.join(HERE, 'test-artifacts');
const PORT = '8125';
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const results = [];
function check(name, ok, detail = '') {
    results.push(Boolean(ok));
    console.log(`${ok ? 'PASS' : 'FAIL'} [browser] ${name}${detail ? ` -- ${detail}` : ''}`);
}

app.whenReady().then(async () => {
    const server = spawn('node', [path.join(HERE, 'serve.mjs')], { env: { ...process.env, PORT }, stdio: 'ignore' });
    await sleep(800);
    fs.mkdirSync(ARTIFACTS, { recursive: true });
    const downloads = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-browser-downloads-'));
    const window = new BrowserWindow({ width: 1440, height: 950, show: false, webPreferences: { backgroundThrottling: false } });
    const violations = [];
    const errors = [];
    window.webContents.on('console-message', (event) => {
        const text = String(event.message || '');
        if (text.includes('Content Security Policy')) violations.push(text);
        // Kigumi's backend lets only its own sites ask it for the model list; the agent keeps its built-in one.
        if (/kigumi-backend.*blocked by CORS|kigumi-backend.*net::ERR_FAILED/.test(text)) return;
        if (event.level === 'error' || /Uncaught/.test(text)) errors.push(text);
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
            await sleep(300);
        }
    }
    const shot = async (name) => fs.writeFileSync(path.join(ARTIFACTS, `${name}.png`), (await window.webContents.capturePage()).toPNG());
    const explorer = 'document.querySelector("#slot-left iframe")?.contentDocument';
    const view = 'document.querySelector("#slot-center iframe:not([hidden])")?.contentDocument';
    try {
        // A fresh browser: nothing left from an earlier run.
        await session.defaultSession.clearStorageData();
        const started = Date.now();
        await window.loadURL(`http://127.0.0.1:${PORT}/`);
        window.showInactive();
        const ready = await wait("document.body.classList.contains('kigumi-ready')", 240000);
        check('Python, kumiki and Kigumi start in the page', ready === true, `${Math.round((Date.now() - started) / 1000)} s`);
        const warning = await wait("document.querySelector('#web-storage-warning')?.textContent", 20000);
        check('the projects page warns that files live in the browser only', Boolean(warning && warning.includes('NOT to disk')));
        await shot('start');
        const startStatus = await wait(`(${explorer}?.body?.innerText || '').includes('Open Project') ? ${explorer}.body.innerText : null`, 30000);
        check('with no project open, Project status offers Open Project, not Initialize Project',
            Boolean(startStatus && !startStatus.includes('Initialize Project')));
        check('the agent panel is open from the start', await wait(`!!document.querySelector('#slot-right iframe') && !document.querySelector('#slot-right').hidden`, 30000) === true);

        await js(`(() => {
            document.querySelector('.web-new-project input').value = 'Shed';
            document.querySelector('.web-new-project button').click();
        })()`);
        const made = await wait(`window.kigumiWeb.listProjects().find((p) => p.name === 'Shed' && p.files.includes('my_cute_frame.py'))`, 60000);
        check('New Project makes a project with the starter frame, kept in the browser', Boolean(made), JSON.stringify(made && made.files));
        check('the new project opens', await wait(`document.querySelector('#status-workspace')?.textContent === 'Shed'`, 30000) === true);

        const frameRow = await wait(`(() => {
            const row = [...(${explorer}?.querySelectorAll('.ks-row') || [])].find((one) => (one.dataset.key || '').endsWith('my_cute_frame.py'));
            return row ? row.dataset.key : null;
        })()`, 120000);
        check('the explorer lists the starter frame', Boolean(frameRow), frameRow);
        const opened = Date.now();
        await js(`[...${explorer}.querySelectorAll('.ks-row')].find((one) => one.dataset.key === ${JSON.stringify(frameRow)}).click()`);
        const canvas = await wait(`${view}?.querySelector('canvas')?.width`, 240000);
        const timbers = await wait(`${view}?.querySelectorAll('.lp-row-timber').length`, 240000);
        check('the starter frame builds and draws in a view', canvas > 100 && timbers > 0,
            `${timbers} timbers, ${Math.round((Date.now() - opened) / 1000)} s`);
        await sleep(1500);
        await shot('frame');

        // Saved in the code editor: the frame file changes, which reaches the browser's copy.
        const filePath = frameRow.replace(/^frame-file:workspace:/, '');
        await js(`window.kigumiShell.send({ type: 'shell:command', command: 'run', args: ['kigumi.openFileSource', ${JSON.stringify(filePath)}] })`);
        const editorText = await wait(`(() => {
            const doc = ${view};
            const lines = doc && doc.querySelector('.monaco-editor .view-lines');
            return lines && lines.textContent.includes('my_cute_frame') ? lines.textContent.length : null;
        })()`, 60000);
        check('the frame file opens in the code editor', Boolean(editorText));
        await shot('editor');
        await js(`window.__kigumiWorker.postMessage({ type: 'test:appendToFile', file: ${JSON.stringify(filePath)}, text: '\\n# edited in the browser\\n' })`);
        const synced = await wait(`(async () => {
            const db = await new Promise((resolve) => { const r = indexedDB.open('kigumi-web', 1); r.onsuccess = () => resolve(r.result); });
            const record = await new Promise((resolve) => { const r = db.transaction('projects').objectStore('projects').getAll(); r.onsuccess = () => resolve(r.result.find((p) => p.name === 'Shed')); });
            db.close();
            return record && record.files['my_cute_frame.py'].includes('# edited in the browser');
        })()`, 15000);
        check('a change to a project file reaches the browser\'s copy', synced === true);

        // New Frame (the last row of the frames list) and New File (a folder's right-click menu): each asks
        // for a name in the quick pick, and the file reaches the browser's copy.
        const savedFile = (name) => `(async () => {
            const db = await new Promise((resolve) => { const r = indexedDB.open('kigumi-web', 1); r.onsuccess = () => resolve(r.result); });
            const record = await new Promise((resolve) => { const r = db.transaction('projects').objectStore('projects').getAll(); r.onsuccess = () => resolve(r.result.find((p) => p.name === 'Shed')); });
            db.close();
            return record && typeof record.files[${JSON.stringify(name)}] === 'string' ? record.files[${JSON.stringify(name)}] : null;
        })()`;
        const answer = (text) => js(`(() => {
            const input = document.querySelector('#quickpick-filter');
            input.value = ${JSON.stringify(text)};
            input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
            return true;
        })()`);
        await js(`${explorer}.querySelector('.ks-row[data-key="frames-new"]').click(); true`);
        const framePrompt = await wait(`!document.querySelector('#quickpick').hidden && document.querySelector('#quickpick-filter').value`, 15000);
        await answer('Garden Shed');
        const newFrame = await wait(savedFile('garden_shed.py'), 30000);
        const newFrameRow = await wait(`!!${explorer}?.querySelector('.ks-row[data-key$="garden_shed.py"][data-key^="frame-file:workspace:"]') || null`, 120000);
        const newFrameTimbers = await wait(`${view}?.querySelectorAll('.lp-row-timber').length === 1 || null`, 240000);
        check('New Frame asks for a name, then makes, lists and shows the frame', framePrompt === 'my_frame'
            && Boolean(newFrame && newFrame.includes('def garden_shed(')) && newFrameRow === true && newFrameTimbers === true,
            `${framePrompt}, row ${newFrameRow}, view ${newFrameTimbers}`);
        await shot('new-frame');

        await js(`(() => {
            const row = ${explorer}.querySelector('.ks-row[data-key="files-root"]');
            const box = row.getBoundingClientRect();
            row.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, clientX: box.left + 20, clientY: box.top + 5 }));
            return true;
        })()`);
        const menuItem = await wait(`[...(${explorer}?.querySelectorAll('.ks-menu-item') || [])].some((item) => item.textContent.includes('New File')) || null`, 10000);
        await js(`[...${explorer}.querySelectorAll('.ks-menu-item')].find((item) => item.textContent.includes('New File')).click(); true`);
        const filePrompt = await wait(`!document.querySelector('#quickpick').hidden && document.querySelector('#quickpick-filter').value`, 15000);
        await answer('notes/plan.txt');
        const newFile = await wait(`(async () => (await ${savedFile('notes/plan.txt')}) === '' || null)()`, 30000);
        check('a folder\'s right-click menu has New File, which makes the file it is given', menuItem === true
            && filePrompt === 'untitled.py' && newFile === true, `${filePrompt}, saved ${newFile}`);

        // Delete File, from the new frame's right-click menu: asked first, then gone from the list and the browser's copy.
        const shedRow = `${explorer}.querySelector('.ks-row[data-key$="garden_shed.py"][data-key^="frame-file:workspace:"]')`;
        await js(`(() => {
            const row = ${shedRow};
            const box = row.getBoundingClientRect();
            row.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, clientX: box.left + 20, clientY: box.top + 5 }));
            return true;
        })()`);
        const deleteItem = await wait(`[...(${explorer}?.querySelectorAll('.ks-menu-item') || [])].some((item) => item.textContent.includes('Delete File')) || null`, 10000);
        await js(`[...${explorer}.querySelectorAll('.ks-menu-item')].find((item) => item.textContent.includes('Delete File')).click(); true`);
        const asked = await wait(`!document.querySelector('#quickpick').hidden || null`, 15000);
        await js(`(() => {
            const input = document.querySelector('#quickpick-filter');
            input.value = 'Delete';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
            return true;
        })()`);
        const deleted = await wait(`(async () => (await ${savedFile('garden_shed.py')}) === null || null)()`, 30000);
        const unlisted = await wait(`!${shedRow} || null`, 60000);
        check('a frame\'s right-click menu has Delete File, which asks, then removes the frame', deleteItem === true
            && asked === true && deleted === true && unlisted === true, `asked ${asked}, deleted ${deleted}, unlisted ${unlisted}`);

        // The agent: its panel says how it can be run here, and its tools work.
        await js(`window.kigumiShell.send({ type: 'shell:command', command: 'web:settings',
            args: [{ values: { ...window.kigumiWeb.storedSettings(), 'agent.enabled': true } }] })`);
        const agent = 'document.querySelector("#slot-right iframe")?.contentDocument';
        const notice = await wait(`(() => {
            const doc = ${agent};
            const element = doc && doc.querySelector('.web-agent-notice');
            return element && doc.defaultView.getComputedStyle(element).display !== 'none' ? element.textContent : null;
        })()`, 60000);
        check('turned on, the agent opens and says how it can be run here', Boolean(notice && notice.includes('much better results')));
        await shot('agent');
        const tool = (name, input = {}) => js(`new Promise((resolve) => {
            const id = Math.random();
            const worker = window.__kigumiWorker;
            const listen = (event) => {
                if (event.data && event.data.type === 'test:agentToolResult' && event.data.id === id) {
                    worker.removeEventListener('message', listen);
                    resolve(event.data.error ? 'ERROR ' + event.data.error : event.data.result.map((part) => part.text || '').join('\\n'));
                }
            };
            worker.addEventListener('message', listen);
            worker.postMessage({ type: 'test:agentTool', id, name: ${JSON.stringify(name)}, input: ${JSON.stringify(input)} });
        })`);
        const found = await tool('search_files', { pattern: 'def my_cute_frame' });
        check("the agent's search finds a line in the project", found.includes('my_cute_frame.py:'), found.slice(0, 120));
        const api = await tool('kumiki_api', { name: 'create_axis_aligned_timber' });
        check("the agent's kumiki_api looks a name up in kumiki", api.includes('create_axis_aligned_timber') && !api.startsWith('ERROR'), api.slice(0, 120));
        // The tab signing in opens: noted, not opened.
        await js(`window.open = (url) => { window.__signInUrl = url; return {}; }; true`);
        await js(`${agent}.querySelector('.web-agent-sign-in .sign-in-chip[data-provider="github"]').click()`);
        const signInHref = await wait('window.__signInUrl', 15000);
        const signInUrl = signInHref ? new URL(signInHref) : null;
        check('signing in opens the provider in a tab, coming back to auth.html',
            Boolean(signInUrl && signInUrl.hostname.endsWith('supabase.co') && (signInUrl.searchParams.get('redirect_to') || '').endsWith('/auth.html')),
            signInHref && signInHref.slice(0, 100));
        // Coming back to auth.html hands the code to this tab, which tries it (a made-up one fails).
        const authWindow = new BrowserWindow({ show: false });
        await authWindow.loadURL(`http://127.0.0.1:${PORT}/auth.html?code=not-a-real-code`);
        const refused = await wait(`(document.querySelector('#status-message')?.textContent || '').includes('Could not sign in') || null`, 30000);
        check('auth.html hands sign-in back to the Kigumi tab', refused === true);
        if (!authWindow.isDestroyed()) authWindow.destroy();
        const listed = await tool('list_projects');
        check("the agent's list_projects names the open project", listed.includes('"open": "Shed"'), listed.replace(/\s+/g, ' ').slice(0, 120));

        // A bigger frame from kumiki's examples: the 120 sq ft tiny house.
        await js(`window.kigumiShell.send({ type: 'shell:command', command: 'browseExamples', args: [] })`);
        const houseRow = await wait(`(() => {
            const row = [...(${explorer}?.querySelectorAll('.ks-row') || [])].find((one) => (one.dataset.key || '').includes('tinyhouse120'));
            return row ? row.dataset.key : null;
        })()`, 30000);
        const examples = await js(`[...${explorer}.querySelectorAll('.ks-row')].map((one) => one.dataset.key || '').filter((key) => key.startsWith('frame-file:library:'))`);
        check('Example Frames lists each of kumiki\'s examples once', examples.length > 0 && new Set(examples).size === examples.length
            && new Set(examples.map((key) => key.split('/').pop())).size === examples.length, `${examples.length} rows`);
        const shipped = await js(`[...${explorer}.querySelectorAll('.ks-row')].find((one) => one.dataset.key === 'pattern-section:shipped-patterns')?.textContent || ''`);
        check('kumiki\'s own patterns are listed', /\((\d+)\)/.test(shipped) && Number(shipped.match(/\((\d+)\)/)[1]) > 0, shipped.trim());
        const houseStart = Date.now();
        if (houseRow) await js(`[...${explorer}.querySelectorAll('.ks-row')].find((one) => one.dataset.key === ${JSON.stringify(houseRow)}).click()`);
        const houseTimbers = houseRow ? await wait(`(() => {
            const doc = ${view};
            const count = doc && doc.querySelector('canvas') ? doc.querySelectorAll('.lp-row-timber').length : 0;
            return count > 20 ? count : null;
        })()`, 300000) : null;
        check('a bigger example frame (the tiny house) builds and draws', Boolean(houseTimbers),
            `${houseTimbers} timbers, ${Math.round((Date.now() - houseStart) / 1000)} s`);
        await sleep(2000);
        await shot('tinyhouse');

        await window.reload();
        await wait("document.body.classList.contains('kigumi-ready')", 240000);
        const reloaded = await wait(`document.querySelector('.web-project .welcome-recent-folder')?.textContent`, 30000);
        check('after a reload the browser still has the project', reloaded === 'Shed', reloaded);
        const recentRow = await wait(`[...(${explorer}?.querySelectorAll('.ks-status-label') || [])].some((label) => label.textContent === 'Shed') || null`, 30000);
        check('Project status lists it as a recent project', recentRow === true);
        await js(`[...${explorer}.querySelectorAll('.ks-status-action')].find((row) => row.textContent.includes('Shed')).click()`);
        check('clicking it there opens it', await wait(`document.querySelector('#status-workspace')?.textContent === 'Shed'`, 30000) === true);
        await js("document.querySelector('#status-workspace').click()");
        await wait("!document.querySelector('#status-workspace') || document.querySelector('#status-workspace').textContent !== 'Shed'", 30000);

        await js("document.querySelector('.web-project .web-project-action').click()");
        const deadline = Date.now() + 10000;
        while (Date.now() < deadline && downloaded.length === 0) await sleep(200);
        let names = [];
        if (downloaded[0] && downloaded[0].state === 'completed') {
            names = JSON.parse(execFileSync('python3', ['-c',
                'import json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; print(json.dumps(z.namelist()))',
                downloaded[0].target]).toString());
        }
        check('Export .zip downloads the project', names.includes('Shed/my_cute_frame.py'), JSON.stringify(names));

        await js("document.querySelector('.web-project .welcome-recent-folder').click()");
        check('opening it again works from the browser\'s copy', await wait(`document.querySelector('#status-workspace')?.textContent === 'Shed'`, 30000) === true);
        await js("document.querySelector('#status-workspace').click()");
        await wait("!!document.querySelector('.web-project')", 30000);
        await js("window.confirm = () => true; [...document.querySelectorAll('.web-project .web-project-action')].find((b) => b.textContent === 'Delete').click()");
        check('Delete removes the project from the browser', await wait("window.kigumiWeb.listProjects().length === 0", 10000) === true,
            JSON.stringify(await js('window.kigumiWeb.listProjects()')));

        check('no content security policy violations', violations.length === 0, violations.slice(0, 2).join(' | '));
        check('no errors in the page', errors.length === 0, errors.slice(0, 3).join(' | '));
    } catch (error) {
        console.error(error);
        results.push(false);
    }
    const failed = results.filter((ok) => !ok).length;
    console.log(`${results.length - failed} passed, ${failed} failed`);
    server.kill();
    fs.rmSync(downloads, { recursive: true, force: true });
    app.exit(failed ? 1 : 0);
});
