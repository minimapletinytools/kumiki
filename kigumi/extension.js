const path = require('path');
const vscode = require('vscode');
const { FrameViewSession } = require('./frame-view-session');
const { KigumiSidebarProvider } = require('./sidebar-provider');
const { getInitializationStatus, initializeWorkspaceProject } = require('./project-initializer');

let outputChannel = null;
const frameSessions = new Map();       // filePath → FrameViewSession (main sessions)
const patternSessions = new Map();     // slotName → FrameViewSession (pattern sessions)
let patternSlotCounter = 0;
let sidebarProvider = null;
let openInSplitView = true;

/**
 * Main activation function for the Kigumi extension.
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('Kigumi');
    context.subscriptions.push(outputChannel);
    openInSplitView = vscode.workspace.getConfiguration('kigumi').get('viewer.openInSplitView', true);
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((event) => {
        if (event.affectsConfiguration('kigumi.viewer.openInSplitView')) {
            openInSplitView = vscode.workspace.getConfiguration('kigumi').get('viewer.openInSplitView', true);
        }
    }));

    sidebarProvider = new KigumiSidebarProvider(context, {
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
    context.subscriptions.push(explorerTreeView.onDidChangeSelection((event) => {
        const selected = event.selection && event.selection.length > 0 ? event.selection[0] : null;
        sidebarProvider.setSelectedElementData(selected);
    }));
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
        if (initStatus.projectStatus === 'local-dev') {
            vscode.window.showInformationMessage('Kigumi local development mode detected. Project initialization is disabled for this workspace.');
            await sidebarProvider.refresh(true);
            return;
        }
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

    const refreshPatterns = vscode.commands.registerCommand('kigumi.refreshPatterns', async () => {
        if (sidebarProvider) {
            await sidebarProvider.refreshPatterns(true);
        }
    });
    context.subscriptions.push(refreshPatterns);

    const toggleOpenInSplitView = vscode.commands.registerCommand('kigumi.toggleOpenInSplitView', async () => {
        openInSplitView = !openInSplitView;
        await vscode.workspace.getConfiguration('kigumi').update('viewer.openInSplitView', openInSplitView, vscode.ConfigurationTarget.Global);
        const mode = openInSplitView ? 'split view' : 'current view';
        vscode.window.showInformationMessage(`Kigumi open mode: ${mode}`);
    });
    context.subscriptions.push(toggleOpenInSplitView);

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

    // --- Toggle Group by Patternbook ---
    const toggleGroupByPatternbook = vscode.commands.registerCommand('kigumi.toggleGroupByPatternbook', async () => {
        if (sidebarProvider) {
            sidebarProvider.toggleGroupByPatternbook();
        }
    });
    context.subscriptions.push(toggleGroupByPatternbook);

    // --- Open Patternbook Group ---
    const openPatternbookGroup = vscode.commands.registerCommand('kigumi.openPatternbookGroup', async (groupData) => {
        if (!groupData || !groupData.patterns || groupData.patterns.length === 0) {
            vscode.window.showErrorMessage('Patternbook has no patterns.');
            return;
        }

        // Open the first pattern in the patternbook (which will load the whole patternbook)
        const firstPattern = groupData.patterns[0];
        if (!firstPattern || !firstPattern.sourceFile) {
            vscode.window.showErrorMessage('Cannot find pattern source file.');
            return;
        }

        try {
            let mainSession = _findAnyAliveMainSession();
            if (!mainSession) {
                // Open the source file in the viewer first
                await openFileInViewer(firstPattern.sourceFile, context);
                mainSession = frameSessions.get(firstPattern.sourceFile);
            }

            if (!mainSession || !mainSession.runnerSession || !mainSession.runnerSession.isAlive()) {
                vscode.window.showErrorMessage('Kigumi runner is not available. Open a frame first.');
                return;
            }

            // Open the entire patternbook by opening it without a specific pattern name
            await _openBookFromWebview(mainSession, firstPattern.sourceFile, context);
        } catch (error) {
            outputChannel.appendLine(`Open patternbook error: ${error.message}\n${error.stack}`);
            vscode.window.showErrorMessage(`Failed to open patternbook: ${error.message}`);
        }
    });
    context.subscriptions.push(openPatternbookGroup);

    // --- View Pattern Source ---
    const viewPatternSource = vscode.commands.registerCommand('kigumi.viewPatternSource', async (elementArg) => {
        const selectedElement = elementArg || sidebarProvider?.getSelectedElementData();
        if (!selectedElement || !selectedElement.data || !selectedElement.data.sourceFile) {
            vscode.window.showErrorMessage('Please select a pattern first.');
            return;
        }

        const patternData = selectedElement.data;
        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot) {
            vscode.window.showErrorMessage('Open a workspace folder first.');
            return;
        }

        try {
            const { viewShippedPatternSource } = require('./pattern-source-utils');
            
            // Check if the file is in workspace or from dependencies
            const isInWorkspace = patternData.sourceFile.startsWith(workspaceRoot);
            
            if (isInWorkspace) {
                // Open workspace file directly
                const uri = vscode.Uri.file(patternData.sourceFile);
                const doc = await vscode.workspace.openTextDocument(uri);
                await vscode.window.showTextDocument(doc);
            } else {
                // Create read-only copy in workspace
                const readOnlyPath = await viewShippedPatternSource(patternData.sourceFile, workspaceRoot);
                const uri = vscode.Uri.file(readOnlyPath);
                const doc = await vscode.workspace.openTextDocument(uri);
                const editor = await vscode.window.showTextDocument(doc);
                vscode.window.showInformationMessage(`Opened read-only copy of pattern. Edit the original or create a new pattern.`);
            }
        } catch (error) {
            outputChannel.appendLine(`View source error: ${error.message}\n${error.stack}`);
            vscode.window.showErrorMessage(`Failed to view pattern source: ${error.message}`);
        }
    });
    context.subscriptions.push(viewPatternSource);

    // --- Duplicate Pattern to Workspace ---
    const duplicatePatternToWorkspace = vscode.commands.registerCommand('kigumi.duplicatePatternToWorkspace', async (elementArg) => {
        const selectedElement = elementArg || sidebarProvider?.getSelectedElementData();
        if (!selectedElement || !selectedElement.data || !selectedElement.data.sourceFile) {
            vscode.window.showErrorMessage('Please select a pattern first.');
            return;
        }

        const patternData = selectedElement.data;
        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot) {
            vscode.window.showErrorMessage('Open a workspace folder first.');
            return;
        }

        try {
            const { duplicatePatternToWorkspace: duplicateFn } = require('./pattern-source-utils');
            const newPath = await duplicateFn(patternData.sourceFile, workspaceRoot);
            
            const uri = vscode.Uri.file(newPath);
            const doc = await vscode.workspace.openTextDocument(uri);
            await vscode.window.showTextDocument(doc);
            
            vscode.window.showInformationMessage(`Pattern duplicated to: ${path.relative(workspaceRoot, newPath)}`);
            
            // Refresh sidebar to show the new pattern
            if (sidebarProvider) {
                await sidebarProvider.refreshPatterns(true);
            }
        } catch (error) {
            outputChannel.appendLine(`Duplicate pattern error: ${error.message}\n${error.stack}`);
            vscode.window.showErrorMessage(`Failed to duplicate pattern: ${error.message}`);
        }
    });
    context.subscriptions.push(duplicatePatternToWorkspace);

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
                    openInSplitView,
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
            openInSplitView,
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
            openInSplitView,
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
        { slotName: 'main', sessionType: 'main', openInSplitView }
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
