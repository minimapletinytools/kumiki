/** Provide workspace and viewer services for the browser shell. */

const fs = require('fs');
const path = require('path');
const { createMatcher } = require('../electron/glob-match');

function createBrowserHost({ connection, workspaceFolder, settings, runCommand, setStatus, setProgress }) {
    function watchFiles(baseDir, glob, { onCreate, onChange, onDelete } = {}) {
        const matches = createMatcher(glob);
        const watcher = fs.watch(baseDir, { recursive: glob.includes('/') }, (event, filename) => {
            if (!filename || !matches(String(filename).split(path.sep).join('/'))) return;
            const filePath = path.join(baseDir, String(filename));
            if (event === 'change') onChange?.(filePath);
            else if (fs.existsSync(filePath)) (onCreate || onChange)?.(filePath);
            else onDelete?.(filePath);
        });
        return { dispose: () => watcher.close() };
    }

    async function showFile(filePath) {
        const existing = connection.findPanel((panel) => panel.type === 'editor' && panel.filePath === filePath);
        if (existing) return existing.reveal();
        const stat = await fs.promises.stat(filePath);
        if (stat.size > 2 * 1024 * 1024 || !/\.(py|json|md|txt|toml|yaml|yml)$/i.test(filePath)) {
            setStatus('info', 'The web prototype previews text source files up to 2 MB.');
            return;
        }
        const escape = (text) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const source = escape(await fs.promises.readFile(filePath, 'utf8'));
        const panel = connection.createPanel('editor', { title: path.basename(filePath), filePath });
        panel.setHtml(`<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'self';"><link rel="stylesheet" href="/web-host/source.css"><title>Source</title></head><body><p>Source preview. Edit the file in your workspace to refresh the viewer.</p><pre>${source}</pre></body></html>`);
    }

    return {
        locale: 'en',
        showsFileBrowser: true,
        getConfig: (key, fallback) => settings.get(key, fallback),
        updateConfig: async (key, value) => settings.set(key, value),
        onConfigChange: (callback) => settings.onChange((key) => callback((candidate) => key === candidate)),
        workspaceRoots: () => [workspaceFolder],
        workspaceRootFor(filePath) {
            const relative = path.relative(workspaceFolder, filePath);
            return relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative)
                ? workspaceFolder : null;
        },
        async showMessage(level, text, ...actions) {
            setStatus(level, text);
            if (actions.length) {
                const picked = await connection.pick(actions.map((label) => ({ label })), text);
                return picked?.label;
            }
        },
        async confirm({ message, detail, action }) {
            const picked = await connection.pick([{ label: action }, { label: 'Cancel' }], `${message} ${detail || ''}`);
            return picked?.label === action;
        },
        async withProgress(title, task) {
            setProgress(title);
            try { return await task(); } finally { setProgress(null); }
        },
        async openExternal(url) {
            if (!/^https?:\/\//i.test(url)) throw new Error('Only HTTP links can be opened.');
            connection.send({ type: 'browser:external', url });
        },
        async copyText(text) { connection.send({ type: 'browser:clipboard', text }); },
        openFileAt: showFile,
        showFile,
        async showSourceBesideViewer() {},
        async getDocumentState(filePath) {
            return { isDirty: false, version: fs.statSync(filePath).mtimeMs, save: async () => true };
        },
        activeFile() {
            const filePath = connection.activePanel?.filePath;
            return filePath ? { filePath, languageId: filePath.endsWith('.py') ? 'python' : 'plaintext' } : null;
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
