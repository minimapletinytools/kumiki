const path = require('path');
const fs = require('fs');
const vscode = require('vscode');
const { PythonRunnerSession } = require('./runner-session');
const { FileWatcher } = require('./file-watcher');
const { RefreshProfiler } = require('./refresh-profiler');
const { createFrameViewer, initializeFrameViewer, renderFrameViewer, requestViewerScreenshot } = require('./viewer');

const VIEWER_LOG_LEVEL_ORDER = {
    debug: 10,
    info: 20,
    warn: 30,
    error: 40,
};

// Minimum level to allow per log source. Lower levels are suppressed.
const VIEWER_LOG_SOURCE_MIN_LEVEL = {
};

function normalizeViewerLogLevel(level) {
    if (typeof level !== 'string') {
        return 'info';
    }
    const normalized = level.toLowerCase();
    if (!Object.prototype.hasOwnProperty.call(VIEWER_LOG_LEVEL_ORDER, normalized)) {
        return 'info';
    }
    return normalized;
}

function shouldSuppressViewerLog(source, level) {
    const effectiveSource = typeof source === 'string' && source ? source : 'webview';
    const incomingLevel = normalizeViewerLogLevel(level);
    const minLevel = normalizeViewerLogLevel(VIEWER_LOG_SOURCE_MIN_LEVEL[effectiveSource] || 'debug');
    return VIEWER_LOG_LEVEL_ORDER[incomingLevel] < VIEWER_LOG_LEVEL_ORDER[minLevel];
}

function sanitizeLogPathSegment(value, fallback) {
    const normalized = String(value || fallback || 'session')
        .replace(/[^a-zA-Z0-9._-]+/g, '_')
        .replace(/^_+|_+$/g, '');
    return normalized || fallback || 'session';
}

class FrameViewSession {
    /**
     * @param {string} filePath
     * @param {vscode.ExtensionContext} context
     * @param {vscode.OutputChannel} channel
     * @param {Function} onDispose
     * @param {object} [options]
     * @param {string} [options.slotName]      - runner slot name (default: 'main')
     * @param {'main'|'pattern'} [options.sessionType] - controls panel-close behaviour
     * @param {PythonRunnerSession} [options.sharedRunner] - reuse an existing runner
     * @param {string} [options.patternName]   - human-readable pattern label
     */
    constructor(filePath, context, channel, onDispose, options = {}) {
        this.filePath = filePath;
        this.context = context;
        this.channel = channel;
        this.onDispose = onDispose;
        this.panel = null;
        this.runnerSession = options.sharedRunner || null;
        this.ownsRunner = !options.sharedRunner;
        this.fileWatcher = null;
        this.isDisposed = false;
        this.isRefreshing = false;
        this.pendingRefreshReason = null;
        this.refreshSequence = 0;
        this.refreshOptions = {};
        this.renderParameters = {};
        this.profiler = new RefreshProfiler({ log: (msg) => this.log(msg) });
        this.slotName = options.slotName || 'main';
        this.sessionType = options.sessionType || 'main';
        this.patternName = options.patternName || null;
        this.openInSplitView = options.openInSplitView !== false;
        this.autoRefreshOnFileChange = options.autoRefreshOnFileChange === true;
        this.lastDirtyRefreshVersion = null;
        this.lastRefreshReason = null;
        this.lastRefreshAt = null;
        this.viewerSettings = null;
        // Cached payloads for potential panel re-open flows
        this._lastFrameData = null;
        this._lastGeometryData = null;
        this._lastProfiling = null;
    }

    getViewerSettingsPath() {
        const workspaceFolder = vscode.workspace.getWorkspaceFolder(vscode.Uri.file(this.filePath));
        const projectRoot = this.runnerSession && this.runnerSession.projectRoot
            ? this.runnerSession.projectRoot
            : workspaceFolder && workspaceFolder.uri && workspaceFolder.uri.fsPath
                ? workspaceFolder.uri.fsPath
                : path.dirname(this.filePath);
        return path.join(projectRoot, '.kigumi', 'kigumi-settings.json');
    }

    loadViewerSettingsFromDisk() {
        const settingsPath = this.getViewerSettingsPath();
        if (!fs.existsSync(settingsPath)) {
            return null;
        }
        try {
            const raw = fs.readFileSync(settingsPath, 'utf8');
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== 'object') {
                return null;
            }
            return parsed;
        } catch (error) {
            this.log(`[settings] Failed to read ${settingsPath}: ${error.message || error}`);
            return null;
        }
    }

    async saveViewerSettingsToDisk(settings) {
        const settingsPath = this.getViewerSettingsPath();
        fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
        await fs.promises.writeFile(settingsPath, `${JSON.stringify(settings, null, 2)}\n`, 'utf8');
        return settingsPath;
    }

    getRefreshStatsPath() {
        const projectRoot = this.runnerSession && this.runnerSession.projectRoot
            ? this.runnerSession.projectRoot
            : path.dirname(this.filePath);
        return path.join(projectRoot, '.kigumi', 'refresh-stats.json');
    }

    getLogsDirectoryPath() {
        const projectRoot = this.runnerSession && this.runnerSession.projectRoot
            ? this.runnerSession.projectRoot
            : path.dirname(this.filePath);
        return path.join(projectRoot, '.kigumi', 'logs');
    }

    getSessionLogPath() {
        const baseFileName = sanitizeLogPathSegment(path.basename(this.filePath, path.extname(this.filePath)), 'frame');
        const slotName = sanitizeLogPathSegment(this.slotName, 'main');
        return path.join(this.getLogsDirectoryPath(), `${baseFileName}.${slotName}.jsonl`);
    }

    postLoadingStatus(stage, details = {}) {
        if (!this.panel) {
            return;
        }
        this.panel.webview.postMessage({
            type: 'viewerState',
            viewerOptions: this.refreshOptions,
            viewerSettings: this.viewerSettings,
            uiState: {
                phase: 'waiting_for_runner',
                loadingText: stage,
                keepLoading: true,
                refreshToken: Number.isFinite(details.refreshToken) ? details.refreshToken : this.refreshSequence,
                error: null,
            },
        }).catch((error) => {
            this.log(`[webview] Failed to post loading status '${stage}': ${error.message || error}`);
        });
    }

    writeRefreshStats(statsPayload) {
        return this.profiler.writeRefreshStats(statsPayload, this.getRefreshStatsPath());
    }

    async initialize() {
        if (this.isDisposed) {
            throw new Error(`Cannot initialize disposed frame view session for ${this.filePath}`);
        }
        if (this.panel) {
            return;
        }

        const initTiming = this.profiler.createTimingTracker({ stage: 'initialize' });
        this.profiler.markTiming(initTiming, 'initialize.start');

        if (!this.runnerSession) {
            this.runnerSession = new PythonRunnerSession(this.filePath, this.context, this.channel);
            this.ownsRunner = true;
        }

        this.viewerSettings = this.loadViewerSettingsFromDisk();
        if (this.viewerSettings && this.viewerSettings.viewerOptions && typeof this.viewerSettings.viewerOptions === 'object') {
            this.refreshOptions = {
                ...this.refreshOptions,
                ...this.viewerSettings.viewerOptions,
            };
        }

        this._setupRunnerMilestoneHandler();

        this.profiler.markTiming(initTiming, 'initialize.createPanel.start');
        const isLocalDev = this.runnerSession.isLocalDev;
        this.panel = createFrameViewer(this.filePath, this.patternName, isLocalDev, this.openInSplitView);
        this.profiler.markTiming(initTiming, 'initialize.createPanel.end');

        this.profiler.markTiming(initTiming, 'initialize.webviewHtml.start');
        initializeFrameViewer(this.panel, this.filePath, {
            loadingText: 'initial creation',
            viewerOptions: this.refreshOptions,
            viewerSettings: this.viewerSettings,
        }, this.runnerSession.isLocalDev);
        this.profiler.markTiming(initTiming, 'initialize.webviewHtml.end');
        this.panel.onDidDispose(() => {
            this.panel = null;
            this.log(`[panel] Panel closed, disposing session for slot '${this.slotName}'`);
            void this.dispose();
        });
        this._setupWebviewMessageHandler();
        this.log('[webview] viewer log bridge active');
        this.postLoadingStatus('raising frame', { reason: 'session initialize', refreshToken: this.refreshSequence });

        this.profiler.resetMilestones();
        this.profiler.markTiming(initTiming, 'initialize.runner.start');
        try {
            await this.runnerSession.start();
        } catch (startError) {
            this.profiler.markTiming(initTiming, 'initialize.runner.error', {
                message: startError && startError.message ? startError.message : String(startError),
            });
            this.channel.appendLine(`[${path.basename(this.filePath)}] Runner startup failed: ${startError && startError.message ? startError.message : String(startError)}`);
            this.channel.show(true);
            const errorMessage = `Failed to start Python runner. Check the output channel for details.`;
            this.pushViewerErrorStateWithLink(errorMessage, `Kigumi Python Runner Error: ${startError && startError.message ? startError.message : 'unknown'}`);
            throw startError;
        }
        this.profiler.markTiming(initTiming, 'initialize.runner.end');
        await this._pushCadqueryStatus();

        // For shared-runner pattern sessions, load the slot now
        if (this.sessionType === 'pattern' && !this.ownsRunner) {
            // Slot was already loaded by the caller (extension.js raise_specific_pattern)
        }

        this.profiler.markTiming(initTiming, 'initialize.watcher.start');
        this.fileWatcher = new FileWatcher(
            this.filePath,
            this.runnerSession.projectRoot,
            (source) => this.onFileChanged(source),
            (message) => this.log(`[watcher] ${message}`)
        );
        this.fileWatcher.start({ enabled: this.autoRefreshOnFileChange });
        this.profiler.markTiming(initTiming, 'initialize.watcher.end');

        this.profiler.markTiming(initTiming, 'initialize.end');

        this.log(`Session initialized for ${this.filePath} (slot=${this.slotName}, type=${this.sessionType})`);
    }

    _setupWebviewMessageHandler() {
        if (!this.panel) {
            return;
        }
        this.panel.webview.onDidReceiveMessage((message) => {
            if (!message) {
                return;
            }
            if (message.type === 'requestRefresh') {
                this.log('[webview] Manual refresh requested from viewer');
                if (message.renderParameters && typeof message.renderParameters === 'object') {
                    this.renderParameters = { ...message.renderParameters };
                }
                this.refresh('manual refresh button').catch((error) => {
                    this.log(`[refresh] Manual refresh failed: ${error.message || error}`);
                });
                return;
            }
            if (message.type === 'setRefreshOptions') {
                // Merge viewer-supplied refresh options (e.g. geometryMode) into the
                // session's stored options so subsequent get_geometry calls include
                // them. We do NOT trigger a refresh here: the viewer applies
                // client-side options (like geometryMode mesh swap) locally, and
                // any future refresh will pick up the stored options automatically.
                const options = (message.options && typeof message.options === 'object') ? message.options : {};
                this.refreshOptions = { ...this.refreshOptions, ...options };
                this.log(`[webview] setRefreshOptions: ${JSON.stringify(options)}`);
                return;
            }
            if (message.type === 'requestSaveViewerSettings') {
                this._handleSaveViewerSettingsRequest(message).catch((error) => {
                    this.log(`[settings] requestSaveViewerSettings error: ${error.message || error}`);
                });
                return;
            }
            if (message.type === 'openOutputChannel') {
                this.channel.show(true);
                return;
            }
            if (message.type === 'openKigumiOutput') {
                this.channel.show(true);
                return;
            }
            if (message.type === 'findCSGAtPoint') {
                this._handleFindCSGAtPoint(message).catch((err) => {
                    this.log(`[csg-nav] findCSGAtPoint error: ${err.message || err}`);
                });
                return;
            }
            if (message.type === 'requestCSGTree') {
                this._handleRequestCSGTree(message).catch((err) => {
                    this.log(`[layers] requestCSGTree error: ${err.message || err}`);
                });
                return;
            }
            if (message.type === 'requestCSGByPath') {
                this._handleRequestCSGByPath(message).catch((err) => {
                    this.log(`[layers] requestCSGByPath error: ${err.message || err}`);
                });
                return;
            }
            if (message.type === 'requestLayersTree') {
                this._handleRequestLayersTree(message).catch((err) => {
                    this.log(`[layers] requestLayersTree error: ${err.message || err}`);
                });
                return;
            }
            if (message.type === 'requestExportStl') {
                this._handleExportBatchRequest({
                    formats: ['stl', '3mf'],
                    includeCombined: true,
                    includeIndividuals: message.includeIndividuals !== false,
                    includeAccessories: message.includeAccessories !== false,
                }).catch((err) => {
                    this.log(`[export] requestExportStl error: ${err.message || err}`);
                });
                return;
            }
            if (message.type === 'requestExportStep') {
                this._handleExportBatchRequest({
                    formats: ['step'],
                    includeCombined: true,
                    includeIndividuals: message.includeIndividuals !== false,
                    includeAccessories: message.includeAccessories !== false,
                }).catch((err) => {
                    this.log(`[export] requestExportStep error: ${err.message || err}`);
                });
                return;
            }
            if (message.type === 'requestExportFiles') {
                this._handleExportBatchRequest(message).catch((err) => {
                    this.log(`[export] requestExportFiles error: ${err.message || err}`);
                });
                return;
            }
            if (message.type === 'requestInstallCadqueryOcp') {
                this._handleInstallCadqueryOcp().catch((err) => {
                    this.log(`[export] requestInstallCadqueryOcp error: ${err.message || err}`);
                });
                return;
            }
            if (message.type !== 'viewerLog') {
                return;
            }
            const eventName = typeof message.event === 'string' ? message.event : 'unknown';
            const source = typeof message.source === 'string' ? message.source : 'webview';
            const level = normalizeViewerLogLevel(message.level);
            if (shouldSuppressViewerLog(source, level)) {
                return;
            }
            const version = typeof message.version === 'string' ? message.version : 'unknown';
            const details = message.details && typeof message.details === 'object'
                ? JSON.stringify(message.details)
                : '{}';
            this.log(`[webview:${source}:${level}] ${eventName} v${version} ${details}`);
        });
    }

    getLogSnapshot(options = {}) {
        const minLevel = normalizeViewerLogLevel(options.minLevel || 'debug');
        const containsText = typeof options.contains === 'string' ? options.contains.trim().toLowerCase() : '';
        const logPath = this.getSessionLogPath();
        const allEntries = [];

        if (fs.existsSync(logPath)) {
            const rawLines = fs.readFileSync(logPath, 'utf8')
                .split('\n')
                .map((line) => line.trim())
                .filter((line) => line.length > 0);
            for (const line of rawLines) {
                try {
                    const parsed = JSON.parse(line);
                    if (parsed && typeof parsed === 'object') {
                        allEntries.push(parsed);
                    }
                } catch (_error) {
                    // Ignore malformed trailing or partial log lines.
                }
            }
        }

        const entries = allEntries.filter((entry) => {
            if (VIEWER_LOG_LEVEL_ORDER[entry.level] < VIEWER_LOG_LEVEL_ORDER[minLevel]) {
                return false;
            }
            if (containsText && !String(entry.message).toLowerCase().includes(containsText)) {
                return false;
            }
            return true;
        });
        if (options.clear === true) {
            fs.mkdirSync(path.dirname(logPath), { recursive: true });
            fs.writeFileSync(logPath, '', 'utf8');
        }
        return {
            logPath,
            totalEntries: allEntries.length,
            returnedEntries: entries.length,
            entries,
        };
    }

    async refreshOnceIfDirty(options = {}) {
        const textDocument = await vscode.workspace.openTextDocument(vscode.Uri.file(this.filePath));
        if (!textDocument.isDirty) {
            this.lastDirtyRefreshVersion = null;
            return {
                refreshed: false,
                reason: 'not-dirty',
                filePath: this.filePath,
                version: textDocument.version,
            };
        }

        const targetVersion = textDocument.version;
        if (this.lastDirtyRefreshVersion === targetVersion) {
            return {
                refreshed: false,
                reason: 'already-refreshed-for-version',
                filePath: this.filePath,
                version: targetVersion,
            };
        }

        const saveIfDirty = options.saveIfDirty !== false;
        if (saveIfDirty) {
            await textDocument.save();
        }

        await this.refresh(options.reason || 'automation dirty refresh once');
        this.lastDirtyRefreshVersion = targetVersion;
        return {
            refreshed: true,
            reason: saveIfDirty ? 'dirty-save-and-refresh' : 'dirty-refresh',
            filePath: this.filePath,
            version: targetVersion,
        };
    }

    setWatcherEnabled(enabled) {
        this.autoRefreshOnFileChange = Boolean(enabled);
        if (this.fileWatcher) {
            this.fileWatcher.setEnabled(this.autoRefreshOnFileChange);
        }
    }

    isWatcherEnabled() {
        if (!this.fileWatcher) {
            return this.autoRefreshOnFileChange;
        }
        return this.fileWatcher.isEnabled;
    }

    async syncRenderParametersFromPanel() {
        if (this.isDisposed || !this.panel) {
            return;
        }

        try {
            const payload = await this._requestWebviewAction(
                'collectPendingRenderParameters',
                'collect-pending-render-parameters',
            );
            if (payload.renderParameters && typeof payload.renderParameters === 'object') {
                this.renderParameters = { ...payload.renderParameters };
            }
        } catch (error) {
            this.log(`[refresh] Could not sync panel parameters: ${error.message || error}`);
        }
    }

    async refreshWithPanelParameters(reason = 'manual render') {
        await this.syncRenderParametersFromPanel();
        await this.refresh(reason);
    }

    getCameraState() {
        return this._requestWebviewAction('getCameraState', 'get-camera-state');
    }

    setCameraState(cameraState, options = {}) {
        return this._requestWebviewAction('setCameraState', 'set-camera-state', {
            cameraState,
            options,
        });
    }

    _requestWebviewAction(type, requestPrefix, payload = {}, options = {}) {
        if (this.isDisposed || !this.panel) {
            return Promise.reject(new Error(`Viewer panel is not available for ${this.filePath}`));
        }

        const timeoutMs = Number.isFinite(options.timeoutMs) ? Number(options.timeoutMs) : 6000;
        const requestId = `${requestPrefix}-${Date.now()}-${Math.floor(Math.random() * 1000000)}`;
        const requestType = `${type}Request`;
        const resultType = `${type}Result`;

        return new Promise((resolve, reject) => {
            let settled = false;
            let timeoutHandle = null;

            const cleanup = () => {
                if (timeoutHandle) {
                    clearTimeout(timeoutHandle);
                    timeoutHandle = null;
                }
                listener.dispose();
            };

            const listener = this.panel.webview.onDidReceiveMessage((message) => {
                if (!message || message.type !== resultType || message.requestId !== requestId) {
                    return;
                }
                if (settled) {
                    return;
                }
                settled = true;
                cleanup();
                if (message.ok) {
                    resolve(message.payload || {});
                    return;
                }
                reject(new Error(message.error || `${type} failed`));
            });

            timeoutHandle = setTimeout(() => {
                if (settled) {
                    return;
                }
                settled = true;
                cleanup();
                reject(new Error(`Timed out waiting for ${type} (${timeoutMs}ms)`));
            }, timeoutMs);

            this.panel.webview.postMessage({
                type: requestType,
                requestId,
                ...payload,
            }).then((posted) => {
                if (!posted && !settled) {
                    settled = true;
                    cleanup();
                    reject(new Error(`Failed to post ${requestType} to webview`));
                }
            }, (error) => {
                if (!settled) {
                    settled = true;
                    cleanup();
                    reject(error);
                }
            });
        });
    }

    /**
     * Re-create the webview panel for a pattern session whose runner is still alive.
     */
    async reopenPanel() {
        if (this.isDisposed) {
            throw new Error(`Cannot reopen disposed session for ${this.filePath}`);
        }
        if (this.panel) {
            return; // already has a panel
        }
        if (!this.runnerSession || !this.runnerSession.isAlive()) {
            throw new Error(`Runner is not alive for ${this.filePath}`);
        }

        const isLocalDev = this.runnerSession.isLocalDev;
        this.panel = createFrameViewer(this.filePath, this.patternName, isLocalDev, this.openInSplitView);
        this.panel.onDidDispose(() => {
            this.panel = null;
            this.log(`[panel] Panel closed, disposing session for slot '${this.slotName}'`);
            void this.dispose();
        });
        this._setupWebviewMessageHandler();

        if (this._lastFrameData && this._lastGeometryData) {
            // Fast path: use cached data, no round-trip to runner
            renderFrameViewer(this.panel, this.filePath, this._lastFrameData, this._lastGeometryData, this._lastProfiling, {
                phase: 'ready',
                refreshToken: this.refreshSequence,
                loadingText: '',
                keepLoading: false,
            }, this.refreshOptions, this.viewerSettings);
            this.log(`[reopen] Re-rendered from cached data for slot '${this.slotName}'`);
        } else {
            initializeFrameViewer(this.panel, this.filePath, {
                loadingText: 'reopening',
                viewerOptions: this.refreshOptions,
                viewerSettings: this.viewerSettings,
            }, isLocalDev);
            await this.refresh('panel reopen');
        }
    }

    reveal() {
        if (this.panel) {
            this.panel.reveal();
        }
    }

    async ensureRunnerSession() {
        if (this.isDisposed) {
            throw new Error(`Session is disposed for ${this.filePath}`);
        }

        if (this.runnerSession && this.runnerSession.isAlive()) {
            return;
        }

        // Shared runners are managed by the owner — don't restart here
        if (!this.ownsRunner) {
            throw new Error(`Shared runner is dead for slot '${this.slotName}'; owner must restart it`);
        }

        if (this.runnerSession) {
            try {
                await this.runnerSession.dispose();
            } catch (error) {
                this.log(`[runner] dispose after failure: ${error.message || error}`);
            }
        }

        this.log(`[runner] Restarting Python runner for ${path.basename(this.filePath)}`);
        this.runnerSession = new PythonRunnerSession(this.filePath, this.context, this.channel);
        this._setupRunnerMilestoneHandler();
        await this.runnerSession.start();
    }

    async refresh(reason = 'manual render') {
        if (this.isDisposed) {
            return;
        }
        if (this.isRefreshing) {
            this.pendingRefreshReason = reason;
            this.log(`[refresh] Queuing pending refresh for ${this.filePath} (${reason})`);
            return;
        }

        this.isRefreshing = true;
        this.pendingRefreshReason = null;
        this.refreshSequence += 1;
        const refreshToken = this.refreshSequence;
        this.lastRefreshReason = reason;
        this.lastRefreshAt = new Date().toISOString();
        this.log(`[refresh] Reloading ${path.basename(this.filePath)} (${reason})`);
        this.postLoadingStatus('raising frame', { reason, refreshToken });
        let refreshError = null;
        const timing = this.profiler.createTimingTracker({ reason, refreshToken });
        this.profiler.markTiming(timing, 'refresh.start', { reason, refreshToken });
        this.profiler.resetMilestones();
        try {
            const refreshStartNs = process.hrtime.bigint();

            this.profiler.markTiming(timing, 'ensureRunner.start');
            await this.ensureRunnerSession();
            this.profiler.markTiming(timing, 'ensureRunner.end');

            this.profiler.markTiming(timing, 'runner.reload_example.start');
            const reloadResult = await this.runnerSession.slotRequest('reload_example', this.slotName, {
                filePath: this.filePath,
                renderParameters: this.renderParameters,
            });
            this.profiler.markTiming(timing, 'runner.reload_example.end');

            this.profiler.markTiming(timing, 'runner.get_frame.start');
            const frameData = await this.runnerSession.slotRequest('get_frame', this.slotName);
            this.profiler.markTiming(timing, 'runner.get_frame.end');
            const frameRenderParams = frameData && frameData.renderParameters && typeof frameData.renderParameters === 'object'
                ? frameData.renderParameters
                : null;
            if (frameRenderParams && frameRenderParams.applied && typeof frameRenderParams.applied === 'object') {
                this.renderParameters = { ...frameRenderParams.applied };
            }

            this.profiler.markTiming(timing, 'runner.get_geometry.start');
            const geometryData = await this.runnerSession.slotRequest('get_geometry', this.slotName, this.refreshOptions);
            this.profiler.markTiming(timing, 'runner.get_geometry.end');

            this.profiler.markTiming(timing, 'runner.get_layers_tree.start');
            let layersData = null;
            try {
                layersData = await this.runnerSession.slotRequest('get_layers_tree', this.slotName);
            } catch (err) {
                this.log(`[layers] get_layers_tree failed: ${err.message || err}`);
            }
            this.profiler.markTiming(timing, 'runner.get_layers_tree.end');

            const refresh_total_s = Number(process.hrtime.bigint() - refreshStartNs) / 1e9;

            const changedKeys = Array.isArray(geometryData && geometryData.changedKeys) ? geometryData.changedKeys : [];
            const removedKeys = Array.isArray(geometryData && geometryData.removedKeys) ? geometryData.removedKeys : [];
            const meshes = Array.isArray(geometryData && geometryData.meshes) ? geometryData.meshes : [];
            const remeshMetrics = Array.isArray(geometryData && geometryData.remeshMetrics) ? geometryData.remeshMetrics : [];
            const totalTimbers = geometryData && geometryData.counts && Number.isFinite(geometryData.counts.totalTimbers)
                ? geometryData.counts.totalTimbers
                : meshes.length;

            const refreshStatsPayload = {
                timestamp: new Date().toISOString(),
                sourceFile: this.filePath,
                reason,
                refresh: {
                    scriptReloadDuration_ms: reloadResult && reloadResult.profiling && typeof reloadResult.profiling.reload_s === 'number'
                        ? Math.round(reloadResult.profiling.reload_s * 1000)
                        : null,
                    meshBuildDuration_ms: geometryData && geometryData.profiling && typeof geometryData.profiling.geometry_s === 'number'
                        ? Math.round(geometryData.profiling.geometry_s * 1000)
                        : null,
                    totalRefreshDuration_ms: Math.round(refresh_total_s * 1000),
                    changedTimberCount: changedKeys.length,
                    removedTimberCount: removedKeys.length,
                    totalTimberCount: totalTimbers,
                    changedTimberKeys: changedKeys,
                    removedTimberKeys: removedKeys,
                    timings: this.profiler.buildTimingSummary(timing, reloadResult, geometryData),
                    perTimberMetrics: remeshMetrics.map((entry) => ({
                        timberKey: entry.timberKey,
                        remeshDuration_ms: typeof entry.remesh_s === 'number' ? Math.round(entry.remesh_s * 1000) : null,
                        csgDepth: typeof entry.csg_depth === 'number' ? entry.csg_depth : null,
                        triangleCount: typeof entry.triangle_count === 'number' ? entry.triangle_count : null,
                    })),
                },
            };

            this.profiler.markTiming(timing, 'stats.write.start');
            const statsPath = this.writeRefreshStats(refreshStatsPayload);
            this.profiler.markTiming(timing, 'stats.write.end', { statsPath });

            this.profiler.markTiming(timing, 'webview.renderFrameViewer.start');
            const profiling = {
                reload_s: reloadResult && reloadResult.profiling ? reloadResult.profiling.reload_s : null,
                geometry_s: geometryData && geometryData.profiling ? geometryData.profiling.geometry_s : null,
                refresh_total_s,
                changed_timbers: changedKeys.length,
                removed_timbers: removedKeys.length,
                total_timbers: totalTimbers,
                remesh_metrics: remeshMetrics,
                timing: this.profiler.buildTimingSummary(timing, reloadResult, geometryData),
                milestones: this.profiler.getMilestones(),
                stats_path: statsPath,
            };
            renderFrameViewer(this.panel, this.filePath, frameData, geometryData, profiling, {
                phase: 'ready',
                refreshToken,
                loadingText: '',
                keepLoading: false,
            }, this.refreshOptions, this.viewerSettings);
            // Cache payloads for panel re-open (pattern sessions)
            this._lastFrameData = frameData;
            this._lastGeometryData = geometryData;
            this._lastProfiling = profiling;
            this._lastLayersData = layersData;
            if (layersData && this.panel && !this.isDisposed) {
                this.panel.webview.postMessage({
                    type: 'layersTree',
                    payload: layersData,
                }).catch((err) => {
                    this.log(`[layers] Failed to post layers tree: ${err.message || err}`);
                });
            }
            this.profiler.markTiming(timing, 'webview.renderFrameViewer.end');
            this.profiler.markTiming(timing, 'refresh.end', { refresh_total_ms: Math.round(refresh_total_s * 1000) });
            await this._pushCadqueryStatus();
            this.log(`[refresh] Reload complete for ${path.basename(this.filePath)}`);
        } catch (error) {
            refreshError = error;
            this.profiler.markTiming(timing, 'refresh.error', {
                message: error && error.message ? error.message : String(error),
            });
        } finally {
            this.isRefreshing = false;
        }

        // Drain pending refresh before blocking on error reporting
        if (this.pendingRefreshReason) {
            const pendingReason = this.pendingRefreshReason;
            this.pendingRefreshReason = null;
            this.log(`[refresh] Draining pending refresh (${pendingReason})`);
            // Fire-and-forget so it doesn't block error reporting
            this.refresh(pendingReason).catch((err) => {
                this.log(`[refresh] Pending refresh failed: ${err.message || err}`);
            });
        }

        if (refreshError) {
            await this.reportRunnerError(refreshError, `[refresh] ${path.basename(this.filePath)} (${reason})`);
            throw refreshError;
        }
    }

    async captureScreenshot(options = {}) {
        if (this.isDisposed || !this.panel) {
            throw new Error(`Viewer panel is not available for ${this.filePath}`);
        }

        const timeoutMs = typeof options.timeoutMs === 'number' ? options.timeoutMs : 8000;
        const result = await requestViewerScreenshot(this.panel, { timeoutMs });

        const dataUrl = result.dataUrl || '';
        const match = /^data:image\/png;base64,(.+)$/u.exec(dataUrl);
        if (!match) {
            throw new Error('Screenshot payload is not a PNG data URL');
        }

        const imageBuffer = Buffer.from(match[1], 'base64');
        if (options.outputPath) {
            fs.mkdirSync(path.dirname(options.outputPath), { recursive: true });
            fs.writeFileSync(options.outputPath, imageBuffer);
            this.log(`[screenshot] Wrote ${options.outputPath}`);
        }

        return {
            outputPath: options.outputPath || null,
            byteLength: imageBuffer.length,
            width: result.width,
            height: result.height,
        };
    }

    async capturePanelSnapshot(options = {}) {
        if (this.isDisposed || !this.panel) {
            throw new Error(`Viewer panel is not available for ${this.filePath}`);
        }

        const timeoutMs = typeof options.timeoutMs === 'number' ? options.timeoutMs : 3000;
        const requestId = `panel-snapshot-${Date.now()}-${Math.floor(Math.random() * 1000000)}`;

        return new Promise((resolve, reject) => {
            let settled = false;
            let timeoutHandle = null;

            const cleanup = () => {
                if (timeoutHandle) {
                    clearTimeout(timeoutHandle);
                    timeoutHandle = null;
                }
                listener.dispose();
            };

            const listener = this.panel.webview.onDidReceiveMessage((message) => {
                if (!message || message.type !== 'capturePanelSnapshotResult' || message.requestId !== requestId) {
                    return;
                }
                if (settled) {
                    return;
                }

                settled = true;
                cleanup();
                if (message.ok) {
                    resolve(message.snapshot || {});
                    return;
                }
                reject(new Error(message.error || 'Panel snapshot failed'));
            });

            timeoutHandle = setTimeout(() => {
                if (settled) {
                    return;
                }
                settled = true;
                cleanup();
                reject(new Error(`Timed out waiting for panel snapshot (${timeoutMs}ms)`));
            }, timeoutMs);

            this.panel.webview.postMessage({
                type: 'capturePanelSnapshotRequest',
                requestId,
            }).then((posted) => {
                if (!posted && !settled) {
                    settled = true;
                    cleanup();
                    reject(new Error('Failed to post panel snapshot request to webview'));
                }
            }, (error) => {
                if (!settled) {
                    settled = true;
                    cleanup();
                    reject(error);
                }
            });
        });
    }

    getTestSnapshot() {
        const frameData = this._lastFrameData || null;
        const geometryData = this._lastGeometryData || null;
        const profilingData = this._lastProfiling || null;
        return {
            filePath: this.filePath,
            isDisposed: this.isDisposed,
            hasPanel: Boolean(this.panel),
            panelTitle: this.panel ? this.panel.title : null,
            sessionType: this.sessionType,
            slotName: this.slotName,
            refreshSequence: this.refreshSequence,
            lastRefreshReason: this.lastRefreshReason,
            lastRefreshAt: this.lastRefreshAt,
            lastDirtyRefreshVersion: this.lastDirtyRefreshVersion,
            watcherEnabled: this.isWatcherEnabled(),
            logPath: this.getSessionLogPath(),
            hasRunner: Boolean(this.runnerSession),
            runnerAlive: Boolean(this.runnerSession && this.runnerSession.isAlive()),
            frame: frameData ? {
                name: frameData.name || null,
                timberCount: Number.isFinite(frameData.timber_count) ? frameData.timber_count : 0,
                accessoryCount: Number.isFinite(frameData.accessories_count) ? frameData.accessories_count : 0,
            } : null,
            geometry: geometryData ? {
                meshCount: Array.isArray(geometryData.meshes) ? geometryData.meshes.length : 0,
                changedCount: Array.isArray(geometryData.changedKeys) ? geometryData.changedKeys.length : 0,
                removedCount: Array.isArray(geometryData.removedKeys) ? geometryData.removedKeys.length : 0,
            } : null,
            profiling: profilingData ? {
                reloadSeconds: typeof profilingData.reload_s === 'number' ? profilingData.reload_s : null,
                geometrySeconds: typeof profilingData.geometry_s === 'number' ? profilingData.geometry_s : null,
                refreshTotalSeconds: typeof profilingData.refresh_total_s === 'number' ? profilingData.refresh_total_s : null,
            } : null,
        };
    }

    async _handleFindCSGAtPoint(message) {
        if (!this.runnerSession) {
            return;
        }
        const payload = {
            memberKey: message.memberKey,
            point: message.point,
            currentPath: message.currentPath || [],
            ctrlClick: !!message.ctrlClick,
        };
        const result = await this.runnerSession.slotRequest('find_csg_at_point', this.slotName, payload);
        if (this.panel && !this.isDisposed) {
            this.panel.webview.postMessage({ type: 'csgSelectionResult', ...result });
        }
    }

    async _handleRequestCSGTree(message) {
        if (!this.runnerSession) {
            return;
        }
        const payload = {
            memberKey: message.memberKey,
            cutIndex: Number.isFinite(message.cutIndex) ? Number(message.cutIndex) : 0,
        };
        const result = await this.runnerSession.slotRequest('get_csg_tree', this.slotName, payload);
        if (this.panel && !this.isDisposed) {
            this.panel.webview.postMessage({ type: 'csgTree', payload: result });
        }
    }

    async _handleRequestCSGByPath(message) {
        if (!this.runnerSession) {
            return;
        }
        const payload = {
            memberKey: message.memberKey,
            path: Array.isArray(message.path) ? message.path : [],
            featureLabel: message.featureLabel || null,
        };
        try {
            const result = await this.runnerSession.slotRequest('find_csg_by_path', this.slotName, payload);
            if (this.panel && !this.isDisposed) {
                this.panel.webview.postMessage({ type: 'csgSelectionResult', ...result });
            }
        } catch (err) {
            this.log(`[layers] find_csg_by_path failed: ${err.message || err}`);
        }
    }

    async _handleRequestLayersTree(message) {
        if (!this.runnerSession) {
            return;
        }
        const result = await this.runnerSession.slotRequest('get_layers_tree', this.slotName);
        if (this.panel && !this.isDisposed) {
            this.panel.webview.postMessage({ type: 'layersTree', payload: result });
        }
    }

    getExportDirectory() {
        const projectRoot = this.runnerSession && this.runnerSession.projectRoot
            ? this.runnerSession.projectRoot
            : path.dirname(this.filePath);
        const baseName = path.basename(this.filePath, path.extname(this.filePath));
        const safeBaseName = (baseName || 'frame')
            .replace(/[^a-zA-Z0-9._-]+/g, '_')
            .replace(/^_+|_+$/g, '') || 'frame';
        return path.join(projectRoot, 'kigumi_exports', safeBaseName);
    }

    async _handleExportRequest(format, includeCombined = true, includeIndividuals = true, includeAccessories = true) {
        if (!this.runnerSession) {
            return;
        }

        await this.ensureRunnerSession();

        const normalizedFormat = format === 'step'
            ? 'step'
            : format === '3mf'
                ? '3mf'
                : format === 'obj'
                    ? 'obj'
                    : 'stl';
        const outputDir = this.getExportDirectory();
        fs.mkdirSync(outputDir, { recursive: true });

        try {
            const result = await this.runnerSession.slotRequest('export_frame', this.slotName, {
                format: normalizedFormat,
                outputDir,
                includeCombined: Boolean(includeCombined),
                includeIndividuals: Boolean(includeIndividuals),
                includeAccessories: Boolean(includeAccessories),
            });

            const writtenFiles = Array.isArray(result && result.files) ? result.files : [];
            const formatLabel = normalizedFormat.toUpperCase();
            this.log(`[export] Wrote ${writtenFiles.length} ${formatLabel} file(s) to ${outputDir}`);
            return { format: normalizedFormat, writtenFiles, outputDir };
        } catch (error) {
            const details = this.extractRunnerErrorDetails(error);
            const formatLabel = normalizedFormat.toUpperCase();
            this.log(`[export] ${formatLabel} export failed: ${details.message}`);

            const openOutputAction = 'Open Kigumi Output';
            const installHint = normalizedFormat === 'step' && details.message.includes('cadquery-ocp')
                ? ' Install STEP support with: pip install cadquery-ocp'
                : normalizedFormat === '3mf' && details.message.includes('3MF export requires')
                    ? ' Install 3MF support with: pip install lxml networkx'
                : '';
            const choice = await vscode.window.showErrorMessage(
                `Kigumi ${formatLabel} export failed: ${details.message}${installHint}`,
                openOutputAction
            );
            if (choice === openOutputAction) {
                this.channel.show(true);
            }
            throw error;
        }
    }

    async _handleExportBatchRequest(message) {
        const formatsRaw = Array.isArray(message && message.formats) ? message.formats : [];
        const formats = [...new Set(formatsRaw
            .map((entry) => (typeof entry === 'string' ? entry.toLowerCase() : ''))
            .filter((entry) => entry === 'stl' || entry === '3mf' || entry === 'obj' || entry === 'step'))];

        if (formats.length === 0) {
            void vscode.window.showWarningMessage('Select at least one export format.');
            return;
        }

        const includeCombined = message.includeCombined !== false;
        const includeIndividuals = message.includeIndividuals === true;
        const includeAccessories = message.includeAccessories !== false;

        if (!includeCombined && !includeIndividuals) {
            void vscode.window.showWarningMessage('Enable combined and/or individual export.');
            return;
        }

        const allWrittenFiles = [];
        const failedFormats = [];
        let outputDir = this.getExportDirectory();

        for (const format of formats) {
            try {
                const result = await this._handleExportRequest(
                    format,
                    includeCombined,
                    includeIndividuals,
                    includeAccessories,
                );
                if (result && Array.isArray(result.writtenFiles)) {
                    allWrittenFiles.push(...result.writtenFiles);
                    outputDir = result.outputDir || outputDir;
                }
            } catch (_error) {
                failedFormats.push(format.toUpperCase());
            }
        }

        const formatLabel = formats.map((entry) => entry.toUpperCase()).join(', ');
        const summary = `Kigumi exported ${allWrittenFiles.length} file(s) across ${formatLabel} to ${outputDir}`;
        this.log(`[export] ${summary}`);

        if (failedFormats.length > 0) {
            void vscode.window.showWarningMessage(`${summary}. Failed: ${failedFormats.join(', ')}`);
        } else {
            void vscode.window.showInformationMessage(summary);
        }
    }

    async _handleSaveViewerSettingsRequest(message) {
        const payload = (message && message.settings && typeof message.settings === 'object')
            ? message.settings
            : null;

        if (!payload) {
            throw new Error('requestSaveViewerSettings requires a settings payload');
        }

        const viewerOptions = (payload.viewerOptions && typeof payload.viewerOptions === 'object')
            ? payload.viewerOptions
            : {};
        const ui = (payload.ui && typeof payload.ui === 'object') ? payload.ui : {};
        const settings = {
            version: Number.isFinite(payload.version) ? Number(payload.version) : 1,
            savedAt: new Date().toISOString(),
            viewerOptions,
            ui,
        };

        const settingsPath = await this.saveViewerSettingsToDisk(settings);
        this.viewerSettings = settings;
        this.refreshOptions = { ...this.refreshOptions, ...viewerOptions };
        this.log(`[settings] Saved viewer settings to ${settingsPath}`);

        if (this.panel && !this.isDisposed) {
            this.panel.webview.postMessage({
                type: 'viewerSettingsSaved',
                ok: true,
                path: settingsPath,
                savedAt: settings.savedAt,
            }).catch((error) => {
                this.log(`[settings] Failed to post viewerSettingsSaved: ${error.message || error}`);
            });
        }
    }

    async _pushCadqueryStatus() {
        if (!this.panel || !this.runnerSession) {
            return;
        }

        let installed = false;
        try {
            installed = await this.runnerSession.isCadqueryOcpInstalled();
        } catch (error) {
            this.log(`[export] Failed to detect cadquery-ocp: ${error.message || error}`);
        }

        this.panel.webview.postMessage({
            type: 'dependencyStatus',
            payload: {
                cadqueryOcpInstalled: installed,
            },
        }).catch((error) => {
            this.log(`[webview] Failed to post dependency status: ${error.message || error}`);
        });
    }

    async _handleInstallCadqueryOcp() {
        if (!this.runnerSession) {
            return;
        }

        this._postCadqueryInstallStatus(true);
        try {
            await this.runnerSession.installCadqueryOcp();

            if (this.ownsRunner) {
                await this.runnerSession.dispose();
                this.runnerSession = null;
                await this.ensureRunnerSession();
            } else {
                this.log('[export] cadquery-ocp installed. Restart the main Kigumi viewer session if STEP export was attempted before install.');
            }

            await this._pushCadqueryStatus();
            void vscode.window.showInformationMessage('Kigumi installed cadquery-ocp for STEP export.');
        } catch (error) {
            const details = this.extractRunnerErrorDetails(error);
            this.log(`[export] cadquery-ocp install failed: ${details.message}`);
            const openOutputAction = 'Open Kigumi Output';
            const choice = await vscode.window.showErrorMessage(
                `Failed to install cadquery-ocp: ${details.message}`,
                openOutputAction
            );
            if (choice === openOutputAction) {
                this.channel.show(true);
            }
        } finally {
            this._postCadqueryInstallStatus(false);
        }
    }

    _postCadqueryInstallStatus(isInstalling) {
        if (!this.panel) {
            return;
        }

        this.panel.webview.postMessage({
            type: 'dependencyInstallStatus',
            payload: {
                installingCadqueryOcp: Boolean(isInstalling),
            },
        }).catch((error) => {
            this.log(`[webview] Failed to post dependency install status: ${error.message || error}`);
        });
    }

    async onFileChanged(source) {
        if (this.isDisposed) {
            return;
        }

        this.log(`[watcher] Auto-reloading due to ${source} change...`);
        try {
            await this.refresh(`${source} change`);
        } catch (error) {
            this.log(`[watcher] Auto-reload failed for ${path.basename(this.filePath)}: ${error.message || error}`);
        }
    }

    extractRunnerErrorDetails(error) {
        const payload = error && error.runnerError && typeof error.runnerError === 'object'
            ? error.runnerError
            : null;
        const message = payload && typeof payload.message === 'string'
            ? payload.message
            : (error && error.message ? error.message : String(error));
        const traceback = payload && typeof payload.traceback === 'string'
            ? payload.traceback
            : (error && typeof error.runnerTraceback === 'string' ? error.runnerTraceback : null);
        const type = payload && typeof payload.type === 'string'
            ? payload.type
            : (error && typeof error.runnerErrorType === 'string' ? error.runnerErrorType : null);
        return { message, traceback, type };
    }

    parseTracebackLocation(traceback) {
        if (!traceback || typeof traceback !== 'string') {
            return null;
        }
        const fileLineRegex = /File "([^"]+)", line (\d+)/g;
        const candidates = [];
        let match = fileLineRegex.exec(traceback);
        while (match) {
            candidates.push({ filePath: match[1], lineNumber: Number(match[2]) });
            match = fileLineRegex.exec(traceback);
        }
        for (let index = candidates.length - 1; index >= 0; index -= 1) {
            const candidate = candidates[index];
            if (candidate.filePath && fs.existsSync(candidate.filePath) && Number.isFinite(candidate.lineNumber)) {
                return candidate;
            }
        }
        return null;
    }

    deriveViewerErrorMessage(details) {
        const message = details && typeof details.message === 'string' ? details.message : '';
        if (!message) {
            return 'Unable to render this file in Kigumi viewer.';
        }

        if (message.includes("Module must expose a module-level 'example' Frame, a 'patternbook', or a build_frame() function")) {
            return "This file is not a valid Kigumi frame/example/pattern. Add module-level 'example', 'patternbook', or build_frame().";
        }

        if (message.includes('No patternbook found in')) {
            return 'This file does not define a patternbook that Kigumi can open.';
        }

        return `Kigumi failed to render this file: ${message}`;
    }

    pushViewerErrorState(details) {
        if (!this.panel) {
            return;
        }

        const refreshToken = this.refreshSequence;
        const loadingText = this.deriveViewerErrorMessage(details);
        this.panel.webview.postMessage({
            type: 'viewerState',
            uiState: {
                phase: 'error',
                loadingText,
                keepLoading: true,
                refreshToken,
                error: details && typeof details.message === 'string' ? details.message : null,
                showOutputLink: false,
            },
        }).catch((postError) => {
            this.log(`[webview] Failed to post error state: ${postError.message || postError}`);
        });
    }

    pushViewerErrorStateWithLink(displayMessage, fullError) {
        if (!this.panel) {
            return;
        }

        const refreshToken = this.refreshSequence;
        this.panel.webview.postMessage({
            type: 'viewerState',
            uiState: {
                phase: 'error',
                loadingText: displayMessage,
                keepLoading: true,
                refreshToken,
                error: fullError,
                showOutputLink: true,
            },
        }).catch((postError) => {
            this.log(`[webview] Failed to post error state with link: ${postError.message || postError}`);
        });
    }

    async openTracebackLocation(location) {
        if (!location) {
            return;
        }
        try {
            const uri = vscode.Uri.file(location.filePath);
            const document = await vscode.workspace.openTextDocument(uri);
            const editor = await vscode.window.showTextDocument(document, { preview: false });
            const lineIndex = Math.max(0, location.lineNumber - 1);
            const range = new vscode.Range(lineIndex, 0, lineIndex, 0);
            editor.selection = new vscode.Selection(range.start, range.end);
            editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
        } catch (openError) {
            this.log(`[error] Failed to open traceback location: ${openError.message || openError}`);
        }
    }

    async reportRunnerError(error, contextLabel) {
        const details = this.extractRunnerErrorDetails(error);
        const errorTypePart = details.type ? `${details.type}: ` : '';
        this.log(`[error] ${contextLabel} -> ${errorTypePart}${details.message}`);
        this.pushViewerErrorState(details);

        if (details.traceback) {
            this.channel.appendLine(`[${path.basename(this.filePath)}] [traceback] BEGIN`);
            for (const tracebackLine of details.traceback.split('\n')) {
                this.channel.appendLine(`[${path.basename(this.filePath)}] ${tracebackLine}`);
            }
            this.channel.appendLine(`[${path.basename(this.filePath)}] [traceback] END`);
        }

        this.channel.show(true);
        const location = this.parseTracebackLocation(details.traceback);
        const actions = ['Open Kigumi Output'];
        if (location) {
            actions.push('Go to Error');
        }

        const choice = await vscode.window.showErrorMessage(
            `Kigumi Python error: ${details.message}`,
            ...actions
        );

        if (choice === 'Open Kigumi Output') {
            this.channel.show(true);
        }
        if (choice === 'Go to Error' && location) {
            await this.openTracebackLocation(location);
        }

        if (error && typeof error === 'object') {
            error.kigumiErrorNotified = true;
        }
    }

    async dispose() {
        if (this.isDisposed) {
            return;
        }
        this.isDisposed = true;

        this.log(`Disposing session for ${this.filePath} (slot=${this.slotName})`);

        if (this.fileWatcher) {
            this.fileWatcher.dispose();
            this.fileWatcher = null;
        }

        if (this.runnerSession) {
            if (this.ownsRunner) {
                await this.runnerSession.dispose();
            } else {
                // Unload our slot from the shared runner, but don't kill the process
                try {
                    if (this.runnerSession.isAlive() && this.slotName !== 'main') {
                        await this.runnerSession.request('unload_slot', { slot: this.slotName });
                    }
                } catch (error) {
                    this.log(`[slot] Failed to unload slot '${this.slotName}': ${error.message || error}`);
                }
            }
            this.runnerSession = null;
        }

        if (this.panel) {
            const panel = this.panel;
            this.panel = null;
            panel.dispose();
        }

        if (this.onDispose) {
            this.onDispose(this.filePath, this.slotName);
        }
    }

    log(message) {
        const formatted = `[${path.basename(this.filePath)}] ${message}`;
        const match = /\[(debug|info|warn|error)\]/i.exec(String(message));
        const level = normalizeViewerLogLevel(match ? match[1] : 'info');
        const entry = {
            timestamp: new Date().toISOString(),
            level,
            message: formatted,
            filePath: this.filePath,
            slotName: this.slotName,
            sessionType: this.sessionType,
        };
        try {
            const logPath = this.getSessionLogPath();
            fs.mkdirSync(path.dirname(logPath), { recursive: true });
            fs.appendFile(logPath, `${JSON.stringify(entry)}\n`, 'utf8', () => {});
        } catch (_error) {
            // Logging must not break the viewer session.
        }
        this.channel.appendLine(formatted);
        if (this.panel) {
            this.panel.webview.postMessage({ type: 'logEntry', text: formatted }).catch(() => {});
        }
    }

    _setupRunnerMilestoneHandler() {
        if (!this.runnerSession) {
            return;
        }
        this.runnerSession.onMilestone = (milestone) => {
            const name = typeof milestone.name === 'string' ? milestone.name : 'milestone';
            this.profiler.addMilestone(name);
            this.postLoadingStatus(name);
        };
    }
}

module.exports = { FrameViewSession };
