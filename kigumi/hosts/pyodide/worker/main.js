/**
 * Kigumi in a browser, with nothing on a server: this Web Worker runs Kigumi's core (bundled by
 * ../build.mjs) and Python in Pyodide, and the page (../page/) shows the app's shell, explorer,
 * viewers and editor on top of it.
 *
 * Where the core expects Node, the stand-ins in ./shims/ work through Pyodide: files are Pyodide's
 * (in memory), and Python "processes" run in it (../python/kigumi_pyodide.py). The page holds the
 * projects (IndexedDB) and the settings (localStorage); the open project is written into Pyodide's
 * files, and every change made there goes back to the page.
 */

const path = require('path');
const fs = require('fs');
const runtime = require('./shims/runtime');
const { PageStore, injectBridge } = require('../../../app-shell/page-store');
const { ShellConnection, PanelSurface } = require('../../../app-shell/shell-connection');
const { createEditorTabs } = require('../../../app-shell/editor-tabs');
const { webviewDir } = require('../../../webview-html');
const { setHost } = require('../../../host');
const { createKigumiApp } = require('../../../kigumi-app');
const { ensureKigumiYaml } = require('../../../project-root');
const { getInlineExampleFrameContent } = require('../../../project-initializer');
const { SettingsStore, defaultsFromPackageJson } = require('../../electron/settings-store');
const { LogChannel } = require('../../electron/log-channel');
const { createBrowserHost } = require('../browser-host');
const { writeProjectFiles, readProjectFiles, watchProjectFiles } = require('../project-files');
const { createAgentPanel } = require('../../../agent/agent-panel');
const { createProjectFiles } = require('../../../agent/project-files');
const { createAccount } = require('../../../agent/account');
const { backendConfig } = require('../../../agent/backend-config');
const { createMcpRelay } = require('../../../agent/mcp-relay');
const browserBackend = backendConfig(typeof KIGUMI_WEB_BACKEND_CONFIG === 'undefined' ? {} : KIGUMI_WEB_BACKEND_CONFIG);
const { createModelList } = require('../../../agent/models');
const { findKumikiSource, kumikiExamples, projectPython } = require('../../../agent/kumiki-source');
const { pythonKumikiApi } = require('../../../agent/kumiki-api');
const { loadSystemPrompt } = require('../../../agent/system-prompt');
const { viewHost, sharedTools } = require('../../../agent/agent');
const { createFileTools } = require('../../../agent/file-tools');

const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.28.3/full/';
const MANIFOLD_URL = 'https://cdn.jsdelivr.net/npm/manifold-3d@3.5.4/manifold.js';
// kumiki's dependencies: Pyodide's own, and trimesh (pure Python) from PyPI.
const PYODIDE_PACKAGES = ['numpy', 'sympy', 'lxml', 'networkx', 'scipy', 'typing-extensions', 'micropip'];
const PYPI_PACKAGES = ['trimesh==4.11.3'];

const HOME = '/home/pyodide';
const DATA = `${HOME}/kigumi`;
const PROJECTS = `${HOME}/projects`;
const PROJECT_ID = /^[a-zA-Z0-9-]{1,64}$/;
const MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024;
const BASE = new URL('.', self.location.href).href.replace(/\/$/, '');

const post = (message) => self.postMessage(message);
// `step` is the start-up step (page/loading.js STEPS); `detail` a package as it loads.
const status = (text, step, detail) => post({ type: 'web:loading', text, step, detail });

/** Load Pyodide, kumiki and its packages, Manifold, and Kigumi's own files. */
async function bootPython() {
    status('Loading Python…', 0);
    const { loadPyodide } = await import(/* webpackIgnore: true */ `${PYODIDE_URL}pyodide.mjs`);
    const py = await loadPyodide({ indexURL: PYODIDE_URL, env: { HOME } });
    status('Loading kumiki’s packages…', 1);
    await py.loadPackage(PYODIDE_PACKAGES, {
        messageCallback: (message) => {
            if (/^Loaded /.test(message)) status(null, 1, String(message).replace(/\s+from\s.*$/, ''));
        },
    });
    const micropip = py.pyimport('micropip');
    status(null, 1, `Installing ${PYPI_PACKAGES.join(', ')}`);
    await micropip.install(PYPI_PACKAGES);
    status('Loading kumiki…', 2, '');
    const manifest = await (await fetch(`${BASE}/manifest.json`)).json();
    await py.runPythonAsync(`import micropip\nawait micropip.install(${JSON.stringify(`${BASE}/${manifest.wheel}`)}, deps=False)`);
    const Manifold = (await import(/* webpackIgnore: true */ MANIFOLD_URL)).default;
    const wasm = await Manifold();
    wasm.setup();
    py.registerJsModule('_manifold_wasm', { Manifold: wasm.Manifold, Mesh: wasm.Mesh });
    const sitePackages = py.runPython('import site; site.getsitepackages()[0]');
    const files = await (await fetch(`${BASE}/kigumi-files.json`)).json();
    for (const [file, text] of Object.entries(files)) {
        py.FS.mkdirTree(path.dirname(file));
        py.FS.writeFile(file, text);
    }
    py.FS.writeFile(`${sitePackages}/manifold3d.py`, files['/python/manifold3d.py']);
    py.FS.writeFile(`${sitePackages}/kigumi_pyodide.py`, files['/python/kigumi_pyodide.py']);
    for (const dir of [DATA, PROJECTS]) py.FS.mkdirTree(dir);
    runtime.py = py;
    return py;
}

/** Write a project's stand-in .venv (the core looks for its python) and its marker files. */
function prepareProjectDir(dir) {
    fs.mkdirSync(path.join(dir, '.venv', 'bin'), { recursive: true });
    for (const name of ['python3', 'python']) fs.writeFileSync(path.join(dir, '.venv', 'bin', name), '#!pyodide\n');
    ensureKigumiYaml(dir);
    fs.writeFileSync(path.join(dir, '.kigumi', 'kigumi.yaml'), [
        'schema_version: 1',
        `project_root: '${dir}'`,
        `python_path: '${dir}/.venv/bin/python3'`,
        `venv_path: '${dir}/.venv'`,
        'local_dev: false',
        'browser: true',
        '',
    ].join('\n'));
}

function folderName(name) {
    return name.replace(/[^\w .-]+/g, '_').replace(/^[ ._]+|[ ._]+$/g, '') || 'project';
}

async function start() {
    const queued = [];
    let receive = (message) => queued.push(message);
    let onAuthLink = (url) => queued.push({ authLink: url });
    let runTestTool = null;
    self.onmessage = (event) => {
        // For the browser test (test/browser-smoke.cjs): a file changed as an editor save would.
        if (event.data && event.data.type === 'test:appendToFile') {
            fs.appendFileSync(event.data.file, event.data.text);
            return;
        }
        // For the browser test: run one of the agent's tools, as a model's call would.
        if (event.data && event.data.type === 'test:agentTool' && runTestTool) {
            runTestTool(event.data);
            return;
        }
        // Sign-in came back (page/auth.html): finish it.
        if (event.data && event.data.type === 'web:authLink') {
            onAuthLink(String(event.data.url));
            return;
        }
        receive(event.data);
    };

    await bootPython();
    status('Starting Kigumi…', 3, '');

    const packageJson = JSON.parse(fs.readFileSync('/kigumi/package.json', 'utf8'));
    const settings = new SettingsStore(`${DATA}/settings.json`, {
        ...defaultsFromPackageJson(packageJson), 'viewer.autoRefreshOnFileChange': true,
        // On here, unlike the standalone app: the browser has no other agent to reach Kigumi with.
        'agent.enabled': true,
    });
    const channel = new LogChannel(`${DATA}/logs/kigumi.log`);
    const log = (line) => channel.appendLine(line);

    // Panel pages go to the page, which shows each as a blob: there is no server to fetch them from.
    class BlobPageStore extends PageStore {
        serve(html) {
            const id = String(this.nextId++);
            const page = injectBridge(html).replace(`src="/webview/shell/panel-bridge.js"`, `src="${BASE}/webview/shell/panel-bridge.js"`);
            this.pages.set(id, page);
            post({ type: 'web:page', id, html: page });
            return `kigumi-page:${id}`;
        }

        release(url) {
            if (url && url.startsWith('kigumi-page:')) {
                this.pages.delete(url.slice('kigumi-page:'.length));
                post({ type: 'web:releasePage', id: url.slice('kigumi-page:'.length) });
            }
        }
    }
    const pages = new BlobPageStore({ origin: BASE, webviewDir });
    // Pages' security policies name where their scripts come from: this site, whatever its path.
    Object.defineProperty(PanelSurface.prototype, 'cspSource', { get: () => self.location.origin });

    let connection;
    let kigumiApp = null;
    let project = null; // { id, name, dir }
    let projectWatch = null;
    let shown = null;
    let progress = null;
    let switching = Promise.resolve();
    let knownProjects = [];

    function setStatus(level, message) {
        shown = message ? { level, message } : null;
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
            if (message && message.type === 'logReady') panel.postMessage({ type: 'logEntries', entries: channel.entries, filePath: null });
        });
        panel.loadUrl(`${BASE}/webview/shell/log.html`);
        return undefined;
    }

    connection = new ShellConnection({
        transport: { send: post, onMessage: (callback) => { receive = callback; } },
        pages,
        status: () => ({
            workspace: project ? { name: project.name, path: project.name } : null,
            web: { projectId: project ? project.id : null },
            status: shown,
            progress,
            version: `${packageJson.version} · browser`,
            autoRefresh: settings.get('viewer.autoRefreshOnFileChange', true),
            agent: agentEnabled(),
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
        editorUrl: `${BASE}/webview/editor/editor.html`,
        log,
        setStatus,
        askToSave: async (name) => {
            const picked = await connection.pick([{ label: 'Save' }, { label: "Don't Save" }, { label: 'Cancel' }],
                `Save the changes you made to ${name}?`);
            return picked ? { Save: 'save', "Don't Save": 'discard' }[picked.label] || 'cancel' : 'cancel';
        },
    });

    function sendProjectFiles(update) {
        if (project) post({ type: 'web:files', id: project.id, name: project.name, ...update });
    }

    function startKigumi() {
        setHost(createBrowserHost({
            connection, workspaceFolder: project ? project.dir : null, settings, runCommand, setStatus, setProgress,
            editors, showLog: openLog, log, mcp: mcp.controls, closeProject: () => switchProject(null), agentPanel: true,
            projects: {
                open: () => pickProject(),
                recent: () => knownProjects.map((one) => ({ id: one.id, label: one.name, description: 'In this browser' })),
                openRecent: async (id) => post({ type: 'web:requestOpen', id }),
            },
        }));
        kigumiApp = createKigumiApp({ extensionPath: '/kigumi', storagePath: `${DATA}/tools`, channel });
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
            if (!PANELS_KEPT_ACROSS_PROJECTS.has(panel.type)) panel.dispose();
        }
        return true;
    }

    /** Open `next` ({ id, name, files? }) in place of the open project, or none. */
    function switchProject(next, { starter = false } = {}) {
        const run = async () => {
            if (!(await closeProjectTabs())) return false;
            if (projectWatch) projectWatch.dispose();
            projectWatch = null;
            const old = kigumiApp;
            kigumiApp = null;
            if (old) await old.dispose();
            project = null;
            if (next) {
                const home = path.join(PROJECTS, next.id);
                const dir = path.join(home, folderName(next.name));
                fs.rmSync(home, { recursive: true, force: true });
                fs.mkdirSync(dir, { recursive: true });
                prepareProjectDir(dir);
                writeProjectFiles(dir, next.files || {});
                if (starter && !fs.existsSync(path.join(dir, 'my_cute_frame.py'))) {
                    fs.writeFileSync(path.join(dir, 'my_cute_frame.py'), getInlineExampleFrameContent());
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
                        post({ type: 'browser:download', name: path.basename(relative), base64: fs.readFileSync(filePath).toString('base64') });
                    },
                });
                log(`[web] Project: ${next.name} (${next.id})`);
            } else {
                log('[web] Project: (none)');
            }
            startKigumi();
            if (project) sendProjectFiles({ full: true, files: readProjectFiles(project.dir) });
            connection.pushState();
            return true;
        };
        const done = switching.then(run, run);
        switching = done.catch(() => false);
        return done;
    }

    /** Project status's Open Project: one of the projects kept in this browser. */
    async function pickProject() {
        if (knownProjects.length === 0) {
            setStatus('info', 'No projects yet: make one with New Project.');
            return;
        }
        const picked = await connection.pick(knownProjects.map((one) => ({ label: one.name, value: one.id })), 'Open a project kept in this browser');
        if (picked && picked.value) post({ type: 'web:requestOpen', id: picked.value });
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

    /** The settings quick pick, the status bar's gear. */
    async function chooseSetting() {
        const onOff = (key, fallback = false) => (settings.get(key, fallback) === true ? 'on' : 'off');
        const picked = await connection.pick([
            { label: `Auto refresh on file change: ${onOff('viewer.autoRefreshOnFileChange', true)}`, value: 'viewer.autoRefreshOnFileChange' },
            { label: `Drawings (beta): ${onOff('viewer.drawingBeta')}`, value: 'viewer.drawingBeta' },
        ], 'Turn a setting on or off (kept in this browser)');
        if (picked && picked.value) {
            settings.set(picked.value, settings.get(picked.value, picked.value === 'viewer.autoRefreshOnFileChange') !== true);
        }
    }

    // The agent: as the standalone app's (hosts/electron/main.js), its requests sent from here.
    const PANELS_KEPT_ACROSS_PROJECTS = new Set(['agent', 'log']);
    const agentEnabled = () => settings.get('agent.enabled', false) === true;
    // What the page keeps for the account and the model list (localStorage), as web:store.
    const stored = {};
    const store = {
        getItem: (key) => (key in stored ? stored[key] : null),
        setItem: (key, value) => { stored[key] = String(value); post({ type: 'web:store', values: { ...stored } }); },
        removeItem: (key) => { delete stored[key]; post({ type: 'web:store', values: { ...stored } }); },
    };
    let account = null;
    let modelList = null;
    let agentPanel = null;

    function prepareAgent() {
        const config = browserBackend;
        if (!account) {
            account = createAccount({
                ...config,
                storage: store,
                // page/auth.html hands the code back to this page (web:authLink).
                redirectTo: new URL('auth.html', `${BASE}/`).href,
                openExternal: (url) => post({ type: 'browser:signIn', url }),
                onChange: () => {
                    if (agentPanel && agentPanel.session) agentPanel.session.postState();
                    setTimeout(() => {
                        if (!account.state().signedIn && settings.get('mcp.enabled', false)) settings.set('mcp.enabled', false);
                        else void mcp.sync();
                    }, 0);
                },
            });
        }
        if (!modelList) {
            modelList = createModelList({
                backendUrl: config.backendUrl,
                storage: {
                    load: () => JSON.parse(store.getItem('kigumi.models')),
                    save: (models) => store.setItem('kigumi.models', JSON.stringify(models)),
                },
                onChange: () => agentPanel && agentPanel.session && agentPanel.session.postState(),
            });
        }
        return { account, models: modelList };
    }

    onAuthLink = (url) => {
        log('[account] sign-in link received');
        prepareAgent();
        account.completeSignIn(url).then(() => log('[account] signed in')).catch((error) => {
            log(`[account] sign-in failed: ${error.message}`);
            setStatus('error', `Could not sign in: ${error.message}`);
        });
    };

    // The kumiki library's source, which the agent may read: inside Pyodide's site-packages.
    let kumikiSource = null;
    let kumikiSourceFor = null;
    function knownKumikiSource() {
        const dir = project ? project.dir : null;
        if (kumikiSourceFor !== dir) {
            kumikiSourceFor = dir;
            kumikiSource = null;
            void findKumikiSource(dir).then((folder) => {
                if (kumikiSourceFor === dir) kumikiSource = folder;
            });
        }
        return kumikiSource;
    }

    // The open project's panels, for the agent, which outlives a project.
    const livePanels = new Proxy({}, {
        get(_target, key) {
            const panels = kigumiApp && kigumiApp.panels;
            if (key === 'then') return undefined;
            if (!panels) return typeof key === 'string' ? () => { throw new Error('No project is open.'); } : undefined;
            const value = panels[key];
            return typeof value === 'function' ? value.bind(panels) : value;
        },
    });

    /** Wait until the project `id` is the one open; the page opens it (web:requestOpen). */
    async function projectOpened(id) {
        for (let waited = 0; waited < 60000; waited += 100) {
            if (project && project.id === id) return;
            await new Promise((resolve) => setTimeout(resolve, 100));
        }
        throw new Error('The project did not open.');
    }

    /** The agent's project tools here: projects by name, kept in this browser. */
    function agentProjects() {
        const done = (switched, what) => {
            if (!switched) throw new Error(`The user kept the project open (an editor had unsaved changes), so ${what} did not happen.`);
        };
        const named = (name) => knownProjects.find((one) => one.name === name)
            || knownProjects.find((one) => one.name.toLowerCase() === String(name).trim().toLowerCase());
        return {
            byName: true,
            current: () => (project ? project.name : null),
            recent: () => knownProjects.map((one) => one.name),
            open: async (name) => {
                const found = named(name);
                if (!found) throw new Error(`No project is named ${name}. list_projects lists them.`);
                if (project && project.id === found.id) return;
                post({ type: 'web:requestOpen', id: found.id });
                await projectOpened(found.id);
            },
            create: async (name) => {
                done(await switchProject(checkProject({ id: crypto.randomUUID(), name: String(name) }), { starter: true }), `making ${name}`);
            },
            close: async () => {
                if (!project) throw new Error('No project is open.');
                done(await switchProject(null), 'closing it');
            },
        };
    }

    function runToolCommand(id, args) {
        const handler = kigumiApp && kigumiApp.commands[id];
        if (!handler) throw new Error(`Kigumi has no command ${id}`);
        return handler(args);
    }

    function agentHost() {
        knownKumikiSource();
        const files = createProjectFiles({ root: () => (project ? project.dir : null),
            readOnly: () => [kumikiSource, kumikiExamples(kumikiSource)].filter(Boolean) });
        return viewHost({
            panels: livePanels,
            run: runToolCommand,
            files,
            workspaceFolders: () => (project ? [project.dir] : []),
            kumikiApi: pythonKumikiApi({ python: () => projectPython(project && project.dir), cwd: () => project && project.dir }),
            kumikiSource: knownKumikiSource,
            kumikiExamples: () => kumikiExamples(knownKumikiSource()),
            systemPrompt: loadSystemPrompt(),
            projects: agentProjects(),
        });
    }

    runTestTool = ({ id, name, input }) => {
        const host = agentHost();
        const tool = [...sharedTools(host), ...createFileTools({ files: host.files })].find((one) => one.name === name);
        Promise.resolve().then(() => tool.run(input || {})).then(
            (result) => post({ type: 'test:agentToolResult', id, result }),
            (error) => post({ type: 'test:agentToolResult', id, error: String(error && error.message || error) }));
    };

    agentPanel = createAgentPanel({
        connection,
        pageUrl: `${BASE}/webview/agent/agent.html?host=web`,
        settings,
        makeHost: agentHost,
        prepare: prepareAgent,
        conversationsDir: `${DATA}/conversations`,
        locale: (self.navigator && self.navigator.language) || 'en',
        log,
    });

    async function onCommand(id, ...args) {
        if (id === 'web:openProject') {
            const { files } = args[0] || {};
            await switchProject({ ...checkProject(args[0]), files });
        } else if (id === 'web:newProject') {
            await switchProject(checkProject(args[0]), { starter: true });
        } else if (id === 'web:closeProject' || id === 'openFolder') {
            await switchProject(null);
        } else if (id === 'web:projects') {
            knownProjects = ((args[0] || {}).projects || []).filter((one) => one && PROJECT_ID.test(one.id));
            // With none open, Project status lists them.
            if (!project && kigumiApp) await runCommand('kigumi.refreshSidebar');
        } else if (id === 'web:settings') {
            settings.replace((args[0] || {}).values);
        } else if (id === 'web:store') {
            Object.assign(stored, (args[0] || {}).values);
        } else if (id === 'toggleAgent') {
            agentPanel.toggle();
        } else if (id === 'run') {
            await runCommand(...args);
        } else if (id === 'browsePatterns') {
            if (project) revealInExplorer(['patterns-root', 'pattern-section:workspace-patternbooks', 'pattern-section:shipped-patterns']);
        } else if (id === 'browseExamples') {
            if (project && !revealInExplorer(['example-frames-root', 'library-frames:kumiki'])) {
                setStatus('info', 'No examples were found in kumiki.');
            }
        } else if (id === 'openLog') {
            openLog();
        } else if (id === 'openSettings') {
            await chooseSetting();
        }
    }

    const mcp = createMcpRelay({
        settings, storage: store, account: () => prepareAgent().account, backendUrl: browserBackend.backendUrl,
        tools: () => sharedTools(agentHost()), setStatus,
        copyText: (text) => post({ type: 'browser:clipboard', text }),
    });
    startKigumi();
    // Not opened on the settings arriving at start: showOnStartup decides that, below.
    let agentWasEnabled = true;
    let mcpReady = false;
    settings.onChange(() => {
        // The page keeps the settings: each change goes back to it.
        post({ type: 'web:settings', values: settings.values });
        if (mcpReady) void mcp.sync();
        agentPanel.closeIfDisabled();
        // Turned on just now: show it, rather than leave the user to find its button.
        if (agentEnabled() && !agentWasEnabled) agentPanel.toggle();
        agentWasEnabled = agentEnabled();
        connection.pushState();
    });
    post({ type: 'web:ready' });
    for (const message of queued.splice(0)) {
        if (message.authLink) onAuthLink(message.authLink);
        else receive(message);
    }
    mcpReady = true;
    void mcp.sync();
    agentWasEnabled = agentEnabled();
    if (agentEnabled() && settings.get('agent.showOnStartup', true)) agentPanel.toggle();
    self.__kigumi = { connection, settings, get project() { return project; }, get app() { return kigumiApp; }, switchProject, knownProjects: () => knownProjects };
}

start().catch((error) => {
    console.error(error);
    post({ type: 'web:failed', message: String(error && error.stack || error) });
});
