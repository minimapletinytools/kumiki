const path = require('path');
const vscode = require('vscode');
const { scanWorkspaceForFrames } = require('./frame-scanner');
const { discoverDependencyContent } = require('./discovery-adapter');
const { getInitializationStatus, isInitializationInProgress } = require('./project-initializer');
const { groupPatternsByPatternbook } = require('./pattern-source-utils');
const { createTranslator } = require('./i18n');

// Resolved once from VS Code's own display language (no user override yet —
// changing VS Code's display language requires a restart anyway, same as
// vscode.l10n).
const t = createTranslator(vscode.env && vscode.env.language);

class SidebarNode {
    constructor({ key, type, label, collapsibleState = vscode.TreeItemCollapsibleState.None, command, description, tooltip, iconPath, data, contextValue }) {
        this.key = key;
        this.type = type;
        this.label = label;
        this.collapsibleState = collapsibleState;
        this.command = command;
        this.description = description;
        this.tooltip = tooltip;
        this.iconPath = iconPath;
        this.data = data || {};
        this.contextValue = contextValue;
    }
}

class KigumiSidebarProvider {
    constructor(context, options = {}) {
        this.context = context;
        this.options = options;
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;

        this._didLoadOnce = false;
        this._scanPromise = null;
        this._groupByPatternbook = true;
        this._selectedElementData = null;
        this._state = {
            workspaceRoot: null,
            initStatus: null,
            kumikiInstalledVersion: 'unknown',
            kumikiLatestVersion: 'unknown',
            // Frames: files with example= or build_frame (not patternbooks)
            frames: [],
            // Workspace patternbooks discovered via scanner
            workspacePatternbooks: [],
            // Shipped / dependency patterns (unchanged pipeline)
            shippedPatterns: [],
            dependencyPatterns: [],
            shippedExamples: [],
            dependencyExamples: [],
            scanErrors: [],
            discoveryErrors: [],
            isScanning: false,
        };
    }

    dispose() {
        this._onDidChangeTreeData.dispose();
    }

    toggleGroupByPatternbook() {
        this._groupByPatternbook = !this._groupByPatternbook;
        this._onDidChangeTreeData.fire();
    }

    getGroupByPatternbook() {
        return this._groupByPatternbook;
    }

    getTreeItem(element) {
        const item = new vscode.TreeItem(element.label, element.collapsibleState);
        item.id = element.key;
        item.contextValue = element.contextValue || element.type;
        item.command = element.command;
        item.description = element.description;
        item.tooltip = element.tooltip || element.label;
        if (element.iconPath) {
            item.iconPath = element.iconPath;
        }
        return item;
    }

    setSelectedElementData(element) {
        this._selectedElementData = element;
    }

    getSelectedElementData() {
        return this._selectedElementData;
    }

    async getChildren(element) {
        this.ensureLoaded();

        if (!element) {
            return this.getRootNodes();
        }

        if (element.type === 'projectHeaderRoot') {
            return this.getProjectHeaderActionNodes();
        }

        if (element.type === 'framesRoot') {
            return this.getWorkspaceFrameNodes();
        }

        if (element.type === 'exampleFramesRoot') {
            return this.getLibraryFrameNodes();
        }

        if (element.type === 'libraryFrameGroup') {
            return this.getLibraryFrameGroupChildren(element.data.items);
        }

        if (element.type === 'patternsRoot') {
            return this.getPatternSectionNodes();
        }

        if (element.type === 'patternSection') {
            return this.getPatternNodesForSection(element.data.sectionKey);
        }

        if (element.type === 'workspacePatternbook') {
            return this.getWorkspacePatternbookPatternNodes(element.data.patternbook);
        }

        if (element.type === 'workspacePatternFolder') {
            return this.getWorkspacePatternFolderChildren(element.data.pathPrefix);
        }

        if (element.type === 'patternbookGroup') {
            return this.getShippedPatternNodesForPatternbook(element.data.sectionKey, element.data.patternbookName);
        }

        if (element.type === 'errorsRoot') {
            return this.getErrorNodes();
        }

        return [];
    }

    ensureLoaded() {
        if (this._didLoadOnce) {
            return;
        }
        this._didLoadOnce = true;
        void this.refresh(false);
    }

    async refresh(forceRescan = true) {
        if (this._scanPromise && !forceRescan) {
            return this._scanPromise;
        }

        this._scanPromise = this._runFullScan(forceRescan)
            .finally(() => {
                this._scanPromise = null;
            });

        return this._scanPromise;
    }

    // Kept for backward compat with extension.js command wiring
    async refreshPatterns(forceRescan = true) {
        return this.refresh(forceRescan);
    }

    async getTestSnapshot(options = {}) {
        const forceRefresh = options.forceRefresh !== false;
        if (forceRefresh) {
            await this.refresh(true);
        }

        const roots = await this.getChildren(null);
        const rootSnapshots = [];
        for (const root of roots) {
            const children = await this.getChildren(root);
            rootSnapshots.push({
                key: root.key,
                type: root.type,
                label: root.label,
                description: root.description || '',
                childCount: children.length,
                childLabels: children.slice(0, 20).map((child) => child.label),
            });
        }

        return {
            groupByPatternbook: this._groupByPatternbook,
            state: {
                workspaceRoot: this._state.workspaceRoot,
                frameCount: this._state.frames.length,
                workspacePatternbookCount: this._state.workspacePatternbooks.length,
                shippedPatternCount: this._state.shippedPatterns.length,
                dependencyPatternCount: this._state.dependencyPatterns.length,
                isScanning: this._state.isScanning,
                scanErrorCount: this._state.scanErrors.length,
                discoveryErrorCount: this._state.discoveryErrors.length,
            },
            roots: rootSnapshots,
        };
    }

    async _runFullScan(_forceRescan) {
        const workspaceFolder = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
        if (!workspaceFolder) {
            this._state = {
                workspaceRoot: null,
                initStatus: null,
                kumikiInstalledVersion: 'unknown',
                kumikiLatestVersion: 'unknown',
                frames: [],
                workspacePatternbooks: [],
                shippedPatterns: [],
                dependencyPatterns: [],
                shippedExamples: [],
                dependencyExamples: [],
                scanErrors: [],
                discoveryErrors: ['Open a workspace folder to use Kigumi Explorer.'],
                isScanning: false,
            };
            this._onDidChangeTreeData.fire();
            return;
        }

        const workspaceRoot = workspaceFolder.uri.fsPath;
        const initStatus = getInitializationStatus(workspaceRoot);
        const isLocalDev = initStatus.projectStatus === 'local-dev';
        const canRunScans = !!(isLocalDev || initStatus.isInitialized);

        if (!canRunScans) {
            this._state = {
                ...this._state,
                workspaceRoot,
                initStatus,
                kumikiInstalledVersion: 'unknown',
                kumikiLatestVersion: 'unknown',
                frames: [],
                workspacePatternbooks: [],
                shippedPatterns: [],
                dependencyPatterns: [],
                shippedExamples: [],
                dependencyExamples: [],
                scanErrors: [],
                discoveryErrors: [],
                isScanning: false,
            };
            this._onDidChangeTreeData.fire();
            return;
        }

        const versionInfoPromise = this.options.getKumikiVersionInfo
            ? this.options.getKumikiVersionInfo(workspaceRoot)
            : Promise.resolve({ installedVersion: 'unknown', latestVersion: 'unknown' });
        const timeoutSeconds = vscode.workspace.getConfiguration('kigumi').get('explorer.scanTimeoutSeconds', 15);
        const timeoutMs = Math.max(1000, Number(timeoutSeconds) * 1000);

        // Show scanning state immediately
        this._state = {
            ...this._state,
            workspaceRoot,
            initStatus,
            isScanning: true,
        };
        this._onDidChangeTreeData.fire();

        // Workspace scan and shipped scan run concurrently
        const [workspaceResult, shippedResult] = await Promise.allSettled([
            this._scanWorkspace(workspaceRoot, timeoutMs),
            isLocalDev ? Promise.resolve(null) : this._scanShipped(workspaceRoot, timeoutMs),
        ]);

        const scanErrors = [];
        let frames = [];
        let workspacePatternbooks = [];
        if (workspaceResult.status === 'fulfilled') {
            frames = workspaceResult.value.frames;
            workspacePatternbooks = workspaceResult.value.patternbooks;
            scanErrors.push(...workspaceResult.value.scanErrors);
        } else {
            scanErrors.push({ filePath: workspaceRoot, reason: `Workspace scan failed: ${workspaceResult.reason?.message || workspaceResult.reason}` });
        }

        const discoveryErrors = [];
        let shippedPatterns = [];
        let dependencyPatterns = [];
        let shippedExamples = [];
        let dependencyExamples = [];

        if (shippedResult && shippedResult.status === 'fulfilled' && shippedResult.value) {
            shippedPatterns = shippedResult.value.shippedPatterns;
            dependencyPatterns = shippedResult.value.dependencyPatterns;
            shippedExamples = shippedResult.value.shippedExamples;
            dependencyExamples = shippedResult.value.dependencyExamples;
        } else if (shippedResult && shippedResult.status === 'rejected') {
            discoveryErrors.push(`Dependency discovery failed: ${shippedResult.reason?.message || shippedResult.reason}`);
        }

        let kumikiInstalledVersion = 'unknown';
        let kumikiLatestVersion = 'unknown';
        try {
            const payload = await versionInfoPromise;
            kumikiInstalledVersion = (payload && payload.installedVersion) || 'unknown';
            kumikiLatestVersion = (payload && payload.latestVersion) || 'unknown';
        } catch (_error) {
            kumikiInstalledVersion = 'unknown';
            kumikiLatestVersion = 'unknown';
        }

        this._state = {
            workspaceRoot,
            initStatus,
            kumikiInstalledVersion,
            kumikiLatestVersion,
            frames,
            workspacePatternbooks,
            shippedPatterns,
            dependencyPatterns,
            shippedExamples,
            dependencyExamples,
            scanErrors,
            discoveryErrors,
            isScanning: false,
        };
        this._logScanIssues();
        this._onDidChangeTreeData.fire();
    }

    _logScanIssues() {
        const logLine = this.options.logLine;
        if (typeof logLine !== 'function') {
            return;
        }

        const discoveryErrors = this._state.discoveryErrors || [];
        const scanErrors = this._state.scanErrors || [];
        if (discoveryErrors.length === 0 && scanErrors.length === 0) {
            return;
        }

        logLine('[explorer] Scan issues detected:');
        for (const message of discoveryErrors) {
            logLine(`[explorer] discovery error: ${message}`);
        }
        for (const err of scanErrors) {
            const filePath = err && err.filePath ? err.filePath : '<unknown>';
            const reason = err && err.reason ? err.reason : String(err);
            logLine(`[explorer] scan error: ${reason}`);
            logLine(`[explorer] scan error file: ${filePath}`);
        }
    }

    async _scanWorkspace(workspaceRoot, timeoutMs) {
        const showPoop = vscode.workspace.getConfiguration('kigumi').get('viewer.showPoopTaggedJoints', false);
        const result = await scanWorkspaceForFrames(workspaceRoot, {
            timeoutMs,
            pythonCommand: this.options.getPythonCommand?.(),
            logLine: this.options.logLine,
            showPoopTaggedJoints: showPoop,
        });

        return {
            frames: result.frameFiles || [],
            patternbooks: result.patternbookFiles || [],
            scanErrors: result.scanErrors || [],
        };
    }

    async _scanShipped(workspaceRoot, timeoutMs) {
        const dep = await discoverDependencyContent(workspaceRoot, {
            timeoutMs,
            pythonCommand: this.options.getPythonCommand?.(),
        });

        const toItem = (filePath) => ({
            sourceFile: filePath,
            name: path.basename(filePath, '.py'),
            groups: [],
        });

        const expandPatternbookRecords = (records, fallbackPaths) => {
            const normalizedRecords = Array.isArray(records)
                ? records
                : (fallbackPaths || []).map((filePath) => ({
                    sourceFile: filePath,
                    patternbookName: path.basename(filePath, '.py'),
                    patternNames: [path.basename(filePath, '.py')],
                    groupNames: [],
                }));

            const items = [];
            for (const rec of normalizedRecords) {
                const sourceFile = rec && rec.sourceFile;
                if (!sourceFile) {
                    continue;
                }
                const patternbookName = rec.patternbookName || path.basename(sourceFile, '.py');
                const names = Array.isArray(rec.patternNames) && rec.patternNames.length > 0
                    ? rec.patternNames
                    : [patternbookName];
                const uniqueNames = Array.from(new Set(names)).sort((a, b) => a.localeCompare(b));
                for (const name of uniqueNames) {
                    items.push({
                        sourceFile,
                        name,
                        patternbookName,
                        groups: Array.isArray(rec.groupNames) ? rec.groupNames : [],
                        patternNames: uniqueNames,
                    });
                }
            }

            items.sort((a, b) => {
                const left = `${a.patternbookName}:${a.name}`;
                const right = `${b.patternbookName}:${b.name}`;
                return left.localeCompare(right);
            });
            return items;
        };

        return {
            shippedPatterns: expandPatternbookRecords(dep.kumikiPatternbooks, dep.kumikiPatterns),
            shippedExamples: (dep.kumikiExamples || []).map(toItem),
            dependencyPatterns: expandPatternbookRecords(dep.dependencyPatternbooks, dep.dependencyPatterns),
            dependencyExamples: (dep.dependencyExamples || []).map(toItem),
        };
    }

    // ---------------------------------------------------------------------------
    // Tree building
    // ---------------------------------------------------------------------------

    getRootNodes() {
        const nodes = [];

        const initStatus = this._state.initStatus;
        const isLocalDev = !!(initStatus && initStatus.projectStatus === 'local-dev');
        const isInitializing = isInitializationInProgress();
        const hasProject = !!(initStatus && (initStatus.hasExistingProject || initStatus.isInitialized));
        if (isLocalDev) {
            nodes.push(new SidebarNode({
                key: 'project-status-local-dev',
                type: 'projectStatusAction',
                label: t('sidebar.kumikiDevMode'),
                description: t('sidebar.kumikiDevMode.desc'),
                iconPath: new vscode.ThemeIcon('beaker'),
                contextValue: 'projectStatusAction',
                command: {
                    title: 'Project status',
                    command: 'kigumi.initializeProjectInWorkspace',
                },
            }));
        } else if (isInitializing) {
            nodes.push(new SidebarNode({
                key: 'project-status-initializing',
                type: 'projectStatusAction',
                label: t('sidebar.initializingProject'),
                description: t('sidebar.initializingProject.desc'),
                iconPath: new vscode.ThemeIcon('loading~spin'),
                contextValue: 'projectStatusAction',
            }));
        } else if (!hasProject) {
            nodes.push(new SidebarNode({
                key: 'project-status-initialize',
                type: 'projectStatusAction',
                label: t('sidebar.initializeProjectAction'),
                description: t('sidebar.initializeProjectAction.desc'),
                collapsibleState: vscode.TreeItemCollapsibleState.None,
                command: {
                    title: 'Initialize project',
                    command: 'kigumi.initializeProjectInWorkspace',
                },
                iconPath: new vscode.ThemeIcon('rocket'),
                contextValue: 'projectStatusAction',
            }));
        } else {
            const projectLabel = initStatus && initStatus.projectRoot
                ? path.basename(initStatus.projectRoot)
                : t('sidebar.currentWorkspace');
            nodes.push(new SidebarNode({
                key: 'project-status-initialized',
                type: 'projectStatusAction',
                label: t('sidebar.projectInitialized'),
                description: projectLabel,
                iconPath: new vscode.ThemeIcon('pass'),
                contextValue: 'projectStatusAction',
                command: {
                    title: 'Project status',
                    command: 'kigumi.initializeProjectInWorkspace',
                },
            }));
        }

        const canShowKumikiVersionActions = !!(initStatus && initStatus.isInitialized);
        if (canShowKumikiVersionActions) {
            const installed = this._state.kumikiInstalledVersion || 'unknown';
            const latest = this._state.kumikiLatestVersion || 'unknown';
            if (installed !== 'unknown' && latest !== 'unknown' && installed === latest) {
                nodes.push(new SidebarNode({
                    key: 'kumiki-version-up-to-date',
                    type: 'kumikiVersionAction',
                    label: t('sidebar.kumikiUpToDate', { version: installed }),
                    description: t('sidebar.kumikiUpToDate.desc'),
                    iconPath: new vscode.ThemeIcon('verified-filled'),
                    contextValue: 'kumikiVersionAction',
                }));
            } else {
                nodes.push(new SidebarNode({
                    key: 'kumiki-version-update',
                    type: 'kumikiVersionAction',
                    label: t('sidebar.updateKumikiAction', { installed, latest }),
                    description: t('sidebar.updateKumikiAction.desc'),
                    command: {
                        title: 'Update Kumiki',
                        command: 'kigumi.updateKumiki',
                    },
                    iconPath: new vscode.ThemeIcon('cloud-download'),
                    contextValue: 'kumikiVersionAction',
                }));
            }
        }

        nodes.push(new SidebarNode({
            key: 'kumiki-website-action',
            type: 'kumikiWebsiteAction',
            label: t('sidebar.goToWebsiteAction'),
            description: 'github.com/minimapletinytools/kumiki',
            command: {
                title: 'Open Kumiki Website',
                command: 'kigumi.openWebsite',
            },
            iconPath: new vscode.ThemeIcon('link-external'),
            contextValue: 'kumikiWebsiteAction',
        }));

        const wsFrameCount = this._state.frames.length;
        nodes.push(new SidebarNode({
            key: 'frames-root',
            type: 'framesRoot',
            label: this._state.isScanning ? t('sidebar.framesScanning') : t('sidebar.frames', { count: wsFrameCount }),
            collapsibleState: vscode.TreeItemCollapsibleState.Expanded,
            iconPath: new vscode.ThemeIcon(this._state.isScanning ? 'loading~spin' : 'home'),
        }));

        const libFrameCount = (this._state.shippedExamples || []).length + (this._state.dependencyExamples || []).length;
        if (libFrameCount > 0) {
            nodes.push(new SidebarNode({
                key: 'example-frames-root',
                type: 'exampleFramesRoot',
                label: t('sidebar.exampleFrames'),
                collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                iconPath: new vscode.ThemeIcon('symbol-folder'),
            }));
        }

        nodes.push(new SidebarNode({
            key: 'patterns-root',
            type: 'patternsRoot',
            label: this._state.isScanning ? t('sidebar.patternsScanning') : t('sidebar.patterns'),
            collapsibleState: vscode.TreeItemCollapsibleState.Expanded,
            iconPath: new vscode.ThemeIcon(this._state.isScanning ? 'loading~spin' : 'book'),
        }));

        const totalErrors = this._state.discoveryErrors.length + this._state.scanErrors.length;
        if (totalErrors > 0) {
            nodes.push(new SidebarNode({
                key: 'errors-root',
                type: 'errorsRoot',
                label: t('sidebar.scanIssues', { count: totalErrors }),
                collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                iconPath: new vscode.ThemeIcon('warning'),
            }));
        }

        return nodes;
    }

    getProjectHeaderActionNodes() {
        const workspaceRoot = this._state.workspaceRoot;
        const initStatus = this._state.initStatus;

        if (!workspaceRoot) {
            return [new SidebarNode({
                key: 'project-header-action:no-workspace',
                type: 'projectHeaderAction',
                label: t('sidebar.openWorkspaceFolderAction'),
                description: t('sidebar.openWorkspaceFolderAction.desc'),
                iconPath: new vscode.ThemeIcon('folder-opened'),
                contextValue: 'projectHeaderAction',
            })];
        }

        if (initStatus && initStatus.projectStatus === 'local-dev') {
            return [new SidebarNode({
                key: 'project-header-action:local-dev',
                type: 'projectHeaderAction',
                label: t('sidebar.localDevelopmentModeAction'),
                description: t('sidebar.localDevelopmentModeAction.desc'),
                iconPath: new vscode.ThemeIcon('beaker'),
                contextValue: 'projectHeaderAction',
                command: {
                    title: 'Show project status',
                    command: 'kigumi.initializeProjectInWorkspace',
                },
            })];
        }

        if (initStatus && initStatus.isInitialized) {
            return [new SidebarNode({
                key: 'project-header-action:initialized',
                type: 'projectHeaderAction',
                label: t('sidebar.projectInitializedAction'),
                description: t('sidebar.projectInitializedAction.desc'),
                iconPath: new vscode.ThemeIcon('pass'),
                contextValue: 'projectHeaderAction',
                command: {
                    title: 'Show project status',
                    command: 'kigumi.initializeProjectInWorkspace',
                },
            })];
        }

        if (initStatus && initStatus.hasExistingProject) {
            return [new SidebarNode({
                key: 'project-header-action:existing',
                type: 'projectHeaderAction',
                label: t('sidebar.finishProjectSetupAction'),
                description: t('sidebar.finishProjectSetupAction.desc'),
                iconPath: new vscode.ThemeIcon('warning'),
                contextValue: 'projectHeaderAction',
                command: {
                    title: 'Initialize project',
                    command: 'kigumi.initializeProjectInWorkspace',
                },
            })];
        }

        return [new SidebarNode({
            key: 'project-header-action:init',
            type: 'projectHeaderAction',
            label: t('sidebar.initializeCurrentProjectAction'),
            description: t('sidebar.initializeCurrentProjectAction.desc'),
            iconPath: new vscode.ThemeIcon('tools'),
            contextValue: 'projectHeaderAction',
            command: {
                title: 'Initialize project',
                command: 'kigumi.initializeProjectInWorkspace',
            },
        })];
    }

    getWorkspaceFrameNodes() {
        const nodes = [];
        if (this._state.isScanning) {
            nodes.push(new SidebarNode({
                key: 'frames-scanning',
                type: 'loading',
                label: t('sidebar.scanningWorkspace'),
                iconPath: new vscode.ThemeIcon('loading~spin'),
            }));
        }

        const wsFrames = this._state.frames || [];

        if (wsFrames.length === 0) {
            nodes.push(new SidebarNode({
                key: 'frames-empty',
                type: 'placeholder',
                label: t('sidebar.noFrameDefinitionsFound'),
                description: this._state.workspaceRoot ? '' : t('sidebar.openAWorkspace'),
                iconPath: new vscode.ThemeIcon('circle-slash'),
            }));
            return nodes;
        }

        nodes.push(...wsFrames.map((frameFile) => new SidebarNode({
            key: `frame-file:workspace:${frameFile.filePath}`,
            type: 'frameFile',
            label: frameFile.relativePath,
            collapsibleState: vscode.TreeItemCollapsibleState.None,
            command: {
                title: 'Open frame file',
                command: 'kigumi.openFrameFromSidebar',
                arguments: [frameFile.filePath],
            },
            iconPath: new vscode.ThemeIcon('fish2-very-sad'),
            data: frameFile,
        })));

        return nodes;
    }

    getLibraryFrameNodes() {
        const nodes = [];
        const shippedFrames = this._state.shippedExamples || [];
        const depFrames = this._state.dependencyExamples || [];

        // Kumiki frames
        if (shippedFrames.length > 0) {
            nodes.push(new SidebarNode({
                key: 'library-frames:kumiki',
                type: 'libraryFrameGroup',
                label: t('sidebar.kumiki'),
                collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                iconPath: new vscode.ThemeIcon('package'),
                data: { items: shippedFrames },
            }));
        }

        // Group dependency frames by library name
        const depsByLib = {};
        for (const item of depFrames) {
            const libName = item.name || path.basename(item.sourceFile, '.py');
            if (!depsByLib[libName]) {
                depsByLib[libName] = [];
            }
            depsByLib[libName].push(item);
        }

        for (const libName of Object.keys(depsByLib).sort()) {
            nodes.push(new SidebarNode({
                key: `library-frames:dep:${libName}`,
                type: 'libraryFrameGroup',
                label: libName,
                collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                iconPath: new vscode.ThemeIcon('extensions'),
                data: { items: depsByLib[libName] },
            }));
        }

        return nodes;
    }

    getLibraryFrameGroupChildren(items) {
        return (items || []).map((item) => new SidebarNode({
            key: `frame-file:library:${item.sourceFile}`,
            type: 'frameFile',
            label: item.name,
            collapsibleState: vscode.TreeItemCollapsibleState.None,
            command: {
                title: 'Open frame file',
                command: 'kigumi.openFrameFromSidebar',
                arguments: [item.sourceFile],
            },
            iconPath: new vscode.ThemeIcon('fish2-very-sad'),
            data: item,
        }));
    }

    getPatternSectionNodes() {
        const nodes = [];

        if (this._state.isScanning) {
            nodes.push(new SidebarNode({
                key: 'patterns-scanning',
                type: 'loading',
                label: t('sidebar.scanning'),
                description: t('sidebar.scanningDesc'),
                iconPath: new vscode.ThemeIcon('loading~spin'),
            }));
        }

        // Workspace patterns section
        const pbCount = this._state.workspacePatternbooks.length;
        nodes.push(new SidebarNode({
            key: 'pattern-section:workspace-patternbooks',
            type: 'patternSection',
            label: t('sidebar.workspace', { count: pbCount }),
            collapsibleState: vscode.TreeItemCollapsibleState.Expanded,
            iconPath: new vscode.ThemeIcon('folder-opened'),
            data: { sectionKey: 'workspace-patternbooks' },
        }));

        // Shipped kumiki patterns
        const shippedCount = this._state.shippedPatterns.length;
        if (shippedCount > 0 || this._state.shippedExamples.length > 0) {
            nodes.push(new SidebarNode({
                key: 'pattern-section:shipped-patterns',
                type: 'patternSection',
                label: t('sidebar.kumikiCount', { count: shippedCount }),
                collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                iconPath: new vscode.ThemeIcon('package'),
                data: { sectionKey: 'shipped-patterns' },
            }));
        }

        // Dependency patterns
        const depCount = this._state.dependencyPatterns.length;
        if (depCount > 0 || this._state.dependencyExamples.length > 0) {
            nodes.push(new SidebarNode({
                key: 'pattern-section:dependency-patterns',
                type: 'patternSection',
                label: t('sidebar.dependencies', { count: depCount }),
                collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                iconPath: new vscode.ThemeIcon('extensions'),
                data: { sectionKey: 'dependency-patterns' },
            }));
        }

        return nodes;
    }

    getPatternNodesForSection(sectionKey) {
        if (sectionKey === 'workspace-patternbooks') {
            return this._groupByPatternbook
                ? this.getWorkspacePatternbookNodes()
                : this.getFlatWorkspacePatternNodes();
        }
        if (sectionKey === 'shipped-patterns') {
            return this.getShippedPatternSectionNodes('shipped-patterns', this._state.shippedPatterns, this._groupByPatternbook);
        }
        if (sectionKey === 'dependency-patterns') {
            return this.getShippedPatternSectionNodes('dependency-patterns', this._state.dependencyPatterns, this._groupByPatternbook);
        }
        return [];
    }

    _getPatternDisplayLabel(p) {
        const segments = (p.path || '').split('/');
        return segments[segments.length - 1] || p.path || '';
    }

    getWorkspacePatternbookNodes() {
        if (this._groupByPatternbook) {
            const allPatterns = this._getAllWorkspacePatterns();
            const nodes = this._buildPatternTreeNodes(allPatterns, null);
            if (nodes.length === 0) {
                return [new SidebarNode({
                    key: 'workspace-patternbooks-empty',
                    type: 'placeholder',
                    label: t('sidebar.noPatternsFound'),
                    description: t('sidebar.noPatternsFoundHint'),
                    iconPath: new vscode.ThemeIcon('circle-slash'),
                })];
            }
            return nodes;
        } else {
            return this.getFlatWorkspacePatternNodes();
        }
    }

    _getAllWorkspacePatterns() {
        const all = [];
        for (const pb of (this._state.workspacePatternbooks || [])) {
            for (const p of (Array.isArray(pb.patterns) ? pb.patterns : [])) {
                all.push({ path: p.path, tags: p.tags, pattern_type: p.pattern_type, sourceFile: pb.filePath });
            }
        }
        return all;
    }

    _buildPatternTreeNodes(allPatterns, parentPath) {
        const prefix = parentPath ? parentPath + '/' : '';
        const childSegments = new Set();
        for (const p of allPatterns) {
            if (!p.path.startsWith(prefix)) continue;
            const remainder = p.path.slice(prefix.length);
            if (!remainder) continue;
            const firstSeg = remainder.split('/')[0];
            if (firstSeg) childSegments.add(firstSeg);
        }

        const nodes = [];
        for (const seg of [...childSegments].sort()) {
            const childPath = prefix + seg;
            const patternAtPath = allPatterns.find(p => p.path === childPath);
            const hasChildren = allPatterns.some(p => p.path.startsWith(childPath + '/'));

            if (hasChildren) {
                const isMain = patternAtPath && Array.isArray(patternAtPath.tags) && patternAtPath.tags.includes('main');
                const sourceFile = patternAtPath ? patternAtPath.sourceFile : null;
                nodes.push(new SidebarNode({
                    key: `workspace-pattern-folder:${childPath}`,
                    type: 'workspacePatternFolder',
                    label: seg,
                    description: isMain ? t('sidebar.mainBadge') : undefined,
                    collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                    command: isMain ? {
                        title: 'Open pattern',
                        command: 'kigumi.openPatternFromSidebar',
                        arguments: [{ sourceFile, patternName: childPath }],
                    } : undefined,
                    // A folder that's also directly openable as a pattern (isMain)
                    // gets folder-library instead of a plain folder, so it reads
                    // as "this is a folder AND a pattern" at a glance.
                    iconPath: new vscode.ThemeIcon(isMain ? 'folder-library' : 'folder'),
                    tooltip: childPath,
                    data: { pathPrefix: childPath, sourceFile },
                    contextValue: isMain ? 'patternFolderWithMain' : 'patternFolder',
                }));
            } else if (patternAtPath) {
                nodes.push(new SidebarNode({
                    key: `workspace-pattern:${patternAtPath.sourceFile}:${childPath}`,
                    type: 'patternItem',
                    label: seg,
                    tooltip: `${childPath} — ${patternAtPath.sourceFile}`,
                    command: {
                        title: 'Open pattern',
                        command: 'kigumi.openPatternFromSidebar',
                        arguments: [{ sourceFile: patternAtPath.sourceFile, patternName: childPath }],
                    },
                    iconPath: new vscode.ThemeIcon('library'),
                    data: { sourceFile: patternAtPath.sourceFile, patternName: childPath, sectionKey: 'workspace-patternbooks' },
                    contextValue: 'patternItemWorkspace',
                }));
            }
        }
        return nodes;
    }

    getWorkspacePatternFolderChildren(pathPrefix) {
        const allPatterns = this._getAllWorkspacePatterns();
        return this._buildPatternTreeNodes(allPatterns, pathPrefix);
    }

    getWorkspacePatternbookPatternNodes(pb) {
        const patterns = Array.isArray(pb.patterns) ? pb.patterns : [];

        if (patterns.length === 0) {
            return [new SidebarNode({
                key: `workspace-pb-empty:${pb && pb.filePath}`,
                type: 'placeholder',
                label: t('sidebar.noPatternsFound'),
                iconPath: new vscode.ThemeIcon('circle-slash'),
            })];
        }

        return patterns.map((p) => {
            const displayLabel = this._getPatternDisplayLabel(p);
            const patternName = p.path;
            return new SidebarNode({
                key: `workspace-pattern:${pb.filePath}:${patternName}`,
                type: 'patternItem',
                label: displayLabel,
                tooltip: `${patternName} — ${pb.filePath}`,
                command: {
                    title: 'Open pattern',
                    command: 'kigumi.openPatternFromSidebar',
                    arguments: [{ sourceFile: pb.filePath, patternName }],
                },
                iconPath: new vscode.ThemeIcon('library'),
                data: { sourceFile: pb.filePath, patternName, sectionKey: 'workspace-patternbooks' },
                contextValue: 'patternItemWorkspace',
            });
        });
    }

    getFlatWorkspacePatternNodes()
 {
        const patternbooks = this._state.workspacePatternbooks || [];
        const nodes = [];

        for (const pb of patternbooks) {
            for (const p of (Array.isArray(pb.patterns) ? pb.patterns : [])) {
                const displayLabel = this._getPatternDisplayLabel(p);
                const patternName = p.path;
                nodes.push(new SidebarNode({
                    key: `workspace-pattern-flat:${pb.filePath}:${patternName}`,
                    type: 'patternItem',
                    label: displayLabel,
                    description: pb.patternbookName,
                    tooltip: `${patternName} — ${pb.filePath}`,
                    command: {
                        title: 'Open pattern',
                        command: 'kigumi.openPatternFromSidebar',
                        arguments: [{ sourceFile: pb.filePath, patternName }],
                    },
                    iconPath: new vscode.ThemeIcon('library'),
                    data: { sourceFile: pb.filePath, patternName, sectionKey: 'workspace-patternbooks' },
                    contextValue: 'patternItemWorkspace',
                }));
            }
        }

        if (nodes.length === 0) {
            return [new SidebarNode({
                key: 'workspace-patterns-empty',
                type: 'placeholder',
                label: t('sidebar.noPatternsFound'),
                iconPath: new vscode.ThemeIcon('circle-slash'),
            })];
        }

        nodes.sort((a, b) => `${a.label}:${a.description}`.localeCompare(`${b.label}:${b.description}`));
        return nodes;
    }

    getShippedPatternSectionNodes(sectionKey, patternItems, grouped = true) {
        if (!patternItems || patternItems.length === 0) {
            return [new SidebarNode({
                key: `patterns-empty:${sectionKey}`,
                type: 'placeholder',
                label: t('sidebar.noPatternsFound'),
                iconPath: new vscode.ThemeIcon('circle-slash'),
            })];
        }

        if (!grouped) {
            return patternItems
                .map((item) => {
                    const itemName = item.name || path.basename(item.sourceFile, '.py');
                    const patternbookName = path.basename(item.sourceFile, '.py');
                    return new SidebarNode({
                        key: `pattern-item-flat:${sectionKey}:${item.sourceFile}:${itemName}`,
                        type: 'patternItem',
                        label: itemName,
                        description: patternbookName,
                        tooltip: item.sourceFile,
                        command: {
                            title: 'Open pattern',
                            command: 'kigumi.openPatternFromSidebar',
                            arguments: [{ sourceFile: item.sourceFile, patternName: item.name || null }],
                        },
                        iconPath: new vscode.ThemeIcon('library'),
                        data: { sourceFile: item.sourceFile, patternName: item.name, sectionKey },
                        contextValue: 'patternItem',
                    });
                })
                .sort((a, b) => `${a.label}:${a.description}`.localeCompare(`${b.label}:${b.description}`));
        }

        const groupedMap = groupPatternsByPatternbook(patternItems);
        const nodes = [];

        for (const [patternbookName, items] of groupedMap.entries()) {
            nodes.push(new SidebarNode({
                key: `patternbook-group:${sectionKey}:${patternbookName}`,
                type: 'patternbookGroup',
                label: patternbookName,
                description: items.length === 1
                    ? t('sidebar.patternCount.singular', { count: items.length })
                    : t('sidebar.patternCount.plural', { count: items.length }),
                collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                command: {
                    title: 'Open patternbook',
                    command: 'kigumi.openPatternbookGroup',
                    arguments: [{ sectionKey, patternbookName, patterns: items }],
                },
                iconPath: new vscode.ThemeIcon('folder'),
                data: { sectionKey, patternbookName, patterns: items },
                contextValue: 'patternbookGroupItem',
            }));
        }

        return nodes;
    }

    getShippedPatternNodesForPatternbook(sectionKey, patternbookName) {
        const patternItems = sectionKey === 'shipped-patterns'
            ? this._state.shippedPatterns
            : this._state.dependencyPatterns;

        const filteredItems = patternItems.filter((item) => {
            const pbName = item.patternbookName || path.basename(item.sourceFile, '.py');
            return pbName === patternbookName;
        });

        if (filteredItems.length === 0) {
            return [new SidebarNode({
                key: `patternbook-empty:${sectionKey}:${patternbookName}`,
                type: 'placeholder',
                label: t('sidebar.noPatternsFound'),
                iconPath: new vscode.ThemeIcon('circle-slash'),
            })];
        }

        return filteredItems.map((item) => {
            const itemName = item.name || path.basename(item.sourceFile, '.py');
            return new SidebarNode({
                key: `pattern-item:${sectionKey}:${item.sourceFile}:${itemName}`,
                type: 'patternItem',
                label: itemName,
                tooltip: item.sourceFile,
                command: {
                    title: 'Open pattern',
                    command: 'kigumi.openPatternFromSidebar',
                    arguments: [{ sourceFile: item.sourceFile, patternName: item.name || null }],
                },
                iconPath: new vscode.ThemeIcon('library'),
                data: { sourceFile: item.sourceFile, patternName: item.name, sectionKey },
                contextValue: 'patternItem',
            });
        });
    }

    getErrorNodes() {
        const rows = [];
        for (const message of this._state.discoveryErrors) {
            rows.push(new SidebarNode({
                key: `discovery-error:${message}`,
                type: 'error',
                label: message,
                iconPath: new vscode.ThemeIcon('error'),
            }));
        }

        for (const err of this._state.scanErrors) {
            rows.push(new SidebarNode({
                key: `scan-error:${err.filePath || ''}`,
                type: 'error',
                label: err.reason,
                description: path.basename(err.filePath || ''),
                tooltip: `${err.reason}\n${err.filePath}`,
                iconPath: new vscode.ThemeIcon('warning'),
            }));
        }

        return rows;
    }
}

module.exports = {
    KigumiSidebarProvider,
    SidebarNode,
};
