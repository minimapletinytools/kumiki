/**
 * Kigumi in a browser: an HTTP server on the loopback interface that runs Kigumi's core and its
 * Python runner, and serves the app's shell, explorer and viewers to one browser tab at a time (the
 * newest; the one before offers to take it back).
 *
 * The browser holds the projects (hosts/web/web-projects.js keeps them in IndexedDB). The one open
 * is written into a working folder under the data folder, whose .venv links to one shared Python
 * environment with kumiki; every change made there is sent back to the browser. So are the
 * settings: the browser keeps them, and the server's settings file mirrors what it sends.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { PageStore } = require('../../app-shell/page-store');
const { ShellConnection } = require('../../app-shell/shell-connection');
const { createEditorTabs } = require('../../app-shell/editor-tabs');
const { webviewDir } = require('../../webview-html');
const { setHost } = require('../../host');
const { createKigumiApp } = require('../../kigumi-app');
const { ensureKigumiYaml } = require('../../project-root');
const { getInlineExampleFrameContent } = require('../../project-initializer');
const { SettingsStore, defaultsFromPackageJson } = require('../electron/settings-store');
const { LogChannel } = require('../electron/log-channel');
const { createBrowserHost } = require('./browser-host');
const { writeProjectFiles, readProjectFiles, watchProjectFiles } = require('./project-files');
const { createAgentPanel } = require('../../agent/agent-panel');
const { viewHost, sharedTools } = require('../../agent/agent');
const { createMcpService } = require('../../agent/mcp-service');
const { createProjectFiles } = require('../../agent/project-files');
const { createAccount } = require('../../agent/account');
const { createModelList } = require('../../agent/models');
const { backendConfig } = require('../../agent/backend-config');
const { findKumikiSource, kumikiExamples, projectPython } = require('../../agent/kumiki-source');
const { pythonKumikiApi } = require('../../agent/kumiki-api');
const { loadSystemPrompt } = require('../../agent/system-prompt');

const KIGUMI_DIR = path.resolve(__dirname, '../..');
const packageJson = require('../../package.json');
const TYPES = {
    '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8', '.json': 'application/json',
    '.png': 'image/png', '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.woff2': 'font/woff2',
};
// A whole project travels in one message when it is opened.
const MAX_MESSAGE_BYTES = 24 * 1024 * 1024;
const MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024;
// The browser's own scripts, served from /web-host/, in the order the shell page loads them.
const WEB_SCRIPTS = ['zip.js', 'web-projects.js', 'transport.js'];
const WEB_FILES = new Set([...WEB_SCRIPTS, 'web.css']);
const PROJECT_ID = /^[a-zA-Z0-9-]{1,64}$/;

/** Allow the viewer's template style attributes in the browser adapter. */
function browserPage(html) {
    return html.replace(/style-src [^;"]*;/, "$& style-src-attr 'unsafe-inline';");
}

/** The shell page for a browser: the web scripts and stylesheet, and fetches to this server. */
function shellPage(html) {
    return html
        .replace("script-src 'self';", "script-src 'self'; connect-src 'self';")
        .replace('<script src="shell.js">',
            `${WEB_SCRIPTS.map((name) => `<script src="/web-host/${name}"></script>`).join('')}<script src="shell.js">`)
        .replace('<link rel="stylesheet" href="shell.css">', '<link rel="stylesheet" href="shell.css"><link rel="stylesheet" href="/web-host/web.css">')
        .replace('<head>', '<head><base href="/webview/shell/">');
}

/** Return an HTTP server and shell transport; reject cross-origin control requests. */
function createWebServer({ pages, onMessage, onDisconnect = () => {}, onAuthCallback = null }) {
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
        return reply(response, 200, body, TYPES[path.extname(target)] || 'application/octet-stream');
    }
    const server = http.createServer(async (request, response) => {
        response.setHeader('Cache-Control', 'no-store');
        response.setHeader('X-Content-Type-Options', 'nosniff');
        response.setHeader('Cross-Origin-Resource-Policy', 'same-origin');
        response.setHeader('Referrer-Policy', 'no-referrer');
        response.setHeader('Content-Security-Policy', "frame-ancestors 'self'");
        if (request.headers.host !== new URL(origin).host) {
            return reply(response, 403, 'Use the server URL printed at startup.');
        }
        // Sign-in comes back here from the sign-in provider's site, so it is the one page another site
        // may send the browser to. The code it carries is no use without what this server keeps.
        if (onAuthCallback && request.method === 'GET' && request.url.startsWith('/auth/callback')) {
            const { status, html } = await onAuthCallback(new URL(request.url, origin).search);
            return reply(response, status, html, TYPES['.html']);
        }
        if ((request.headers.origin && request.headers.origin !== origin)
            || request.headers['sec-fetch-site'] === 'cross-site') {
            return reply(response, 403, 'Use the server URL printed at startup.');
        }
        try {
            const url = new URL(request.url, origin);
            const pathname = decodeURIComponent(url.pathname);
            if (request.method === 'POST' && pathname === '/message') {
                if (request.headers.origin !== origin || !client || request.headers['x-kigumi-client'] !== client
                    || request.headers['content-type'] !== 'application/json') return reply(response, 403);
                let size = 0;
                const chunks = [];
                for await (const chunk of request) {
                    size += chunk.length;
                    if (size > MAX_MESSAGE_BYTES) {
                        return reply(response, 413, 'Message too large');
                    }
                    chunks.push(chunk);
                }
                let message;
                try {
                    message = JSON.parse(Buffer.concat(chunks).toString());
                } catch {
                    return reply(response, 400, 'Invalid JSON');
                }
                if (!message || typeof message.type !== 'string') return reply(response, 400);
                onMessage(message);
                return reply(response, 204);
            }
            if (request.method !== 'GET') return reply(response, 405);
            if (pathname === '/events') {
                const id = url.searchParams.get('client');
                if (!id || !/^[a-zA-Z0-9-]{1,80}$/.test(id)) return reply(response, 400);
                // The newest tab takes over: the one before is told, and its stream ends. Only one
                // tab at a time drives Kigumi; the old one offers to take it back.
                if (stream) {
                    const old = stream;
                    stream = null;
                    client = null;
                    old.write(`data: ${JSON.stringify({ type: 'web:takenOver' })}\n\n`);
                    old.end();
                }
                client = id;
                stream = response;
                response.writeHead(200, {
                    'Content-Type': 'text/event-stream', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no',
                });
                response.write(': connected\n\n');
                const heartbeat = setInterval(() => response.write(': heartbeat\n\n'), 15000);
                response.on('close', () => {
                    clearInterval(heartbeat);
                    // A tab taken over has already given way; only the current one's leaving matters.
                    if (stream !== response) return;
                    stream = null;
                    client = null;
                    onDisconnect();
                });
                return undefined;
            }
            if (pathname === '/' || pathname === '/webview/shell/shell.html') {
                const html = await fs.promises.readFile(path.join(webviewDir, 'shell/shell.html'), 'utf8');
                return reply(response, 200, shellPage(html), TYPES['.html']);
            }
            if (pathname.startsWith('/page/')) {
                const html = pages.get(pathname.slice('/page/'.length));
                return html === undefined ? reply(response, 404) : reply(response, 200, browserPage(html), TYPES['.html']);
            }
            if (pathname.startsWith('/webview/')) return await file(response, webviewDir, pathname.slice('/webview/'.length));
            if (pathname.startsWith('/web-host/') && WEB_FILES.has(pathname.slice('/web-host/'.length))) {
                return await file(response, __dirname, pathname.slice('/web-host/'.length));
            }
            return reply(response, 404);
        } catch (error) {
            return reply(response, error instanceof URIError ? 400 : 404);
        }
    });
    return {
        server,
        /** Whether a browser tab is connected. */
        get connected() { return Boolean(stream); },
        send(message) {
            if (stream && !stream.write(`data: ${JSON.stringify(message)}\n\n`)) {
                // End a stalled stream before geometry messages pile up without a bound.
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

/** The Python environment web projects share: `venv`, $KIGUMI_WEB_VENV, or this checkout's .venv. */
function sharedVenv(venv) {
    const candidate = venv || process.env.KIGUMI_WEB_VENV || path.resolve(KIGUMI_DIR, '..', '.venv');
    if (!fs.existsSync(candidate)) {
        throw new Error(`No Python environment at ${candidate}. Make one with kumiki installed, and pass it as --venv.`);
    }
    return fs.realpathSync(candidate);
}

/** A project's name as a folder name. */
function folderName(name) {
    return name.replace(/[^\w .-]+/g, '_').replace(/^[ ._]+|[ ._]+$/g, '') || 'project';
}

/** Make `dir` a project Kigumi can run: its .venv the shared one, and the project's marker files. */
function prepareProjectDir(dir, venv) {
    fs.mkdirSync(dir, { recursive: true });
    const link = path.join(dir, '.venv');
    if (!fs.existsSync(link)) {
        fs.symlinkSync(venv, link, 'dir');
    }
    ensureKigumiYaml(dir);
    const python = path.join(link, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python3');
    fs.writeFileSync(path.join(dir, '.kigumi', 'kigumi.yaml'), [
        'schema_version: 1',
        `project_root: '${dir.replace(/'/g, "''")}'`,
        `python_path: '${python.replace(/'/g, "''")}'`,
        `venv_path: '${link.replace(/'/g, "''")}'`,
        'local_dev: false',
        'web: true',
        '',
    ].join('\n'), 'utf8');
}

/**
 * Start the server. `dataDir` holds its settings, log and the open project's working folder; `venv`
 * is the shared Python environment (see sharedVenv).
 */
async function start({ port = 7346, dataDir = path.join(os.homedir(), '.kigumi', 'web'), venv = null } = {}) {
    const python = sharedVenv(venv);
    const projectsDir = path.join(dataDir, 'projects');
    fs.mkdirSync(projectsDir, { recursive: true });
    const settings = new SettingsStore(path.join(dataDir, 'settings.json'), {
        ...defaultsFromPackageJson(packageJson), 'viewer.autoRefreshOnFileChange': true,
    });
    const channel = new LogChannel(path.join(dataDir, 'logs', 'kigumi.log'));
    const log = (line) => channel.appendLine(line);
    const pages = new PageStore({ origin: '', webviewDir });
    let receive;
    let connection;
    let kigumiApp = null;
    let project = null; // { id, name, dir }
    let projectWatch = null;
    let status = null;
    let progress = null;
    let switching = Promise.resolve();

    const web = createWebServer({
        pages,
        onAuthCallback: (search) => finishSignIn(search),
        onMessage: (message) => receive && receive(message),
        onDisconnect: () => {
            // A fresh page cannot finish a quick pick the previous one opened.
            for (const pending of connection.pendingPicks.values()) pending.resolve(undefined);
            connection.pendingPicks.clear();
        },
    });
    const origin = await web.listen(port);

    function setStatus(level, message) {
        status = message ? { level, message } : null;
        connection.pushState();
    }
    function setProgress(title) {
        progress = title;
        connection.pushState();
    }
    async function runCommand(id, ...args) {
        try {
            const command = kigumiApp && kigumiApp.commands[id];
            if (!command) throw new Error(`Unknown command: ${id}`);
            return await command(...args);
        } catch (error) {
            log(`[web] ${error.stack || error}`);
            setStatus('error', error.message);
            return undefined;
        }
    }
    function openLog() {
        const existing = connection.findPanel((panel) => panel.type === 'log');
        if (existing) return existing.reveal();
        const panel = connection.createPanel('log', { title: 'Log' });
        const subscription = channel.onEntry((entry) => panel.postMessage({ type: 'logEntry', entry }));
        panel.onDispose(() => subscription.dispose());
        panel.onMessage((message) => {
            if (message && message.type === 'logReady') {
                panel.postMessage({ type: 'logEntries', entries: channel.entries, filePath: null });
            }
        });
        panel.loadUrl(`${origin}/webview/shell/log.html`);
        return undefined;
    }

    connection = new ShellConnection({
        transport: { send: web.send, onMessage: (callback) => { receive = callback; } },
        pages,
        status: () => ({
            workspace: project ? { name: project.name, path: project.name } : null,
            web: { projectId: project ? project.id : null },
            status,
            progress,
            version: `${packageJson.version} · web`,
            autoRefresh: settings.get('viewer.autoRefreshOnFileChange', true),
            agent: agentPanel.enabled(),
        }),
        onCommand: (id, ...args) => {
            void onCommand(id, ...args).catch((error) => {
                log(`[web] ${id} failed: ${error.stack || error}`);
                setStatus('error', error.message);
            });
        },
        closeRequest: (panelId) => editors.confirmClose(panelId),
    });
    const editors = createEditorTabs({
        connection,
        editorUrl: `${origin}/webview/editor/editor.html`,
        log,
        setStatus,
        askToSave: async (name) => {
            const picked = await connection.pick([{ label: 'Save' }, { label: "Don't Save" }, { label: 'Cancel' }],
                `Save the changes you made to ${name}?`);
            return picked ? { Save: 'save', "Don't Save": 'discard' }[picked.label] || 'cancel' : 'cancel';
        },
    });

    // The agent (agent/agent-panel.js), on the open project. Signing in to a Kigumi account comes back
    // to this server (/auth/callback), which must be one of the sign-in service's redirect URLs.
    let account = null;
    let modelList = null;
    let kumikiSource = null;
    let kumikiSourceFor = null;
    const projectDir = () => (project ? project.dir : null);
    function knownKumikiSource() {
        if (kumikiSourceFor !== projectDir()) {
            const asked = projectDir();
            kumikiSourceFor = asked;
            kumikiSource = null;
            if (asked) void findKumikiSource(asked).then((folder) => { if (kumikiSourceFor === asked) kumikiSource = folder; });
        }
        return kumikiSource;
    }
    // The open project's panels, for the agent, which outlives a project.
    const livePanels = new Proxy({}, {
        get(_target, key) {
            if (key === 'then') return undefined;
            const panels = kigumiApp && kigumiApp.panels;
            if (!panels) return typeof key === 'string' ? () => { throw new Error('No project is open.'); } : undefined;
            const value = panels[key];
            return typeof value === 'function' ? value.bind(panels) : value;
        },
    });
    function runToolCommand(id, args) {
        const handler = kigumiApp && kigumiApp.commands[id];
        if (!handler) throw new Error(`Kigumi has no command ${id}`);
        return handler(args);
    }
    function agentHost() {
        knownKumikiSource();
        return viewHost({
            panels: livePanels,
            run: runToolCommand,
            files: createProjectFiles({ root: projectDir, readOnly: () => [kumikiSource, kumikiExamples(kumikiSource)].filter(Boolean) }),
            workspaceFolders: () => (projectDir() ? [projectDir()] : []),
            kumikiApi: pythonKumikiApi({ python: () => projectPython(projectDir()), cwd: projectDir }),
            kumikiSource: knownKumikiSource,
            kumikiExamples: () => kumikiExamples(knownKumikiSource()),
            projects: webProjects,
            systemPrompt: loadSystemPrompt(),
        });
    }
    const memory = new Map();
    const agentPanel = createAgentPanel({
        connection,
        // ?host=web: the panel shows the web version's notice about running the agent.
        pageUrl: `${origin}/webview/agent/agent.html?host=web`,
        settings,
        makeHost: agentHost,
        prepare: () => {
            const config = backendConfig(process.env);
            if (!account) {
                account = createAccount({
                    ...config,
                    storage: { getItem: (key) => (memory.has(key) ? memory.get(key) : null),
                        setItem: (key, value) => memory.set(key, value), removeItem: (key) => memory.delete(key) },
                    redirectTo: `${origin}/auth/callback`,
                    openExternal: async (url) => connection.send({ type: 'browser:external', url }),
                    onChange: () => agentPanel.session && agentPanel.session.postState(),
                });
            }
            if (!modelList) {
                const file = path.join(dataDir, 'models.json');
                modelList = createModelList({
                    backendUrl: config.backendUrl,
                    storage: { load: () => JSON.parse(fs.readFileSync(file, 'utf8')),
                        save: (models) => fs.writeFileSync(file, JSON.stringify(models, null, 1)) },
                    onChange: () => agentPanel.session && agentPanel.session.postState(),
                });
            }
            return { account, models: modelList };
        },
        conversationsDir: path.join(dataDir, 'conversations'),
        locale: 'en',
        log,
    });

    // Kigumi's tools for agents on this machine (Claude Code and others), over MCP, as in the app.
    const mcp = createMcpService({
        settings,
        tools: () => sharedTools(agentHost()),
        version: packageJson.version,
        log,
        setStatus,
        copyText: (text) => connection.send({ type: 'browser:clipboard', text }),
    });

    // The agent's project tools (agent/project-tools.js), by name: the projects live in the browser,
    // which keeps the server told of them (`web:projects`) and opens one when asked (`web:requestOpen`).
    let knownProjects = [];
    const pendingOpens = new Map();
    function settleOpen(id, switched) {
        const resolve = pendingOpens.get(id);
        if (resolve) resolve(switched);
    }
    const kept = (switched, what) => {
        if (!switched) throw new Error(`The user kept the project open (an editor had unsaved changes), so ${what} did not happen.`);
    };
    const webProjects = {
        byName: true,
        current: () => (project ? project.name : null),
        recent: () => knownProjects.filter((one) => !project || one.id !== project.id).map((one) => one.name),
        async open(name) {
            const wanted = String(name).trim().toLowerCase();
            const found = knownProjects.find((one) => one.id === name) || knownProjects.find((one) => one.name.trim().toLowerCase() === wanted);
            if (!found) throw new Error(`This browser has no project named "${name}". list_projects lists them.`);
            if (project && project.id === found.id) return;
            if (!web.connected) throw new Error('No browser is connected to Kigumi, and the projects live in the browser.');
            const opened = new Promise((resolve) => pendingOpens.set(found.id, resolve));
            web.send({ type: 'web:requestOpen', id: found.id });
            let timer;
            const timedOut = new Promise((resolve) => { timer = setTimeout(() => resolve('timeout'), 30000); });
            const result = await Promise.race([opened, timedOut]);
            clearTimeout(timer);
            pendingOpens.delete(found.id);
            if (result === 'timeout') throw new Error(`The browser did not open "${found.name}" within 30 seconds.`);
            kept(result, `opening ${found.name}`);
        },
        async create(name) {
            const checked = checkProject({ id: require('crypto').randomUUID(), name: String(name) });
            kept(await switchProject(checked, { starter: true }), `making ${checked.name}`);
        },
        async close() {
            if (!project) throw new Error('No project is open.');
            kept(await switchProject(null), 'closing it');
        },
    };

    /** Finish signing in from where the sign-in page sent the browser back to; the page to show there. */
    async function finishSignIn(search) {
        const page = (title, text) => `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${title}</title>`
            + '<style>body{font:16px system-ui,sans-serif;display:grid;place-items:center;min-height:90vh;margin:0}'
            + 'main{max-width:420px;text-align:center}p{color:#6e6e73}</style></head>'
            + `<body><main><h1>${title}</h1><p>${text}</p></main></body></html>`;
        try {
            if (!account) throw new Error('Kigumi was restarted since sign-in began.');
            await account.completeSignIn(`kigumi://auth${search}`);
            log('[account] signed in');
            return { status: 200, html: page("You're signed in", 'Go back to the Kigumi tab. You can close this one.') };
        } catch (error) {
            log(`[account] sign-in failed: ${error.message}`);
            const text = String(error.message || error).replace(/[<>&"]/g, '');
            return { status: 400, html: page("Sign-in didn't finish", `${text}. Go back to Kigumi and try again.`) };
        }
    }

    /** The settings quick pick, the status bar's gear: the switches people look for. */
    async function chooseSetting() {
        const onOff = (key, fallback = false) => (settings.get(key, fallback) === true ? 'on' : 'off');
        const picked = await connection.pick([
            { label: `Agent panel: ${onOff('agent.enabled')}`, value: 'agent.enabled' },
            { label: `Auto refresh on file change: ${onOff('viewer.autoRefreshOnFileChange', true)}`, value: 'viewer.autoRefreshOnFileChange' },
            { label: `MCP server, for agents on this machine: ${onOff('mcp.enabled')}`, value: 'mcp.enabled' },
            ...(mcp.running ? [{ label: 'Copy MCP setup for Claude Code', value: 'copyMcpSetup' }] : []),
        ], 'Turn a setting on or off (kept in this browser)');
        if (picked && picked.value === 'copyMcpSetup') {
            mcp.copySetup('claude-code');
        } else if (picked && picked.value) {
            settings.set(picked.value, settings.get(picked.value, picked.value === 'viewer.autoRefreshOnFileChange') !== true);
        }
    }

    function sendProjectFiles(update) {
        if (project) web.send({ type: 'web:files', id: project.id, name: project.name, ...update });
    }

    function startKigumi() {
        setHost(createBrowserHost({
            connection, workspaceFolder: project ? project.dir : null, settings, runCommand, setStatus, setProgress,
            editors, showLog: openLog, log, agentPanel: true, mcp: mcp.controls,
        }));
        kigumiApp = createKigumiApp({ extensionPath: KIGUMI_DIR, storagePath: path.join(dataDir, 'tools'), channel });
        kigumiApp.sidebarController.attach(connection.createPanel('explorer', { title: 'Explorer' }));
    }

    /** Close the open project's tabs, asking about unsaved edits; false if the user kept one. */
    async function closeProjectTabs() {
        for (const id of editors.dirtyIds()) {
            const panel = connection.panels.get(id);
            if (panel) panel.reveal();
            if (!(await editors.confirmClose(id))) return false;
        }
        for (const panel of [...connection.panels.values()]) {
            if (panel.type !== 'log' && panel.type !== 'agent') panel.dispose();
        }
        return true;
    }

    /**
     * Open `next` ({ id, name, files? }) in place of the open project, or none. Its files are
     * written into a fresh working folder; with `starter`, a new project gets the starter frame.
     */
    function switchProject(next, { starter = false } = {}) {
        const run = async () => {
            if (!(await closeProjectTabs())) {
                if (next) settleOpen(next.id, false);
                return false;
            }
            if (projectWatch) projectWatch.dispose();
            projectWatch = null;
            const old = kigumiApp;
            kigumiApp = null;
            if (old) await old.dispose();
            project = null;
            if (next) {
                // Under its id, so names can repeat; named for the project, which is what shows.
                const home = path.join(projectsDir, next.id);
                const dir = path.join(home, folderName(next.name));
                fs.rmSync(home, { recursive: true, force: true });
                prepareProjectDir(dir, python);
                writeProjectFiles(dir, next.files || {});
                if (starter && !fs.existsSync(path.join(dir, 'my_cute_frame.py'))) {
                    fs.writeFileSync(path.join(dir, 'my_cute_frame.py'), getInlineExampleFrameContent(), 'utf8');
                }
                project = { id: next.id, name: next.name, dir };
                projectWatch = watchProjectFiles(dir, {
                    onFiles: (update) => sendProjectFiles(update),
                    onExport: (relative, filePath) => {
                        const size = fs.statSync(filePath).size;
                        if (size > MAX_DOWNLOAD_BYTES) {
                            setStatus('warning', `${path.basename(filePath)} is too large to download (${Math.round(size / 1048576)} MB).`);
                            return;
                        }
                        web.send({ type: 'browser:download', name: path.basename(relative),
                            base64: fs.readFileSync(filePath).toString('base64') });
                    },
                });
                log(`[web] Project: ${next.name} (${next.id})`);
            } else {
                log('[web] Project: (none)');
            }
            startKigumi();
            // The browser's copy takes whatever the working folder now has, e.g. the starter frame.
            if (project) sendProjectFiles({ full: true, files: readProjectFiles(project.dir) });
            connection.pushState();
            if (next) settleOpen(next.id, true);
            return true;
        };
        const done = switching.then(run, run);
        switching = done.catch(() => false);
        return done;
    }

    function checkProject({ id, name } = {}) {
        if (typeof id !== 'string' || !PROJECT_ID.test(id)) throw new Error('A project id is letters, digits and dashes.');
        if (typeof name !== 'string' || !name.trim() || name.length > 80) throw new Error('A project needs a name of up to 80 characters.');
        return { id, name: name.trim() };
    }

    function revealInExplorer(keys) {
        connection.setSideShown('left', true);
        return kigumiApp.sidebarController.reveal(keys).length > 0;
    }

    async function onCommand(id, ...args) {
        if (id === 'web:openProject') {
            const { files } = args[0] || {};
            await switchProject({ ...checkProject(args[0]), files });
        } else if (id === 'web:newProject') {
            await switchProject(checkProject(args[0]), { starter: true });
        } else if (id === 'web:closeProject' || id === 'openFolder') {
            await switchProject(null);
        } else if (id === 'run') {
            await runCommand(...args);
        } else if (id === 'browsePatterns') {
            if (project) revealInExplorer(['patterns-root', 'pattern-section:workspace-patternbooks', 'pattern-section:shipped-patterns']);
        } else if (id === 'browseExamples') {
            if (project && !revealInExplorer(['example-frames-root', 'library-frames:kumiki'])) {
                setStatus('info', 'No examples: the shared Python environment has no kumiki installed.');
            }
        } else if (id === 'openLog') {
            openLog();
        } else if (id === 'openSettings') {
            await chooseSetting();
        } else if (id === 'toggleAgent') {
            agentPanel.toggle();
        } else if (id === 'web:projects') {
            // The browser's list of its projects, which the agent's project tools go by.
            knownProjects = ((args[0] || {}).projects || [])
                .filter((one) => one && typeof one.id === 'string' && PROJECT_ID.test(one.id) && typeof one.name === 'string')
                .map(({ id: projectId, name }) => ({ id: projectId, name }));
        } else if (id === 'web:settings') {
            settings.replace((args[0] || {}).values);
        }
    }

    startKigumi();
    let agentWasEnabled = agentPanel.enabled();
    const subscription = settings.onChange(() => {
        // The browser keeps the settings: each change goes back to it.
        web.send({ type: 'web:settings', values: settings.values });
        agentPanel.closeIfDisabled();
        if (agentPanel.enabled() && !agentWasEnabled) agentPanel.toggle();
        agentWasEnabled = agentPanel.enabled();
        connection.pushState();
        void mcp.sync();
    });
    void mcp.sync();
    return {
        origin,
        connection,
        get app() { return kigumiApp; },
        get project() { return project; },
        settings,
        mcp,
        switchProject,
        async close() {
            subscription.dispose();
            agentPanel.stop();
            await mcp.close();
            if (projectWatch) projectWatch.dispose();
            await web.close();
            connection.dispose();
            if (kigumiApp) await kigumiApp.dispose();
            settings.dispose();
        },
    };
}

function parseArgs(argv) {
    const options = {};
    for (let i = 0; i < argv.length; i++) {
        if (argv[i] === '--venv') options.venv = path.resolve(argv[++i]);
        else if (argv[i] === '--data') options.dataDir = path.resolve(argv[++i]);
        else if (argv[i] === '--port') options.port = Number(argv[++i]);
    }
    if (!options.port && process.env.PORT) options.port = Number(process.env.PORT);
    return options;
}

if (require.main === module) {
    start(parseArgs(process.argv.slice(2)))
        .then((running) => {
            console.log(`Kigumi web: ${running.origin}`);
            console.log('One browser tab at a time. Press Ctrl+C to stop.');
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
        .catch((error) => {
            console.error(error.message || error);
            process.exitCode = 1;
        });
}

module.exports = { createWebServer, start, browserPage, shellPage, prepareProjectDir };
