/**
 * Entry point of the standalone Kigumi app (Electron main process).
 *
 * Usage: electron hosts/electron/main.js [project-folder]
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { app, net, protocol, Menu, dialog, nativeImage, safeStorage, shell: electronShell } = require('electron');
const { setHost } = require('../../host');
const { createKigumiApp } = require('../../kigumi-app');
const { DEFAULT_FILES_EXCLUDE } = require('../../sidebar-files');
const { KEYBINDINGS_SETTING, resolveKeybindings, acceleratorFor } = require('../../keybindings');
const { createKeyboardShortcutsPanel, shellKeys, runKeyCommand } = require('../../app-shell/keyboard-shortcuts');
const { webviewDir } = require('../../webview-html');
const { ShellConnection } = require('../../app-shell/shell-connection');
const { PageStore } = require('../../app-shell/page-store');
const { createAppWindow } = require('./app-window');
const { createElectronHost } = require('./electron-host');
const { SettingsStore, defaultsFromPackageJson } = require('../../app-shell/settings-store');
const { LogChannel } = require('../../app-shell/log-channel');
const { createProjectLifecycle } = require('../../app-shell/project-lifecycle');
const { createLogPanel } = require('../../app-shell/log-panel');
const { createEditorTabs } = require('../../app-shell/editor-tabs');
const { createAgentPanel } = require('../../agent/agent-panel');
const { withRecentFolder, offeredRecentFolders } = require('./recent-folders');
const { createAccount } = require('../../agent/account');
const { backendConfig } = require('../../agent/backend-config');
const { createModelList } = require('../../agent/models');
const { SecureStorage } = require('./secure-storage');
const { createProjectContext } = require('../../agent/project-context');
const { mcpTools } = require('../../agent/agent');
const { createMcpService } = require('../../agent/mcp-service');
const { RELEASES_URL, createUpdateChecker, downloadUrl } = require('./update-check');
const { createAutoInstaller } = require('./auto-update');
const { LANGUAGE_SETTING, LANGUAGE_CHOICES, chooseLanguage } = require('../../i18n');

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
    // Project folders opened lately, newest first: File > Open Recent and the welcome page.
    'app.recentFolders': [],
    // The agent panel: off (the default) hides it everywhere. An OpenRouter key, or none (then the
    // Kigumi account). The model is an id from agent/models.js.
    'agent.enabled': false,
    'agent.openrouterApiKey': '',
    'agent.model': '',
    'agent.showOnStartup': true,
    // Kigumi's tools for any agent, over MCP on this machine only. See agent/mcp-http.js.
    'mcp.enabled': false,
    'mcp.port': 7345,
    'mcp.token': '',
    // Look for a newer Kigumi release on start and once a day; prereleases only when asked.
    'app.checkForUpdates': true,
    'app.updatePrereleases': false,
    // Kigumi's language: default (the system's), en or ja.
    [LANGUAGE_SETTING]: 'default',
    // Keyboard shortcuts that differ from the defaults: { command: key }, "" for none (keybindings.js).
    [KEYBINDINGS_SETTING]: {},
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

/** The language Kigumi's views are in: app.language's, else the system's. */
function appLocale() {
    return chooseLanguage(settings.get(LANGUAGE_SETTING, 'default'), app.getLocale());
}
let logChannel = null;
let workspaceFolder = null;
const status = { message: null, level: 'info', progress: null, logBadge: false };
let statusTimer = null;
let updates = null;

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
        update: updates && updates.available ? { version: updates.available.version } : null,
        recentFolders: recentFolders().map((one) => ({ ...one, shown: tildePath(one.path) })),
        // The menus run the keys; the shell shows them on the welcome page.
        keys: settings ? shellKeys(settings, { platform: process.platform, desktop: true, dispatch: false }) : null,
    };
}

/** The recent folders worth offering: still there, and not the one open. */
function recentFolders() {
    if (!settings) return [];
    return offeredRecentFolders(settings.get('app.recentFolders', []),
        { current: workspaceFolder, exists: (folder) => fs.existsSync(folder) && fs.statSync(folder).isDirectory() });
}

// The menu and the welcome page follow, as for any setting.
function clearRecentFolders() {
    settings.set('app.recentFolders', []);
}

/** Whether the built-in agent is offered at all (`agent.enabled`). */
function agentEnabled() {
    return Boolean(settings) && settings.get('agent.enabled', false) === true;
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
        title: 'Open Kigumi Project',
        properties: ['openDirectory', 'createDirectory'],
    });
    if (!canceled && filePaths.length > 0) {
        await switchProject(filePaths[0]);
    }
}

/** Ask for a folder for a new project, starting in Documents, then open it and set it up. */
async function chooseNewProjectFolder() {
    const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
        title: 'New Kigumi Project',
        message: 'Choose or make the folder for the new project.',
        buttonLabel: 'Create Project',
        defaultPath: app.getPath('documents'),
        properties: ['openDirectory', 'createDirectory'],
    });
    if (!canceled && filePaths.length > 0) {
        await createProject(filePaths[0]);
    }
}

/**
 * Make `folder` (absolute) if need be, open it, and set it up as a project: its venv, kumiki and a
 * starter frame. Return whether it was opened.
 */
async function createProject(folder) {
    checkNewProjectFolder(folder);
    fs.mkdirSync(folder, { recursive: true });
    if (!(await switchProject(folder))) {
        return false;
    }
    await runAppCommand('kigumi.initializeProjectInWorkspace');
    return true;
}

function checkNewProjectFolder(folder) {
    if (!path.isAbsolute(folder)) {
        throw new Error(`${folder} is not an absolute path.`);
    }
    if (fs.existsSync(folder) && !fs.statSync(folder).isDirectory()) {
        throw new Error(`${folder} is a file, not a folder.`);
    }
}

function checkProjectFolder(folder) {
    if (!path.isAbsolute(folder) || !fs.existsSync(folder) || !fs.statSync(folder).isDirectory()) {
        throw new Error(`${folder} is not a folder. Give the absolute path of an existing one.`);
    }
}

/** Close the project, leaving none open. */
function closeWorkspaceFolder() {
    return switchProject(null);
}

/** What the agent's project tools (agent/project-tools.js) do here. */
function agentProjects() {
    const expand = (folder) => (folder.startsWith('~') ? path.join(os.homedir(), folder.slice(1)) : folder);
    const done = (switched, what) => {
        if (!switched) throw new Error(`The user kept the project open (an editor had unsaved changes), so ${what} did not happen.`);
    };
    return {
        current: () => workspaceFolder,
        recent: () => recentFolders().map((one) => one.path),
        open: async (folder) => {
            const target = expand(folder);
            checkProjectFolder(target);
            done(await switchProject(target), `opening ${target}`);
        },
        create: async (folder) => {
            const target = expand(folder);
            checkNewProjectFolder(target);
            done(await createProject(target), `making ${target}`);
        },
        close: async () => {
            if (!workspaceFolder) throw new Error('No project is open.');
            done(await closeWorkspaceFolder(), 'closing it');
        },
    };
}

/** Open one of the recent folders, by path; one that isn't listed is ignored. */
function openRecentFolder(folder) {
    if (recentFolders().some((one) => one.path === folder)) {
        return switchProject(folder);
    }
    return false;
}

let projectLifecycle = null;

/** Switch projects after confirming unsaved editor changes. */
function switchProject(folder) {
    return projectLifecycle(folder);
}

/** Start Kigumi's side of the open project: the host, the app, its commands and the explorer. */
function openProject() {
    setHost(createElectronHost({
        window: mainWindow,
        connection,
        settings,
        workspaceFolder,
        locale: appLocale(),
        log: (line) => logChannel.appendLine(line),
        runCommand: runAppCommand,
        setStatus,
        setProgress,
        openEditor: openEditorTab,
        documents: editors,
        showLog: openLogTab,
        mcp: mcpControls,
        closeProject: () => closeWorkspaceFolder(),
        // Project status's Open Project and recent folders, with none open.
        projects: {
            open: () => chooseWorkspaceFolder(),
            recent: () => recentFolders().map((one) => ({ id: one.path, label: one.name, description: tildePath(one.path) })),
            openRecent: (folder) => openRecentFolder(folder),
        },
    }));
    kigumiApp = createKigumiApp({
        extensionPath: KIGUMI_DIR,
        storagePath: path.join(app.getPath('userData'), 'tools'),
        channel: logChannel,
        enableTestCommands: process.env.KIGUMI_ENABLE_TEST_COMMANDS === '1',
        bundledUv: bundledUvPath(),
    });
    kigumiApp.sidebarController.attach(connection.createPanel('explorer', { title: 'Explorer' }));
}

/** Show the explorer with the rows `keys` expanded, the first at the top; false if it has none of them. */
function revealInExplorer(keys) {
    connection.setSideShown('left', true);
    return kigumiApp.sidebarController.reveal(keys).length > 0;
}

// Patterns and examples come from the project's kumiki, so there are none without a project.
function browsePatterns() {
    if (!workspaceFolder) {
        setStatus('info', 'Open a project to browse patterns.');
        return;
    }
    revealInExplorer(['patterns-root', 'pattern-section:workspace-patternbooks', 'pattern-section:shipped-patterns']);
}

function browseExamples() {
    if (!workspaceFolder) {
        setStatus('info', 'Open a project to browse examples.');
        return;
    }
    if (!revealInExplorer(['example-frames-root', 'library-frames:kumiki'])) {
        setStatus('info', 'No examples yet: kumiki is not installed in this project. Kigumi > Initialize Project sets it up.');
    }
}

/** The Log tab, showing everything, or `source` (a view's file name) only. */
let openLogTab = null;

// Code editor tabs (app-shell/editor-tabs.js), made once the window is.
let editors = null;

function openEditorTab(filePath, line = 1) {
    return editors.open(filePath, line);
}

function confirmCloseEditor(panelId) {
    return editors.confirmClose(panelId);
}

async function askToSave(name) {
    const { response } = await dialog.showMessageBox(mainWindow, {
        type: 'warning',
        buttons: ['Save', "Don't Save", 'Cancel'],
        defaultId: 0,
        cancelId: 2,
        message: `Do you want to save the changes you made to ${name}?`,
        detail: "Your changes will be lost if you don't save them.",
    });
    return ['save', 'discard', 'cancel'][response];
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

let account = null;
let modelList = null;
// A kigumi://auth link that came before the account existed (a cold start from the browser).
let pendingAuthLink = null;

/** Sign-in coming back from the browser: kigumi://auth?code=… */
function handleAuthLink(url) {
    if (!account) {
        pendingAuthLink = url;
        return;
    }
    logChannel.appendLine('[account] sign-in link received');
    if (mainWindow && !mainWindow.isDestroyed()) {
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.focus();
    }
    account.completeSignIn(url).then(() => logChannel.appendLine('[account] signed in')).catch((error) => {
        logChannel.appendLine(`[account] sign-in failed: ${error.message}`);
        setStatus('error', `Could not sign in: ${error.message}`);
    });
}

// The models offered, as the backend lists them, the last list kept for starting offline.
function createAppModelList() {
    const file = path.join(app.getPath('userData'), 'models.json');
    modelList = createModelList({
        backendUrl: backendConfig(process.env).backendUrl,
        storage: {
            load: () => JSON.parse(fs.readFileSync(file, 'utf8')),
            save: (models) => fs.writeFileSync(file, JSON.stringify(models, null, 1)),
        },
        onChange: () => agentPanel && agentPanel.session && agentPanel.session.postState(),
    });
    refreshModels();
}

function refreshModels() {
    modelList.refresh().catch((error) => logChannel.appendLine(`[agent] [warn] couldn't fetch the model list: ${error.message}`));
}

function createAppAccount() {
    const config = backendConfig(process.env);
    account = createAccount({
        ...config,
        storage: new SecureStorage(path.join(app.getPath('userData'), 'account'), safeStorage,
            (line) => logChannel.appendLine(line)),
        // A page of the backend's, which opens kigumi://auth with the code: ending on kigumi:// itself
        // leaves the browser tab loading forever.
        redirectTo: `${config.backendUrl.replace(/\/$/, '')}/auth/callback`,
        openExternal: (url) => electronShell.openExternal(url),
        onChange: () => agentPanel && agentPanel.session && agentPanel.session.postState(),
    });
    const link = pendingAuthLink || process.argv.find((arg) => arg.startsWith('kigumi://auth'));
    pendingAuthLink = null;
    if (link) handleAuthLink(link);
}

// The kumiki library's source, which the agent may read: found once per project.
const agentHost = createProjectContext({ root: () => workspaceFolder,
    panels: () => kigumiApp && kigumiApp.panels, run: runToolCommand, projects: agentProjects });

// The agent's panel (agent/agent-panel.js), made once the window is.
let agentPanel = null;

// Shows or hides the agent. Hidden, it keeps its conversation.
function toggleAgentPanel() {
    if (agentPanel) agentPanel.toggle();
}

/** Shows the agent panel's settings again after a setting changed elsewhere. */
function refreshAgentPanel() {
    if (agentPanel) agentPanel.refresh();
}

// Kigumi's MCP server (agent/mcp-service.js), made once the window is.
let mcp = null;

// What the host offers the views about MCP (host.js, `mcp`), before and after the server is made.
const mcpControls = {
    state: () => mcp.controls.state(),
    onChange: (listener) => mcp.controls.onChange(listener),
    copySetup: (clientId) => mcp.copySetup(clientId),
};

function syncMcpServer() {
    return mcp ? mcp.sync() : Promise.resolve();
}

function copyMcpSetup(clientId) {
    if (mcp) mcp.copySetup(clientId);
}

function onShellCommand(id, ...args) {
    if (id === 'openFolder') return chooseWorkspaceFolder();
    if (id === 'newProject') return chooseNewProjectFolder();
    if (id === 'browsePatterns') return browsePatterns();
    if (id === 'browseExamples') return browseExamples();
    if (id === 'openRecentFolder') return openRecentFolder(args[0]);
    if (id === 'clearRecentFolders') return clearRecentFolders();
    if (id === 'openLog') return openLogTab();
    if (id === 'openSettings') return openSettingsFile();
    if (id === 'openKeyboardShortcuts') return openKeyboardShortcuts();
    if (id === 'keyCommand') return runKeyCommand(args[0], { runCommand: runAppCommand, actions: keyActions });
    if (id === 'toggleAgent') return toggleAgentPanel();
    if (id === 'copyMcpSetup') return copyMcpSetup();
    if (id === 'showUpdate') return showUpdate();
    if (id === 'run' && typeof args[0] === 'string') return runAppCommand(args[0], ...args.slice(1));
    return undefined;
}

/** Fetch GitHub's list of releases. */
async function fetchReleases() {
    const response = await net.fetch(RELEASES_URL, {
        headers: { Accept: 'application/vnd.github+json', 'User-Agent': `Kigumi/${packageJson.version}` },
    });
    if (!response.ok) throw new Error(`GitHub answered ${response.status} ${response.statusText}`);
    return response.json();
}

// Installing updates in place (auto-update.js), made when first needed.
let autoInstaller = null;
function installer() {
    if (!autoInstaller) {
        autoInstaller = createAutoInstaller({ autoUpdater: require('electron-updater').autoUpdater,
            packaged: app.isPackaged, platform: process.platform, log: (line) => logChannel.appendLine(line) });
    }
    return autoInstaller;
}

/**
 * Offer the available update: install it in place (the Mac and Windows, from a release with an
 * update file), else download it; or read its notes, skip it, or leave it for later.
 */
async function showUpdate(release = updates && updates.available) {
    if (!release || !mainWindow || mainWindow.isDestroyed()) return;
    const inPlace = installer().canInstall(release);
    const { response } = await dialog.showMessageBox(mainWindow, {
        type: 'info',
        message: `Kigumi ${release.version} is available`,
        detail: `You have ${packageJson.version}. `
            + (inPlace ? 'Kigumi downloads the new version and restarts into it; '
                : 'Download the new version and install it over this one; ')
            + 'your settings and projects are kept.',
        buttons: [inPlace ? 'Install and Restart' : 'Download', 'Release Notes', 'Skip This Version', 'Later'],
        defaultId: 0,
        cancelId: 3,
    });
    if (response === 0) {
        if (inPlace) await installUpdate(release);
        else void electronShell.openExternal(downloadUrl(release, process.platform, process.arch));
    }
    if (response === 1) void electronShell.openExternal(release.page);
    if (response === 2) updates.skip(release.version);
}

/** Download `release`, showing how far along in the status bar, then restart into it. */
async function installUpdate(release) {
    const title = `Downloading Kigumi ${release.version}`;
    setProgress(`${title}…`);
    try {
        await installer().download(release, { onProgress: (percent) => setProgress(`${title}… ${percent}%`) });
    } catch (error) {
        logChannel.appendLine(`[update] [error] ${error.stack || error}`);
        const { response } = await dialog.showMessageBox(mainWindow, {
            type: 'warning', message: `Could not install Kigumi ${release.version}`,
            detail: `${error.message || error}\n\nYou can download it and install it over this one instead.`,
            buttons: ['Download', 'Cancel'], defaultId: 0, cancelId: 1,
        });
        if (response === 0) void electronShell.openExternal(downloadUrl(release, process.platform, process.arch));
        return;
    } finally {
        setProgress(null);
    }
    const { response } = await dialog.showMessageBox(mainWindow, {
        type: 'info', message: `Kigumi ${release.version} is ready`,
        detail: 'Restart now to use it, or it goes in the next time Kigumi quits.',
        buttons: ['Restart Now', 'Later'], defaultId: 0, cancelId: 1,
    });
    if (response === 0) installer().restart();
}

/** Kigumi > Check for Updates…: look now, and say what was found. */
async function checkForUpdatesNow() {
    let newer;
    try {
        newer = await updates.check({ manual: true });
    } catch (error) {
        await dialog.showMessageBox(mainWindow, {
            type: 'warning', message: 'Could not check for updates', detail: String(error.message || error),
        });
        return;
    }
    if (newer) {
        await showUpdate(newer);
    } else {
        await dialog.showMessageBox(mainWindow, {
            type: 'info', message: 'Kigumi is up to date', detail: `${packageJson.version} is the newest release.`,
        });
    }
}

/** `folder`, with the home folder at its start written ~. */
function tildePath(folder) {
    const home = os.homedir();
    return folder === home || folder.startsWith(home + path.sep) ? '~' + folder.slice(home.length) : folder;
}

function recentFoldersMenu() {
    const recent = recentFolders();
    if (recent.length === 0) {
        return [{ label: 'No Recent Folders', enabled: false }];
    }
    return [
        ...recent.map((one) => ({
            label: `${one.name} — ${tildePath(one.path)}`,
            click: () => void switchProject(one.path),
        })),
        { type: 'separator' },
        { label: 'Clear Recently Opened', click: () => clearRecentFolders() },
    ];
}

// Where the About window and the Help menu point.
const LINKS = Object.freeze({
    website: 'https://kumiki.build',
    docs: 'https://kumiki.build/docs/',
    discord: 'https://discord.gg/cQhUG7WJ8',
    discussions: 'https://github.com/minimapletinytools/kumiki/discussions',
});

/** About Kigumi: its version, what it runs on, its licence, and links to the website and the community. */
async function showAbout() {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    const links = [['Website', LINKS.website], ['Discord', LINKS.discord], ['GitHub Discussions', LINKS.discussions]];
    const { response } = await dialog.showMessageBox(mainWindow, {
        type: 'none',
        icon: nativeImage.createFromPath(path.join(KIGUMI_DIR, 'app-icon.png')),
        title: 'About Kigumi',
        message: `Kigumi ${packageJson.version}`,
        detail: [
            'The viewer and editor for kumiki, the Python library for timber framing and joinery.',
            '',
            `Electron ${process.versions.electron}, Chromium ${process.versions.chrome}, Node ${process.versions.node}`,
            `${os.type()} ${os.release()} (${process.arch})`,
            '',
            '© 2026 minimaple. Kumiki and Kigumi are open source under the MPL-2.0.',
        ].join('\n'),
        buttons: ['OK', ...links.map(([label]) => label)],
        defaultId: 0,
        cancelId: 0,
    });
    if (response > 0) void electronShell.openExternal(links[response - 1][1]);
}

// The Keyboard Shortcuts tab (app-shell/keyboard-shortcuts.js), made once the window is; and whether
// it is waiting for a new key, when the menus let keys through to it.
let openKeyboardShortcuts = () => {};
let recordingKeys = false;

/** Close the active tab, asking first about an editor's unsaved changes. */
async function closeActiveTab() {
    const active = connection.activePanel;
    if (active && await confirmCloseEditor(active.id)) active.dispose();
}

// What the app's own keys run (keybindings.js app.*).
const keyActions = {
    closeTab: () => closeActiveTab(),
    toggleAgent: () => toggleAgentPanel(),
    showLog: () => openLogTab(),
    openSettings: () => openSettingsFile(),
    keyboardShortcuts: () => openKeyboardShortcuts(),
};

function buildMenu() {
    const isMac = process.platform === 'darwin';
    // Each item's key from the keyboard shortcuts; while the Keyboard Shortcuts tab waits for a new key,
    // the keys go to it instead of running their items.
    const keys = resolveKeybindings({ overrides: settings.get(KEYBINDINGS_SETTING, {}) });
    const keyed = (id) => ({ accelerator: acceleratorFor(id, keys), registerAccelerator: !recordingKeys });
    const command = (label, id) => ({ label, ...keyed(id), click: () => runAppCommand(id) });
    // On macOS the edit keys (⌘C, ⌘V, …) in text boxes need menu items; these are hidden but keep their keys.
    const editKeys = isMac ? [{ type: 'separator', visible: false },
        ...['undo', 'redo', 'cut', 'copy', 'paste', 'selectAll'].map((role) => ({ role, visible: false }))] : [];
    const template = [
        {
            label: 'File',
            submenu: [
                command('Go to File…', 'kigumi.quickOpenFile'),
                command('Open in Viewer…', 'kigumi.quickOpenInViewer'),
                command('Open Current File in Viewer', 'kigumi.openCurrentFileInViewer'),
                { type: 'separator' },
                { label: 'New Project…', click: () => chooseNewProjectFolder() },
                { label: 'Open Project…', click: () => chooseWorkspaceFolder() },
                { label: 'Open Recent', submenu: recentFoldersMenu() },
                { label: 'Close Project', enabled: Boolean(workspaceFolder), click: () => closeWorkspaceFolder() },
                { type: 'separator' },
                {
                    label: 'Close Tab',
                    ...keyed('app.closeTab'),
                    click: () => closeActiveTab(),
                },
                ...(isMac ? [] : [{ type: 'separator' }, { role: 'quit' }]),
                ...editKeys,
            ],
        },
        {
            // On macOS this is the app menu too, so Kigumi shows once.
            label: 'Kigumi',
            submenu: [
                { label: 'About Kigumi', click: () => void showAbout() },
                { type: 'separator' },
                command('Refresh Active Viewer', 'kigumi.render'),
                command('Refresh Explorer', 'kigumi.refreshSidebar'),
                {
                    label: 'Auto Refresh on File Change',
                    type: 'checkbox',
                    checked: settings.get('viewer.autoRefreshOnFileChange', false),
                    click: () => runAppCommand('kigumi.toggleAutoRefreshOnFileChange'),
                },
                { type: 'separator' },
                { label: 'Browse Patterns', enabled: Boolean(workspaceFolder), click: () => browsePatterns() },
                { label: 'Browse Examples', enabled: Boolean(workspaceFolder), click: () => browseExamples() },
                command('Close Pattern Viewer…', 'kigumi.unloadPattern'),
                { type: 'separator' },
                command('Initialize Project', 'kigumi.initializeProjectInWorkspace'),
                command('Update Kumiki', 'kigumi.updateKumiki'),
                { label: 'Check for Updates…', click: () => void checkForUpdatesNow() },
                { type: 'separator' },
                {
                    label: 'Enable Built-in Agent',
                    type: 'checkbox',
                    checked: agentEnabled(),
                    click: () => settings.set('agent.enabled', !agentEnabled()),
                },
                { label: 'Toggle Agent Panel', ...keyed('app.toggleAgent'), click: () => toggleAgentPanel() },
                { label: 'Copy MCP Setup for Claude Code', enabled: Boolean(mcp && mcp.running), click: () => copyMcpSetup() },
                { type: 'separator' },
                {
                    label: 'Language',
                    submenu: LANGUAGE_CHOICES.map(({ id, label }) => ({
                        label,
                        type: 'radio',
                        checked: settings.get(LANGUAGE_SETTING, 'default') === id,
                        click: () => settings.set(LANGUAGE_SETTING, id),
                    })),
                },
                { label: 'Open Settings File', ...keyed('app.openSettings'), click: () => openSettingsFile() },
                { label: 'Keyboard Shortcuts…', ...keyed('app.keyboardShortcuts'), click: () => openKeyboardShortcuts() },
                { label: 'Show Log', ...keyed('app.showLog'), click: () => openLogTab() },
                { label: 'Open Logs Folder', click: () => electronShell.openPath(path.dirname(logChannel.filePath)) },
                { role: 'togglefullscreen' },
                ...(isMac ? [{ type: 'separator' }, { role: 'services' }, { type: 'separator' },
                    { role: 'hide' }, { role: 'hideOthers' }, { role: 'unhide' }, { type: 'separator' }, { role: 'quit' }] : []),
            ],
        },
    ];
    const help = {
        // On macOS the role adds the menu search box.
        label: 'Help',
        role: 'help',
        submenu: [
            { label: 'Kumiki Website', click: () => electronShell.openExternal(LINKS.website) },
            { label: 'Documentation', click: () => electronShell.openExternal(LINKS.docs) },
            { type: 'separator' },
            { label: 'Discord', click: () => electronShell.openExternal(LINKS.discord) },
            { label: 'GitHub Discussions', click: () => electronShell.openExternal(LINKS.discussions) },
        ],
    };
    // macOS makes the first menu the app menu: Kigumi, then File.
    Menu.setApplicationMenu(Menu.buildFromTemplate([...(isMac ? template.reverse() : template), help]));
}

async function start() {
    // Run from source, the Dock shows Electron's icon; a build has its own (electron-builder.yml).
    if (process.platform === 'darwin' && !app.isPackaged && app.dock) {
        app.dock.setIcon(path.join(KIGUMI_DIR, 'app-icon.png'));
    }
    protocol.handle('kigumi', handleProtocol);

    const userData = app.getPath('userData');
    settings = new SettingsStore(path.join(userData, 'settings.json'), { ...defaultsFromPackageJson(packageJson), ...APP_DEFAULTS });
    settings.watch();
    workspaceFolder = resolveWorkspaceFolder();
    if (workspaceFolder) {
        settings.set('app.workspaceFolder', workspaceFolder);
        settings.set('app.recentFolders', withRecentFolder(settings.get('app.recentFolders', []), workspaceFolder));
    }
    logChannel = new LogChannel(path.join(userData, 'logs', 'kigumi.log'), {
        onShow: () => {
            status.logBadge = true;
            pushShellState();
        },
    });
    logChannel.appendLine(`[app] Kigumi ${packageJson.version} (Electron ${process.versions.electron})`);
    logChannel.appendLine(`[app] Workspace: ${workspaceFolder || '(none)'}`);
    if (settings.setAside) {
        logChannel.appendLine(`[app] [warn] settings.json could not be read; it was moved to ${settings.setAside} and Kigumi started with its defaults`);
    }

    const log = (line) => logChannel.appendLine(line);
    const appWindow = createAppWindow({ origin: ORIGIN, log });
    if (agentEnabled()) {
        createAppAccount();
        createAppModelList();
    }
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
    editors = createEditorTabs({ connection, editorUrl: `${ORIGIN}/webview/editor/editor.html`, log, setStatus, askToSave });
    openKeyboardShortcuts = createKeyboardShortcutsPanel({ connection, settings, pageUrl: `${ORIGIN}/webview/shell/keyboard-shortcuts.html`,
        platform: process.platform, desktop: true,
        onRecording: (on) => {
            if (recordingKeys === on) return;
            recordingKeys = on;
            buildMenu();
        } });
    openLogTab = createLogPanel({ connection, channel: logChannel, pageUrl: `${ORIGIN}/webview/shell/log.html`,
        filePath: logChannel.filePath, openFile: () => electronShell.openPath(logChannel.filePath),
        openLocation: openEditorTab, onShow: () => { status.logBadge = false; } });
    projectLifecycle = createProjectLifecycle({ connection, editors, current: () => workspaceFolder, replace: async (folder) => {
        const old = kigumiApp;
        kigumiApp = null;
        if (old) await old.dispose();
        workspaceFolder = folder;
        settings.set('app.workspaceFolder', folder);
        if (folder) settings.set('app.recentFolders', withRecentFolder(settings.get('app.recentFolders', []), folder));
        logChannel.appendLine(`[app] Workspace: ${folder || '(none)'}`);
        openProject();
        buildMenu();
    } });
    agentPanel = createAgentPanel({
        connection,
        pageUrl: `${ORIGIN}/webview/agent/agent.html`,
        settings,
        makeHost: agentHost,
        prepare: () => {
            if (!account) createAppAccount();
            if (!modelList) createAppModelList();
            return { account, models: modelList };
        },
        conversationsDir: path.join(userData, 'conversations'),
        mcp: mcpControls,
        locale: appLocale(),
        log,
    });
    mcp = createMcpService({
        settings,
        tools: () => mcpTools(agentHost()),
        ready: () => Boolean(kigumiApp),
        version: packageJson.version,
        log,
        setStatus,
        copyText: (text) => require('electron').clipboard.writeText(text),
    });
    mainWindow.on('focus', () => pushShellState());
    // Quitting asks about each editor tab with unsaved edits, as closing one does.
    let closeConfirmed = false;
    mainWindow.on('close', (event) => {
        const dirty = editors.dirtyIds();
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

    // A new language shows once Kigumi restarts: the open views already have their strings.
    let locale = appLocale();
    async function offerRestartForLanguage() {
        if (appLocale() === locale) return;
        locale = appLocale();
        const { response } = await dialog.showMessageBox(mainWindow, {
            type: 'info',
            message: 'Restart Kigumi to change its language?',
            detail: 'Your projects and settings are kept.',
            buttons: ['Restart', 'Later'],
            defaultId: 0,
            cancelId: 1,
        });
        if (response !== 0) return;
        for (const id of editors.dirtyIds()) {
            const panel = connection.panels.get(id);
            if (panel) panel.reveal();
            if (!(await confirmCloseEditor(id))) return;
        }
        closeConfirmed = true;
        app.relaunch();
        mainWindow.close();
    }

    openProject();
    if (agentEnabled() && settings.get('agent.showOnStartup', true)) {
        toggleAgentPanel();
    }

    updates = createUpdateChecker({
        currentVersion: packageJson.version,
        settings,
        fetchReleases,
        onChange: () => pushShellState(),
        log,
    });
    updates.start();
    let checkingForUpdates = settings.get('app.checkForUpdates', true);

    let agentWasEnabled = agentEnabled();
    settings.onChange(() => {
        if (settings.get('app.checkForUpdates', true) !== checkingForUpdates) {
            checkingForUpdates = settings.get('app.checkForUpdates', true);
            updates.start();
        }
        refreshAgentPanel();
        // Turned on just now: show it, rather than leave the user to find its button.
        if (agentEnabled() && !agentWasEnabled && agentPanel) agentPanel.show();
        agentWasEnabled = agentEnabled();
        buildMenu();
        pushShellState();
        void syncMcpServer();
        void offerRestartForLanguage();
    });
    buildMenu();
    void syncMcpServer();

    mainWindow.on('closed', async () => {
        if (agentPanel) agentPanel.stop();
        updates.stop();
        if (mcp) await mcp.close();
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
            logEntries: () => logChannel.entries,
            onShellCommand,
            settings,
            panels: () => kigumiApp && kigumiApp.panels,
            updates: () => updates,
            switchProject,
            agentProjects,
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

// kigumi:// links from the browser (sign-in) open this app, once there is a backend to sign in to;
// until then the system's handler is left alone. Run from source, Electron is told which app it is.
if (backendConfig(process.env).supabaseUrl) {
    const fromSource = process.defaultApp && process.argv.length >= 2;
    app.setAsDefaultProtocolClient('kigumi', ...(fromSource ? [process.execPath, [path.resolve(process.argv[1])]] : []));
}
app.on('open-url', (event, url) => {
    event.preventDefault();
    if (url.startsWith('kigumi://auth')) handleAuthLink(url);
});

// One Kigumi at a time: a second launch focuses the running window.
if (!app.requestSingleInstanceLock()) {
    app.quit();
} else {
    app.on('second-instance', (_event, argv) => {
        // On Windows and Linux a kigumi:// link starts a second instance, carrying the link.
        const link = argv.find((arg) => arg.startsWith('kigumi://auth'));
        if (link) {
            handleAuthLink(link);
            return;
        }
        if (!mainWindow || mainWindow.isDestroyed()) return;
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.focus();
        const requested = argv.slice(1).find((arg) => !arg.startsWith('-') && fs.existsSync(arg) && fs.statSync(arg).isDirectory());
        if (requested && path.resolve(requested) !== workspaceFolder) {
            void switchProject(path.resolve(requested));
        }
    });
    app.whenReady().then(start);
}
app.on('window-all-closed', () => app.quit());
