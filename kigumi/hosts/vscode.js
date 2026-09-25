/**
 * The Host (see ../host.js) backed by the VS Code extension API.
 */

const vscode = require('vscode');

const SHOW_MESSAGE = {
    info: (...args) => vscode.window.showInformationMessage(...args),
    warning: (...args) => vscode.window.showWarningMessage(...args),
    error: (...args) => vscode.window.showErrorMessage(...args),
};

function existingWorkspaceFolders() {
    return (vscode.workspace.workspaceFolders || []).filter((folder) => folder && folder.uri);
}

function createViewerSurface({ title, beside, resourceRoot }) {
    const panel = vscode.window.createWebviewPanel(
        'kigumiViewer',
        title,
        beside ? vscode.ViewColumn.Beside : vscode.ViewColumn.Active,
        {
            enableScripts: true,
            retainContextWhenHidden: true,
            localResourceRoots: [vscode.Uri.file(resourceRoot)],
        }
    );
    return {
        get title() { return panel.title; },
        set title(value) { panel.title = value; },
        get active() { return panel.active; },
        get visible() { return panel.visible; },
        get cspSource() { return panel.webview.cspSource; },
        setHtml(html) { panel.webview.html = html; },
        resourceUri(absPath) { return panel.webview.asWebviewUri(vscode.Uri.file(absPath)).toString(); },
        postMessage(message) { return Promise.resolve(panel.webview.postMessage(message)); },
        onMessage(callback) { return panel.webview.onDidReceiveMessage(callback); },
        onDispose(callback) { return panel.onDidDispose(callback); },
        reveal() { panel.reveal(panel.viewColumn, false); },
        dispose() { panel.dispose(); },
    };
}

function createVscodeHost() {
    return {
        get locale() {
            return vscode.env && vscode.env.language;
        },

        getConfig(key, fallback) {
            return vscode.workspace.getConfiguration('kigumi').get(key, fallback);
        },

        workspaceRoots() {
            return existingWorkspaceFolders().map((folder) => folder.uri.fsPath);
        },

        workspaceRootFor(filePath) {
            const folder = vscode.workspace.getWorkspaceFolder(vscode.Uri.file(filePath));
            return folder && folder.uri ? folder.uri.fsPath : null;
        },

        showMessage(level, text, ...actions) {
            return Promise.resolve(SHOW_MESSAGE[level](text, ...actions));
        },

        async openFileAt(filePath, line = 1) {
            const document = await vscode.workspace.openTextDocument(vscode.Uri.file(filePath));
            const editor = await vscode.window.showTextDocument(document, { preview: false });
            const lineIndex = Math.max(0, line - 1);
            const range = new vscode.Range(lineIndex, 0, lineIndex, 0);
            editor.selection = new vscode.Selection(range.start, range.end);
            editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
        },

        async getDocumentState(filePath) {
            const document = await vscode.workspace.openTextDocument(vscode.Uri.file(filePath));
            return {
                isDirty: document.isDirty,
                version: document.version,
                save: () => Promise.resolve(document.save()),
            };
        },

        watchFiles(baseDir, glob, { onCreate, onChange, onDelete } = {}) {
            const watcher = vscode.workspace.createFileSystemWatcher(
                new vscode.RelativePattern(baseDir, glob),
                !onCreate,
                !onChange,
                !onDelete,
            );
            const toPath = (handler) => (uri) => handler(uri && uri.fsPath);
            if (onCreate) watcher.onDidCreate(toPath(onCreate));
            if (onChange) watcher.onDidChange(toPath(onChange));
            if (onDelete) watcher.onDidDelete(toPath(onDelete));
            return watcher;
        },

        createViewerSurface,
    };
}

module.exports = { createVscodeHost };
