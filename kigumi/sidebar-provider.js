const path = require('path');
const fs = require('fs');
const vscode = require('vscode');
const { scanWorkspaceForFrames } = require('./frame-scanner');
const {
    discoverDependencyContent,
    discoverWorkspaceContent,
    normalizeRunnerPatterns,
} = require('./discovery-adapter');
const { getInitializationStatus } = require('./project-initializer');
const { isPatternbookFile, groupPatternsByPatternbook } = require('./pattern-source-utils');

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
        this._loadPromise = null;
        this._patternLoadPromise = null;
        this._groupByPatternbook = true; // Default to grouping by patternbook
        this._selectedElementData = null; // Track current selection for context menu commands
        this._state = {
            workspaceRoot: null,
            initStatus: null,
            frames: [],
            frameErrors: [],
            workspacePatterns: [],
            workspaceExamples: [],
            shippedPatterns: [],
            dependencyPatterns: [],
            shippedExamples: [],
            dependencyExamples: [],
            discoveryErrors: [],
            isRefreshingFrames: false,
            isRefreshingPatterns: false,
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

        if (element.type === 'framesRoot') {
            return this.getFrameFileNodes();
        }

        if (element.type === 'frameFile') {
            return this.getFrameEntryNodes(element.data.filePath, element.data.frameEntries || []);
        }

        if (element.type === 'patternsRoot') {
            return this.getPatternSectionNodes();
        }

        if (element.type === 'patternSection') {
            return this.getPatternNodesForSection(element.data.sectionKey);
        }

        if (element.type === 'patternbookGroup') {
            return this.getPatternNodesForPatternbook(element.data.sectionKey, element.data.patternbookName);
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
        if (this._loadPromise) {
            return this._loadPromise;
        }

        this._loadPromise = this.loadFrameState(forceRescan)
            .finally(() => {
                this._loadPromise = null;
            });

        if (!this._patternLoadPromise) {
            this._patternLoadPromise = this.loadPatternState(forceRescan)
                .finally(() => {
                    this._patternLoadPromise = null;
                });
        }

        return Promise.allSettled([this._loadPromise, this._patternLoadPromise]);
    }

    async refreshPatterns(forceRescan = true) {
        if (this._patternLoadPromise) {
            return this._patternLoadPromise;
        }

        this._patternLoadPromise = this.loadPatternState(forceRescan)
            .finally(() => {
                this._patternLoadPromise = null;
            });

        return this._patternLoadPromise;
    }

    async loadFrameState(_forceRescan) {
        const workspaceFolder = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
        if (!workspaceFolder) {
            this._state = {
                workspaceRoot: null,
                initStatus: null,
                frames: [],
                frameErrors: [],
                workspacePatterns: [],
                workspaceExamples: [],
                shippedPatterns: [],
                dependencyPatterns: [],
                shippedExamples: [],
                dependencyExamples: [],
                discoveryErrors: ['Open a workspace folder to use Kigumi Explorer.'],
                isRefreshingFrames: false,
                isRefreshingPatterns: false,
            };
            this._onDidChangeTreeData.fire();
            return;
        }

        const workspaceRoot = workspaceFolder.uri.fsPath;
        const timeoutSeconds = vscode.workspace.getConfiguration('kigumi').get('explorer.scanTimeoutSeconds', 5);
        const timeoutMs = Math.max(1000, Number(timeoutSeconds) * 1000);

        const discoveryErrors = [];
        let framesResult = { frameFiles: [], scanErrors: [] };
        this._state = {
            ...this._state,
            workspaceRoot,
            initStatus: getInitializationStatus(workspaceRoot),
            isRefreshingFrames: true,
        };
        this._onDidChangeTreeData.fire();

        try {
            framesResult = await scanWorkspaceForFrames(workspaceRoot, {
                timeoutMs,
                pythonCommand: this.options.getPythonCommand?.(),
            });
            
            // Filter out patternbook files from frames
            const filteredFrames = [];
            for (const frameFile of framesResult.frameFiles || []) {
                try {
                    const content = fs.readFileSync(frameFile.filePath, 'utf-8');
                    if (!isPatternbookFile(content)) {
                        filteredFrames.push(frameFile);
                    }
                } catch (_) {
                    // If we can't read the file, include it in frames
                    filteredFrames.push(frameFile);
                }
            }
            framesResult.frameFiles = filteredFrames;
        } catch (error) {
            discoveryErrors.push(`Frame scan failed: ${error.message || error}`);
        }

        this._state = {
            ...this._state,
            workspaceRoot,
            initStatus: getInitializationStatus(workspaceRoot),
            frames: framesResult.frameFiles || [],
            frameErrors: framesResult.scanErrors || [],
            discoveryErrors: this.mergeDiscoveryErrors(discoveryErrors, 'frames'),
            isRefreshingFrames: false,
        };
        this._onDidChangeTreeData.fire();
    }

    async loadPatternState(forceRescan) {
        const workspaceFolder = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
        if (!workspaceFolder) {
            return;
        }

        const workspaceRoot = workspaceFolder.uri.fsPath;
        const initStatus = getInitializationStatus(workspaceRoot);
        const isLocalDev = initStatus.projectStatus === 'local-dev';
        const timeoutSeconds = vscode.workspace.getConfiguration('kigumi').get('explorer.scanTimeoutSeconds', 5);
        const timeoutMs = Math.max(1000, Number(timeoutSeconds) * 1000);

        let workspaceContent = { workspacePatterns: [], workspaceExamples: [] };
        let dependencyContent = {
            kumikiPatterns: [],
            kumikiExamples: [],
            dependencyPatterns: [],
            dependencyExamples: [],
        };
        let runnerPatternData = {
            workspacePatterns: [],
            workspaceExamples: [],
            kumikiShippedPatterns: [],
            kumikiShippedExamples: [],
        };
        const discoveryErrors = [];

        this._state = {
            ...this._state,
            workspaceRoot,
            initStatus,
            isRefreshingPatterns: true,
        };
        this._onDidChangeTreeData.fire();

        try {
            workspaceContent = await discoverWorkspaceContent(workspaceRoot);
        } catch (error) {
            discoveryErrors.push(`Workspace pattern scan failed: ${error.message || error}`);
        }

        try {
            const runnerSources = await this.options.getPatternSources?.(forceRescan);
            runnerPatternData = normalizeRunnerPatterns(runnerSources);
        } catch (error) {
            discoveryErrors.push(`Runner pattern query failed: ${error.message || error}`);
        }

        if (!isLocalDev) {
            try {
                dependencyContent = await discoverDependencyContent(workspaceRoot, {
                    timeoutMs,
                    pythonCommand: this.options.getPythonCommand?.(),
                });
            } catch (error) {
                discoveryErrors.push(`Dependency discovery failed: ${error.message || error}`);
            }
        }

        const fallbackWorkspacePatterns = (workspaceContent.workspacePatterns || []).map((filePath) => ({
            sourceFile: filePath,
            name: path.basename(filePath, '.py'),
            groups: [],
        }));

        const fallbackWorkspaceExamples = (workspaceContent.workspaceExamples || []).map((filePath) => ({
            sourceFile: filePath,
            name: path.basename(filePath, '.py'),
            groups: [],
        }));

        const mergedWorkspacePatterns = runnerPatternData.workspacePatterns.length > 0
            ? runnerPatternData.workspacePatterns
            : fallbackWorkspacePatterns;

        const mergedWorkspaceExamples = runnerPatternData.workspaceExamples.length > 0
            ? runnerPatternData.workspaceExamples
            : fallbackWorkspaceExamples;

        const fallbackShippedPatterns = (dependencyContent.kumikiPatterns || []).map((filePath) => ({
            sourceFile: filePath,
            name: path.basename(filePath, '.py'),
            groups: [],
        }));

        const fallbackShippedExamples = (dependencyContent.kumikiExamples || []).map((filePath) => ({
            sourceFile: filePath,
            name: path.basename(filePath, '.py'),
            groups: [],
        }));

        const mergedShippedPatterns = isLocalDev
            ? []
            : (runnerPatternData.kumikiShippedPatterns.length > 0
                ? runnerPatternData.kumikiShippedPatterns
                : fallbackShippedPatterns);

        const mergedShippedExamples = isLocalDev
            ? []
            : (runnerPatternData.kumikiShippedExamples.length > 0
                ? runnerPatternData.kumikiShippedExamples
                : fallbackShippedExamples);

        this._state = {
            ...this._state,
            workspacePatterns: mergedWorkspacePatterns,
            workspaceExamples: mergedWorkspaceExamples,
            shippedPatterns: mergedShippedPatterns,
            dependencyPatterns: (dependencyContent.dependencyPatterns || []).map((filePath) => ({ sourceFile: filePath })),
            shippedExamples: mergedShippedExamples,
            dependencyExamples: (dependencyContent.dependencyExamples || []).map((filePath) => ({ sourceFile: filePath })),
            discoveryErrors: this.mergeDiscoveryErrors(discoveryErrors, 'patterns'),
            isRefreshingPatterns: false,
        };
        this._onDidChangeTreeData.fire();
    }

    mergeDiscoveryErrors(nextErrors, category) {
        const existing = Array.isArray(this._state.discoveryErrors) ? this._state.discoveryErrors : [];
        const keep = existing.filter((message) => {
            if (category === 'frames') {
                return !message.startsWith('Frame scan failed:');
            }
            return !(
                message.startsWith('Workspace pattern scan failed:')
                || message.startsWith('Runner pattern query failed:')
                || message.startsWith('Dependency discovery failed:')
            );
        });
        return keep.concat(nextErrors);
    }

    getRootNodes() {
        const nodes = [];

        if (this._state.initStatus && this._state.initStatus.projectStatus === 'local-dev') {
            nodes.push(new SidebarNode({
                key: 'local-dev-indicator',
                type: 'info',
                label: 'Local development mode active',
                description: 'Using workspace patterns/examples',
                iconPath: new vscode.ThemeIcon('beaker'),
            }));
        }

        nodes.push(new SidebarNode({
            key: 'frames-root',
            type: 'framesRoot',
            label: `Frames (${this._state.frames.length})`,
            collapsibleState: vscode.TreeItemCollapsibleState.Expanded,
            iconPath: new vscode.ThemeIcon('symbol-class'),
        }));

        nodes.push(new SidebarNode({
            key: 'patterns-root',
            type: 'patternsRoot',
            label: this._state.isRefreshingPatterns ? 'Patterns (loading...)' : 'Patterns',
            collapsibleState: vscode.TreeItemCollapsibleState.Expanded,
            iconPath: new vscode.ThemeIcon(this._state.isRefreshingPatterns ? 'loading~spin' : 'symbol-array'),
        }));

        const totalErrors = this._state.discoveryErrors.length + this._state.frameErrors.length;
        if (totalErrors > 0) {
            nodes.push(new SidebarNode({
                key: 'errors-root',
                type: 'errorsRoot',
                label: `Scan Issues (${totalErrors})`,
                collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                iconPath: new vscode.ThemeIcon('warning'),
            }));
        }

        return nodes;
    }

    getFrameFileNodes() {
        if (this._state.frames.length === 0) {
            return [new SidebarNode({
                key: 'frames-empty',
                type: 'placeholder',
                label: 'No frame definitions found',
                description: this._state.workspaceRoot ? '' : 'Open a workspace',
                iconPath: new vscode.ThemeIcon('circle-slash'),
            })];
        }

        return this._state.frames.map((frameFile) => {
            const entryCount = frameFile.frameEntries.length;
            return new SidebarNode({
                key: `frame-file:${frameFile.filePath}`,
                type: 'frameFile',
                label: frameFile.relativePath,
                description: `${entryCount} frame entry${entryCount === 1 ? '' : 'ies'}`,
                collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                command: {
                    title: 'Open frame file',
                    command: 'kigumi.openFrameFromSidebar',
                    arguments: [frameFile.filePath],
                },
                iconPath: new vscode.ThemeIcon('file-code'),
                data: frameFile,
            });
        });
    }

    getFrameEntryNodes(filePath, frameEntries) {
        return frameEntries.map((entryName) => new SidebarNode({
            key: `frame-entry:${filePath}:${entryName}`,
            type: 'frameEntry',
            label: entryName,
            command: {
                title: 'Open frame entry file',
                command: 'kigumi.openFrameFromSidebar',
                arguments: [filePath],
            },
            iconPath: new vscode.ThemeIcon('symbol-method'),
        }));
    }

    getPatternSectionNodes() {
        const nodes = [];

        if (this._state.isRefreshingPatterns) {
            nodes.push(new SidebarNode({
                key: 'patterns-loading',
                type: 'loading',
                label: 'Loading patterns...',
                description: 'searching workspace and dependencies',
                iconPath: new vscode.ThemeIcon('loading~spin'),
            }));
        }

        const sections = [
            {
                key: 'workspace-patterns',
                label: `Workspace patterns (${this._state.workspacePatterns.length})`,
            },
            {
                key: 'workspace-examples',
                label: `Workspace examples (${this._state.workspaceExamples.length})`,
            },
            {
                key: 'shipped-patterns',
                label: `Kumiki shipped patterns (${this._state.shippedPatterns.length})`,
            },
            {
                key: 'dependency-patterns',
                label: `Dependency patterns (${this._state.dependencyPatterns.length})`,
            },
            {
                key: 'shipped-examples',
                label: `Kumiki examples (${this._state.shippedExamples.length})`,
            },
            {
                key: 'dependency-examples',
                label: `Dependency examples (${this._state.dependencyExamples.length})`,
            },
        ];

        nodes.push(...sections.map((section) => {
            // Add grouping indicator for shipped-patterns section
            const groupIndicator = section.key === 'shipped-patterns' && this._groupByPatternbook ? ' (grouped by patternbook)' : '';
            return new SidebarNode({
                key: `pattern-section:${section.key}`,
                type: 'patternSection',
                label: section.label + groupIndicator,
                collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                iconPath: new vscode.ThemeIcon('list-tree'),
                data: { sectionKey: section.key },
            });
        }));

        return nodes;
    }

    getPatternNodesForSection(sectionKey) {
        let patternItems = [];
        if (sectionKey === 'workspace-patterns') {
            patternItems = this._state.workspacePatterns;
        } else if (sectionKey === 'workspace-examples') {
            return this.getExampleNodesForSection('workspace-examples');
        } else if (sectionKey === 'shipped-patterns') {
            patternItems = this._state.shippedPatterns;
        } else if (sectionKey === 'dependency-patterns') {
            patternItems = this._state.dependencyPatterns;
        } else if (sectionKey === 'shipped-examples') {
            return this.getExampleNodesForSection('shipped-examples');
        } else if (sectionKey === 'dependency-examples') {
            return this.getExampleNodesForSection('dependency-examples');
        }

        if (!patternItems || patternItems.length === 0) {
            return [new SidebarNode({
                key: `patterns-empty:${sectionKey}`,
                type: 'placeholder',
                label: 'No patterns found',
                iconPath: new vscode.ThemeIcon('circle-slash'),
            })];
        }

        // Group by patternbook if enabled for shipped-patterns
        if (sectionKey === 'shipped-patterns' && this._groupByPatternbook) {
            const grouped = groupPatternsByPatternbook(patternItems);
            const nodes = [];
            
            for (const [patternbookName, items] of grouped.entries()) {
                nodes.push(new SidebarNode({
                    key: `patternbook-group:${sectionKey}:${patternbookName}`,
                    type: 'patternbookGroup',
                    label: patternbookName,
                    description: `${items.length} pattern${items.length === 1 ? '' : 's'}`,
                    collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                    iconPath: new vscode.ThemeIcon('folder'),
                    command: {
                        title: 'Open patternbook',
                        command: 'kigumi.openPatternbookGroup',
                        arguments: [{ sectionKey, patternbookName, patterns: items }],
                    },
                    data: { sectionKey, patternbookName, patterns: items },
                }));
            }
            return nodes;
        }

        return patternItems.map((item) => {
            const itemName = item.name || path.basename(item.sourceFile, '.py');
            const groups = Array.isArray(item.groups) && item.groups.length > 0 ? `Groups: ${item.groups.join(', ')}` : '';
            // Only allow view/duplicate for shipped patterns, not workspace patterns
            const contextValue = sectionKey === 'shipped-patterns' ? 'patternItem' : 'patternItemWorkspace';
            return new SidebarNode({
                key: `pattern-item:${sectionKey}:${item.sourceFile}:${itemName}`,
                type: 'patternItem',
                label: itemName,
                description: groups,
                tooltip: item.sourceFile,
                command: {
                    title: 'Open pattern',
                    command: 'kigumi.openPatternFromSidebar',
                    arguments: [{ sourceFile: item.sourceFile, patternName: item.name || null }],
                },
                iconPath: new vscode.ThemeIcon('symbol-string'),
                data: { sourceFile: item.sourceFile, patternName: item.name, sectionKey },
                contextValue,
            });
        });
    }

    getPatternNodesForPatternbook(sectionKey, patternbookName) {
        let patternItems = [];
        if (sectionKey === 'shipped-patterns') {
            patternItems = this._state.shippedPatterns;
        }

        const filteredItems = patternItems.filter((item) => {
            const pbName = path.basename(item.sourceFile, '.py');
            return pbName === patternbookName;
        });

        if (filteredItems.length === 0) {
            return [new SidebarNode({
                key: `patternbook-empty:${sectionKey}:${patternbookName}`,
                type: 'placeholder',
                label: 'No patterns found',
                iconPath: new vscode.ThemeIcon('circle-slash'),
            })];
        }

        return filteredItems.map((item) => {
            const itemName = item.name || path.basename(item.sourceFile, '.py');
            const groups = Array.isArray(item.groups) && item.groups.length > 0 ? `Groups: ${item.groups.join(', ')}` : '';
            return new SidebarNode({
                key: `pattern-item:${sectionKey}:${item.sourceFile}:${itemName}`,
                type: 'patternItem',
                label: itemName,
                description: groups,
                tooltip: item.sourceFile,
                command: {
                    title: 'Open pattern',
                    command: 'kigumi.openPatternFromSidebar',
                    arguments: [{ sourceFile: item.sourceFile, patternName: item.name || null }],
                },
                iconPath: new vscode.ThemeIcon('symbol-string'),
                data: { sourceFile: item.sourceFile, patternName: item.name, sectionKey },
                contextValue: 'patternItem',
            });
        });
    }

    getExampleNodesForSection(sectionKey) {
        let items = this._state.dependencyExamples;
        if (sectionKey === 'workspace-examples') {
            items = this._state.workspaceExamples;
        } else if (sectionKey === 'shipped-examples') {
            items = this._state.shippedExamples;
        }

        if (!items || items.length === 0) {
            return [new SidebarNode({
                key: `examples-empty:${sectionKey}`,
                type: 'placeholder',
                label: 'No examples found',
                iconPath: new vscode.ThemeIcon('circle-slash'),
            })];
        }

        return items.map((item) => {
            const fileName = path.basename(item.sourceFile, '.py');
            return new SidebarNode({
                key: `example-item:${sectionKey}:${item.sourceFile}`,
                type: 'exampleItem',
                label: fileName,
                tooltip: item.sourceFile,
                command: {
                    title: 'Open example',
                    command: 'kigumi.openExampleFromSidebar',
                    arguments: [item.sourceFile],
                },
                iconPath: new vscode.ThemeIcon('symbol-event'),
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

        for (const err of this._state.frameErrors) {
            rows.push(new SidebarNode({
                key: `frame-error:${err.filePath}`,
                type: 'error',
                label: err.reason,
                description: path.basename(err.filePath),
                tooltip: `${err.reason}\n${err.filePath}`,
                iconPath: new vscode.ThemeIcon('warning'),
            }));
        }

        return rows;
    }
}

module.exports = {
    KigumiSidebarProvider,
};
