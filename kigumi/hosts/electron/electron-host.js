/**
 * The Host (see ../../host.js) for the standalone Electron app.
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { dialog, shell: electronShell } = require('electron');
const { createMatcher } = require('./glob-match');

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

function languageOf(filePath) {
    return filePath && filePath.endsWith('.py') ? 'python' : 'plaintext';
}

/**
 * @param {object} options
 * @param {import('./shell').Shell} options.shell
 * @param {import('./settings-store').SettingsStore} options.settings
 * @param {string|null} options.workspaceFolder
 * @param {string} options.locale
 * @param {(line: string) => void} options.log
 * @param {(command: string, ...args: any[]) => Promise<any>} options.runCommand
 * @param {(level: string, text: string) => void} options.setStatus
 * @param {(title: string|null) => void} options.setProgress
 */
function createElectronHost({ shell, settings, workspaceFolder, locale, log, runCommand, setStatus, setProgress }) {
    function openInEditor(filePath, line = 1) {
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

    function watchFiles(baseDir, glob, { onCreate, onChange, onDelete } = {}) {
        if (!baseDir || !fs.existsSync(baseDir)) {
            return { dispose() {} };
        }
        const matches = createMatcher(glob);
        let watcher;
        try {
            watcher = fs.watch(baseDir, { recursive: glob.includes('/') }, (eventType, filename) => {
                if (!filename) return;
                const relative = filename.toString().split(path.sep).join('/');
                if (!matches(relative)) return;
                const fsPath = path.join(baseDir, filename.toString());
                if (eventType === 'change') {
                    if (onChange) onChange(fsPath);
                } else if (fs.existsSync(fsPath)) {
                    // Editors often save by replacing the file, which arrives as a rename.
                    (onCreate || onChange || (() => {}))(fsPath);
                } else if (onDelete) {
                    onDelete(fsPath);
                }
            });
        } catch (error) {
            log(`[watch] Could not watch ${baseDir}: ${error.message}`);
            return { dispose() {} };
        }
        return { dispose: () => watcher.close() };
    }

    return {
        locale,

        getConfig: (key, fallback) => settings.get(key, fallback),

        updateConfig: async (key, value) => settings.set(key, value),

        onConfigChange: (callback) => settings.onChange((changedKey) => callback((key) => key === changedKey)),

        workspaceRoots: () => (workspaceFolder ? [workspaceFolder] : []),

        workspaceRootFor(filePath) {
            if (!workspaceFolder) return null;
            const relative = path.relative(workspaceFolder, filePath);
            return relative && !relative.startsWith('..') && !path.isAbsolute(relative) ? workspaceFolder : null;
        },

        async showMessage(level, text, ...actions) {
            if (actions.length === 0) {
                setStatus(level, text);
                return undefined;
            }
            const { response } = await dialog.showMessageBox(shell.window, {
                type: level === 'warning' ? 'warning' : level === 'error' ? 'error' : 'info',
                message: text,
                buttons: [...actions, 'Close'],
                defaultId: 0,
                cancelId: actions.length,
            });
            return actions[response];
        },

        async confirm({ message, detail, action }) {
            const { response } = await dialog.showMessageBox(shell.window, {
                type: 'question',
                message,
                detail,
                buttons: [action, 'Cancel'],
                defaultId: 0,
                cancelId: 1,
            });
            return response === 0;
        },

        async withProgress(title, task) {
            setProgress(title);
            try {
                return await task();
            } finally {
                setProgress(null);
            }
        },

        openExternal: (url) => electronShell.openExternal(url),

        async openFileAt(filePath, line = 1) {
            openInEditor(filePath, line);
        },

        async showFile(filePath) {
            openInEditor(filePath, 1);
        },

        // The app shows sources on request only.
        async showSourceBesideViewer() {},

        async getDocumentState(filePath) {
            let version = 0;
            try {
                version = fs.statSync(filePath).mtimeMs;
            } catch (_error) {
                version = 0;
            }
            return { isDirty: false, version, save: async () => true };
        },

        activeFile() {
            const surface = shell.activeSurface;
            return surface && surface.filePath
                ? { filePath: surface.filePath, languageId: languageOf(surface.filePath) }
                : null;
        },

        async pickOne(items, { placeholder } = {}) {
            return shell.pick(items, placeholder);
        },

        watchFiles,

        // Every save of a Python file in the workspace.
        onDocumentChange(callback) {
            return watchFiles(workspaceFolder, '**/*.py', {
                onChange: (filePath) => callback({ filePath, languageId: 'python', isDirty: false, saved: true }),
            });
        },

        runCommand,

        createViewerSurface({ title, filePath }) {
            return shell.createTab({ kind: 'viewer', title, filePath });
        },
    };
}

module.exports = { createElectronHost };
