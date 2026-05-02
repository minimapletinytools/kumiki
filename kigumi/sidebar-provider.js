const path = require('path');
const vscode = require('vscode');
const { scanWorkspaceForFrames } = require('./frame-scanner');
const { discoverDependencyContent } = require('./discovery-adapter');
const { getInitializationStatus } = require('./project-initializer');
const { groupPatternsByPatternbook } = require('./pattern-source-utils');

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

        if (element.type === 'framesRoot') {
            return this.getFrameFileNodes();
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

    async _runFullScan(_forceRescan) {
        const workspaceFolder = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
        if (!workspaceFolder) {
            this._state = {
                workspaceRoot: null,
                initStatus: null,
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
        const timeoutSeconds = vscode.workspace.getConfiguration('kigumi').get('explorer.scanTimeoutSeconds', 5);
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

        this._state = {
            workspaceRoot,
            initStatus,
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
        this._onDidChangeTreeData.fire();
    }

    async _scanWorkspace(workspaceRoot, timeoutMs) {
        const result = await scanWorkspaceForFrames(workspaceRoot, {
            timeoutMs,
            pythonCommand: this.options.getPythonCommand?.(),
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

        return {
            shippedPatterns: (dep.kumikiPatterns || []).map(toItem),
            shippedExamples: (dep.kumikiExamples || []).map(toItem),
            dependencyPatterns: (dep.dependencyPatterns || []).map(toItem),
            dependencyExamples: (dep.dependencyExamples || []).map(toItem),
        };
    }

    // ---------------------------------------------------------------------------
    // Tree building
    // ---------------------------------------------------------------------------

    getRootNodes() {
        const nodes = [];

        if (this._state.initStatus && this._state.initStatus.projectStatus === 'local-dev') {
            nodes.push(new SidebarNode({
                key: 'local-dev-indicator',
                type: 'info',
                label: 'Local development mode active',
                description: 'Using workspace patterns',
                iconPath: new vscode.ThemeIcon('beaker'),
            }));
        }

        const frameCount = this._state.frames.length;
        nodes.push(new SidebarNode({
            key: 'frames-root',
            type: 'framesRoot',
            label: this._state.isScanning ? 'Frames (scanning...)' : `Frames (${frameCount})`,
            collapsibleState: vscode.TreeItemCollapsibleState.Expanded,
            iconPath: new vscode.ThemeIcon(this._state.isScanning ? 'loading~spin' : 'symbol-class'),
        }));

        const pbCount = this._state.workspacePatternbooks.length;
        nodes.push(new SidebarNode({
            key: 'patterns-root',
            type: 'patternsRoot',
            label: this._state.isScanning ? 'Patterns (scanning...)' : 'Patterns',
            collapsibleState: vscode.TreeItemCollapsibleState.Expanded,
            iconPath: new vscode.ThemeIcon(this._state.isScanning ? 'loading~spin' : 'symbol-array'),
            description: this._state.isScanning ? '' : `${pbCount} workspace patternbook${pbCount === 1 ? '' : 's'}`,
        }));

        const totalErrors = this._state.discoveryErrors.length + this._state.scanErrors.length;
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
        const nodes = [];
        if (this._state.isScanning) {
            nodes.push(new SidebarNode({
                key: 'frames-scanning',
                type: 'loading',
                label: 'Scanning workspace...',
                iconPath: new vscode.ThemeIcon('loading~spin'),
            }));
        }

        if (this._state.frames.length === 0) {
            nodes.push(new SidebarNode({
                key: 'frames-empty',
                type: 'placeholder',
                label: 'No frame definitions found',
                description: this._state.workspaceRoot ? '' : 'Open a workspace',
                iconPath: new vscode.ThemeIcon('circle-slash'),
            }));
            return nodes;
        }

        nodes.push(...this._state.frames.map((frameFile) => new SidebarNode({
            key: `frame-file:${frameFile.filePath}`,
            type: 'frameFile',
            label: frameFile.relativePath,
            collapsibleState: vscode.TreeItemCollapsibleState.None,
            command: {
                title: 'Open frame file',
                command: 'kigumi.openFrameFromSidebar',
                arguments: [frameFile.filePath],
            },
            iconPath: new vscode.ThemeIcon('file-code'),
            data: frameFile,
        })));

        return nodes;
    }

    getPatternSectionNodes() {
        const nodes = [];

        if (this._state.isScanning) {
            nodes.push(new SidebarNode({
                key: 'patterns-scanning',
                type: 'loading',
                label: 'Scanning...',
                description: 'searching workspace and dependencies',
                iconPath: new vscode.ThemeIcon('loading~spin'),
            }));
        }

        // Workspace patternbooks section
        const pbCount = this._state.workspacePatternbooks.length;
        nodes.push(new SidebarNode({
            key: 'pattern-section:workspace-patternbooks',
            type: 'patternSection',
            label: this._groupByPatternbook
                ? `Workspace (${pbCount} patternbook${pbCount === 1 ? '' : 's'})`
                : 'Workspace patterns',
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
                label: `Kumiki shipped (${shippedCount})`,
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
                label: `Dependencies (${depCount})`,
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

    getWorkspacePatternbookNodes() {
        const patternbooks = this._state.workspacePatternbooks;
        if (!patternbooks || patternbooks.length === 0) {
            return [new SidebarNode({
                key: 'workspace-patternbooks-empty',
                type: 'placeholder',
                label: 'No patternbooks found',
                description: 'Files with patternbook = ... will appear here',
                iconPath: new vscode.ThemeIcon('circle-slash'),
            })];
        }

        return patternbooks.map((pb) => new SidebarNode({
            key: `workspace-patternbook:${pb.filePath}`,
            type: 'workspacePatternbook',
            label: pb.patternbookName,
            description: `${pb.patternNames.length} pattern${pb.patternNames.length === 1 ? '' : 's'}`,
            collapsibleState: pb.patternNames.length > 0
                ? vscode.TreeItemCollapsibleState.Collapsed
                : vscode.TreeItemCollapsibleState.None,
            command: pb.patternNames.length === 0 ? {
                title: 'Open patternbook file',
                command: 'kigumi.openFrameFromSidebar',
                arguments: [pb.filePath],
            } : undefined,
            iconPath: new vscode.ThemeIcon('book'),
            tooltip: pb.filePath,
            data: { patternbook: pb },
            contextValue: 'patternItemWorkspace',
        }));
    }

    getWorkspacePatternbookPatternNodes(pb) {
        if (!pb || !Array.isArray(pb.patternNames) || pb.patternNames.length === 0) {
            return [new SidebarNode({
                key: `workspace-pb-empty:${pb && pb.filePath}`,
                type: 'placeholder',
                label: 'No patterns found',
                iconPath: new vscode.ThemeIcon('circle-slash'),
            })];
        }

        return pb.patternNames.map((patternName) => new SidebarNode({
            key: `workspace-pattern:${pb.filePath}:${patternName}`,
            type: 'patternItem',
            label: patternName,
            tooltip: `${patternName} — ${pb.filePath}`,
            command: {
                title: 'Open pattern',
                command: 'kigumi.openPatternFromSidebar',
                arguments: [{ sourceFile: pb.filePath, patternName }],
            },
            iconPath: new vscode.ThemeIcon('symbol-string'),
            data: { sourceFile: pb.filePath, patternName, sectionKey: 'workspace-patternbooks' },
            contextValue: 'patternItemWorkspace',
        }));
    }

    getFlatWorkspacePatternNodes() {
        const patternbooks = this._state.workspacePatternbooks || [];
        const nodes = [];

        for (const pb of patternbooks) {
            const names = Array.isArray(pb.patternNames) ? pb.patternNames : [];
            for (const patternName of names) {
                nodes.push(new SidebarNode({
                    key: `workspace-pattern-flat:${pb.filePath}:${patternName}`,
                    type: 'patternItem',
                    label: patternName,
                    description: pb.patternbookName,
                    tooltip: `${patternName} — ${pb.filePath}`,
                    command: {
                        title: 'Open pattern',
                        command: 'kigumi.openPatternFromSidebar',
                        arguments: [{ sourceFile: pb.filePath, patternName }],
                    },
                    iconPath: new vscode.ThemeIcon('symbol-string'),
                    data: { sourceFile: pb.filePath, patternName, sectionKey: 'workspace-patternbooks' },
                    contextValue: 'patternItemWorkspace',
                }));
            }
        }

        if (nodes.length === 0) {
            return [new SidebarNode({
                key: 'workspace-patterns-empty',
                type: 'placeholder',
                label: 'No patterns found',
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
                label: 'No patterns found',
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
                        iconPath: new vscode.ThemeIcon('symbol-string'),
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
                description: `${items.length} pattern${items.length === 1 ? '' : 's'}`,
                collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
                iconPath: new vscode.ThemeIcon('folder'),
                data: { sectionKey, patternbookName, patterns: items },
                contextValue: 'patternItem',
            }));
        }

        return nodes;
    }

    getShippedPatternNodesForPatternbook(sectionKey, patternbookName) {
        const patternItems = sectionKey === 'shipped-patterns'
            ? this._state.shippedPatterns
            : this._state.dependencyPatterns;

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
                iconPath: new vscode.ThemeIcon('symbol-string'),
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
