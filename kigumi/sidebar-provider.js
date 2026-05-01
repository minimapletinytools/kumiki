const path = require('path');
const vscode = require('vscode');
const { scanWorkspaceForFrames } = require('./frame-scanner');
const {
    discoverDependencyContent,
    discoverWorkspaceContent,
    normalizeRunnerPatterns,
} = require('./discovery-adapter');
const { getInitializationStatus } = require('./project-initializer');

class SidebarNode {
    constructor({ key, type, label, collapsibleState = vscode.TreeItemCollapsibleState.None, command, description, tooltip, iconPath, data }) {
        this.key = key;
        this.type = type;
        this.label = label;
        this.collapsibleState = collapsibleState;
        this.command = command;
        this.description = description;
        this.tooltip = tooltip;
        this.iconPath = iconPath;
        this.data = data || {};
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
        this._state = {
            workspaceRoot: null,
            initStatus: null,
            frames: [],
            frameErrors: [],
            workspacePatterns: [],
            shippedPatterns: [],
            dependencyPatterns: [],
            shippedExamples: [],
            dependencyExamples: [],
            discoveryErrors: [],
        };
    }

    dispose() {
        this._onDidChangeTreeData.dispose();
    }

    getTreeItem(element) {
        const item = new vscode.TreeItem(element.label, element.collapsibleState);
        item.id = element.key;
        item.contextValue = element.type;
        item.command = element.command;
        item.description = element.description;
        item.tooltip = element.tooltip || element.label;
        if (element.iconPath) {
            item.iconPath = element.iconPath;
        }
        return item;
    }

    async getChildren(element) {
        await this.ensureLoaded();

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

        if (element.type === 'examplesRoot') {
            return this.getExampleSectionNodes();
        }

        if (element.type === 'exampleSection') {
            return this.getExampleNodesForSection(element.data.sectionKey);
        }

        if (element.type === 'errorsRoot') {
            return this.getErrorNodes();
        }

        return [];
    }

    async ensureLoaded() {
        if (this._didLoadOnce) {
            return;
        }
        await this.refresh(false);
    }

    async refresh(forceRescan = true) {
        if (this._loadPromise) {
            return this._loadPromise;
        }

        this._loadPromise = this.loadState(forceRescan)
            .finally(() => {
                this._loadPromise = null;
            });

        return this._loadPromise;
    }

    async loadState(forceRescan) {
        const workspaceFolder = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
        if (!workspaceFolder) {
            this._state = {
                workspaceRoot: null,
                initStatus: null,
                frames: [],
                frameErrors: [],
                workspacePatterns: [],
                shippedPatterns: [],
                dependencyPatterns: [],
                shippedExamples: [],
                dependencyExamples: [],
                discoveryErrors: ['Open a workspace folder to use Kigumi Explorer.'],
            };
            this._didLoadOnce = true;
            this._onDidChangeTreeData.fire();
            return;
        }

        const workspaceRoot = workspaceFolder.uri.fsPath;
        const timeoutSeconds = vscode.workspace.getConfiguration('kigumi').get('explorer.scanTimeoutSeconds', 5);
        const timeoutMs = Math.max(1000, Number(timeoutSeconds) * 1000);

        const discoveryErrors = [];
        let framesResult = { frameFiles: [], scanErrors: [] };
        let workspaceContent = { workspacePatterns: [] };
        let dependencyContent = {
            kumikiPatterns: [],
            kumikiExamples: [],
            dependencyPatterns: [],
            dependencyExamples: [],
        };
        let runnerPatternData = {
            workspacePatterns: [],
            kumikiShippedPatterns: [],
        };

        try {
            framesResult = await scanWorkspaceForFrames(workspaceRoot, { timeoutMs });
        } catch (error) {
            discoveryErrors.push(`Frame scan failed: ${error.message || error}`);
        }

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

        try {
            dependencyContent = await discoverDependencyContent(workspaceRoot, {
                timeoutMs,
                pythonCommand: this.options.getPythonCommand?.(),
            });
        } catch (error) {
            discoveryErrors.push(`Dependency discovery failed: ${error.message || error}`);
        }

        const fallbackWorkspacePatterns = (workspaceContent.workspacePatterns || []).map((filePath) => ({
            sourceFile: filePath,
            name: path.basename(filePath, '.py'),
            groups: [],
        }));

        const mergedWorkspacePatterns = runnerPatternData.workspacePatterns.length > 0
            ? runnerPatternData.workspacePatterns
            : fallbackWorkspacePatterns;

        const initStatus = getInitializationStatus(workspaceRoot);

        this._state = {
            workspaceRoot,
            initStatus,
            frames: framesResult.frameFiles || [],
            frameErrors: framesResult.scanErrors || [],
            workspacePatterns: mergedWorkspacePatterns,
            shippedPatterns: runnerPatternData.kumikiShippedPatterns || [],
            dependencyPatterns: (dependencyContent.dependencyPatterns || []).map((filePath) => ({ sourceFile: filePath })),
            shippedExamples: (dependencyContent.kumikiExamples || []).map((filePath) => ({ sourceFile: filePath })),
            dependencyExamples: (dependencyContent.dependencyExamples || []).map((filePath) => ({ sourceFile: filePath })),
            discoveryErrors,
        };

        this._didLoadOnce = true;
        this._onDidChangeTreeData.fire();
    }

    getRootNodes() {
        const nodes = [];

        nodes.push(this.createOpenCurrentFileNode());
        nodes.push(this.createInitializeProjectNode());

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
            label: 'Patterns',
            collapsibleState: vscode.TreeItemCollapsibleState.Expanded,
            iconPath: new vscode.ThemeIcon('symbol-array'),
        }));

        nodes.push(new SidebarNode({
            key: 'examples-root',
            type: 'examplesRoot',
            label: 'Examples',
            collapsibleState: vscode.TreeItemCollapsibleState.Expanded,
            iconPath: new vscode.ThemeIcon('beaker'),
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

    createOpenCurrentFileNode() {
        return new SidebarNode({
            key: 'action-open-current-file',
            type: 'actionOpenCurrentFile',
            label: 'Open current file in Kigumi',
            command: {
                title: 'Open current file in Kigumi',
                command: 'kigumi.openCurrentFileInViewer',
            },
            iconPath: new vscode.ThemeIcon('play-circle'),
        });
    }

    createInitializeProjectNode() {
        const initStatus = this._state.initStatus;
        const isInitialized = !!(initStatus && initStatus.isInitialized);

        return new SidebarNode({
            key: 'action-init-project',
            type: 'actionInitializeProject',
            label: 'Initialize new project in workspace',
            description: isInitialized ? 'Already initialized' : 'Create .kigumi + .venv + sample',
            tooltip: isInitialized
                ? 'Project files already exist in this workspace.'
                : 'Set up Kigumi project files, Python environment, and create my_cute_frame.py if missing.',
            command: isInitialized
                ? undefined
                : {
                    title: 'Initialize new project in workspace',
                    command: 'kigumi.initializeProjectInWorkspace',
                },
            iconPath: new vscode.ThemeIcon(isInitialized ? 'check' : 'tools'),
        });
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
        const sections = [
            {
                key: 'workspace-patterns',
                label: `Workspace patterns (${this._state.workspacePatterns.length})`,
            },
            {
                key: 'shipped-patterns',
                label: `Kumiki shipped patterns (${this._state.shippedPatterns.length})`,
            },
            {
                key: 'dependency-patterns',
                label: `Dependency patterns (${this._state.dependencyPatterns.length})`,
            },
        ];

        return sections.map((section) => new SidebarNode({
            key: `pattern-section:${section.key}`,
            type: 'patternSection',
            label: section.label,
            collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
            iconPath: new vscode.ThemeIcon('list-tree'),
            data: { sectionKey: section.key },
        }));
    }

    getPatternNodesForSection(sectionKey) {
        let patternItems = [];
        if (sectionKey === 'workspace-patterns') {
            patternItems = this._state.workspacePatterns;
        } else if (sectionKey === 'shipped-patterns') {
            patternItems = this._state.shippedPatterns;
        } else if (sectionKey === 'dependency-patterns') {
            patternItems = this._state.dependencyPatterns;
        }

        if (!patternItems || patternItems.length === 0) {
            return [new SidebarNode({
                key: `patterns-empty:${sectionKey}`,
                type: 'placeholder',
                label: 'No patterns found',
                iconPath: new vscode.ThemeIcon('circle-slash'),
            })];
        }

        return patternItems.map((item) => {
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
            });
        });
    }

    getExampleSectionNodes() {
        const sections = [
            {
                key: 'shipped-examples',
                label: `Kumiki shipped examples (${this._state.shippedExamples.length})`,
            },
            {
                key: 'dependency-examples',
                label: `Dependency examples (${this._state.dependencyExamples.length})`,
            },
        ];

        return sections.map((section) => new SidebarNode({
            key: `example-section:${section.key}`,
            type: 'exampleSection',
            label: section.label,
            collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
            iconPath: new vscode.ThemeIcon('list-tree'),
            data: { sectionKey: section.key },
        }));
    }

    getExampleNodesForSection(sectionKey) {
        const items = sectionKey === 'shipped-examples'
            ? this._state.shippedExamples
            : this._state.dependencyExamples;

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
