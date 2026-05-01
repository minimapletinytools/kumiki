const vscode = require('vscode');
const { FrameViewSession } = require('./frame-view-session');
const { KigumiSidebarProvider } = require('./sidebar-provider');
const { getInitializationStatus, initializeWorkspaceProject } = require('./project-initializer');

let outputChannel = null;
const frameSessions = new Map();       // filePath → FrameViewSession (main sessions)
const patternSessions = new Map();     // slotName → FrameViewSession (pattern sessions)
let patternSlotCounter = 0;
let sidebarProvider = null;

/**
 * Main activation function for the Kigumi extension.
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('Kigumi');
    context.subscriptions.push(outputChannel);

    sidebarProvider = new KigumiSidebarProvider(context, {
        getPatternSources: async (forceRescan) => {
            const mainSession = _findAnyAliveMainSession();
            if (!mainSession || !mainSession.runnerSession || !mainSession.runnerSession.isAlive()) {
                return { sources: [] };
            }
            return mainSession.runnerSession.request(
                'list_available_patterns',
                forceRescan ? { rescan: true } : {}
            );
        },
        getPythonCommand: () => {
            const mainSession = _findAnyAliveMainSession();
            if (!mainSession || !mainSession.runnerSession || !mainSession.runnerSession.isAlive()) {
                return undefined;
            }
            return mainSession.runnerSession.getPythonCommand();
        },
    });

    const explorerTreeView = vscode.window.createTreeView('kigumi.explorer', {
        treeDataProvider: sidebarProvider,
        showCollapseAll: true,
    });
    context.subscriptions.push(sidebarProvider, explorerTreeView);

    const disposable = vscode.commands.registerCommand('kigumi.render', async function () {
        try {
            await renderActiveEditor(context);
        } catch (error) {
            outputChannel.show(true);
            if (!error || !error.kigumiErrorNotified) {
                vscode.window.showErrorMessage(`Kigumi error: ${error.message}`);
            }
        }
    });

    context.subscriptions.push(disposable);

    const openCurrentFileInViewer = vscode.commands.registerCommand('kigumi.openCurrentFileInViewer', async () => {
        try {
            await renderActiveEditor(context);
        } catch (error) {
            outputChannel.show(true);
            vscode.window.showErrorMessage(`Open current file failed: ${error.message || error}`);
        }
    });
    context.subscriptions.push(openCurrentFileInViewer);

    const initializeProjectInWorkspace = vscode.commands.registerCommand('kigumi.initializeProjectInWorkspace', async () => {
        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot) {
            vscode.window.showErrorMessage('Open a workspace folder first.');
            return;
        }

        const initStatus = getInitializationStatus(workspaceRoot);
        if (initStatus.isInitialized) {
            vscode.window.showInformationMessage('Kigumi project is already initialized in this workspace.');
            await sidebarProvider.refresh(true);
            return;
        }

        try {
            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: 'Initializing Kigumi project',
                cancellable: false,
            }, async () => {
                await initializeWorkspaceProject(workspaceRoot);
            });
            vscode.window.showInformationMessage('Kigumi workspace initialized.');
        } catch (error) {
            outputChannel.show(true);
            vscode.window.showErrorMessage(`Initialize project failed: ${error.message || error}`);
        } finally {
            await sidebarProvider.refresh(true);
        }
    });
    context.subscriptions.push(initializeProjectInWorkspace);

    const refreshSidebar = vscode.commands.registerCommand('kigumi.refreshSidebar', async () => {
        if (sidebarProvider) {
            await sidebarProvider.refresh(true);
        }
    });
    context.subscriptions.push(refreshSidebar);

    const openFrameFromSidebar = vscode.commands.registerCommand('kigumi.openFrameFromSidebar', async (filePath) => {
        await openFileInViewer(filePath, context);
    });
    context.subscriptions.push(openFrameFromSidebar);

    const openPatternFromSidebar = vscode.commands.registerCommand('kigumi.openPatternFromSidebar', async (patternRecord) => {
        const sourceFile = patternRecord && patternRecord.sourceFile;
        const patternName = patternRecord && patternRecord.patternName;
        if (!sourceFile) {
            vscode.window.showErrorMessage('Pattern entry is missing a source file.');
            return;
        }

        let mainSession = _findAnyAliveMainSession();
        if (!mainSession) {
            if (!patternName) {
                await openFileInViewer(sourceFile, context);
                return;
            }
            await openFileInViewer(sourceFile, context);
            mainSession = frameSessions.get(sourceFile);
        }

        if (!mainSession || !mainSession.runnerSession || !mainSession.runnerSession.isAlive()) {
            vscode.window.showErrorMessage('Kigumi runner is not available. Open a frame first.');
            return;
        }

        if (patternName) {
            await _openPatternFromWebview(mainSession, patternName, sourceFile, context);
            return;
        }

        await _openBookFromWebview(mainSession, sourceFile, context);
    });
    context.subscriptions.push(openPatternFromSidebar);

    const openExampleFromSidebar = vscode.commands.registerCommand('kigumi.openExampleFromSidebar', async (sourceFile) => {
        await openFileInViewer(sourceFile, context);
    });
    context.subscriptions.push(openExampleFromSidebar);

    // --- Browse Patterns command ---
    const browsePatterns = vscode.commands.registerCommand('kigumi.browsePatterns', async function () {
        try {
            // We need a running main session to query patterns via its runner process.
            // If none exists, try to create one from the active editor.
            let mainSession = _findAnyAliveMainSession();
            if (!mainSession) {
                const editor = vscode.window.activeTextEditor;
                if (!editor || editor.document.languageId !== 'python') {
                    vscode.window.showErrorMessage('Open a Python file first, then run Render Kigumi before browsing patterns.');
                    return;
                }
                if (editor.document.isDirty) {
                    await editor.document.save();
                }
                mainSession = await getOrCreateSession(editor.document.fileName, context);
            }

            const runner = mainSession.runnerSession;
            if (!runner || !runner.isAlive()) {
                vscode.window.showErrorMessage('Kigumi runner is not running. Run Render Kigumi first.');
                return;
            }

            // Query available patterns
            const result = await runner.request('list_available_patterns');
            if (!result || !result.sources || result.sources.length === 0) {
                vscode.window.showInformationMessage('No patterns found in shipped library or local project.');
                return;
            }

            // Build QuickPick items
            const items = [];
            for (const source of result.sources) {
                const sourceLabel = source.source === 'shipped' ? 'Shipped Library' : 'Local Project';
                items.push({ label: sourceLabel, kind: vscode.QuickPickItemKind.Separator });
                for (const pattern of source.patterns) {
                    const groupsStr = pattern.groups.length > 0 ? ` (${pattern.groups.join(', ')})` : '';
                    items.push({
                        label: pattern.name,
                        description: `${sourceLabel}${groupsStr}`,
                        detail: pattern.source_file,
                        _sourceFile: pattern.source_file,
                        _patternName: pattern.name,
                    });
                }
            }

            const picked = await vscode.window.showQuickPick(items, {
                placeHolder: 'Select a pattern to view',
                matchOnDescription: true,
                matchOnDetail: true,
            });
            if (!picked || !picked._patternName) {
                return;
            }

            // Open pattern in a new slot
            patternSlotCounter += 1;
            const slotName = `pattern_${patternSlotCounter}`;

            // Load the pattern into the shared runner
            await runner.request('raise_specific_pattern', {
                slot: slotName,
                sourceFile: picked._sourceFile,
                patternName: picked._patternName,
            });

            // Create a FrameViewSession that shares the main runner
            const patternSession = new FrameViewSession(
                picked._sourceFile,
                context,
                outputChannel,
                (_filePath, disposedSlotName) => {
                    if (patternSessions.get(disposedSlotName) === patternSession) {
                        patternSessions.delete(disposedSlotName);
                    }
                },
                {
                    slotName,
                    sessionType: 'pattern',
                    sharedRunner: runner,
                    patternName: picked._patternName,
                }
            );
            patternSessions.set(slotName, patternSession);
            await patternSession.initialize();
            patternSession.reveal();
            await patternSession.refresh('pattern open');
        } catch (error) {
            outputChannel.show(true);
            if (!error || !error.kigumiErrorNotified) {
                vscode.window.showErrorMessage(`Browse Patterns error: ${error.message}`);
            }
        }
    });

    context.subscriptions.push(browsePatterns);

    // --- Unload Pattern command ---
    const unloadPattern = vscode.commands.registerCommand('kigumi.unloadPattern', async function () {
        if (patternSessions.size === 0) {
            vscode.window.showInformationMessage('No pattern viewers are open.');
            return;
        }

        const items = [];
        for (const [slotName, session] of patternSessions) {
            const label = session.patternName || slotName;
            items.push({ label, description: slotName, _slotName: slotName });
        }

        const picked = await vscode.window.showQuickPick(items, {
            placeHolder: 'Select a pattern to unload',
        });
        if (!picked) {
            return;
        }

        const session = patternSessions.get(picked._slotName);
        if (session) {
            await session.dispose();
        }
    });

    context.subscriptions.push(unloadPattern);

    const screenshotDisposable = vscode.commands.registerCommand(
        'kigumi.captureRenderedScreenshot',
        async (options = {}) => {
            const targetFilePath =
                typeof options.filePath === 'string' && options.filePath
                    ? options.filePath
                    : vscode.window.activeTextEditor && vscode.window.activeTextEditor.document
                        ? vscode.window.activeTextEditor.document.fileName
                        : null;

            if (!targetFilePath) {
                throw new Error('No target file path available for screenshot capture');
            }

            const session = frameSessions.get(targetFilePath);
            if (!session || session.isDisposed) {
                throw new Error(`No active Kigumi session for ${targetFilePath}`);
            }

            const timeoutMs =
                typeof options.timeoutMs === 'number' ? options.timeoutMs : undefined;
            const outputPath =
                typeof options.outputPath === 'string' && options.outputPath ? options.outputPath : undefined;

            return session.captureScreenshot({ timeoutMs, outputPath });
        }
    );

    context.subscriptions.push(screenshotDisposable);
    context.subscriptions.push({
        dispose: async () => {
            const allSessions = [
                ...Array.from(frameSessions.values()),
                ...Array.from(patternSessions.values()),
            ];
            frameSessions.clear();
            patternSessions.clear();
            await Promise.allSettled(allSessions.map((session) => session.dispose()));
        },
    });
}

function getWorkspaceRoot() {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
        return null;
    }
    return folders[0].uri.fsPath;
}

async function renderActiveEditor(context) {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor!');
        return;
    }

    const document = editor.document;
    if (document.languageId !== 'python') {
        vscode.window.showErrorMessage('Current file is not a Python file!');
        return;
    }

    if (document.isDirty) {
        await document.save();
    }

    const filePath = document.fileName;
    const session = await getOrCreateSession(filePath, context);
    session.reveal();
    await session.refresh();

    if (sidebarProvider) {
        await sidebarProvider.refresh(false);
    }
}

async function openFileInViewer(filePath, context) {
    if (!filePath || typeof filePath !== 'string') {
        vscode.window.showErrorMessage('No file path provided.');
        return;
    }

    const uri = vscode.Uri.file(filePath);
    const document = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(document, { preview: false });
    await renderActiveEditor(context);
}

/**
 * Find any alive main session (for reusing its runner).
 */
function _findAnyAliveMainSession() {
    for (const session of frameSessions.values()) {
        if (!session.isDisposed && session.runnerSession && session.runnerSession.isAlive()) {
            return session;
        }
    }
    return null;
}

/**
 * Open a pattern viewer triggered from the webview pattern list.
 */
async function _openPatternFromWebview(mainSession, patternName, sourceFile, context) {
    const runner = mainSession.runnerSession;
    if (!runner || !runner.isAlive()) {
        vscode.window.showErrorMessage('Kigumi runner is not running.');
        return;
    }

    patternSlotCounter += 1;
    const slotName = `pattern_${patternSlotCounter}`;

    await runner.request('raise_specific_pattern', {
        slot: slotName,
        sourceFile,
        patternName,
    });

    const patternSession = new FrameViewSession(
        sourceFile,
        context,
        outputChannel,
        (_filePath, disposedSlotName) => {
            if (patternSessions.get(disposedSlotName) === patternSession) {
                patternSessions.delete(disposedSlotName);
            }
        },
        {
            slotName,
            sessionType: 'pattern',
            sharedRunner: runner,
            patternName,
        }
    );
    patternSessions.set(slotName, patternSession);
    await patternSession.initialize();
    patternSession.reveal();
    await patternSession.refresh('pattern open from webview');
}

/**
 * Open a whole pattern book as one tab (renders the file's example/patternbook).
 */
async function _openBookFromWebview(mainSession, sourceFile, context) {
    const runner = mainSession.runnerSession;
    if (!runner || !runner.isAlive()) {
        vscode.window.showErrorMessage('Kigumi runner is not running.');
        return;
    }

    patternSlotCounter += 1;
    const slotName = `pattern_${patternSlotCounter}`;
    const bookName = sourceFile.replace(/\\/g, '/').split('/').pop().replace(/\.py$/, '');

    // Load the whole file into a slot (uses resolve_frame_from_module → renders all patterns)
    await runner.request('load_slot', {
        slot: slotName,
        filePath: sourceFile,
    });

    const patternSession = new FrameViewSession(
        sourceFile,
        context,
        outputChannel,
        (_filePath, disposedSlotName) => {
            if (patternSessions.get(disposedSlotName) === patternSession) {
                patternSessions.delete(disposedSlotName);
            }
        },
        {
            slotName,
            sessionType: 'pattern',
            sharedRunner: runner,
            patternName: bookName,
        }
    );
    patternSessions.set(slotName, patternSession);
    await patternSession.initialize();
    patternSession.reveal();
    await patternSession.refresh('book open from webview');
}

/**
 * Get or create a session for the given file path.
 * Reuses an existing session for the same file or creates a new panel/session.
 */
async function getOrCreateSession(filePath, context) {
    const existingSession = frameSessions.get(filePath);
    if (existingSession && !existingSession.isDisposed) {
        return existingSession;
    }

    const session = new FrameViewSession(
        filePath,
        context,
        outputChannel,
        (disposedFilePath) => {
            if (frameSessions.get(disposedFilePath) === session) {
                frameSessions.delete(disposedFilePath);
            }
        },
        { slotName: 'main', sessionType: 'main' }
    );
    session.onLoadPattern = async (patternName, sourceFile) => {
        await _openPatternFromWebview(session, patternName, sourceFile, context);
    };
    session.onLoadBook = async (sourceFile) => {
        await _openBookFromWebview(session, sourceFile, context);
    };
    frameSessions.set(filePath, session);
    await session.initialize();
    return session;
}

async function deactivate() {
    const allSessions = [
        ...Array.from(frameSessions.values()),
        ...Array.from(patternSessions.values()),
    ];
    frameSessions.clear();
    patternSessions.clear();
    await Promise.allSettled(allSessions.map((session) => session.dispose()));
}

module.exports = {
    activate,
    deactivate,
};
