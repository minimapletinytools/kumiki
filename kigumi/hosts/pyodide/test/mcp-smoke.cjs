/** Exercise the browser MCP controls against the local authenticated Cloudflare fixture. */
const { app, BrowserWindow, session } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const assert = require('assert/strict');
const HERE = path.resolve(__dirname, '..');
const backend = process.env.KIGUMI_BACKEND_DIR || path.resolve(HERE, '../../../../kigumi-backend');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

app.whenReady().then(async () => {
    const fixture = spawn('node', ['test/mcp-runtime.mjs', '--serve'], { cwd: backend, stdio: ['ignore', 'pipe', 'inherit'] });
    const server = spawn('node', ['serve.mjs'], { cwd: HERE, env: { ...process.env, PORT: '8127' }, stdio: 'ignore' });
    let window;
    try {
        const config = await new Promise((resolve, reject) => {
            let output = '';
            const timer = setTimeout(() => reject(new Error('Backend fixture startup timed out')), 30000);
            fixture.stdout.on('data', data => {
                output += data;
                const match = output.match(/FIXTURE (.+)\n/);
                if (match) { clearTimeout(timer); resolve(JSON.parse(match[1])); }
            });
            fixture.once('exit', code => { clearTimeout(timer); reject(new Error(`Backend exited: ${code}`)); });
        });
        window = new BrowserWindow({ show: false, webPreferences: { backgroundThrottling: false } });
        const js = code => window.webContents.executeJavaScript(code);
        const wait = async (code, timeout = 180000) => {
            const deadline = Date.now() + timeout;
            while (Date.now() < deadline) {
                const value = await js(code).catch(() => null);
                if (value) return value;
                await sleep(200);
            }
            throw new Error(`Timed out: ${code}`);
        };
        await session.defaultSession.clearStorageData();
        await window.loadURL('http://127.0.0.1:8127/manifest.json');
        const accountSession = { access_token: config.token, refresh_token: 'test-refresh', expires_at: Math.floor(Date.now() / 1000) + 3600,
            token_type: 'bearer', user: { id: '11111111-1111-4111-8111-111111111111', email: 'test@kigumi.test', aud: 'authenticated' } };
        await js(`localStorage.clear(); localStorage.setItem('kigumi.web.store', ${JSON.stringify(JSON.stringify({ 'sb-supabase-auth-token': JSON.stringify(accountSession) }))});
            localStorage.setItem('kigumi.web.settings', JSON.stringify({'agent.enabled':true,'agent.showOnStartup':false,'mcp.enabled':false}));`);
        await window.loadURL('http://127.0.0.1:8127/');
        await wait("document.body.classList.contains('kigumi-ready')");
        await js(`window.__kigumiWorker.addEventListener('message', ({data}) => { if(data.type==='browser:clipboard') window.mcpSetup=data.text; });`);
        // MCP and agent settings, at the top of the agent panel.
        await js(`document.querySelector('#toggle-right').click()`);
        const agent = `document.querySelector('#slot-right iframe')?.contentDocument`;
        await wait(`${agent} && !${agent}.getElementById('mcp-settings').hidden`);
        await js(`${agent}.getElementById('settings-toggle').getAttribute('aria-expanded') === 'true' || ${agent}.getElementById('settings-toggle').click()`);
        await js(`${agent}.getElementById('setting-mcp').click()`);
        await wait(`${agent}?.querySelector('.mcp-setup[data-client="url"]')`, 30000);
        await js(`${agent}.querySelector('.mcp-setup[data-client="url"]').click()`);
        const setup = await wait('window.mcpSetup', 10000);
        const url = setup.match(/URL: (.+)/)[1];
        const token = setup.match(/Bearer (.+)/)[1];
        const call = async (method, params) => {
            const response = await fetch(url, { method: 'POST', headers: { Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' },
                body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }) });
            assert.equal(response.status, 200);
            const body = await response.json();
            assert.equal(body.error, undefined, JSON.stringify(body));
            return body.result;
        };
        await call('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'smoke', version: '1' } });
        assert.ok((await call('tools/list')).tools.some(tool => tool.name === 'list_panels'));
        const result = await call('tools/call', { name: 'list_panels', arguments: {} });
        assert.ok(Array.isArray(JSON.parse(result.content[0].text).panels));
        const tool = (name, args) => call('tools/call', { name, arguments: args });
        const names = (await call('tools/list')).tools.map(one => one.name);
        for (const name of ['new_project', 'list_projects', 'open_project', 'close_project', 'delete_file', 'rename_file', 'list_files', 'search_files', 'read_file', 'write_file', 'edit_file']) assert.ok(names.includes(name), name);
        assert.ok(!(await tool('new_project', { folder: 'MCP files' })).isError);
        const createdFile = await tool('write_file', { file_path: 'notes/a.txt', content: 'hello' });
        assert.ok(!createdFile.isError, JSON.stringify(createdFile));
        assert.ok(!(await tool('write_file', { file_path: 'src/frame.py', content: 'width = 1\n' })).isError);
        assert.ok(!(await tool('edit_file', { file_path: 'src/frame.py', old_string: 'width = 1', new_string: 'width = 2' })).isError);
        assert.match((await tool('read_file', { file_path: 'src/frame.py' })).content[0].text, /width = 2/);
        assert.match((await tool('list_files', {})).content[0].text, /src\/frame.py/);
        assert.match((await tool('search_files', { pattern: 'width' })).content[0].text, /width = 2/);
        assert.ok((await tool('write_file', { file_path: '../outside.py', content: 'no' })).isError);
        assert.ok(!(await tool('write_file', { file_path: 'notes/occupied.txt', content: '' })).isError);
        assert.ok((await tool('rename_file', { file_path: 'notes/a.txt', new_path: 'notes/occupied.txt' })).isError);
        assert.ok(!(await tool('rename_file', { file_path: 'notes/a.txt', new_path: 'notes/b.txt' })).isError);
        await wait(`(async () => {
            const db = await new Promise(resolve => { const req = indexedDB.open('kigumi-web'); req.onsuccess = () => resolve(req.result); });
            const project = await new Promise(resolve => { const req = db.transaction('projects').objectStore('projects').getAll(); req.onsuccess = () => resolve(req.result.find(one => one.name === 'MCP files')); });
            db.close();
            return project?.files['notes/b.txt'] === 'hello' && !('notes/a.txt' in project.files);
        })()`);
        assert.ok(!(await tool('delete_file', { file_path: 'notes/b.txt' })).isError);
        assert.ok((await tool('delete_file', { file_path: 'notes/b.txt' })).isError);
        await js(`${agent}.getElementById('setting-mcp').click()`);
        let status;
        for (let i = 0; i < 50; i++) {
            status = (await fetch(url, { headers: { Authorization: `Bearer ${token}` } })).status;
            if (status === 410) break;
            await sleep(100);
        }
        assert.equal(status, 410);
        console.log('PASS: signed-in browser, agent panel enable/copy, public MCP initialize/list/call, project/file management, collision/path checks, disable/revoke');
    } catch (error) {
        console.error(error);
        process.exitCode = 1;
    } finally {
        window?.destroy();
        fixture.kill();
        server.kill();
        app.exit(process.exitCode || 0);
    }
});
