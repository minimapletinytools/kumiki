const path = require('path');
const { createPanelInspection } = require('./panel-inspection');
const { createFileWatch } = require('./file-watch');

/** Return the editor, panel, settings and workspace services shared by shell hosts. */
function createShellHostServices({ connection, settings, workspaceFolder, documents, setProgress, log }) {
    const watchFiles = createFileWatch(log);
    return {
        ...createPanelInspection(connection),
        getConfig: (key, fallback) => settings.get(key, fallback),
        updateConfig: async (key, value) => settings.set(key, value),
        onConfigChange: (callback) => settings.onChange((key) => callback((candidate) => key === candidate)),
        workspaceRoots: () => workspaceFolder ? [workspaceFolder] : [],
        workspaceRootFor(filePath) {
            if (!workspaceFolder) return null;
            const relative = path.relative(workspaceFolder, filePath);
            return relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative)
                ? workspaceFolder : null;
        },
        getDocumentState: (filePath) => documents.getDocumentState(filePath),
        onDocumentChange(callback) {
            const buffer = documents.onDocumentChange(callback);
            const disk = watchFiles(workspaceFolder, '**/*.py', {
                onChange: (filePath) => {
                    if (![...documents.tabs.values()].some((tab) => tab.filePath === filePath)) {
                        callback({ filePath, languageId: 'python', isDirty: false, saved: true });
                    }
                },
            });
            return { dispose() { buffer.dispose(); disk.dispose(); } };
        },
        activeFile() {
            const panel = connection.activePanel;
            return panel && panel.filePath ? { filePath: panel.filePath,
                languageId: panel.filePath.endsWith('.py') ? 'python' : 'plaintext' } : null;
        },
        async withProgress(title, task) {
            setProgress(title);
            try { return await task(); } finally { setProgress(null); }
        },
        askText: (options) => connection.ask(options),
        pickOne: (items, options = {}) => connection.pick(items, options.placeholder),
        watchFiles,
        createViewerSurface: ({ title, filePath }) => connection.createPanel('viewer', { title, filePath }),
    };
}

module.exports = { createShellHostServices };
