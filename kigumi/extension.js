const path = require('path');
const fs = require('fs');
const vscode = require('vscode');
const { FrameViewSession } = require('./frame-view-session');
const { KigumiSidebarProvider } = require('./sidebar-provider');
const { normalizeRetentionDays, pruneOldLogFiles } = require('./log-retention');
const {
    getInitializationStatus,
    initializeWorkspaceProject,
    updateWorkspaceKumiki,
    isInitializationInProgress,
    getWorkspaceKumikiVersionInfo,
} = require('./project-initializer');

let outputChannel = null;
const frameSessions = new Map();       // filePath → FrameViewSession (main sessions)
const patternSessions = new Map();     // slotName → FrameViewSession (pattern sessions)
let patternSlotCounter = 0;
let sidebarProvider = null;
let openInSplitView = true;
let autoRefreshOnFileChange = false;
let logRetentionDays = 15;
const BUILD_MARKER = '🧪 KIGUMI_BUILD_2026-05-17T02:45Z';
const ENABLE_TEST_COMMANDS = process.env.KIGUMI_ENABLE_TEST_COMMANDS === '1';

function _extractSourcePathFromSidebarElement(element) {
    if (!element || !element.data) {
        return null;
    }
    const data = element.data;
    if (typeof data.sourceFile === 'string' && data.sourceFile) {
        return data.sourceFile;
    }
    if (typeof data.filePath === 'string' && data.filePath) {
        return data.filePath;
    }
    if (data.patternbook && typeof data.patternbook.filePath === 'string' && data.patternbook.filePath) {
        return data.patternbook.filePath;
    }
    if (Array.isArray(data.patterns) && data.patterns.length > 0) {
        const firstPattern = data.patterns[0];
        if (firstPattern && typeof firstPattern.sourceFile === 'string' && firstPattern.sourceFile) {
            return firstPattern.sourceFile;
        }
    }
    return null;
}

function _isLibraryPatternLeafElement(element) {
    if (!element || element.type !== 'patternItem' || !element.data) {
        return false;
    }
    const sectionKey = element.data.sectionKey;
    return sectionKey === 'shipped-patterns' || sectionKey === 'dependency-patterns';
}

function _isLibraryPatternbookGroupElement(element) {
    if (!element || element.type !== 'patternbookGroup' || !element.data) {
        return false;
    }
    const sectionKey = element.data.sectionKey;
    return sectionKey === 'shipped-patterns' || sectionKey === 'dependency-patterns';
}

function _isDuplicableLibraryElement(element) {
    return _isLibraryPatternLeafElement(element) || _isLibraryPatternbookGroupElement(element);
}

/**
 * Main activation function for the Kigumi extension.
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('Kigumi');
    context.subscriptions.push(outputChannel);
    const extensionVersion = (context.extension && context.extension.packageJSON && context.extension.packageJSON.version)
        ? context.extension.packageJSON.version
        : 'unknown';
    outputChannel.appendLine(`[kigumi] ${BUILD_MARKER} (extension v${extensionVersion})`);
    openInSplitView = vscode.workspace.getConfiguration('kigumi').get('viewer.openInSplitView', true);
    autoRefreshOnFileChange = vscode.workspace.getConfiguration('kigumi').get('viewer.autoRefreshOnFileChange', false);
    logRetentionDays = normalizeRetentionDays(vscode.workspace.getConfiguration('kigumi').get('viewer.logRetentionDays', 15));
    pruneWorkspaceLogs(outputChannel, logRetentionDays);
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((event) => {
        if (event.affectsConfiguration('kigumi.viewer.openInSplitView')) {
            openInSplitView = vscode.workspace.getConfiguration('kigumi').get('viewer.openInSplitView', true);
            void vscode.commands.executeCommand('setContext', 'kigumi.splitViewEnabled', openInSplitView);
        }
        if (event.affectsConfiguration('kigumi.viewer.autoRefreshOnFileChange')) {
            autoRefreshOnFileChange = vscode.workspace.getConfiguration('kigumi').get('viewer.autoRefreshOnFileChange', false);
            for (const session of frameSessions.values()) {
                session.setWatcherEnabled(autoRefreshOnFileChange);
            }
            for (const session of patternSessions.values()) {
                session.setWatcherEnabled(autoRefreshOnFileChange);
            }
            outputChannel.appendLine(`[kigumi] Auto refresh on file change: ${autoRefreshOnFileChange ? 'enabled' : 'disabled'}`);
        }
        if (event.affectsConfiguration('kigumi.viewer.logRetentionDays')) {
            logRetentionDays = normalizeRetentionDays(vscode.workspace.getConfiguration('kigumi').get('viewer.logRetentionDays', 15));
            pruneWorkspaceLogs(outputChannel, logRetentionDays);
            outputChannel.appendLine(`[kigumi] Log retention days: ${logRetentionDays}`);
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
        getKumikiVersionInfo: async (workspaceRoot) => {
            const activeFilePath = getActivePythonFilePath();
            return getWorkspaceKumikiVersionInfo(workspaceRoot, activeFilePath);
        },
        logLine: (message) => {
            if (!outputChannel) {
                return;
            }
            const timestamp = new Date().toISOString();
            outputChannel.appendLine(`[${timestamp}] ${message}`);
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

    const openExplorer = vscode.commands.registerCommand('kigumi.explorer', async () => {
        await vscode.commands.executeCommand('workbench.view.extension.kigumi');
    });
    context.subscriptions.push(openExplorer);

    const initializeProjectInWorkspace = vscode.commands.registerCommand('kigumi.initializeProjectInWorkspace', async () => {
        await runProjectHeaderAction();
    });
    context.subscriptions.push(initializeProjectInWorkspace);

    const projectHeaderAction = vscode.commands.registerCommand('kigumi.projectHeaderAction', async () => {
        await runProjectHeaderAction();
    });
    context.subscriptions.push(projectHeaderAction);

    const updateKumiki = vscode.commands.registerCommand('kigumi.updateKumiki', async () => {
        await runProjectHeaderUpdateAction();
    });
    context.subscriptions.push(updateKumiki);

    const openWebsite = vscode.commands.registerCommand('kigumi.openWebsite', async () => {
        await vscode.env.openExternal(vscode.Uri.parse('https://github.com/minimapletinytools/kumiki'));
    });
    context.subscriptions.push(openWebsite);

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

    const toggleAutoRefresh = vscode.commands.registerCommand('kigumi.toggleAutoRefreshOnFileChange', async () => {
        const current = vscode.workspace.getConfiguration('kigumi').get('viewer.autoRefreshOnFileChange', false);
        const nextValue = !current;
        await vscode.workspace.getConfiguration('kigumi').update(
            'viewer.autoRefreshOnFileChange',
            nextValue,
            vscode.ConfigurationTarget.Workspace
        );
        vscode.window.showInformationMessage(`Kigumi auto refresh on file change ${nextValue ? 'enabled' : 'disabled'}.`);
        return { enabled: nextValue };
    });
    context.subscriptions.push(toggleAutoRefresh);

    const automationListSessions = vscode.commands.registerCommand('kigumi.automationListSessions', async () => {
        const sessions = [];
        for (const session of frameSessions.values()) {
            sessions.push(session.getTestSnapshot());
        }
        for (const session of patternSessions.values()) {
            sessions.push(session.getTestSnapshot());
        }
        return {
            total: sessions.length,
            sessions,
        };
    });
    context.subscriptions.push(automationListSessions);

    const automationOpenFileInViewer = vscode.commands.registerCommand('kigumi.automationOpenFileInViewer', async (options = {}) => {
        const targetFilePath = typeof options === 'string'
            ? options
            : (options && typeof options.filePath === 'string' ? options.filePath : null);
        if (!targetFilePath) {
            return { ok: false, reason: 'missing-file-path' };
        }

        const resolvedFilePath = path.resolve(targetFilePath);
        if (!fs.existsSync(resolvedFilePath)) {
            return { ok: false, reason: 'file-not-found', filePath: resolvedFilePath };
        }
        if (path.extname(resolvedFilePath).toLowerCase() !== '.py') {
            return { ok: false, reason: 'not-python-file', filePath: resolvedFilePath };
        }

        await openFileInViewer(resolvedFilePath, context);
        return { ok: true, filePath: resolvedFilePath };
    });
    context.subscriptions.push(automationOpenFileInViewer);

    const automationRefreshSession = vscode.commands.registerCommand('kigumi.automationRefreshSession', async (options = {}) => {
        const session = findSessionFromOptions(options);
        if (!session) {
            return { ok: false, reason: 'session-not-found' };
        }

        if (options && options.dirtyOnce) {
            const result = await session.refreshOnceIfDirty({
                saveIfDirty: options.saveIfDirty !== false,
                reason: options.reason || 'automation dirty refresh once',
            });
            return { ok: true, mode: 'dirtyOnce', result };
        }

        await session.refresh(options.reason || 'automation refresh');
        return {
            ok: true,
            mode: 'refresh',
            refreshSequence: session.refreshSequence,
            lastRefreshReason: session.lastRefreshReason,
        };
    });
    context.subscriptions.push(automationRefreshSession);

    const automationReadSessionLogs = vscode.commands.registerCommand('kigumi.automationReadSessionLogs', async (options = {}) => {
        const session = findSessionFromOptions(options);
        if (!session) {
            return { ok: false, reason: 'session-not-found', entries: [] };
        }
        const snapshot = session.getLogSnapshot({
            minLevel: options.minLevel,
            contains: options.contains,
            clear: options.clear === true,
        });
        return {
            ok: true,
            filePath: session.filePath,
            slotName: session.slotName,
            ...snapshot,
        };
    });
    context.subscriptions.push(automationReadSessionLogs);

    const automationGetCameraState = vscode.commands.registerCommand('kigumi.automationGetCameraState', async (options = {}) => {
        const session = findSessionFromOptions(options);
        if (!session) {
            return { ok: false, reason: 'session-not-found' };
        }
        const payload = await session.getCameraState();
        return { ok: true, payload };
    });
    context.subscriptions.push(automationGetCameraState);

    const automationSetCameraState = vscode.commands.registerCommand('kigumi.automationSetCameraState', async (options = {}) => {
        const session = findSessionFromOptions(options);
        if (!session) {
            return { ok: false, reason: 'session-not-found' };
        }
        const payload = await session.setCameraState(options.cameraState || {}, {
            timeoutMs: typeof options.timeoutMs === 'number' ? options.timeoutMs : undefined,
        });
        return { ok: true, payload };
    });
    context.subscriptions.push(automationSetCameraState);

    const captureScreenshotBundle = vscode.commands.registerCommand('kigumi.captureScreenshotBundle', async (options = {}) => {
        const session = findSessionFromOptions(options);
        if (!session) {
            throw new Error('No active Kigumi session found for screenshot bundle');
        }

        if (options.preRefresh === true) {
            if (options.preRefreshDirtyOnce === true) {
                await session.refreshOnceIfDirty({
                    saveIfDirty: options.saveIfDirty !== false,
                    reason: 'automation screenshot bundle pre-refresh (dirty once)',
                });
            } else {
                await session.refresh('automation screenshot bundle pre-refresh');
            }
        }

        if (options.cameraState && typeof options.cameraState === 'object') {
            await session.setCameraState(options.cameraState, {
                timeoutMs: typeof options.timeoutMs === 'number' ? options.timeoutMs : undefined,
            });
        }

        const workspaceRoot = getWorkspaceRoot() || path.dirname(session.filePath);
        const outputDir = typeof options.outputDir === 'string' && options.outputDir
            ? options.outputDir
            : path.join(workspaceRoot, '.kigumi', 'automation');
        const basePrefix = typeof options.namePrefix === 'string' && options.namePrefix
            ? options.namePrefix
            : `${path.basename(session.filePath, path.extname(session.filePath))}-${Date.now()}`;
        fs.mkdirSync(outputDir, { recursive: true });

        const screenshotPath = path.join(outputDir, `${basePrefix}.png`);
        const cameraPath = path.join(outputDir, `${basePrefix}.camera.json`);

        const screenshotMeta = await session.captureScreenshot({
            outputPath: screenshotPath,
            timeoutMs: typeof options.timeoutMs === 'number' ? options.timeoutMs : undefined,
        });
        const cameraState = await session.getCameraState();
        fs.writeFileSync(cameraPath, `${JSON.stringify(cameraState, null, 2)}\n`, 'utf8');

        return {
            ok: true,
            filePath: session.filePath,
            slotName: session.slotName,
            screenshotPath,
            cameraPath,
            cameraState,
            screenshot: screenshotMeta,
        };
    });
    context.subscriptions.push(captureScreenshotBundle);

    // Split-view toggle now handled via Settings panel only (kigumi.viewer.openInSplitView setting)

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
        const sourcePath = _extractSourcePathFromSidebarElement(selectedElement);

        if (!selectedElement || !sourcePath) {
            vscode.window.showErrorMessage('Please select a pattern or frame first.');
            return;
        }

        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot) {
            vscode.window.showErrorMessage('Open a workspace folder first.');
            return;
        }

        try {
            const { viewShippedPatternSource } = require('./pattern-source-utils');
            
            // Check if the file is in workspace or from dependencies
            const isInWorkspace = sourcePath.startsWith(workspaceRoot);
            
            if (isInWorkspace) {
                // Open workspace file directly
                const uri = vscode.Uri.file(sourcePath);
                const doc = await vscode.workspace.openTextDocument(uri);
                await vscode.window.showTextDocument(doc);
            } else {
                // Create read-only copy in workspace
                const readOnlyPath = await viewShippedPatternSource(sourcePath, workspaceRoot);
                const uri = vscode.Uri.file(readOnlyPath);
                const doc = await vscode.workspace.openTextDocument(uri);
                await vscode.window.showTextDocument(doc);
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
        if (!_isDuplicableLibraryElement(selectedElement)) {
            vscode.window.showErrorMessage('Duplicate to workspace is only available for library patterns and patternbooks.');
            return;
        }

        const sourcePath = _extractSourcePathFromSidebarElement(selectedElement);
        if (!sourcePath) {
            vscode.window.showErrorMessage('Cannot determine source file for selected item.');
            return;
        }

        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot) {
            vscode.window.showErrorMessage('Open a workspace folder first.');
            return;
        }

        try {
            const { duplicatePatternToWorkspace: duplicateFn } = require('./pattern-source-utils');
            const newPath = await duplicateFn(sourcePath, workspaceRoot);
            
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
                    autoRefreshOnFileChange,
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

    if (ENABLE_TEST_COMMANDS) {
        const sidebarSnapshotDisposable = vscode.commands.registerCommand(
            'kigumi.testGetSidebarSnapshot',
            async (options = {}) => {
                if (!sidebarProvider) {
                    return null;
                }
                return sidebarProvider.getTestSnapshot(options);
            }
        );

        const sessionSnapshotDisposable = vscode.commands.registerCommand(
            'kigumi.testGetSessionSnapshot',
            async (options = {}) => {
                const targetFilePath =
                    typeof options.filePath === 'string' && options.filePath
                        ? options.filePath
                        : vscode.window.activeTextEditor && vscode.window.activeTextEditor.document
                            ? vscode.window.activeTextEditor.document.fileName
                            : null;

                if (!targetFilePath) {
                    return { exists: false, reason: 'No file path was provided.' };
                }

                const session = frameSessions.get(targetFilePath);
                if (!session || session.isDisposed) {
                    return { exists: false, filePath: targetFilePath };
                }

                const snapshot = session.getTestSnapshot();
                if (options.includePanelSnapshot) {
                    try {
                        snapshot.panelSnapshot = await session.capturePanelSnapshot({
                            timeoutMs: Number.isFinite(options.timeoutMs) ? options.timeoutMs : 3000,
                        });
                    } catch (error) {
                        snapshot.panelSnapshot = null;
                        snapshot.panelSnapshotError = error && error.message ? error.message : String(error);
                    }
                }
                return {
                    exists: true,
                    ...snapshot,
                };
            }
        );

        context.subscriptions.push(sidebarSnapshotDisposable, sessionSnapshotDisposable);
    }

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

    // Initialize context variable for dynamic icon
    void vscode.commands.executeCommand('setContext', 'kigumi.splitViewEnabled', openInSplitView);

    async function runProjectHeaderAction() {
        const activeFilePath = getActivePythonFilePath();
        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot && !activeFilePath) {
            vscode.window.showErrorMessage('Open a workspace folder or open a Python file first.');
            return;
        }

        if (isInitializationInProgress()) {
            vscode.window.showInformationMessage('Kigumi initialization is already in progress.');
            return;
        }

        const rootHint = workspaceRoot || path.dirname(activeFilePath);

        const initStatus = getInitializationStatus(rootHint, activeFilePath);
        if (initStatus.projectStatus === 'local-dev') {
            vscode.window.showInformationMessage('Local development mode: using workspace kumiki source; initialization is disabled.');
            if (sidebarProvider) {
                await sidebarProvider.refresh(true);
            }
            return;
        }

        if (initStatus.isInitialized) {
            vscode.window.showInformationMessage('Project initialized: .kigumi.yaml, .kigumi/project.yaml, .venv, and my_cute_frame.py are present.');
            if (sidebarProvider) {
                await sidebarProvider.refresh(true);
            }
            return;
        }

        try {
            let initializeResult = null;
            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: 'Initializing Kigumi project',
                cancellable: false,
            }, async () => {
                const initializePromise = initializeWorkspaceProject(rootHint, activeFilePath);
                if (sidebarProvider) {
                    // initializeWorkspaceProject flips in-progress state synchronously,
                    // so this refresh exposes the transient "Initializing project..." row.
                    await sidebarProvider.refresh(true);
                }
                initializeResult = await initializePromise;
                logKumikiInstallResult('initialize', initializeResult);
            });
            if (initializeResult && Array.isArray(initializeResult.instructionWarnings)) {
                for (const warning of initializeResult.instructionWarnings) {
                    vscode.window.showWarningMessage(warning);
                }
            }
            vscode.window.showInformationMessage('Kigumi workspace initialized and Kumiki was updated to latest.');
        } catch (error) {
            if (error && error.code === 'INITIALIZATION_IN_PROGRESS') {
                vscode.window.showInformationMessage('Kigumi initialization is already in progress.');
            } else {
                outputChannel.show(true);
                vscode.window.showErrorMessage(`Initialize project failed: ${error.message || error}`);
            }
        } finally {
            if (sidebarProvider) {
                await sidebarProvider.refresh(true);
            }
        }
    }

    async function runProjectHeaderUpdateAction() {
        const activeFilePath = getActivePythonFilePath();
        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot && !activeFilePath) {
            vscode.window.showErrorMessage('Open a workspace folder or open a Python file first.');
            return;
        }

        if (isInitializationInProgress()) {
            vscode.window.showInformationMessage('Kigumi update is already in progress.');
            return;
        }

        const rootHint = workspaceRoot || path.dirname(activeFilePath);
        try {
            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: 'Updating Kumiki',
                cancellable: false,
            }, async () => {
                const result = await updateWorkspaceKumiki(rootHint, activeFilePath);
                logKumikiInstallResult('update', result);
            });
            vscode.window.showInformationMessage('Kumiki update complete.');
        } catch (error) {
            if (error && error.code === 'INITIALIZATION_IN_PROGRESS') {
                vscode.window.showInformationMessage('Kigumi update is already in progress.');
            } else {
                outputChannel.show(true);
                vscode.window.showErrorMessage(`Update Kumiki failed: ${error.message || error}`);
            }
        } finally {
            if (sidebarProvider) {
                await sidebarProvider.refresh(true);
            }
        }
    }

    function logKumikiInstallResult(actionName, result) {
        if (!outputChannel || !result) {
            return;
        }
        const action = actionName === 'update' ? 'Update' : 'Install';
        outputChannel.appendLine(`[kigumi] ${action} Kumiki complete.`);
        outputChannel.appendLine(`[kigumi] Installed Kumiki version: ${result.kumikiVersion || 'unknown'}`);
        if (Array.isArray(result.installSummary) && result.installSummary.length > 0) {
            outputChannel.appendLine('[kigumi] Summary:');
            for (const line of result.installSummary) {
                outputChannel.appendLine(`[kigumi] - ${line}`);
            }
        }
        if (Array.isArray(result.instructionWarnings) && result.instructionWarnings.length > 0) {
            for (const warning of result.instructionWarnings) {
                outputChannel.appendLine(`[kigumi] Warning: ${warning}`);
            }
        }
    }
}

function getWorkspaceRoot() {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
        return null;
    }
    return folders[0].uri.fsPath;
}

function getActivePythonFilePath() {
    const editor = vscode.window.activeTextEditor;
    if (!editor || !editor.document || editor.document.languageId !== 'python') {
        return null;
    }
    return editor.document.fileName;
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
            autoRefreshOnFileChange,
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
            autoRefreshOnFileChange,
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
        { slotName: 'main', sessionType: 'main', openInSplitView, autoRefreshOnFileChange }
    );
    frameSessions.set(filePath, session);
    await session.initialize();
    return session;
}

function findSessionFromOptions(options = {}) {
    if (options && typeof options.slotName === 'string' && options.slotName.length > 0) {
        const patternSession = patternSessions.get(options.slotName);
        if (patternSession && !patternSession.isDisposed) {
            return patternSession;
        }
    }

    const targetFilePath =
        typeof options.filePath === 'string' && options.filePath
            ? options.filePath
            : vscode.window.activeTextEditor && vscode.window.activeTextEditor.document
                ? vscode.window.activeTextEditor.document.fileName
                : null;

    if (targetFilePath) {
        const frameSession = frameSessions.get(targetFilePath);
        if (frameSession && !frameSession.isDisposed) {
            return frameSession;
        }
    }

    for (const session of frameSessions.values()) {
        if (!session.isDisposed) {
            return session;
        }
    }
    for (const session of patternSessions.values()) {
        if (!session.isDisposed) {
            return session;
        }
    }
    return null;
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

function pruneWorkspaceLogs(channel, retentionDays) {
    const folders = vscode.workspace.workspaceFolders || [];
    for (const folder of folders) {
        try {
            const result = pruneOldLogFiles(folder.uri.fsPath, retentionDays);
            if (channel && result.removedFiles.length > 0) {
                channel.appendLine(`[kigumi] Removed ${result.removedFiles.length} old log file(s) from ${result.logsDir}`);
            }
        } catch (error) {
            if (channel) {
                channel.appendLine(`[kigumi] Failed to prune old logs in ${folder.uri.fsPath}: ${error.message || error}`);
            }
        }
    }
}

module.exports = {
    activate,
    deactivate,
};
