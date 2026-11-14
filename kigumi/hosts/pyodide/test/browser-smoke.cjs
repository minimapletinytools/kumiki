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
        const loading = await wait("document.getElementById('kw-loading') && getComputedStyle(document.querySelector('.welcome-keys')).display === 'none'", 20000);
        const emojis = await js(`({ logs: [...document.querySelectorAll('.kw-parade span')].map(one => one.textContent),
            rider: document.querySelector('.kw-load-rider')?.textContent })`);
        check('the loading parade uses logs only, with the beaver on the bar', emojis.logs.length > 0
            && emojis.logs.every(emoji => emoji === '🪵') && emojis.rider === '🦫');
        await shot('loading');
        const ready = await wait("document.body.classList.contains('kigumi-ready')", 240000);
        check('Python, kumiki and Kigumi start in the page', ready === true, `${Math.round((Date.now() - started) / 1000)} s`);
        const welcomeBack = await wait("!document.getElementById('kw-loading') && getComputedStyle(document.querySelector('.welcome-keys')).display !== 'none'", 10000);
        check('a loading card stands in for the welcome page while Kigumi starts, and goes once it is ready',
            loading === true && welcomeBack === true, `card ${loading}, welcome back ${welcomeBack}`);
        const warning = await wait("document.querySelector('#web-storage-warning')?.textContent", 20000);
        check('the projects page warns that files live in the browser only', Boolean(warning && warning.includes('NOT to disk')));
        await shot('start');
        const startStatus = await wait(`(${explorer}?.body?.innerText || '').includes('Open Project') ? ${explorer}.body.innerText : null`, 30000);
        check('with no project open, Project status offers Open Project, not Initialize Project',
            Boolean(startStatus && !startStatus.includes('Initialize Project')));
        check('the agent panel is open from the start', await wait(`!!document.querySelector('#slot-right iframe') && !document.querySelector('#slot-right').hidden`, 30000) === true);
        const welcomeParts = await js(`(() => {
            const shown = (id) => { const e = document.getElementById(id); return !!e && !e.hidden && e.offsetParent !== null; };
            const logo = document.getElementById('web-welcome-logo');
            return { logo: !!logo && logo.complete && logo.naturalWidth > 0, agent: shown('web-agent-hint'), projects: shown('web-projects-hint'),
                heading: getComputedStyle(document.querySelector('#welcome h1')).display, lead: document.getElementById('welcome-lead').textContent };
        })()`);
        check('with no project open, the welcome shows the logo, points to the agent and down to the projects',
            welcomeParts.logo && welcomeParts.agent && welcomeParts.projects && welcomeParts.heading === 'none' && welcomeParts.lead === '',
            JSON.stringify(welcomeParts));
        const agentNotice = await wait(`(() => {
            const doc = document.querySelector('#slot-right iframe')?.contentDocument;
            const warning = doc?.querySelector('[data-i18n="agent.web.warning"]');
            const link = warning?.querySelector('a');
            return warning && link && !warning.textContent.includes('{link}') ? { text: warning.textContent, href: link.href,
                body: getComputedStyle(doc.querySelector('.welcome-body')).display } : null;
        })()`, 30000);
        check('the agent panel says the web agent is for trying Kumiki out, linking the standalone app, without its welcome blurb',
            Boolean(agentNotice && agentNotice.text.startsWith('The web agent is just for trying out Kumiki')
                && agentNotice.href === 'https://kumiki.build/install' && agentNotice.body === 'none'), JSON.stringify(agentNotice));

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
        // The editor's contents, not its lines on screen: the file opens on its docstring.
        const editorText = await wait(`(() => {
            const doc = ${view};
            const model = doc && doc.defaultView.monaco && doc.defaultView.monaco.editor.getModels()[0];
            return model && model.getValue().includes('my_cute_frame') ? model.getValue().length : null;
        })()`, 60000);
        check('the frame file opens in the code editor', Boolean(editorText));
        await shot('editor');

        // The browser has no menus, so the shell runs the shortcuts: one pressed in the editor (a panel)
        // goes to the shell through panel-bridge.js. Open Current File in Viewer brings the file's view.
        const mac = process.platform === 'darwin';
        // A view's tab is titled "Kigumi: …"; the editor's by its file.
        const viewShown = `(document.querySelector('#slot-center iframe:not([hidden])')?.title || '').startsWith('Kigumi:')`;
        const shownBefore = await js(viewShown);
        const caught = await js(`(() => {
            const win = ${view}.defaultView;
            const target = win.document.querySelector('.monaco-editor textarea') || win.document.body;
            // dispatchEvent is false when a listener took the key (panel-bridge.js).
            return !target.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'O', code: 'KeyO', shiftKey: true,
                metaKey: ${mac}, ctrlKey: ${!mac}, bubbles: true, cancelable: true }));
        })()`);
        const viewBrought = await wait(`${viewShown} || null`, 30000);
        const status = await js(`document.getElementById('status-message')?.textContent || ''`);
        check('a shortcut pressed in the editor runs in the browser: Open Current File in Viewer brings its view',
            shownBefore === false && caught === true && viewBrought === true, JSON.stringify({ shownBefore, caught, viewBrought, status }));
        await js(`window.kigumiShell.send({ type: 'shell:command', command: 'run', args: ['kigumi.openFileSource', ${JSON.stringify(filePath)}] })`);
        await wait(`(() => { const doc = ${view}; return doc && doc.querySelector('.monaco-editor .view-lines') ? true : null; })()`, 30000);
        const welcomeKey = await js(`document.getElementById('key-open-current-in-viewer')?.textContent`);
        check('the welcome page shows the shortcut as this system writes it', welcomeKey === (mac ? '⇧⌘O' : 'Ctrl+Shift+O'), welcomeKey);
        await js(`(() => {
            const model = ${view}.defaultView.monaco.editor.getModels()[0];
            model.setValue(model.getValue() + '\\n# unsaved buffer rendered\\n');
            return true;
        })()`);
        await wait(`document.querySelector('#tabs')?.textContent.includes('●') || null`, 10000);
        await js(`window.kigumiShell.send({ type: 'shell:command', command: 'run', args: ['kigumi.render'] })`);
        const bufferSaved = await wait(`(async () => {
            const db = await new Promise((resolve) => { const r = indexedDB.open('kigumi-web'); r.onsuccess = () => resolve(r.result); });
            const record = await new Promise((resolve) => { const r = db.transaction('projects').objectStore('projects').getAll(); r.onsuccess = () => resolve(r.result.find((p) => p.name === 'Shed')); });
            db.close();
            return record && record.files['my_cute_frame.py'].includes('# unsaved buffer rendered');
        })()`, 15000);
        check('render saves unsaved editor content through the shared host', bufferSaved === true);

        await js(`window.__kigumiWorker.postMessage({ type: 'test:appendToFile', file: ${JSON.stringify(filePath)}, text: '\\n# edited in the browser\\n' })`);
        const synced = await wait(`(async () => {
            const db = await new Promise((resolve) => { const r = indexedDB.open('kigumi-web'); r.onsuccess = () => resolve(r.result); });
            const record = await new Promise((resolve) => { const r = db.transaction('projects').objectStore('projects').getAll(); r.onsuccess = () => resolve(r.result.find((p) => p.name === 'Shed')); });
            db.close();
            return record && record.files['my_cute_frame.py'].includes('# edited in the browser');
        })()`, 15000);
        check('a change to a project file reaches the browser\'s copy', synced === true);

        // New Frame (the last row of the frames list) and New File (a folder's right-click menu): each asks
        // for a name in the quick pick, and the file reaches the browser's copy.
        const savedFile = (name) => `(async () => {
            const db = await new Promise((resolve) => { const r = indexedDB.open('kigumi-web'); r.onsuccess = () => resolve(r.result); });
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
        const listedPanels = JSON.parse(await tool('list_panels'));
        const editorPanel = listedPanels.panels.find((panel) => panel.kind === 'editor' && panel.filePath === filePath);
        check('agent tools list the browser editor panel', Boolean(editorPanel));
        if (editorPanel) {
            const description = JSON.parse(await tool('describe_panel', { panel_id: editorPanel.id }));
            check('agent tools describe the browser editor', description.kind === 'editor' && description.filePath === filePath);
        }
        const found = await tool('search_files', { pattern: 'def my_cute_frame' });
        check("the agent's search finds a line in the project", found.includes('my_cute_frame.py:'), found.slice(0, 120));
        const api = await tool('kumiki_api', { name: 'create_axis_aligned_timber' });
        check("the agent's kumiki_api looks a name up in kumiki", api.includes('create_axis_aligned_timber') && !api.startsWith('ERROR'), api.slice(0, 120));
        const sourceFound = await tool('kumiki_source', { search: 'def create_axis_aligned_timber' });
        const page = await tool('kumiki_source', { path: 'kumiki.construction', offset: 1, limit: 3 });
        check("kumiki_source searches and reads the browser's kumiki", sourceFound.startsWith('kumiki/construction.py:')
            && page.startsWith('kumiki/construction.py\n1\t'), `${sourceFound.slice(0, 80)} | ${page.slice(0, 60)}`);
        const sheet = await tool('kumiki_source', { path: 'docs/api_cheat_sheet.md', limit: 1 });
        check('kumiki_source reads the cheat sheet from the browser\'s kumiki', sheet.startsWith('docs/api_cheat_sheet.md\n1\t# API cheat sheet'), sheet.slice(0, 120));
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
        // An example frame can be duplicated into the project, where it is listed with the project's frames.
        const rowButtons = (key) => js(`[...(${explorer}.querySelector('.ks-row[data-key="' + CSS.escape(${JSON.stringify(key)}) + '"]')
            ?.querySelectorAll('.ks-row-actions button') || [])].map((one) => one.title)`);
        const exampleButtons = houseRow ? await rowButtons(houseRow) : [];
        if (exampleButtons.includes('Duplicate To Workspace')) {
            await js(`[...${explorer}.querySelector('.ks-row[data-key="' + CSS.escape(${JSON.stringify(houseRow)}) + '"]').querySelectorAll('.ks-row-actions button')]
                .find((one) => one.title === 'Duplicate To Workspace').click()`);
        }
        const copied = await wait(`[...(${explorer}?.querySelectorAll('.ks-row') || [])].map((one) => one.dataset.key || '')
            .find((key) => key.startsWith('frame-file:workspace:') && key.endsWith('/tinyhouse120.py')) || null`, 30000);
        const copiedButtons = copied ? await rowButtons(copied) : [];
        check('an example frame\'s Duplicate To Workspace copies it into the project, whose own frames have no such button',
            Boolean(copied) && !copiedButtons.includes('Duplicate To Workspace'), JSON.stringify({ exampleButtons, copied, copiedButtons }));
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

        // The settings gear's Language: a new one reloads the page, which opens the project again in it.
        async function pickRow(label) {
            const row = await wait(`!document.querySelector('#quickpick').hidden && [...document.querySelectorAll('#quickpick-list .item-label')].some((one) => one.textContent.startsWith(${JSON.stringify(label)})) || null`, 15000);
            if (row) await js(`[...document.querySelectorAll('#quickpick-list .item-label')].find((one) => one.textContent.startsWith(${JSON.stringify(label)})).click()`);
            return row === true;
        }
        async function setLanguage(label) {
            await js("document.querySelector('#status-settings').click()");
            const picked = await pickRow('Language:') && await pickRow(label) && await pickRow('Reload');
            await sleep(1500);
            await wait("document.body.classList.contains('kigumi-ready')", 240000);
            const reopened = await wait(`document.querySelector('#status-workspace')?.textContent === 'Shed'`, 60000) === true;
            const options = await wait(`[...(${explorer}?.querySelectorAll('*') || [])].map((one) => one.textContent).find((text) => /^Kigumi(の設定| options)$/.test(text.trim())) || null`, 60000);
            return { picked, reopened, options: options && options.trim() };
        }
        const japanese = await setLanguage('日本語');
        check('Language in the settings: 日本語 reloads the page, opens the project again, and the explorer is in Japanese',
            japanese.picked && japanese.reopened && japanese.options === 'Kigumiの設定', JSON.stringify(japanese));
        const restored = await setLanguage('Default');
        check('and Default goes back to the browser\'s language', restored.picked && restored.reopened && restored.options === 'Kigumi options', JSON.stringify(restored));
        await js("document.querySelector('#status-workspace').click()");
        await wait("!!document.querySelector('.web-project')", 30000);
        const scrolls = await js(`['welcome', 'welcome-recent-list'].every((id) => getComputedStyle(document.getElementById(id)).overflowY === 'auto')`);
        check('the projects page, and its list of projects, scroll when they are too long', scrolls === true);
        await js("document.querySelector('.web-project .web-project-action.is-danger').click()");
        await wait("!!document.querySelector('dialog.web-delete[open]')", 5000);
        await shot('delete');
        const lockedUntilTyped = await js(`(() => {
            const dialog = document.querySelector('dialog.web-delete');
            const confirm = dialog.querySelector('.web-delete-confirm');
            const input = dialog.querySelector('input');
            const before = confirm.disabled;
            input.value = 'Shed';
            input.dispatchEvent(new Event('input'));
            return before && !confirm.disabled;
        })()`);
        await js("document.querySelector('dialog.web-delete .web-delete-confirm').click()");
        check('Delete warns, waits for the name to be typed, then removes the project from the browser',
            lockedUntilTyped === true && await wait("window.kigumiWeb.listProjects().length === 0", 10000) === true,
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
