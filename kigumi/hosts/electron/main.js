/**
 * Entry point of the standalone Kigumi app (Electron main process).
 *
 * Usage: electron hosts/electron/main.js [project-folder]
 */

const fs = require('fs');
const path = require('path');
const { app, protocol, Menu, dialog, shell: electronShell } = require('electron');
const { setHost } = require('../../host');
const { createKigumiApp } = require('../../kigumi-app');
const { DEFAULT_FILES_EXCLUDE } = require('../../sidebar-files');
const { webviewDir } = require('../../webview-html');
const { ShellConnection } = require('../../app-shell/shell-connection');
const { PageStore } = require('../../app-shell/page-store');
const { createAppWindow } = require('./app-window');
const { createElectronHost } = require('./electron-host');
const { SettingsStore, defaultsFromPackageJson } = require('./settings-store');
const { LogChannel } = require('./log-channel');
const { AgentSession } = require('../../agent/agent-session');
const { createKigumiTools } = require('../../agent/tools');
const { startMcpHttpServer, claudeCodeAddCommand, newToken } = require('../../agent/mcp-http');

const KIGUMI_DIR = path.join(__dirname, '..', '..');
const ORIGIN = 'kigumi://app';
const packageJson = JSON.parse(fs.readFileSync(path.join(KIGUMI_DIR, 'package.json'), 'utf8'));
const STATUS_CLEAR_MS = 10000;

// Where the app's defaults differ from the extension's, plus app-only settings.
// Auto refresh is on because the app has no editor whose unsaved state matters.
const APP_DEFAULTS = {
    'viewer.autoRefreshOnFileChange': true,
    'app.editorCommand': '',
    // Names the explorer's "All files" leaves out; `*` matches anything.
    'app.filesExclude': [...DEFAULT_FILES_EXCLUDE],
    // The agent panel. With no key it uses the Claude login on this machine, if there is one.
    'agent.apiKey': '',
    'agent.model': '',
    // Kigumi's tools for any agent, over MCP on this machine only. See agent/mcp-http.js.
    'mcp.enabled': false,
    'mcp.port': 7345,
    'mcp.token': '',
};

const CONTENT_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json',
    '.ttf': 'font/ttf',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
};

app.setName('Kigumi');
app.setPath('userData', process.env.KIGUMI_USER_DATA || path.join(app.getPath('appData'), 'Kigumi'));
protocol.registerSchemesAsPrivileged([
    { scheme: 'kigumi', privileges: { standard: true, secure: true, supportFetchAPI: true } },
]);

let mainWindow = null;
let connection = null;
let pages = null;
let kigumiApp = null;
let settings = null;
let logChannel = null;
let workspaceFolder = null;
const status = { message: null, level: 'info', progress: null, logBadge: false };
let statusTimer = null;

function notFound() {
    return new Response('Not found', { status: 404 });
}

async function serveFrom(root, relativeParts) {
    const filePath = path.resolve(root, ...relativeParts.map(decodeURIComponent));
    if (filePath !== root && !filePath.startsWith(root + path.sep)) {
        return notFound();
    }
    try {
        const body = await fs.promises.readFile(filePath);
        return new Response(body, {
            headers: { 'content-type': CONTENT_TYPES[path.extname(filePath).toLowerCase()] || 'application/octet-stream' },
        });
    } catch (_error) {
        return notFound();
    }
}

function handleProtocol(request) {
    const url = new URL(request.url);
    if (url.host !== 'app') {
        return notFound();
    }
    const [area, ...rest] = url.pathname.slice(1).split('/');
    if (area === 'page') {
        const html = pages && pages.get(rest[0]);
        return html === undefined
            ? notFound()
            : new Response(html, { headers: { 'content-type': CONTENT_TYPES['.html'] } });
    }
    if (area === 'webview') return serveFrom(webviewDir, rest);
    return notFound();
}

// The uv packaged into the app's resources by scripts/fetch-uv.js, if any.
function bundledUvPath() {
    if (!app.isPackaged) return null;
    const candidate = path.join(process.resourcesPath, 'uv', process.platform === 'win32' ? 'uv.exe' : 'uv');
    return fs.existsSync(candidate) ? candidate : null;
}

// A folder given on the command line, else the last one opened.
function cliFolder() {
    const args = process.argv.slice(app.isPackaged ? 1 : 2).filter((arg) => !arg.startsWith('-'));
    const candidate = args.find((arg) => fs.existsSync(arg) && fs.statSync(arg).isDirectory());
    return candidate ? path.resolve(candidate) : null;
}

function resolveWorkspaceFolder() {
    const fromCli = cliFolder();
    if (fromCli) return fromCli;
    const remembered = settings.get('app.workspaceFolder', null);
    return remembered && fs.existsSync(remembered) ? remembered : null;
}

function shellStatus() {
    return {
        workspace: workspaceFolder ? { name: path.basename(workspaceFolder), path: workspaceFolder } : null,
        status: status.message ? { level: status.level, message: status.message } : null,
        progress: status.progress,
        logBadge: status.logBadge,
        version: packageJson.version,
        autoRefresh: settings ? settings.get('viewer.autoRefreshOnFileChange', false) : false,
    };
}

function pushShellState() {
    if (connection) connection.pushState();
}

function setStatus(level, message) {
    status.level = level;
    status.message = message;
    if (level === 'error' || level === 'warning') {
        status.logBadge = true;
    }
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => {
        status.message = null;
        pushShellState();
    }, STATUS_CLEAR_MS);
    pushShellState();
}

function setProgress(title) {
    status.progress = title;
    pushShellState();
}

async function runAppCommand(id, ...args) {
    const handler = kigumiApp && kigumiApp.commands[id];
    if (!handler) {
        logChannel.appendLine(`[app] Unknown command ${id}`);
        return undefined;
    }
    try {
        return await handler(...args);
    } catch (error) {
        logChannel.appendLine(`[app] ${id} failed: ${error.stack || error}`);
        setStatus('error', `${id} failed: ${error.message || error}`);
        return undefined;
    }
}

async function chooseWorkspaceFolder() {
    const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
        title: 'Open Kigumi Project Folder',
        properties: ['openDirectory', 'createDirectory'],
    });
    if (canceled || filePaths.length === 0 || filePaths[0] === workspaceFolder) {
        return;
    }
    settings.set('app.workspaceFolder', filePaths[0]);
    // Sessions, watchers and the explorer are all rooted in the folder, so start over.
    const cli = cliFolder();
    app.relaunch({ args: process.argv.slice(1).filter((arg) => !cli || path.resolve(arg) !== cli) });
    app.exit(0);
}

async function chooseFrameFile() {
    const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
        title: 'Open Frame File',
        defaultPath: workspaceFolder || undefined,
        properties: ['openFile'],
        filters: [{ name: 'Python', extensions: ['py'] }],
    });
    if (!canceled && filePaths.length > 0) {
        await runAppCommand('kigumi.openFrameFromSidebar', filePaths[0]);
    }
}

function openLogTab() {
    status.logBadge = false;
    const existing = connection.findPanel((panel) => panel.type === 'log');
    if (existing) {
        existing.reveal();
        return;
    }
    const surface = connection.createPanel('log', { title: 'Log' });
    const subscription = logChannel.onLine((line) => {
        void surface.postMessage({ type: 'logLine', line });
    });
    surface.onMessage((message) => {
        if (message && message.type === 'logReady') {
            void surface.postMessage({ type: 'logLines', lines: logChannel.lines, filePath: logChannel.filePath });
        } else if (message && message.type === 'openLogFile') {
            void electronShell.openPath(logChannel.filePath);
        }
    });
    surface.onDispose(() => subscription.dispose());
    surface.loadUrl(`${ORIGIN}/webview/shell/log.html`);
}

// Editor tabs by panel id: whether each has unsaved edits, and how to ask it for them.
const editorTabs = new Map();

function openEditorTab(filePath, line = 1) {
    const existing = connection.findPanel((panel) => panel.type === 'editor' && panel.filePath === filePath);
    if (existing) {
        existing.reveal();
        if (line > 1) {
            void existing.postMessage({ type: 'revealLine', line });
        }
        return existing;
    }

    let fileContent = '';
    try {
        fileContent = fs.readFileSync(filePath, 'utf8');
    } catch (error) {
        logChannel.appendLine(`[editor] Failed to read ${filePath}: ${error.message}`);
        setStatus('error', `Cannot open ${path.basename(filePath)}: ${error.message}`);
        return null;
    }

    const baseName = path.basename(filePath);
    const surface = connection.createPanel('editor', { title: baseName, filePath });
    const pendingContent = new Map();
    let nextRequest = 1;
    const tab = {
        name: baseName,
        isDirty: false,
        // What the editor holds now, unsaved edits included.
        content() {
            const requestId = nextRequest++;
            return new Promise((resolve, reject) => {
                const timer = setTimeout(() => {
                    pendingContent.delete(requestId);
                    reject(new Error(`${baseName} did not answer`));
                }, 3000);
                pendingContent.set(requestId, (content) => {
                    clearTimeout(timer);
                    resolve(content);
                });
                void surface.postMessage({ type: 'getContent', requestId });
            });
        },
        save(content) {
            fs.writeFileSync(filePath, content, 'utf8');
            fileContent = content;
            tab.isDirty = false;
            surface.title = baseName;
            void surface.postMessage({ type: 'saved' });
        },
    };
    editorTabs.set(surface.id, tab);

    surface.onMessage(async (message) => {
        if (!message) return;
        if (message.type === 'editorReady') {
            void surface.postMessage({ type: 'init', filePath, content: fileContent, line });
        } else if (message.type === 'editorDirty') {
            tab.isDirty = !!message.isDirty;
            surface.title = tab.isDirty ? `● ${baseName}` : baseName;
        } else if (message.type === 'editorContent') {
            const resolve = pendingContent.get(message.requestId);
            pendingContent.delete(message.requestId);
            if (resolve) resolve(message.content);
        } else if (message.type === 'editorSave') {
            try {
                tab.save(message.content);
            } catch (error) {
                setStatus('error', `Failed to save ${baseName}: ${error.message}`);
            }
        }
    });

    // Changes made elsewhere -- another editor, an agent -- come into the tab. Polled: an editor
    // that saves by renaming the file would leave an fs.watch watching nothing.
    const onDiskChange = () => {
        let content;
        try {
            content = fs.readFileSync(filePath, 'utf8');
        } catch {
            return;
        }
        if (content === fileContent) {
            return; // our own save, or nothing that matters
        }
        fileContent = content;
        if (tab.isDirty) {
            setStatus('warning', `${baseName} changed on disk; the tab keeps your unsaved edits.`);
            return;
        }
        void surface.postMessage({ type: 'externalUpdate', content });
    };
    fs.watchFile(filePath, { interval: 1000 }, onDiskChange);
    surface.onDispose(() => {
        fs.unwatchFile(filePath, onDiskChange);
        editorTabs.delete(surface.id);
    });

    surface.loadUrl(`${ORIGIN}/webview/editor/editor.html`);
    return surface;
}

// Before an editor tab with unsaved edits closes: save, discard, or keep it open.
async function confirmCloseEditor(panelId) {
    const tab = editorTabs.get(panelId);
    if (!tab || !tab.isDirty) {
        return true;
    }
    const { response } = await dialog.showMessageBox(mainWindow, {
        type: 'warning',
        buttons: ['Save', "Don't Save", 'Cancel'],
        defaultId: 0,
        cancelId: 2,
        message: `Do you want to save the changes you made to ${tab.name}?`,
        detail: "Your changes will be lost if you don't save them.",
    });
    if (response === 2) {
        return false;
    }
    if (response === 0) {
        try {
            tab.save(await tab.content());
        } catch (error) {
            setStatus('error', `Failed to save ${tab.name}: ${error.message}`);
            return false;
        }
    }
    return true;
}

// Opens settings.json, listing every setting with its current value.
async function openSettingsFile() {
    settings.seedDefaults();
    const error = await electronShell.openPath(settings.filePath);
    if (error) {
        electronShell.showItemInFolder(settings.filePath);
    }
}

// An app command for an agent's tool: unlike runAppCommand, a failure reaches the agent.
function runToolCommand(id, args) {
    const handler = kigumiApp && kigumiApp.commands[id];
    if (!handler) {
        throw new Error(`Kigumi has no command ${id}`);
    }
    return handler(args);
}

let agentSession = null;

// Shows or hides the agent. Hidden, it keeps its conversation.
function toggleAgentPanel() {
    if (connection.findPanel((panel) => panel.type === 'agent')) {
        connection.setSideShown('right', !connection.layout.right);
        return;
    }
    const surface = connection.createPanel('agent', { title: 'Agent' });
    agentSession = new AgentSession({
        panels: kigumiApp.panels,
        run: runToolCommand,
        post: (message) => void surface.postMessage(message),
        cwd: () => workspaceFolder,
        setting: (key, fallback) => settings.get(key, fallback),
        version: packageJson.version,
        log: (line) => logChannel.appendLine(line),
    });
    surface.onMessage((message) => agentSession && agentSession.handle(message));
    surface.onDispose(() => {
        if (agentSession) agentSession.stop();
        agentSession = null;
    });
    surface.loadUrl(`${ORIGIN}/webview/agent/agent.html`);
    connection.setSideShown('right', true);
}

let mcpServer = null;

// Serves Kigumi's tools over MCP while `mcp.enabled` is on, on the port and token in settings.
async function syncMcpServer() {
    const wanted = settings.get('mcp.enabled', false) === true;
    const port = Number(settings.get('mcp.port', 7345)) || 0;
    if (mcpServer && (!wanted || mcpServer.port !== port)) {
        await mcpServer.close();
        logChannel.appendLine('[mcp] Stopped');
        mcpServer = null;
    }
    if (!wanted || mcpServer || !kigumiApp) {
        return;
    }
    let token = settings.get('mcp.token', '');
    if (!token) {
        token = newToken();
        settings.set('mcp.token', token);
    }
    try {
        mcpServer = await startMcpHttpServer({
            tools: createKigumiTools({ panels: kigumiApp.panels, run: runToolCommand }),
            token,
            port,
            version: packageJson.version,
            log: (line) => logChannel.appendLine(line),
        });
        logChannel.appendLine(`[mcp] Serving Kigumi's tools at ${mcpServer.url}`);
    } catch (error) {
        logChannel.appendLine(`[mcp] Could not start on port ${port}: ${error.message || error}`);
        setStatus('error', `Kigumi's MCP server could not start on port ${port}: ${error.message || error}`);
    }
}

// Puts the line that adds Kigumi to Claude Code on the clipboard.
function copyMcpSetup() {
    if (!mcpServer) {
        setStatus('warning', 'Turn on "mcp.enabled" in Kigumi settings first.');
        return;
    }
    require('electron').clipboard.writeText(claudeCodeAddCommand(mcpServer.url, settings.get('mcp.token', '')));
    setStatus('info', 'Copied the command that adds Kigumi to Claude Code.');
}

function onShellCommand(id, ...args) {
    if (id === 'openFolder') return chooseWorkspaceFolder();
    if (id === 'openFrameFile') return chooseFrameFile();
    if (id === 'openLog') return openLogTab();
    if (id === 'openSettings') return openSettingsFile();
    if (id === 'toggleAgent') return toggleAgentPanel();
    if (id === 'copyMcpSetup') return copyMcpSetup();
    if (id === 'run' && typeof args[0] === 'string') return runAppCommand(args[0], ...args.slice(1));
    return undefined;
}

function buildMenu() {
    const isMac = process.platform === 'darwin';
    const command = (label, id, accelerator) => ({ label, accelerator, click: () => runAppCommand(id) });
    const template = [
        ...(isMac ? [{ role: 'appMenu' }] : []),
        {
            label: 'File',
            submenu: [
                { label: 'Open Folder…', accelerator: 'CmdOrCtrl+O', click: () => chooseWorkspaceFolder() },
                { label: 'Open Frame File…', accelerator: 'CmdOrCtrl+Shift+O', click: () => chooseFrameFile() },
                { type: 'separator' },
                {
                    label: 'Close Tab',
                    accelerator: 'CmdOrCtrl+W',
                    click: async () => {
                        const active = connection.activePanel;
                        if (active && await confirmCloseEditor(active.id)) active.dispose();
                    },
                },
                ...(isMac ? [] : [{ type: 'separator' }, { role: 'quit' }]),
            ],
        },
        { role: 'editMenu' },
        {
            label: 'Kigumi',
            submenu: [
                command('Refresh Active Viewer', 'kigumi.render', 'CmdOrCtrl+R'),
                command('Browse Patterns…', 'kigumi.browsePatterns', 'CmdOrCtrl+P'),
                command('Close Pattern Viewer…', 'kigumi.unloadPattern'),
                { type: 'separator' },
                command('Initialize Project', 'kigumi.initializeProjectInWorkspace'),
                command('Update Kumiki', 'kigumi.updateKumiki'),
                command('Refresh Explorer', 'kigumi.refreshSidebar'),
                {
                    label: 'Auto Refresh on File Change',
                    type: 'checkbox',
                    checked: settings.get('viewer.autoRefreshOnFileChange', false),
                    click: () => runAppCommand('kigumi.toggleAutoRefreshOnFileChange'),
                },
                { type: 'separator' },
                { label: 'Toggle Agent', accelerator: 'CmdOrCtrl+Shift+A', click: () => toggleAgentPanel() },
                { label: 'Copy MCP Setup for Claude Code', enabled: Boolean(mcpServer), click: () => copyMcpSetup() },
                { type: 'separator' },
                { label: 'Open Settings File', accelerator: 'CmdOrCtrl+,', click: () => openSettingsFile() },
                { label: 'Show Log', accelerator: 'CmdOrCtrl+Shift+U', click: () => openLogTab() },
            ],
        },
        {
            label: 'View',
            submenu: [
                {
                    label: 'Toggle Developer Tools',
                    accelerator: isMac ? 'Alt+Cmd+I' : 'Ctrl+Shift+I',
                    click: () => {
                        mainWindow.webContents.toggleDevTools();
                    },
                },
                { type: 'separator' },
                { role: 'togglefullscreen' },
            ],
        },
        {
            role: 'help',
            submenu: [
                command('Kumiki Website', 'kigumi.openWebsite'),
                { label: 'Open Logs Folder', click: () => electronShell.openPath(path.dirname(logChannel.filePath)) },
            ],
        },
    ];
    Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function start() {
    // Run from source, the Dock shows Electron's icon; a build has its own (electron-builder.yml).
    if (process.platform === 'darwin' && !app.isPackaged && app.dock) {
        app.dock.setIcon(path.join(KIGUMI_DIR, 'templogo.png'));
    }
    protocol.handle('kigumi', handleProtocol);

    const userData = app.getPath('userData');
    settings = new SettingsStore(path.join(userData, 'settings.json'), { ...defaultsFromPackageJson(packageJson), ...APP_DEFAULTS });
    settings.watch();
    workspaceFolder = resolveWorkspaceFolder();
    if (workspaceFolder) {
        settings.set('app.workspaceFolder', workspaceFolder);
    }
    logChannel = new LogChannel(path.join(userData, 'logs', 'kigumi.log'), {
        onShow: () => {
            status.logBadge = true;
            pushShellState();
        },
    });
    logChannel.appendLine(`[app] Kigumi ${packageJson.version} (Electron ${process.versions.electron})`);
    logChannel.appendLine(`[app] Workspace: ${workspaceFolder || '(none)'}`);

    const log = (line) => logChannel.appendLine(line);
    const appWindow = createAppWindow({ origin: ORIGIN, log });
    mainWindow = appWindow.window;
    pages = new PageStore({ origin: ORIGIN, webviewDir });
    connection = new ShellConnection({
        transport: appWindow.transport,
        pages,
        status: shellStatus,
        onCommand: onShellCommand,
        isFocused: () => !mainWindow.isDestroyed() && mainWindow.isFocused(),
        log,
        closeRequest: confirmCloseEditor,
    });
    mainWindow.on('focus', () => pushShellState());
    // Quitting asks about each editor tab with unsaved edits, as closing one does.
    let closeConfirmed = false;
    mainWindow.on('close', (event) => {
        const dirty = [...editorTabs].filter(([, tab]) => tab.isDirty).map(([id]) => id);
        if (closeConfirmed || dirty.length === 0) {
            return;
        }
        event.preventDefault();
        void (async () => {
            for (const id of dirty) {
                const panel = connection.panels.get(id);
                if (panel) panel.reveal();
                if (!(await confirmCloseEditor(id))) {
                    return;
                }
            }
            closeConfirmed = true;
            mainWindow.close();
        })();
    });

    setHost(createElectronHost({
        window: mainWindow,
        connection,
        settings,
        workspaceFolder,
        locale: app.getLocale(),
        log: (line) => logChannel.appendLine(line),
        runCommand: runAppCommand,
        setStatus,
        setProgress,
        openEditor: openEditorTab,
    }));

    kigumiApp = createKigumiApp({
        extensionPath: KIGUMI_DIR,
        storagePath: path.join(userData, 'tools'),
        channel: logChannel,
        enableTestCommands: process.env.KIGUMI_ENABLE_TEST_COMMANDS === '1',
        bundledUv: bundledUvPath(),
    });
    kigumiApp.sidebarController.attach(connection.createPanel('explorer', { title: 'Explorer' }));

    settings.onChange(() => {
        buildMenu();
        pushShellState();
        void syncMcpServer();
    });
    buildMenu();
    void syncMcpServer();

    mainWindow.on('closed', async () => {
        if (agentSession) agentSession.stop();
        if (mcpServer) await mcpServer.close();
        const current = kigumiApp;
        kigumiApp = null;
        connection.dispose();
        connection = null;
        mainWindow = null;
        settings.dispose();
        if (current) await current.dispose();
        app.quit();
    });

    if (process.env.KIGUMI_ENABLE_TEST_COMMANDS === '1') {
        global.__kigumi = {
            runAppCommand,
            connection: () => connection,
            window: () => mainWindow,
            logLines: () => logChannel.lines,
            onShellCommand,
            settings,
            panels: () => kigumiApp && kigumiApp.panels,
        };
        // A test driver run against the live app; its result sets the exit code.
        if (process.env.KIGUMI_TEST_SCRIPT) {
            const driver = require(path.resolve(process.env.KIGUMI_TEST_SCRIPT));
            Promise.resolve(driver(global.__kigumi))
                .then((ok) => app.exit(ok === false ? 1 : 0))
                .catch((error) => {
                    console.error(error);
                    app.exit(1);
                });
        }
    }
}

// One Kigumi at a time: a second launch focuses the running window.
if (!app.requestSingleInstanceLock()) {
    app.quit();
} else {
    app.on('second-instance', (_event, argv) => {
        if (!mainWindow || mainWindow.isDestroyed()) return;
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.focus();
        const requested = argv.slice(1).find((arg) => !arg.startsWith('-') && fs.existsSync(arg) && fs.statSync(arg).isDirectory());
        if (requested && path.resolve(requested) !== workspaceFolder) {
            setStatus('info', `Kigumi is already open on ${path.basename(workspaceFolder || '')}. Use File > Open Folder… to switch to ${path.basename(requested)}.`);
        }
    });
    app.whenReady().then(start);
}
app.on('window-all-closed', () => app.quit());
