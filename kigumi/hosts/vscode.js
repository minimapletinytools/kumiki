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

// The parts of a surface every VS Code webview shares.
function webviewSurface(webview, owner) {
    return {
        get cspSource() { return webview.cspSource; },
        setHtml(html) { webview.html = html; },
        resourceUri(absPath) { return webview.asWebviewUri(vscode.Uri.file(absPath)).toString(); },
        postMessage(message) { return Promise.resolve(webview.postMessage(message)); },
        onMessage(callback) { return webview.onDidReceiveMessage(callback); },
        onDispose(callback) { return owner.onDidDispose(callback); },
    };
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
    return Object.defineProperties(webviewSurface(panel.webview, panel), {
        title: { get: () => panel.title, set: (value) => { panel.title = value; } },
        active: { get: () => panel.active },
        visible: { get: () => panel.visible },
        reveal: { value: () => panel.reveal(panel.viewColumn, false) },
        dispose: { value: () => panel.dispose() },
    });
}

// Registers the sidebar webview view; `onSurface` gets a surface each time
// VS Code resolves it.
function registerSidebarView(context, viewId, resourceRoot, onSurface) {
    const provider = {
        resolveWebviewView(view) {
            view.webview.options = {
                enableScripts: true,
                localResourceRoots: [vscode.Uri.file(resourceRoot)],
            };
            onSurface(webviewSurface(view.webview, view));
        },
    };
    context.subscriptions.push(vscode.window.registerWebviewViewProvider(viewId, provider, {
        webviewOptions: { retainContextWhenHidden: true },
    }));
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

        runCommand(command, ...args) {
            return Promise.resolve(vscode.commands.executeCommand(command, ...args));
        },

        createViewerSurface,
    };
}

module.exports = { createVscodeHost, registerSidebarView };
