/** Exercise the browser MCP controls against the local authenticated Cloudflare fixture. */
const { app, BrowserWindow } = require('electron');
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
        await window.loadURL('http://127.0.0.1:8127/manifest.json');
        const session = { access_token: config.token, refresh_token: 'test-refresh', expires_at: Math.floor(Date.now() / 1000) + 3600,
            token_type: 'bearer', user: { id: '11111111-1111-4111-8111-111111111111', email: 'test@kigumi.test', aud: 'authenticated' } };
        await js(`localStorage.clear(); localStorage.setItem('kigumi.web.store', ${JSON.stringify(JSON.stringify({ 'sb-supabase-auth-token': JSON.stringify(session) }))});
            localStorage.setItem('kigumi.web.settings', JSON.stringify({'agent.enabled':true,'agent.showOnStartup':false,'mcp.enabled':false}));`);
        await window.loadURL('http://127.0.0.1:8127/');
        await wait("document.body.classList.contains('kigumi-ready')");
        await js(`window.__kigumiWorker.addEventListener('message', ({data}) => { if(data.type==='browser:clipboard') window.mcpSetup=data.text; });`);
        const explorer = `document.querySelector('#slot-left iframe')?.contentDocument`;
        await wait(`${explorer}?.querySelector('[data-section="mcp"] .ks-section-header')`);
        await js(`${explorer}.querySelector('[data-section="mcp"] .ks-section-header').click()`);
        await wait(`${explorer}?.querySelector('input[data-option="mcp.enabled"]')`);
        await js(`${explorer}.querySelector('input[data-option="mcp.enabled"]').click()`);
        await wait(`${explorer}?.querySelector('button[data-copy="url"]')`, 30000);
        await js(`${explorer}.querySelector('button[data-copy="url"]').click()`);
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
        await js(`${explorer}.querySelector('input[data-option="mcp.enabled"]').click()`);
        let status;
        for (let i = 0; i < 50; i++) {
            status = (await fetch(url, { headers: { Authorization: `Bearer ${token}` } })).status;
            if (status === 410) break;
            await sleep(100);
        }
        assert.equal(status, 410);
        console.log('PASS: signed-in browser, sidebar enable/copy, public MCP initialize/list/call, real list_panels tool, disable/revoke');
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
