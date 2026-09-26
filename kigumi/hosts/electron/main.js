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
const { webviewDir } = require('../../webview-html');
const { Shell, pages, ORIGIN } = require('./shell');
const { createElectronHost } = require('./electron-host');
const { SettingsStore, defaultsFromPackageJson } = require('./settings-store');
const { LogChannel } = require('./log-channel');

const KIGUMI_DIR = path.join(__dirname, '..', '..');
const PAGES_DIR = path.join(__dirname, 'pages');
const packageJson = JSON.parse(fs.readFileSync(path.join(KIGUMI_DIR, 'package.json'), 'utf8'));
const STATUS_CLEAR_MS = 10000;

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

let shell = null;
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
        const html = pages.get(rest[0]);
        return html === undefined
            ? notFound()
            : new Response(html, { headers: { 'content-type': CONTENT_TYPES['.html'] } });
    }
    if (area === 'webview') return serveFrom(webviewDir, rest);
    if (area === 'shell') return serveFrom(PAGES_DIR, rest);
    return notFound();
}

// The uv packaged into the app's resources by scripts/fetch-uv.js, if any.
function bundledUvPath() {
    if (!app.isPackaged) return null;
    const candidate = path.join(process.resourcesPath, 'uv', process.platform === 'win32' ? 'uv.exe' : 'uv');
    return fs.existsSync(candidate) ? candidate : null;
}

function resourceUri(absPath) {
    const relative = path.relative(webviewDir, absPath).split(path.sep).map(encodeURIComponent).join('/');
    return `${ORIGIN}/webview/${relative}`;
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
    if (shell) shell.pushState();
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
    const { canceled, filePaths } = await dialog.showOpenDialog(shell.window, {
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
    const { canceled, filePaths } = await dialog.showOpenDialog(shell.window, {
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
    const existing = shell.findTab((surface) => surface.kind === 'log');
    if (existing) {
        existing.reveal();
        return;
    }
    const surface = shell.createTab({ kind: 'log', title: 'Log' });
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
    surface.loadUrl(`${ORIGIN}/shell/log.html`);
}

function onShellCommand(id, ...args) {
    if (id === 'openFolder') return chooseWorkspaceFolder();
    if (id === 'openFrameFile') return chooseFrameFile();
    if (id === 'openLog') return openLogTab();
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
                    click: () => {
                        const active = shell.activeSurface;
                        if (active) active.dispose();
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
                        const target = shell.activeSurface ? shell.activeSurface.view.webContents : shell.sidebar.view.webContents;
                        target.toggleDevTools();
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
    protocol.handle('kigumi', handleProtocol);

    const userData = app.getPath('userData');
    settings = new SettingsStore(path.join(userData, 'settings.json'), defaultsFromPackageJson(packageJson));
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

    shell = new Shell({ resourceUri, status: shellStatus, onShellCommand });

    setHost(createElectronHost({
        shell,
        settings,
        workspaceFolder,
        locale: app.getLocale(),
        log: (line) => logChannel.appendLine(line),
        runCommand: runAppCommand,
        setStatus,
        setProgress,
    }));

    kigumiApp = createKigumiApp({
        extensionPath: KIGUMI_DIR,
        storagePath: path.join(userData, 'tools'),
        channel: logChannel,
        enableTestCommands: process.env.KIGUMI_ENABLE_TEST_COMMANDS === '1',
        bundledUv: bundledUvPath(),
    });
    kigumiApp.sidebarController.attach(shell.sidebar);

    settings.onChange(() => {
        buildMenu();
        pushShellState();
    });
    buildMenu();

    shell.window.on('closed', async () => {
        const current = kigumiApp;
        kigumiApp = null;
        shell = null;
        if (current) await current.dispose();
        app.quit();
    });

    if (process.env.KIGUMI_ENABLE_TEST_COMMANDS === '1') {
        global.__kigumi = { runAppCommand, shell: () => shell, logLines: () => logChannel.lines, onShellCommand };
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

app.whenReady().then(start);
app.on('window-all-closed', () => app.quit());
