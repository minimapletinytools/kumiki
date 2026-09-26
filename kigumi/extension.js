const vscode = require('vscode');
const { setHost } = require('./host');
const { createVscodeHost, registerSidebarView } = require('./hosts/vscode');
const { createKigumiApp } = require('./kigumi-app');
const { webviewDir } = require('./webview-html');

const BUILD_MARKER = '🧪 KIGUMI_BUILD_2026-05-17T02:45Z';
const ENABLE_TEST_COMMANDS = process.env.KIGUMI_ENABLE_TEST_COMMANDS === '1';

let app = null;

function activate(context) {
    setHost(createVscodeHost());
    const outputChannel = vscode.window.createOutputChannel('Kigumi');
    context.subscriptions.push(outputChannel);
    const extensionVersion = (context.extension && context.extension.packageJSON && context.extension.packageJSON.version)
        ? context.extension.packageJSON.version
        : 'unknown';
    outputChannel.appendLine(`[kigumi] ${BUILD_MARKER} (extension v${extensionVersion})`);

    app = createKigumiApp({
        extensionPath: context.extensionPath,
        storagePath: context.globalStorageUri.fsPath,
        channel: outputChannel,
        enableTestCommands: ENABLE_TEST_COMMANDS,
    });
    context.subscriptions.push({ dispose: () => app && app.dispose() });

    for (const [id, handler] of Object.entries(app.commands)) {
        context.subscriptions.push(vscode.commands.registerCommand(id, handler));
    }
    context.subscriptions.push(vscode.commands.registerCommand('kigumi.explorer', () => (
        vscode.commands.executeCommand('workbench.view.extension.kigumi')
    )));

    registerSidebarView(context, 'kigumi.explorer', webviewDir, (surface) => app.sidebarController.attach(surface));

    // Drives the split-view icon's `when` clause.
    const setSplitViewContext = () => vscode.commands.executeCommand('setContext', 'kigumi.splitViewEnabled', app.openInSplitView);
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((event) => {
        if (event.affectsConfiguration('kigumi.viewer.openInSplitView')) {
            void setSplitViewContext();
        }
    }));
    void setSplitViewContext();
}

async function deactivate() {
    if (app) {
        const current = app;
        app = null;
        await current.dispose();
    }
}

module.exports = {
    activate,
    deactivate,
};
