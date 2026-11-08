/**
 * The web version end to end, in Chromium: turn the agent panel on from the settings (kept in the
 * browser), make a project in the browser, view its starter frame, see a change on the server reach
 * the browser's copy, edit, close, reload, export it as a .zip, open it again from the browser's
 * copy, and delete it; a browser with no settings of its own starts with the agent off.
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

        const agentShown = () => js(`(() => {
            const slot = document.querySelector('#slot-right');
            const frame = slot && !slot.hidden && slot.querySelector('iframe');
            return !!(frame && frame.contentDocument && frame.contentDocument.body && frame.contentDocument.body.childElementCount);
        })()`).catch(() => false);
        check('the agent panel is off by default', running.settings.get('agent.enabled', false) === false
            && await js("document.querySelector('#toggle-right').hidden") === true);
        await js("document.querySelector('#status-settings').click()");
        await wait("[...document.querySelectorAll('#quickpick-list .item')].some((item) => item.textContent.startsWith('Agent panel'))", 10000);
        await js("[...document.querySelectorAll('#quickpick-list .item')].find((item) => item.textContent.startsWith('Agent panel')).click()");
        check('the settings gear turns the agent panel on, and it opens', await wait(`(async () => {
            const slot = document.querySelector('#slot-right');
            const frame = slot && !slot.hidden && slot.querySelector('iframe');
            return !!(frame && frame.contentDocument && frame.contentDocument.body && frame.contentDocument.body.childElementCount);
        })()`, 20000) === true && running.settings.get('agent.enabled') === true);
        const notice = await wait(`(() => {
            const doc = document.querySelector('#slot-right iframe').contentDocument;
            const box = doc.querySelector('.web-agent-notice');
            if (!box || box.offsetParent === null) return null;
            return { text: box.textContent.replace(/\\s+/g, ' ').trim(),
                signIn: [...box.querySelectorAll('.sign-in-chip')].filter((b) => b.offsetParent !== null).map((b) => b.textContent) };
        })()`, 10000);
        check('the agent panel says how to run the agent here: sign in, MCP, or the app',
            Boolean(notice) && notice.text.includes('coming soon') && notice.text.includes('MCP') && notice.text.includes('standalone app')
                && notice.signIn.join() === 'GitHub,Google', JSON.stringify(notice));
        const callback = await fetch(`${running.origin}/auth/callback?error=access_denied&error_description=Denied`,
            { headers: { 'Sec-Fetch-Site': 'cross-site' } });
        check('sign-in comes back to the server, which answers rather than turning the browser away',
            callback.status === 400 && (await callback.text()).includes("Sign-in didn't finish"), String(callback.status));
        await js(`(() => {
            const doc = document.querySelector('#slot-right iframe').contentDocument;
            doc.getElementById('btn-settings').click();
            const input = doc.getElementById('setting-openrouter-key');
            input.value = 'sk-or-web-test';
            input.dispatchEvent(new Event('change'));
        })()`);
        const usingKey = await wait(`(() => {
            const doc = document.querySelector('#slot-right iframe').contentDocument;
            return !doc.body.classList.contains('needs-key') && doc.getElementById('route-note').textContent.includes('OpenRouter key')
                && doc.getElementById('setting-openrouter-key').value === '' && doc.getElementById('setting-openrouter-key-note').textContent;
        })()`, 10000);
        check('a key typed in the agent\'s settings is used, kept in the browser, and not shown again',
            Boolean(usingKey) && running.settings.get('agent.openrouterApiKey') === 'sk-or-web-test'
            && await js("JSON.parse(localStorage.getItem('kigumi.web.settings') || '{}')['agent.openrouterApiKey'] === 'sk-or-web-test'"),
            usingKey);
        check('the setting is kept in the browser', await wait(
            "JSON.parse(localStorage.getItem('kigumi.web.settings') || '{}')['agent.enabled'] === true", 10000) === true);
        fs.mkdirSync(path.join(__dirname, '..', '..', '.artifacts', 'web'), { recursive: true });
        fs.writeFileSync(path.join(__dirname, '..', '..', '.artifacts', 'web', 'agent.png'), (await window.webContents.capturePage()).toPNG());
        await window.reload();
        check('after a reload, the browser\'s settings are the ones in force',
            await wait("document.querySelector('#toggle-right') && !document.querySelector('#toggle-right').hidden", 20000) === true
            && running.settings.get('agent.enabled') === true);

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
        if (!(await agentShown())) await js("document.querySelector('#toggle-right').click()");
        check('the agent panel is there with a project open', await wait(`(() => {
            const frame = document.querySelector('#slot-right:not([hidden]) iframe');
            return !!(frame && frame.contentDocument && frame.contentDocument.body.childElementCount);
        })()`, 20000) === true);

        const dir = running.project.dir;
        const frame = path.join(dir, 'my_cute_frame.py');

        running.settings.set('mcp.port', 0); // any free port, so a Kigumi app already serving MCP is no matter
        await js("document.querySelector('#status-settings').click()");
        await wait("[...document.querySelectorAll('#quickpick-list .item')].some((item) => item.textContent.startsWith('MCP server'))", 10000);
        await js("[...document.querySelectorAll('#quickpick-list .item')].find((item) => item.textContent.startsWith('MCP server')).click()");
        const deadline = Date.now() + 10000;
        while (!running.mcp.running && Date.now() < deadline) await sleep(200);
        let folder = null;
        const mcpUrl = running.mcp.controls.state().url;
        if (mcpUrl) {
            const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
            const { StreamableHTTPClientTransport } = require('@modelcontextprotocol/sdk/client/streamableHttp.js');
            const client = new Client({ name: 'web-smoke-agent', version: '1.0' });
            await client.connect(new StreamableHTTPClientTransport(new URL(mcpUrl), {
                requestInit: { headers: { Authorization: `Bearer ${running.settings.get('mcp.token')}` } },
            }));
            try {
                const answer = await client.callTool({ name: 'get_workspace_folder', arguments: {} });
                folder = JSON.parse(answer.content[0].text).workspaceFolder;

                // The project tools, over MCP, by name: the projects live in the browser.
                const call = async (name, args = {}) => {
                    const result = await client.callTool({ name, arguments: args });
                    if (result.isError) throw new Error(`${name}: ${result.content[0].text}`);
                    return result.content[0].text;
                };
                const listed = JSON.parse(await call('list_projects'));
                await call('new_project', { folder: 'Barn' });
                const barnStored = await wait(`window.kigumiWeb.listProjects().some((p) => p.name === 'Barn' && p.files.includes('my_cute_frame.py'))`, 20000);
                const barnOpen = running.project && running.project.name === 'Barn';
                await call('open_project', { folder: 'shed' });
                const shedBack = running.project && running.project.name === 'Shed';
                await call('close_project');
                const closed = running.project === null;
                await call('open_project', { folder: 'Shed' });
                const listedAfter = JSON.parse(await call('list_projects'));
                check('over MCP, an agent lists, makes, opens and closes the browser\'s projects by name',
                    listed.open === 'Shed' && barnStored === true && barnOpen && shedBack && closed
                    && listedAfter.open === 'Shed' && listedAfter.recent.includes('Barn'),
                    JSON.stringify({ listed, barnStored, barnOpen, shedBack, closed, listedAfter }));
            } finally {
                await client.close();
            }
        }
        check('the settings gear turns the MCP server on, and an agent reaches the open project through it',
            folder === dir && running.settings.get('mcp.enabled') === true, `${mcpUrl}; ${folder}`);

        const explorer = 'document.querySelector("#slot-left iframe")?.contentDocument';
        // The explorer is made again with each project switch: wait for the new one.
        await wait(`(() => {
            const header = ${explorer}?.querySelector('.ks-section[data-section="options"] .ks-section-header');
            if (!header) return false;
            if (header.getAttribute('aria-expanded') !== 'true') header.click();
            return true;
        })()`, 20000);
        const mcpBox = await wait(`(() => {
            const box = ${explorer}.querySelector('.ks-mcp');
            const address = box && box.querySelector('.ks-mcp-address input');
            return address && address.value ? { address: address.value, agents: box.querySelector('.ks-mcp-agents').textContent,
                setups: [...box.querySelectorAll('.ks-mcp-setups button')].map((b) => b.textContent) } : null;
        })()`, 10000);
        await sleep(500);
        fs.writeFileSync(path.join(__dirname, '..', '..', '.artifacts', 'web', 'mcp.png'), (await window.webContents.capturePage()).toPNG());
        check('with MCP on, Kigumi options shows its address to copy, the setups, and how many agents are connected',
            Boolean(mcpBox) && mcpBox.address === mcpUrl && mcpBox.setups.includes('Claude Code') && /agent/.test(mcpBox.agents),
            JSON.stringify(mcpBox));
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

        await js(`(() => {
            const row = [...${'document.querySelector("#slot-left iframe").contentDocument'}.querySelectorAll('.ks-status-action')]
                .find((one) => one.textContent.includes('Close Project'));
            row.click();
        })()`);
        check('Project status\'s Close Project goes back to the projects page, closing the tabs',
            await wait(`!!document.querySelector('.web-project') && !document.querySelector('#web-storage-warning').hidden
                && ![...document.querySelectorAll('.tab')].some((tab) => tab.textContent.includes('my_cute_frame'))`, 20000) === true
            && running.project === null);
        await js("document.querySelector('.web-project .welcome-recent-folder').click()");
        await wait(`document.querySelector('#status-workspace')?.textContent === 'Shed'`, 20000);
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
            await wait("!window.kigumiWeb.listProjects().some((p) => p.name === 'Shed') && document.querySelectorAll('.web-project').length === 1", 10000) === true);

        await js('localStorage.clear()');
        await window.reload();
        check('a browser with no settings of its own starts with the agent off',
            await wait("document.querySelector('#toggle-right') && document.querySelector('#toggle-right').hidden", 20000) === true
            && running.settings.get('agent.enabled', false) === false);

        // A second tab takes over; the first says so, and takes it back with Use here.
        const second = new BrowserWindow({ width: 1200, height: 900, show: false, webPreferences: { backgroundThrottling: false } });
        await second.loadURL(running.origin);
        const secondRows = async () => second.webContents.executeJavaScript(
            'document.querySelector("#slot-left iframe")?.contentDocument?.querySelectorAll(".ks-row").length || 0').catch(() => 0);
        let rows = 0;
        for (let i = 0; i < 80 && rows === 0; i++) {
            rows = await secondRows();
            if (!rows) await sleep(250);
        }
        const firstCovered = await wait("!!document.getElementById('web-taken-over')", 10000);
        check('a second tab takes Kigumi over, and the first one says so', rows > 0 && firstCovered === true, `${rows} rows`);
        await js("document.querySelector('#web-taken-over button').click()");
        let secondCovered = false;
        for (let i = 0; i < 80 && !secondCovered; i++) {
            secondCovered = await second.webContents.executeJavaScript("!!document.getElementById('web-taken-over')").catch(() => false);
            if (!secondCovered) await sleep(250);
        }
        const firstWorks = await wait('document.querySelector("#slot-left iframe")?.contentDocument?.querySelectorAll(".ks-row").length', 20000);
        check('Use here takes it back', secondCovered && firstWorks > 0);
        second.destroy();

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
