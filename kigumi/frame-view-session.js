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
        this.profiler = new RefreshProfiler({ log: (msg) => this.log(msg) });
        this.slotName = options.slotName || 'main';
        this.sessionType = options.sessionType || 'main';
        this.patternName = options.patternName || null;
        // Cached payloads for potential panel re-open flows
        this._lastFrameData = null;
        this._lastGeometryData = null;
        this._lastProfiling = null;
    }

    getRefreshStatsPath() {
        const projectRoot = this.runnerSession && this.runnerSession.projectRoot
            ? this.runnerSession.projectRoot
            : path.dirname(this.filePath);
        return path.join(projectRoot, '.kigumi', 'refresh-stats.json');
    }

    postLoadingStatus(stage, details = {}) {
        if (!this.panel) {
            return;
        }
        this.panel.webview.postMessage({
            type: 'viewerState',
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
        this._setupRunnerMilestoneHandler();

        this.profiler.markTiming(initTiming, 'initialize.createPanel.start');
        const isLocalDev = this.runnerSession.isLocalDev;
        this.panel = createFrameViewer(this.filePath, this.patternName, isLocalDev);
        this.profiler.markTiming(initTiming, 'initialize.createPanel.end');

        this.profiler.markTiming(initTiming, 'initialize.webviewHtml.start');
        initializeFrameViewer(this.panel, this.filePath, {
            loadingText: 'initial creation',
            viewerOptions: this.refreshOptions,
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
        await this.runnerSession.start();
        this.profiler.markTiming(initTiming, 'initialize.runner.end');

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
        this.fileWatcher.start();
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
                this.onFileChanged('manual refresh button');
                return;
            }
            if (message.type === 'loadPattern') {
                this._handleLoadPatternFromWebview(message).catch((err) => {
                    this.log(`[patterns] loadPattern error: ${err.message || err}`);
                });
                return;
            }
            if (message.type === 'loadBook') {
                this._handleLoadBookFromWebview(message).catch((err) => {
                    this.log(`[patterns] loadBook error: ${err.message || err}`);
                });
                return;
            }
            if (message.type === 'requestLoadPatterns') {
                const rescan = !!message.rescan;
                this.log(`[webview] Load patterns requested from viewer (rescan=${rescan})`);
                this._sendPatternsToWebview(rescan).catch((err) => {
                    this.log(`[patterns] requestLoadPatterns error: ${err.message || err}`);
                });
                return;
            }
            if (message.type === 'openOutputChannel') {
                this.channel.show(true);
                return;
            }
            if (message.type === 'findCSGAtPoint') {
                this._handleFindCSGAtPoint(message).catch((err) => {
                    this.log(`[csg-nav] findCSGAtPoint error: ${err.message || err}`);
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

    /**
     * Ask runner for available patterns and send them to the webview.
     * @param {boolean} [rescan=false] - Force re-import of all pattern modules
     */
    async _sendPatternsToWebview(rescan = false) {
        if (!this.panel || !this.runnerSession || !this.runnerSession.isAlive()) {
            return;
        }
        try {
            const payload = rescan ? { rescan: true } : {};
            const result = await this.runnerSession.request('list_available_patterns', payload);
            if (!this.panel) {
                return;
            }
            this.panel.webview.postMessage({
                type: 'patternsAvailable',
                sources: (result && result.sources) || [],
            }).catch((err) => {
                this.log(`[patterns] Failed to post patterns: ${err.message || err}`);
            });
        } catch (err) {
            this.log(`[patterns] Error fetching patterns: ${err.message || err}`);
        }
    }

    /**
     * Handle a loadPattern message from the webview.
     */
    async _handleLoadPatternFromWebview(message) {
        const patternName = typeof message.patternName === 'string' ? message.patternName : '';
        const sourceFile = typeof message.sourceFile === 'string' ? message.sourceFile : '';
        if (!patternName || !sourceFile) {
            this.log('[patterns] loadPattern missing patternName or sourceFile');
            return;
        }

        this.log(`[patterns] Webview requested pattern: ${patternName} from ${sourceFile}`);

        // Delegate to the onLoadPattern callback (set by extension.js)
        if (typeof this.onLoadPattern === 'function') {
            await this.onLoadPattern(patternName, sourceFile);
        }

        // Notify the webview that loading is complete so it can remove the spinner
        if (this.panel) {
            this.panel.webview.postMessage({
                type: 'patternLoadResult',
                patternName,
                ok: true,
            }).catch(() => {});
        }
    }

    /**
     * Handle a loadBook message from the webview — opens whole book as one tab.
     */
    async _handleLoadBookFromWebview(message) {
        const sourceFile = typeof message.sourceFile === 'string' ? message.sourceFile : '';
        if (!sourceFile) {
            this.log('[patterns] loadBook missing sourceFile');
            return;
        }

        this.log(`[patterns] Webview requested book: ${sourceFile}`);

        if (typeof this.onLoadBook === 'function') {
            await this.onLoadBook(sourceFile);
        }

        if (this.panel) {
            this.panel.webview.postMessage({
                type: 'patternLoadResult',
                sourceFile,
                ok: true,
            }).catch(() => {});
        }
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
        this.panel = createFrameViewer(this.filePath, this.patternName, isLocalDev);
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
            }, this.refreshOptions);
            this.log(`[reopen] Re-rendered from cached data for slot '${this.slotName}'`);
        } else {
            initializeFrameViewer(this.panel, this.filePath, {
                loadingText: 'reopening',
                viewerOptions: this.refreshOptions,
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
            const reloadResult = await this.runnerSession.slotRequest('reload_example', this.slotName, { filePath: this.filePath });
            this.profiler.markTiming(timing, 'runner.reload_example.end');

            this.profiler.markTiming(timing, 'runner.get_frame.start');
            const frameData = await this.runnerSession.slotRequest('get_frame', this.slotName);
            this.profiler.markTiming(timing, 'runner.get_frame.end');

            this.profiler.markTiming(timing, 'runner.get_geometry.start');
            const geometryData = await this.runnerSession.slotRequest('get_geometry', this.slotName, this.refreshOptions);
            this.profiler.markTiming(timing, 'runner.get_geometry.end');

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
            }, this.refreshOptions);
            // Cache payloads for panel re-open (pattern sessions)
            this._lastFrameData = frameData;
            this._lastGeometryData = geometryData;
            this._lastProfiling = profiling;
            this.profiler.markTiming(timing, 'webview.renderFrameViewer.end');
            this.profiler.markTiming(timing, 'refresh.end', { refresh_total_ms: Math.round(refresh_total_s * 1000) });
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
