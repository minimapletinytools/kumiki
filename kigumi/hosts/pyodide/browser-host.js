/**
 * The Host (see ../../host.js) for Kigumi in a browser: the server side of the web host. Files open
 * in the shared code editor tabs; links and the clipboard go to the browser.
 */

const fs = require('fs');
const path = require('path');
const { createMatcher } = require('../electron/glob-match');

function languageOf(filePath) {
    return filePath && filePath.endsWith('.py') ? 'python' : 'plaintext';
}

/**
 * @param {object} options
 * @param {import('../../app-shell/shell-connection').ShellConnection} options.connection
 * @param {string|null} options.workspaceFolder  the open project's working folder
 * @param {import('../electron/settings-store').SettingsStore} options.settings
 * @param {(command: string, ...args: any[]) => Promise<any>} options.runCommand
 * @param {(level: string, text: string) => void} options.setStatus
 * @param {(title: string|null) => void} options.setProgress
 * @param {{ open: (filePath: string, line?: number) => any }} options.editors  app-shell/editor-tabs.js
 * @param {(options: {source?: string}) => void} [options.showLog]
 * @param {(line: string) => void} [options.log]
 * @param {boolean} [options.agentPanel]  whether the agent panel can be turned on
 * @param {object} [options.mcp]  Kigumi's MCP server's controls (agent/mcp-service.js)
 * @param {object} [options.projects]  opening a project (host.js `projects`)
 */
function createBrowserHost({ connection, workspaceFolder, settings, runCommand, setStatus, setProgress, editors,
    showLog = null, log = () => {}, agentPanel = false, mcp = null, closeProject = null, projects = null }) {
    function watchFiles(baseDir, glob, { onCreate, onChange, onDelete } = {}) {
        if (!baseDir || !fs.existsSync(baseDir)) {
            return { dispose() {} };
        }
        const matches = createMatcher(glob);
        let watcher;
        try {
            watcher = fs.watch(baseDir, { recursive: glob.includes('/') }, (event, filename) => {
                if (!filename) return;
                const relative = String(filename).split(path.sep).join('/');
                if (!matches(relative)) return;
                const filePath = path.join(baseDir, String(filename));
                if (event === 'change') {
                    if (onChange) onChange(filePath);
                } else if (fs.existsSync(filePath)) {
                    (onCreate || onChange || (() => {}))(filePath);
                } else if (onDelete) {
                    onDelete(filePath);
                }
            });
        } catch (error) {
            log(`[watch] Could not watch ${baseDir}: ${error.message}`);
            return { dispose() {} };
        }
        return { dispose: () => watcher.close() };
    }

    return {
        locale: 'en',
        showsFileBrowser: true,
        agentPanel,
        // Kigumi's MCP server, which the views' options turn on and copy the setup of.
        ...(mcp ? { mcp } : {}),
        // Project status's Close Project: back to the projects page.
        ...(closeProject ? { closeProject } : {}),
        // Project status's Open Project and recent projects, with none open.
        ...(projects ? { projects } : {}),
        ...(showLog ? { showLog } : {}),
        getConfig: (key, fallback) => settings.get(key, fallback),
        updateConfig: async (key, value) => settings.set(key, value),
        onConfigChange: (callback) => settings.onChange((key) => callback((candidate) => key === candidate)),
        workspaceRoots: () => (workspaceFolder ? [workspaceFolder] : []),
        workspaceRootFor(filePath) {
            if (!workspaceFolder) return null;
            const relative = path.relative(workspaceFolder, filePath);
            return relative && !relative.startsWith('..') && !path.isAbsolute(relative) ? workspaceFolder : null;
        },
        async showMessage(level, text, ...actions) {
            setStatus(level, text);
            if (actions.length) {
                const picked = await connection.pick(actions.map((label) => ({ label })), text);
                return picked ? picked.label : undefined;
            }
            return undefined;
        },
        async confirm({ message, detail, action }) {
            const picked = await connection.pick([{ label: action }, { label: 'Cancel' }], `${message} ${detail || ''}`.trim());
            return Boolean(picked && picked.label === action);
        },
        async withProgress(title, task) {
            setProgress(title);
            try {
                return await task();
            } finally {
                setProgress(null);
            }
        },
        async openExternal(url) {
            if (!/^https?:\/\//i.test(url)) throw new Error('Only web links can be opened.');
            connection.send({ type: 'browser:external', url });
        },
        async copyText(text) {
            connection.send({ type: 'browser:clipboard', text });
        },
        // The browser can't show the server's folders; the explorer lists the project's files.
        async revealInFileManager() {
            setStatus('info', 'The browser keeps your project; its files are listed under All Files in the explorer.');
        },
        async openFileAt(filePath, line = 1) {
            editors.open(filePath, line);
        },
        async showFile(filePath) {
            editors.open(filePath, 1);
        },
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
            const surface = connection.activePanel;
            return surface && surface.filePath ? { filePath: surface.filePath, languageId: languageOf(surface.filePath) } : null;
        },
        pickOne: (items, options = {}) => connection.pick(items, options.placeholder),
        watchFiles,
        onDocumentChange(callback) {
            return watchFiles(workspaceFolder, '**/*.py', {
                onChange: (filePath) => callback({ filePath, languageId: 'python', isDirty: false, saved: true }),
            });
        },
        runCommand,
        createViewerSurface: ({ title, filePath }) => connection.createPanel('viewer', { title, filePath }),
    };
}

module.exports = { createBrowserHost };
