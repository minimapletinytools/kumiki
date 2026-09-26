/**
 * Kigumi's commands and the viewer sessions they manage, independent of the
 * editor. Every editor service goes through the host (host.js); a host entry
 * point creates the app and binds `commands` to its own command system.
 */

const path = require('path');
const fs = require('fs');
const { FrameViewSession } = require('./frame-view-session');
const { PythonRunnerSession } = require('./runner-session');
const { SidebarModel } = require('./sidebar-model');
const { SidebarController } = require('./sidebar-controller');
const { NewPythonFileWatcher } = require('./new-python-file-watcher');
const { normalizeRetentionDays, pruneOldLogFiles } = require('./log-retention');
const {
    getInitializationStatus,
    initializeWorkspaceProject,
    updateWorkspaceKumiki,
    isInitializationInProgress,
    getWorkspaceKumikiVersionInfo,
} = require('./project-initializer');
const { configureToolchain, UV_VERSION } = require('./python-toolchain');
const { getHost } = require('./host');
const { createTranslator } = require('./i18n');

const KUMIKI_WEBSITE = 'https://github.com/minimapletinytools/kumiki';

const t = (key, params) => createTranslator(getHost().locale)(key, params);

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

function _isDuplicableLibraryElement(element) {
    if (!element || !element.data || (element.type !== 'patternItem' && element.type !== 'patternbookGroup')) {
        return false;
    }
    const sectionKey = element.data.sectionKey;
    return sectionKey === 'shipped-patterns' || sectionKey === 'dependency-patterns';
}

function normalizeSessionFilePath(filePath) {
    if (!filePath || typeof filePath !== 'string') {
        return null;
    }
    try {
        return fs.realpathSync.native(filePath);
    } catch (_error) {
        return path.resolve(filePath);
    }
}

/**
 * @param {object} options
 * @param {string} options.extensionPath  where runner.py and package.json live
 * @param {string} options.storagePath  per-user storage (downloaded tools)
 * @param {{appendLine, append, show}} options.channel  the Kigumi log
 * @param {boolean} [options.enableTestCommands]
 * @param {string|null} [options.bundledUv]  a uv binary shipped with the host
 */
function createKigumiApp({ extensionPath, storagePath, channel, enableTestCommands = false, bundledUv = null }) {
    const host = getHost();
    const context = { extensionPath };
    const outputChannel = channel;
    const frameSessions = new Map();       // filePath → FrameViewSession (main sessions)
    const patternSessions = new Map();     // slotName → FrameViewSession (pattern sessions)
    const standaloneRunners = new Set();   // PythonRunnerSession instances not owned by any session
    const disposables = [];
    let patternSlotCounter = 0;

    let openInSplitView = host.getConfig('viewer.openInSplitView', false);
    let autoRefreshOnFileChange = host.getConfig('viewer.autoRefreshOnFileChange', false);
    let logRetentionDays = normalizeRetentionDays(host.getConfig('viewer.logRetentionDays', 15));
    let autoRefreshSidebarOnNewFile = host.getConfig('sidebar.autoRefreshOnNewFile', true);

    const getWorkspaceRoot = () => host.workspaceRoots()[0] || null;

    function getActivePythonFilePath() {
        const active = host.activeFile();
        return active && active.languageId === 'python' ? active.filePath : null;
    }

    pruneWorkspaceLogs();
    configureToolchain({
        toolsDir: storagePath,
        bundledUv,
        log: (line) => outputChannel.appendLine(`[toolchain] ${line}`),
        confirmInstallUv: () => host.confirm({
            message: t('message.installUvPrompt'),
            detail: t('message.installUvDetail', { version: UV_VERSION }),
            action: t('message.installUvAction'),
        }),
        withProgress: (task) => host.withProgress(t('message.installingUvProgress'), task),
    });

    disposables.push(host.onConfigChange((affects) => {
        if (affects('viewer.openInSplitView')) {
            openInSplitView = host.getConfig('viewer.openInSplitView', false);
        }
        if (affects('viewer.autoRefreshOnFileChange')) {
            autoRefreshOnFileChange = host.getConfig('viewer.autoRefreshOnFileChange', false);
            for (const session of [...frameSessions.values(), ...patternSessions.values()]) {
                session.setWatcherEnabled(autoRefreshOnFileChange);
            }
            outputChannel.appendLine(`[kigumi] Auto refresh on file change: ${autoRefreshOnFileChange ? 'enabled' : 'disabled'}`);
        }
        if (affects('viewer.logRetentionDays')) {
            logRetentionDays = normalizeRetentionDays(host.getConfig('viewer.logRetentionDays', 15));
            pruneWorkspaceLogs();
            outputChannel.appendLine(`[kigumi] Log retention days: ${logRetentionDays}`);
        }
        if (affects('sidebar.autoRefreshOnNewFile')) {
            autoRefreshSidebarOnNewFile = host.getConfig('sidebar.autoRefreshOnNewFile', true);
            newPythonFileWatcher.setEnabled(autoRefreshSidebarOnNewFile);
            outputChannel.appendLine(`[kigumi] Auto refresh sidebar on new file: ${autoRefreshSidebarOnNewFile ? 'enabled' : 'disabled'}`);
        }
    }));

    // Marks viewers of an edited Python file as having pending changes.
    disposables.push(host.onDocumentChange(({ filePath, languageId, isDirty, saved }) => {
        if (languageId !== 'python') {
            return;
        }
        const normalizedDocPath = normalizeSessionFilePath(filePath);
        if (!normalizedDocPath) {
            return;
        }
        const nextState = saved ? true : Boolean(isDirty);

        const mainSession = getFrameSession(normalizedDocPath);
        if (mainSession && !mainSession.isDisposed) {
            mainSession.setSourceHasPendingChanges(nextState);
        }
        for (const session of patternSessions.values()) {
            if (session && !session.isDisposed && normalizeSessionFilePath(session.filePath) === normalizedDocPath) {
                session.setSourceHasPendingChanges(nextState);
            }
        }
    }));

    const sidebarModel = new SidebarModel({
        getPythonCommand: () => {
            const mainSession = _findAnyAliveMainSession();
            if (!mainSession || !mainSession.runnerSession || !mainSession.runnerSession.isAlive()) {
                return undefined;
            }
            return mainSession.runnerSession.getPythonCommand();
        },
        getKumikiVersionInfo: async (workspaceRoot) => getWorkspaceKumikiVersionInfo(workspaceRoot, getActivePythonFilePath()),
        logLine: (message) => {
            outputChannel.appendLine(`[${new Date().toISOString()}] ${message}`);
        },
    });

    const sidebarController = new SidebarController(sidebarModel, {
        runCommand: (command, ...args) => host.runCommand(command, ...args),
        log: (message) => outputChannel.appendLine(`[kigumi] ${message}`),
    });
    disposables.push(sidebarController, sidebarModel);

    const newPythonFileWatcher = new NewPythonFileWatcher(
        getWorkspaceRoot(),
        () => {
            void sidebarModel.refresh(true);
        },
        (message) => outputChannel.appendLine(`[kigumi] [sidebar-watch] ${message}`),
    );
    newPythonFileWatcher.setEnabled(autoRefreshSidebarOnNewFile);
    newPythonFileWatcher.start();
    disposables.push(newPythonFileWatcher);

    // Runs `fn(session)` for the session identified by automation `options`,
    // or returns the shared not-found result (merged with `notFoundExtra`).
    function withSession(options, fn, notFoundExtra = {}) {
        const session = findSessionFromOptions(options);
        if (!session) {
            return { ok: false, reason: 'session-not-found', ...notFoundExtra };
        }
        return fn(session);
    }

    function showOutputOnError(error, messageKey) {
        outputChannel.show(true);
        if (!error || !error.kigumiErrorNotified) {
            host.showMessage('error', t(messageKey, { error: (error && error.message) || error }));
        }
    }

    // -------------------------------------------------------------------------
    // Commands
    // -------------------------------------------------------------------------

    const commands = {
        'kigumi.render': async () => {
            try {
                await renderActiveEditor();
            } catch (error) {
                showOutputOnError(error, 'message.kigumiError');
            }
        },

        'kigumi.openCurrentFileInViewer': async () => {
            try {
                await renderActiveEditor({ reason: 'open current file in viewer' });
            } catch (error) {
                outputChannel.show(true);
                host.showMessage('error', t('message.openCurrentFileFailed', { error: error.message || error }));
            }
        },

        'kigumi.initializeProjectInWorkspace': () => runProjectHeaderAction(),
        'kigumi.projectHeaderAction': () => runProjectHeaderAction(),
        'kigumi.updateKumiki': () => runProjectHeaderUpdateAction(),
        'kigumi.openWebsite': () => host.openExternal(KUMIKI_WEBSITE),
        'kigumi.refreshSidebar': () => sidebarModel.refresh(true),
        'kigumi.refreshPatterns': () => sidebarModel.refresh(true),
        'kigumi.toggleGroupByPatternbook': () => sidebarModel.toggleGroupByPatternbook(),

        'kigumi.toggleAutoRefreshOnFileChange': async () => {
            const nextValue = !host.getConfig('viewer.autoRefreshOnFileChange', false);
            await host.updateConfig('viewer.autoRefreshOnFileChange', nextValue);
            host.showMessage('info', t('message.autoRefreshToggled', { state: nextValue ? t('common.enabled') : t('common.disabled') }));
            return { enabled: nextValue };
        },

        'kigumi.automationListSessions': async () => {
            const sessions = [...frameSessions.values(), ...patternSessions.values()].map((session) => session.getTestSnapshot());
            return { total: sessions.length, sessions };
        },

        'kigumi.automationOpenFileInViewer': async (options = {}) => {
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
            await openFileInViewer(resolvedFilePath);
            return { ok: true, filePath: resolvedFilePath };
        },

        'kigumi.automationRefreshSession': async (options = {}) => withSession(options, async (session) => {
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
        }),

        'kigumi.automationReadSessionLogs': async (options = {}) => withSession(options, async (session) => {
            const snapshot = session.getLogSnapshot({
                minLevel: options.minLevel,
                contains: options.contains,
                clear: options.clear === true,
            });
            return { ok: true, filePath: session.filePath, slotName: session.slotName, ...snapshot };
        }, { entries: [] }),

        'kigumi.automationGetCameraState': async (options = {}) => withSession(options, async (session) => {
            const payload = await session.getCameraState();
            return { ok: true, payload };
        }),

        'kigumi.automationSetCameraState': async (options = {}) => withSession(options, async (session) => {
            const payload = await session.setCameraState(options.cameraState || {}, {
                timeoutMs: typeof options.timeoutMs === 'number' ? options.timeoutMs : undefined,
            });
            return { ok: true, payload };
        }),

        'kigumi.captureScreenshot': async (options = {}) => {
            const session = await ensureViewerSessionForScreenshot(options);

            if (options.preRefresh === true) {
                if (options.preRefreshDirtyOnce === true) {
                    await session.refreshOnceIfDirty({
                        saveIfDirty: options.saveIfDirty !== false,
                        reason: 'automation screenshot pre-refresh (dirty once)',
                    });
                } else {
                    await session.refresh('automation screenshot pre-refresh');
                }
            }

            if (options.cameraState && typeof options.cameraState === 'object') {
                await session.setCameraState(options.cameraState, {
                    timeoutMs: typeof options.timeoutMs === 'number' ? options.timeoutMs : undefined,
                });
            }

            let screenshotPath = typeof options.outputPath === 'string' && options.outputPath
                ? options.outputPath
                : null;
            if (!screenshotPath) {
                const workspaceRoot = getWorkspaceRoot() || path.dirname(session.filePath);
                const outputDir = typeof options.outputDir === 'string' && options.outputDir
                    ? options.outputDir
                    : path.join(workspaceRoot, '.kigumi', 'automation');
                const basePrefix = typeof options.namePrefix === 'string' && options.namePrefix
                    ? options.namePrefix
                    : `${path.basename(session.filePath, path.extname(session.filePath))}-${Date.now()}`;
                fs.mkdirSync(outputDir, { recursive: true });
                screenshotPath = path.join(outputDir, `${basePrefix}.png`);
            } else {
                fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
            }

            const screenshotMeta = await session.captureScreenshot({
                outputPath: screenshotPath,
                timeoutMs: typeof options.timeoutMs === 'number' ? options.timeoutMs : undefined,
            });
            return {
                ok: true,
                filePath: session.filePath,
                slotName: session.slotName,
                screenshotPath,
                screenshot: screenshotMeta,
            };
        },

        'kigumi.openFrameFromSidebar': (filePath) => openFileInViewer(filePath),
        'kigumi.openExampleFromSidebar': (sourceFile) => openFileInViewer(sourceFile),

        'kigumi.openPatternFromSidebar': (patternRecord) => openPatternRecord(patternRecord),

        'kigumi.openPatternInNewWindow': (element) => {
            // The sidebar row menu passes the row node; data lives in element.data
            return openPatternRecord(element && (element.data || element), { forceNewWindow: true });
        },

        'kigumi.openPatternbookGroup': async (groupData) => {
            if (!groupData || !groupData.patterns || groupData.patterns.length === 0) {
                host.showMessage('error', t('message.patternbookHasNoPatterns'));
                return;
            }
            // Opening the first pattern's file without a pattern name loads the whole patternbook.
            const firstPattern = groupData.patterns[0];
            if (!firstPattern || !firstPattern.sourceFile) {
                host.showMessage('error', t('message.cannotFindPatternSourceFile'));
                return;
            }
            try {
                const runner = await _getOrCreateBackgroundRunner(firstPattern.sourceFile);
                await _openBookFromWebview(runner, firstPattern.sourceFile);
            } catch (error) {
                outputChannel.appendLine(`Open patternbook error: ${error.message}\n${error.stack}`);
                host.showMessage('error', t('message.failedToOpenPatternbook', { error: error.message }));
            }
        },

        'kigumi.viewPatternSource': async (elementArg) => {
            const selectedElement = elementArg || sidebarController.getSelectedElementData();
            const sourcePath = _extractSourcePathFromSidebarElement(selectedElement);
            if (!selectedElement || !sourcePath) {
                host.showMessage('error', t('message.selectPatternOrFrameFirst'));
                return;
            }
            const workspaceRoot = getWorkspaceRoot();
            if (!workspaceRoot) {
                host.showMessage('error', t('message.openWorkspaceFolderFirst'));
                return;
            }
            try {
                const { viewShippedPatternSource } = require('./pattern-source-utils');
                if (sourcePath.startsWith(workspaceRoot)) {
                    await host.showFile(sourcePath);
                } else {
                    // Library files open as a read-only copy in the workspace.
                    await host.showFile(await viewShippedPatternSource(sourcePath, workspaceRoot));
                    host.showMessage('info', t('message.openedReadOnlyPatternCopy'));
                }
            } catch (error) {
                outputChannel.appendLine(`View source error: ${error.message}\n${error.stack}`);
                host.showMessage('error', t('message.failedToViewPatternSource', { error: error.message }));
            }
        },

        'kigumi.duplicatePatternToWorkspace': async (elementArg) => {
            const selectedElement = elementArg || sidebarController.getSelectedElementData();
            if (!_isDuplicableLibraryElement(selectedElement)) {
                host.showMessage('error', t('message.duplicateToWorkspaceUnavailable'));
                return;
            }
            const sourcePath = _extractSourcePathFromSidebarElement(selectedElement);
            if (!sourcePath) {
                host.showMessage('error', t('message.cannotDetermineSourceFile'));
                return;
            }
            const workspaceRoot = getWorkspaceRoot();
            if (!workspaceRoot) {
                host.showMessage('error', t('message.openWorkspaceFolderFirst'));
                return;
            }
            try {
                const { duplicatePatternToWorkspace } = require('./pattern-source-utils');
                const newPath = await duplicatePatternToWorkspace(sourcePath, workspaceRoot);
                await host.showFile(newPath);
                host.showMessage('info', t('message.patternDuplicatedTo', { path: path.relative(workspaceRoot, newPath) }));
                await sidebarModel.refresh(true);
            } catch (error) {
                outputChannel.appendLine(`Duplicate pattern error: ${error.message}\n${error.stack}`);
                host.showMessage('error', t('message.failedToDuplicatePattern', { error: error.message }));
            }
        },

        'kigumi.browsePatterns': async () => {
            try {
                // Patterns are listed by a running runner; start one from the active file if needed.
                let mainSession = _findAnyAliveMainSession();
                if (!mainSession) {
                    const activeFilePath = getActivePythonFilePath();
                    if (!activeFilePath) {
                        host.showMessage('error', t('message.openPythonFileBeforeBrowsing'));
                        return;
                    }
                    await saveIfDirty(activeFilePath);
                    mainSession = await getOrCreateSession(activeFilePath);
                }

                const runner = mainSession.runnerSession;
                if (!runner || !runner.isAlive()) {
                    host.showMessage('error', t('message.runnerNotRunningRunFirst'));
                    return;
                }

                const result = await runner.request('list_available_patterns');
                if (!result || !result.sources || result.sources.length === 0) {
                    host.showMessage('info', t('message.noPatternsFoundLibraryOrProject'));
                    return;
                }

                const items = [];
                for (const source of result.sources) {
                    const sourceLabel = source.source === 'shipped' ? t('message.shippedLibrary') : t('message.localProject');
                    items.push({ label: sourceLabel, separator: true });
                    for (const pattern of source.patterns) {
                        const groupsStr = pattern.groups.length > 0 ? ` (${pattern.groups.join(', ')})` : '';
                        items.push({
                            label: pattern.name,
                            description: `${sourceLabel}${groupsStr}`,
                            detail: pattern.source_file,
                            value: { sourceFile: pattern.source_file, patternName: pattern.name },
                        });
                    }
                }

                const picked = await host.pickOne(items, {
                    placeholder: t('message.selectPatternToView'),
                    matchOnDescription: true,
                    matchOnDetail: true,
                });
                if (!picked || !picked.value) {
                    return;
                }

                patternSlotCounter += 1;
                const slotName = `pattern_${patternSlotCounter}`;
                await runner.request('raise_specific_pattern', {
                    slot: slotName,
                    sourceFile: picked.value.sourceFile,
                    patternName: picked.value.patternName,
                });
                await createPatternSession(runner, slotName, picked.value.sourceFile, picked.value.patternName, 'pattern open');
            } catch (error) {
                showOutputOnError(error, 'message.browsePatternsError');
            }
        },

        'kigumi.unloadPattern': async () => {
            if (patternSessions.size === 0) {
                host.showMessage('info', t('message.noPatternViewersOpen'));
                return;
            }
            const items = [...patternSessions].map(([slotName, session]) => ({
                label: session.patternName || slotName,
                description: slotName,
                value: slotName,
            }));
            const picked = await host.pickOne(items, { placeholder: t('message.selectPatternToUnload') });
            if (!picked) {
                return;
            }
            const session = patternSessions.get(picked.value);
            if (session) {
                await session.dispose();
            }
        },
    };

    if (enableTestCommands) {
        commands['kigumi.testGetSidebarSnapshot'] = async (options = {}) => sidebarModel.getTestSnapshot(options);

        commands['kigumi.testGetSessionSnapshot'] = async (options = {}) => {
            const active = host.activeFile();
            const targetFilePath = typeof options.filePath === 'string' && options.filePath
                ? options.filePath
                : (active ? active.filePath : null);
            if (!targetFilePath) {
                return { exists: false, reason: 'No file path was provided.' };
            }

            const session = getFrameSession(targetFilePath);
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
            return { exists: true, ...snapshot };
        };
    }

    // -------------------------------------------------------------------------
    // Project setup
    // -------------------------------------------------------------------------

    async function runProjectHeaderAction() {
        const activeFilePath = getActivePythonFilePath();
        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot && !activeFilePath) {
            host.showMessage('error', t('message.openWorkspaceOrPythonFileFirst'));
            return;
        }
        if (isInitializationInProgress()) {
            host.showMessage('info', t('message.initializationAlreadyInProgress'));
            return;
        }

        const rootHint = workspaceRoot || path.dirname(activeFilePath);
        const initStatus = getInitializationStatus(rootHint, activeFilePath);
        if (initStatus.projectStatus === 'local-dev') {
            host.showMessage('info', t('message.localDevModeInitDisabled'));
            await sidebarModel.refresh(true);
            return;
        }
        if (initStatus.isInitialized) {
            host.showMessage('info', t('message.projectAlreadyInitialized'));
            await sidebarModel.refresh(true);
            return;
        }

        try {
            let initializeResult = null;
            await host.withProgress(t('message.initializingProjectProgress'), async () => {
                const initializePromise = initializeWorkspaceProject(rootHint, activeFilePath);
                // initializeWorkspaceProject flips in-progress state synchronously,
                // so this refresh exposes the transient "Initializing project..." row.
                await sidebarModel.refresh(true);
                initializeResult = await initializePromise;
                logKumikiInstallResult('initialize', initializeResult);
            });
            if (initializeResult && Array.isArray(initializeResult.instructionWarnings)) {
                for (const warning of initializeResult.instructionWarnings) {
                    host.showMessage('warning', warning);
                }
            }
            const kumikiVer = initializeResult && initializeResult.kumikiVersion ? ` (kumiki ${initializeResult.kumikiVersion})` : '';
            host.showMessage('info', t('message.workspaceInitialized', { kumikiVer }));
        } catch (error) {
            if (error && error.code === 'INITIALIZATION_IN_PROGRESS') {
                host.showMessage('info', t('message.initializationAlreadyInProgress'));
            } else {
                outputChannel.show(true);
                host.showMessage('error', t('message.initializeProjectFailed', { error: error.message || error }));
            }
        } finally {
            await sidebarModel.refresh(true);
        }
    }

    async function runProjectHeaderUpdateAction() {
        const activeFilePath = getActivePythonFilePath();
        const workspaceRoot = getWorkspaceRoot();
        if (!workspaceRoot && !activeFilePath) {
            host.showMessage('error', t('message.openWorkspaceOrPythonFileFirst'));
            return;
        }
        if (isInitializationInProgress()) {
            host.showMessage('info', t('message.updateAlreadyInProgress'));
            return;
        }

        const rootHint = workspaceRoot || path.dirname(activeFilePath);
        try {
            await host.withProgress(t('message.updatingKumikiProgress'), async () => {
                const result = await updateWorkspaceKumiki(rootHint, activeFilePath);
                logKumikiInstallResult('update', result);
                const ver = result && result.kumikiVersion ? ` to ${result.kumikiVersion}` : '';
                host.showMessage('info', t('message.kumikiUpdated', { ver }));
            });
        } catch (error) {
            if (error && error.code === 'INITIALIZATION_IN_PROGRESS') {
                host.showMessage('info', t('message.updateAlreadyInProgress'));
            } else {
                outputChannel.show(true);
                host.showMessage('error', t('message.updateKumikiFailed', { error: error.message || error }));
            }
        } finally {
            await sidebarModel.refresh(true);
        }
    }

    function logKumikiInstallResult(actionName, result) {
        if (!result) {
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
        for (const warning of (result.instructionWarnings || [])) {
            outputChannel.appendLine(`[kigumi] Warning: ${warning}`);
        }
    }

    // -------------------------------------------------------------------------
    // Viewer sessions
    // -------------------------------------------------------------------------

    async function saveIfDirty(filePath) {
        const document = await host.getDocumentState(filePath);
        if (document && document.isDirty) {
            await document.save();
        }
    }

    async function renderActiveEditor(options = {}) {
        const active = host.activeFile();
        if (!active) {
            host.showMessage('error', t('message.noActiveEditor'));
            return;
        }
        if (active.languageId !== 'python') {
            host.showMessage('error', t('message.currentFileNotPython'));
            return;
        }
        await renderFile(active.filePath, options);
    }

    async function renderFile(filePath, options = {}) {
        await saveIfDirty(filePath);
        const session = await getOrCreateSession(filePath);
        session.reveal();
        await session.refresh(options.reason || 'open current file in viewer');
    }

    async function openFileInViewer(filePath) {
        if (!filePath || typeof filePath !== 'string') {
            host.showMessage('error', t('message.noFilePathProvided'));
            return;
        }
        await host.showSourceBesideViewer(filePath);
        await renderFile(filePath);
    }

    async function openPatternRecord(record, { forceNewWindow = false } = {}) {
        const sourceFile = record && record.sourceFile;
        const patternName = record && record.patternName;
        if (!sourceFile) {
            host.showMessage('error', t('message.patternMissingSourceFile'));
            return;
        }

        let runner;
        try {
            runner = await _getOrCreateBackgroundRunner(sourceFile);
        } catch (error) {
            outputChannel.appendLine(`Open pattern error: ${error.message}\n${error.stack}`);
            host.showMessage('error', t('message.failedToStartRunner', { error: error.message }));
            return;
        }

        if (patternName) {
            await _openPatternFromWebview(runner, patternName, sourceFile, { forceNewWindow });
            return;
        }
        await _openBookFromWebview(runner, sourceFile);
    }

    // The pattern session whose panel is active, else one that is visible.
    function _findActiveOrVisiblePatternSession() {
        const open = [...patternSessions.values()].filter((session) => !session.isDisposed && session.panel);
        return open.find((session) => session.panel.active)
            || open.find((session) => session.panel.visible)
            || null;
    }

    function _findAnyAliveMainSession() {
        for (const session of frameSessions.values()) {
            if (!session.isDisposed && session.runnerSession && session.runnerSession.isAlive()) {
                return session;
            }
        }
        return null;
    }

    // A runner for sidebar opens that doesn't force a main viewer open: an alive
    // main session's runner, else an alive standalone one, else a new one.
    async function _getOrCreateBackgroundRunner(sourceFile) {
        const mainSession = _findAnyAliveMainSession();
        if (mainSession && mainSession.runnerSession && mainSession.runnerSession.isAlive()) {
            return mainSession.runnerSession;
        }
        for (const existing of standaloneRunners) {
            if (existing && existing.isAlive && existing.isAlive()) {
                return existing;
            }
            standaloneRunners.delete(existing);
        }
        const runner = new PythonRunnerSession(sourceFile, context, outputChannel);
        await runner.start();
        standaloneRunners.add(runner);
        return runner;
    }

    // Creates a pattern session sharing `runner`, registers it and brings it up.
    async function createPatternSession(runner, slotName, sourceFile, patternName, refreshReason) {
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
        await patternSession.refresh(refreshReason);
        return patternSession;
    }

    // Opens a pattern, replacing the active/visible pattern viewer unless forceNewWindow.
    async function _openPatternFromWebview(runner, patternName, sourceFile, { forceNewWindow = false } = {}) {
        if (!runner || !runner.isAlive()) {
            host.showMessage('error', t('message.runnerNotRunning'));
            return;
        }

        patternSlotCounter += 1;
        const slotName = `pattern_${patternSlotCounter}`;
        await runner.request('raise_specific_pattern', { slot: slotName, sourceFile, patternName });

        if (!forceNewWindow) {
            const existingSession = _findActiveOrVisiblePatternSession();
            if (existingSession) {
                const oldSlotName = existingSession.slotName;
                patternSessions.delete(oldSlotName);
                patternSessions.set(slotName, existingSession);
                try {
                    if (runner.isAlive() && oldSlotName !== slotName) {
                        await runner.request('unload_slot', { slot: oldSlotName });
                    }
                } catch (err) {
                    outputChannel.appendLine(`Failed to unload old slot '${oldSlotName}': ${err.message || err}`);
                }
                existingSession.reassignPattern({ slotName, patternName, filePath: sourceFile });
                existingSession.reveal();
                await existingSession.refresh('pattern replaced from sidebar');
                return;
            }
        }

        await createPatternSession(runner, slotName, sourceFile, patternName, 'pattern open from webview');
    }

    // Opens a whole pattern book (the file's example/patternbook) as one tab.
    async function _openBookFromWebview(runner, sourceFile) {
        if (!runner || !runner.isAlive()) {
            host.showMessage('error', t('message.runnerNotRunning'));
            return;
        }

        patternSlotCounter += 1;
        const slotName = `pattern_${patternSlotCounter}`;
        const bookName = sourceFile.replace(/\\/g, '/').split('/').pop().replace(/\.py$/, '');
        await runner.request('load_slot', { slot: slotName, filePath: sourceFile });
        await createPatternSession(runner, slotName, sourceFile, bookName, 'book open from webview');
    }

    // The session for a file, reused if one is open.
    async function getOrCreateSession(filePath) {
        const normalizedFilePath = normalizeSessionFilePath(filePath);
        const existingSession = getFrameSession(normalizedFilePath || filePath);
        if (existingSession && !existingSession.isDisposed) {
            return existingSession;
        }

        const session = new FrameViewSession(
            normalizedFilePath || filePath,
            context,
            outputChannel,
            (disposedFilePath) => {
                if (frameSessions.get(disposedFilePath) === session) {
                    frameSessions.delete(disposedFilePath);
                }
            },
            { slotName: 'main', sessionType: 'main', openInSplitView, autoRefreshOnFileChange }
        );
        frameSessions.set(normalizedFilePath || filePath, session);
        await session.initialize();
        return session;
    }

    function getFrameSession(filePath) {
        const normalizedTarget = normalizeSessionFilePath(filePath);
        if (!normalizedTarget) {
            return null;
        }
        for (const [key, session] of frameSessions.entries()) {
            if (!session.isDisposed && normalizeSessionFilePath(key) === normalizedTarget) {
                return session;
            }
        }
        return null;
    }

    async function ensureViewerSessionForScreenshot(options) {
        const session = findSessionFromOptions(options);
        if (session && !session.isDisposed) {
            session.reveal();
            return session;
        }

        const requested = typeof options.filePath === 'string' && options.filePath
            ? options.filePath
            : getActivePythonFilePath();
        const targetFilePath = requested ? normalizeSessionFilePath(requested) : null;
        if (!targetFilePath) {
            throw new Error(
                'No Kigumi viewer is open. Open a Python frame file and run "Kigumi: Open Current File In Viewer", or pass filePath to the screenshot command.'
            );
        }

        const existingSession = getFrameSession(targetFilePath);
        if (existingSession && !existingSession.isDisposed) {
            existingSession.reveal();
            return existingSession;
        }

        await openFileInViewer(targetFilePath);
        const openedSession = getFrameSession(targetFilePath);
        if (!openedSession || openedSession.isDisposed) {
            throw new Error(`Could not open Kigumi viewer for ${targetFilePath}`);
        }
        return openedSession;
    }

    function findSessionFromOptions(options = {}) {
        if (options && typeof options.slotName === 'string' && options.slotName.length > 0) {
            const patternSession = patternSessions.get(options.slotName);
            if (patternSession && !patternSession.isDisposed) {
                return patternSession;
            }
        }

        const active = host.activeFile();
        const targetFilePath = typeof options.filePath === 'string' && options.filePath
            ? options.filePath
            : (active ? active.filePath : null);
        if (targetFilePath) {
            const frameSession = getFrameSession(targetFilePath);
            if (frameSession && !frameSession.isDisposed) {
                return frameSession;
            }
        }

        return [...frameSessions.values(), ...patternSessions.values()].find((session) => !session.isDisposed) || null;
    }

    function pruneWorkspaceLogs() {
        for (const root of host.workspaceRoots()) {
            try {
                const result = pruneOldLogFiles(root, logRetentionDays);
                if (result.removedFiles.length > 0) {
                    outputChannel.appendLine(`[kigumi] Removed ${result.removedFiles.length} old log file(s) from ${result.logsDir}`);
                }
            } catch (error) {
                outputChannel.appendLine(`[kigumi] Failed to prune old logs in ${root}: ${error.message || error}`);
            }
        }
    }

    // Disposes every session and runner, and the app's own listeners.
    async function dispose() {
        const allSessions = [...frameSessions.values(), ...patternSessions.values()];
        frameSessions.clear();
        patternSessions.clear();
        await Promise.allSettled(allSessions.map((session) => session.dispose()));
        const runners = Array.from(standaloneRunners);
        standaloneRunners.clear();
        await Promise.allSettled(runners.map((runner) => runner.dispose()));
        for (const disposable of disposables.splice(0)) {
            disposable.dispose();
        }
    }

    return {
        commands,
        sidebarModel,
        sidebarController,
        get openInSplitView() { return openInSplitView; },
        dispose,
    };
}

module.exports = { createKigumiApp };
