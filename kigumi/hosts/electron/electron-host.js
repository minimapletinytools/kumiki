/**
 * The Host (see ../../host.js) for the standalone Electron app.
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { clipboard, dialog, shell: electronShell } = require('electron');
const { createShellHostServices } = require('../../app-shell/host-services');

const CODE_CLI_CANDIDATES = [
    '/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code',
    '/opt/homebrew/bin/code',
    '/usr/local/bin/code',
    '/usr/bin/code',
];

function onPath(command) {
    const exts = process.platform === 'win32' ? ['.cmd', '.exe', ''] : [''];
    for (const dir of (process.env.PATH || '').split(path.delimiter).filter(Boolean)) {
        for (const ext of exts) {
            const candidate = path.join(dir, command + ext);
            if (fs.existsSync(candidate)) return candidate;
        }
    }
    return null;
}

/**
 * @param {object} options
 * @param {Electron.BrowserWindow} options.window
 * @param {import('../../app-shell/shell-connection').ShellConnection} options.connection
 * @param {import('../../app-shell/settings-store').SettingsStore} options.settings
 * @param {string|null} options.workspaceFolder
 * @param {object} options.documents  shared editor document service
 * @param {string} options.locale
 * @param {(line: string) => void} options.log
 * @param {(command: string, ...args: any[]) => Promise<any>} options.runCommand
 * @param {(level: string, text: string) => void} options.setStatus
 * @param {(title: string|null) => void} options.setProgress
 */
function createElectronHost({ window, connection, settings, workspaceFolder, locale, log, runCommand, setStatus, setProgress, openEditor = null, documents, showLog = null, mcp = null, closeProject = null, projects = null }) {
    function openExternalEditor(filePath, line = 1) {
        const template = settings.get('app.editorCommand', '');
        if (template) {
            const command = template.replace(/\{file\}/g, JSON.stringify(filePath)).replace(/\{line\}/g, String(line));
            spawn(command, { shell: true, detached: true, stdio: 'ignore' }).unref();
            return;
        }
        const code = onPath('code') || CODE_CLI_CANDIDATES.find((candidate) => fs.existsSync(candidate));
        if (code) {
            spawn(code, ['-g', `${filePath}:${line}`], { detached: true, stdio: 'ignore' }).unref();
            return;
        }
        electronShell.showItemInFolder(filePath);
        setStatus('info', `Set "app.editorCommand" in Kigumi settings to open files in your editor (e.g. code -g {file}:{line}).`);
    }

    function openInEditor(filePath, line = 1) {
        if (openEditor) {
            openEditor(filePath, line);
            return;
        }
        openExternalEditor(filePath, line);
    }

    return {
        locale,

        ...createShellHostServices({ connection, settings, workspaceFolder, documents, setProgress, log }),

        // The explorer lists the workspace's files too (sidebar-model.js); VS Code has its own.
        showsFileBrowser: true,

        // The agent panel can be turned on (agent.enabled); the views' options offer it.
        agentPanel: true,

        // Project status's Close Project, as File > Close Project.
        ...(closeProject ? { closeProject } : {}),
        ...(projects ? { projects } : {}),

        // The Log tab, all of it or one view's: what a view's "view log" opens.
        ...(showLog ? { showLog } : {}),

        // Kigumi's MCP server, which the views' options show and copy the setup of.
        mcp,

        async showMessage(level, text, ...actions) {
            if (actions.length === 0) {
                setStatus(level, text);
                return undefined;
            }
            const { response } = await dialog.showMessageBox(window, {
                type: level === 'warning' ? 'warning' : level === 'error' ? 'error' : 'info',
                message: text,
                buttons: [...actions, 'Close'],
                defaultId: 0,
                cancelId: actions.length,
            });
            return actions[response];
        },

        async confirm({ message, detail, action }) {
            const { response } = await dialog.showMessageBox(window, {
                type: 'question',
                message,
                detail,
                buttons: [action, 'Cancel'],
                defaultId: 0,
                cancelId: 1,
            });
            return response === 0;
        },

        openExternal: (url) => electronShell.openExternal(url),

        copyText: async (text) => clipboard.writeText(text),

        revealInFileManager: async (filePath) => electronShell.showItemInFolder(filePath),

        async openFileAt(filePath, line = 1) {
            openInEditor(filePath, line);
        },

        async showFile(filePath) {
            openInEditor(filePath, 1);
        },

        // The app shows sources on request only.
        async showSourceBesideViewer() {},

        runCommand,

    };
}

module.exports = { createElectronHost };
