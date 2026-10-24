/** Serve one trusted Kigumi workspace on the loopback interface. */

const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { PageStore } = require('../../app-shell/page-store');
const { ShellConnection } = require('../../app-shell/shell-connection');
const { webviewDir } = require('../../webview-html');
const { setHost } = require('../../host');
const { createKigumiApp } = require('../../kigumi-app');
const { SettingsStore, defaultsFromPackageJson } = require('../electron/settings-store');
const { LogChannel } = require('../electron/log-channel');
const { createBrowserHost } = require('./browser-host');

const KIGUMI_DIR = path.resolve(__dirname, '../..');
const packageJson = require('../../package.json');
const TYPES = {
    '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8', '.json': 'application/json',
    '.png': 'image/png', '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.woff2': 'font/woff2',
};
const MAX_MESSAGE_BYTES = 2 * 1024 * 1024;

/** Allow the viewer's template style attributes in the browser adapter. */
function browserPage(html) {
    return html.replace(/style-src [^;"]*;/, "$& style-src-attr 'unsafe-inline';");
}

/** Return an HTTP server and shell transport; reject cross-origin control requests. */
function createWebServer({ pages, onMessage, onDisconnect = () => {} }) {
    let origin;
    let stream = null;
    let client = null;
    function reply(response, code, body = '', contentType = 'text/plain; charset=utf-8') {
        response.writeHead(code, { 'Content-Type': contentType });
        response.end(body);
    }
    async function file(response, root, relative) {
        const rootPath = await fs.promises.realpath(root);
        const target = await fs.promises.realpath(path.resolve(root, relative));
        if (!target.startsWith(rootPath + path.sep)) return reply(response, 404);
        const body = await fs.promises.readFile(target);
        reply(response, 200, body, TYPES[path.extname(target)] || 'application/octet-stream');
    }
    const server = http.createServer(async (request, response) => {
        response.setHeader('Cache-Control', 'no-store');
        response.setHeader('X-Content-Type-Options', 'nosniff');
        response.setHeader('Cross-Origin-Resource-Policy', 'same-origin');
        response.setHeader('Referrer-Policy', 'no-referrer');
        response.setHeader('Content-Security-Policy', "frame-ancestors 'self'");
        if (request.headers.host !== new URL(origin).host ||
            (request.headers.origin && request.headers.origin !== origin) ||
            request.headers['sec-fetch-site'] === 'cross-site') {
            return reply(response, 403, 'Use the server URL printed at startup.');
        }
        try {
            const url = new URL(request.url, origin);
            const pathname = decodeURIComponent(url.pathname);
            if (request.method === 'POST' && pathname === '/message') {
                if (request.headers.origin !== origin || !client || request.headers['x-kigumi-client'] !== client ||
                    request.headers['content-type'] !== 'application/json') return reply(response, 403);
                let size = 0;
                const chunks = [];
                for await (const chunk of request) {
                    size += chunk.length;
                    if (size > MAX_MESSAGE_BYTES) {
                        reply(response, 413, 'Message too large');
                        return;
                    }
                    chunks.push(chunk);
                }
                let message;
                try { message = JSON.parse(Buffer.concat(chunks).toString()); }
                catch { return reply(response, 400, 'Invalid JSON'); }
                if (!message || typeof message.type !== 'string') return reply(response, 400);
                onMessage(message);
                return reply(response, 204);
            }
            if (request.method !== 'GET') return reply(response, 405);
            if (pathname === '/events') {
                if (stream) return reply(response, 409, 'This workspace already has a browser connected.');
                const id = url.searchParams.get('client');
                if (!id || !/^[a-zA-Z0-9-]{1,80}$/.test(id)) return reply(response, 400);
                client = id;
                stream = response;
                response.writeHead(200, {
                    'Content-Type': 'text/event-stream', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no',
                });
                response.write(': connected\n\n');
                const heartbeat = setInterval(() => response.write(': heartbeat\n\n'), 15000);
                response.on('close', () => {
                    clearInterval(heartbeat);
                    stream = null;
                    client = null;
                    onDisconnect();
                });
                return;
            }
            if (pathname === '/' || pathname === '/webview/shell/shell.html') {
                const html = await fs.promises.readFile(path.join(webviewDir, 'shell/shell.html'), 'utf8');
                return reply(response, 200, html
                    .replace("script-src 'self';", "script-src 'self'; connect-src 'self';")
                    .replace('<script src="shell.js">', '<script src="/web-host/transport.js"></script><script src="shell.js">')
                    .replace('<head>', '<head><base href="/webview/shell/">'), TYPES['.html']);
            }
            if (pathname.startsWith('/page/')) {
                const html = pages.get(pathname.slice('/page/'.length));
                return html === undefined ? reply(response, 404) : reply(response, 200, browserPage(html), TYPES['.html']);
            }
            if (pathname.startsWith('/webview/')) return await file(response, webviewDir, pathname.slice('/webview/'.length));
            if (pathname === '/web-host/transport.js' || pathname === '/web-host/source.css') {
                return await file(response, __dirname, path.basename(pathname));
            }
            reply(response, 404);
        } catch (error) {
            reply(response, error instanceof URIError ? 400 : 404);
        }
    });
    return {
        server,
        send(message) {
            if (stream && !stream.write(`data: ${JSON.stringify(message)}\n\n`)) {
                // End a stalled stream before geometry messages accumulate without a bound.
                if (stream.writableLength > 32 * 1024 * 1024) stream.destroy();
            }
        },
        async listen(port = 7346) {
            await new Promise((resolve, reject) => {
                server.once('error', reject);
                server.listen(port, '127.0.0.1', resolve);
            });
            origin = `http://127.0.0.1:${server.address().port}`;
            pages.origin = origin;
            return origin;
        },
        async close() {
            const closed = new Promise((resolve) => server.close(resolve));
            server.closeAllConnections();
            await closed;
        },
    };
}

async function start({ workspaceFolder, port = 7346, dataDir = path.join(os.homedir(), '.kigumi', 'web') }) {
    workspaceFolder = fs.realpathSync(workspaceFolder);
    if (!fs.statSync(workspaceFolder).isDirectory()) throw new Error('Pass a workspace directory.');
    const settings = new SettingsStore(path.join(dataDir, 'settings.json'), {
        ...defaultsFromPackageJson(packageJson), 'viewer.autoRefreshOnFileChange': true,
    });
    const channel = new LogChannel(path.join(dataDir, 'kigumi.log'));
    const pages = new PageStore({ origin: '', webviewDir });
    let receive;
    let connection;
    let kigumiApp;
    let status = null;
    let progress = null;
    const web = createWebServer({
        pages,
        onMessage: (message) => receive?.(message),
        onDisconnect: () => {
            // A fresh shell cannot finish a quick pick opened by the previous page.
            for (const pending of connection.pendingPicks.values()) pending.resolve(undefined);
            connection.pendingPicks.clear();
        },
    });
    const origin = await web.listen(port);
    function setStatus(level, message) {
        status = { level, message };
        connection.pushState();
    }
    async function runCommand(id, ...args) {
        try {
            const command = kigumiApp?.commands[id];
            if (!command) throw new Error(`Unknown command: ${id}`);
            return await command(...args);
        } catch (error) {
            channel.appendLine(`[web] ${error.stack || error}`);
            setStatus('error', error.message);
        }
    }
    function openLog() {
        const existing = connection.findPanel((panel) => panel.type === 'log');
        if (existing) return existing.reveal();
        const panel = connection.createPanel('log', { title: 'Log' });
        const subscription = channel.onLine((line) => panel.postMessage({ type: 'logLine', line }));
        panel.onDispose(() => subscription.dispose());
        panel.onMessage((message) => {
            if (message.type === 'logReady') panel.postMessage({ type: 'logLines', lines: channel.lines });
        });
        panel.loadUrl(`${origin}/webview/shell/log.html`);
    }
    connection = new ShellConnection({
        transport: { send: web.send, onMessage: (callback) => { receive = callback; } }, pages,
        status: () => ({
            workspace: { name: path.basename(workspaceFolder), path: workspaceFolder },
            status, progress, version: `${packageJson.version} · web prototype`,
            autoRefresh: settings.get('viewer.autoRefreshOnFileChange', true),
        }),
        onCommand: (id, ...args) => {
            if (id === 'run') void runCommand(...args);
            else if (id === 'openFrameFile') void runCommand('kigumi.quickOpenInViewer');
            else if (id === 'openLog') openLog();
            else if (id === 'openFolder') setStatus('info', 'Restart the web host with the workspace folder you want to open.');
            else if (id === 'openSettings') setStatus('info', `Web settings: ${settings.filePath}. Restart the host after editing.`);
            else if (id === 'toggleAgent') setStatus('info', 'The AI agent is being developed separately; this prototype provides the browser host.');
        },
    });
    setHost(createBrowserHost({
        connection, workspaceFolder, settings, runCommand, setStatus,
        setProgress: (title) => { progress = title; connection.pushState(); },
    }));
    kigumiApp = createKigumiApp({ extensionPath: KIGUMI_DIR, storagePath: path.join(dataDir, 'tools'), channel });
    kigumiApp.sidebarController.attach(connection.createPanel('explorer', { title: 'Explorer' }));
    const subscription = settings.onChange(() => connection.pushState());
    return {
        origin, connection, app: kigumiApp,
        async close() {
            subscription.dispose();
            await web.close();
            connection.dispose();
            await kigumiApp.dispose();
            settings.dispose();
            channel.dispose();
        },
    };
}

if (require.main === module) {
    start({ workspaceFolder: path.resolve(process.argv[2] || process.cwd()), port: Number(process.env.PORT || 7346) })
        .then((running) => {
            console.log(`Kigumi web prototype: ${running.origin}`);
            console.log('One trusted workspace and browser tab per process. Press Ctrl+C to stop.');
            let closing = false;
            const stop = async () => {
                if (closing) return;
                closing = true;
                await running.close();
                process.exit(0);
            };
            process.on('SIGINT', stop);
            process.on('SIGTERM', stop);
        })
        .catch((error) => { console.error(error); process.exitCode = 1; });
}

module.exports = { createWebServer, start, browserPage };
